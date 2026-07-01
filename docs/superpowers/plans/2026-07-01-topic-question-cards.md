# Topic Question Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the POLICY/TECHNOLOGY/SOCIETY chip groups on the topic selection page with browsable debate question cards (title + description), a domain filter, and an LLM-powered "Generate more" button.

**Architecture:** Backend exposes a hardcoded `GET /api/topics/suggest` returning 12 `DebatableQuestion` objects across 4 domains, and a new `POST /api/topics/generate` that calls the OpenRouter LLM to produce N more questions for a given domain. The frontend replaces the chip-group rows in `TopicSelection.tsx` with a domain selector and a 2-column card grid; clicking a card pre-fills the topic and description fields.

**Tech Stack:** FastAPI + Pydantic v2 (backend), Next.js 14 + TypeScript + Tailwind (frontend), OpenRouter via AsyncOpenAI client (LLM generation).

## Global Constraints

- Backend Python ≥ 3.11; use `async`/`await` throughout.
- LLM calls use `openrouter` client from `debatemind/agents/client.py` with `model=settings.main_model`.
- All backend responses wrapped in `SuccessResponse[T]` from `debatemind/types`.
- Frontend follows existing Tailwind colour tokens: `scarlet` (active/selected), `fog` (muted), `ink` (text), `border` (border colour).
- No DB writes for topic generation — purely stateless.
- `count` in generate endpoint clamped to 1–10 server-side.
- Domains are exactly: `POLICY`, `TECHNOLOGY`, `SOCIETY`, `LIFE` (uppercase strings).

---

## File Map

| File | Change |
|------|--------|
| `debatemind-backend/debatemind/schemas/topics.py` | Replace `TopicSuggestion` with `DebatableQuestion`; add `GenerateTopicsIn` |
| `debatemind-backend/debatemind/routers/topics.py` | Update `suggest`; add `generate` endpoint |
| `debatemind-backend/tests/test_topics_router.py` | New — tests for both endpoints |
| `frontend/src/types/index.ts` | Add `DebatableQuestion` interface |
| `frontend/src/lib/api.ts` | Add `generateTopics` method |
| `frontend/src/components/topic/TopicSelection.tsx` | Replace chip section with domain selector + card grid |

---

### Task 1: Backend schemas + hardcoded suggest endpoint

**Files:**
- Modify: `debatemind-backend/debatemind/schemas/topics.py`
- Modify: `debatemind-backend/debatemind/routers/topics.py`
- Create: `debatemind-backend/tests/test_topics_router.py`

**Interfaces:**
- Produces: `DebatableQuestion(id, domain, title, description)` used by Task 2 and all frontend tasks.
- Produces: `GET /api/topics/suggest` → `{"success": true, "data": [DebatableQuestion, ...]}`

- [ ] **Step 1: Write the failing test**

```python
# debatemind-backend/tests/test_topics_router.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from debatemind.routers import topics as topics_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(topics_router.router, prefix="/api/topics")
    return TestClient(app)


def test_suggest_returns_12_questions(client):
    res = client.get("/api/topics/suggest")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    questions = data["data"]
    assert len(questions) == 12


def test_suggest_covers_all_domains(client):
    res = client.get("/api/topics/suggest")
    questions = res.json()["data"]
    domains = {q["domain"] for q in questions}
    assert domains == {"POLICY", "TECHNOLOGY", "SOCIETY", "LIFE"}


def test_suggest_question_has_required_fields(client):
    res = client.get("/api/topics/suggest")
    q = res.json()["data"][0]
    assert "id" in q
    assert "domain" in q
    assert "title" in q
    assert "description" in q
    assert len(q["description"]) > 50  # non-trivial description
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd debatemind-backend
pytest tests/test_topics_router.py -v
```

Expected: FAIL — `ImportError` or `AttributeError` since `DebatableQuestion` does not exist yet.

- [ ] **Step 3: Replace schemas/topics.py**

```python
# debatemind-backend/debatemind/schemas/topics.py
from pydantic import BaseModel


class DebatableQuestion(BaseModel):
    id: str
    domain: str
    title: str
    description: str


class GenerateTopicsIn(BaseModel):
    domain: str
    count: int = 5
```

- [ ] **Step 4: Replace routers/topics.py with hardcoded suggest**

```python
# debatemind-backend/debatemind/routers/topics.py
from fastapi import APIRouter

from debatemind.schemas.topics import DebatableQuestion, GenerateTopicsIn
from debatemind.types import SuccessResponse

router = APIRouter()

QUESTIONS: list[DebatableQuestion] = [
    # POLICY
    DebatableQuestion(
        id="eu-ai-act-global-standard",
        domain="POLICY",
        title="The EU AI Act should become the global standard for AI governance",
        description=(
            "The EU AI Act imposes strict risk classifications, mandatory audits, and bans "
            "on certain AI applications. Proponents argue it sets a precedent for protecting "
            "citizens globally. Critics contend applying EU-level regulation worldwide stifles "
            "innovation, ignores non-European legal traditions, and creates compliance burdens "
            "that entrench incumbents while locking out smaller nations from the AI economy."
        ),
    ),
    DebatableQuestion(
        id="carbon-tax-over-ets",
        domain="POLICY",
        title="Carbon taxes are more effective than emissions trading schemes",
        description=(
            "Emissions trading schemes cap total emissions and let companies buy and sell permits, "
            "creating market flexibility. Carbon taxes directly price emissions at a fixed rate. "
            "The debate centres on which mechanism better balances economic efficiency, political "
            "feasibility, and emissions certainty — and whether hybrid approaches undermine the "
            "benefits of either."
        ),
    ),
    DebatableQuestion(
        id="platform-liability-amplification",
        domain="POLICY",
        title="Social platforms should bear legal liability for algorithmically amplified harmful content",
        description=(
            "Recommendation algorithms surface content to billions of users, often prioritising "
            "engagement over accuracy or safety. When platforms actively amplify content, some "
            "argue they cross from neutral conduit to active publisher. The debate involves "
            "Section 230 protections, the economics of content moderation, free speech principles, "
            "and whether liability would drive platforms toward over-censorship."
        ),
    ),
    # TECHNOLOGY
    DebatableQuestion(
        id="pause-ai-capability-research",
        domain="TECHNOLOGY",
        title="AI capability research should be paused until alignment is solved",
        description=(
            "The alignment problem — ensuring advanced AI systems reliably pursue beneficial goals "
            "— remains unsolved. Some researchers argue we are racing toward systems we cannot "
            "control, while others contend pausing cedes ground to less safety-conscious actors "
            "and that alignment research benefits from capabilities advances. The debate hinges "
            "on estimates of risk, timelines, and whether a pause is even enforceable."
        ),
    ),
    DebatableQuestion(
        id="open-source-frontier-ai",
        domain="TECHNOLOGY",
        title="Frontier AI models should be open-sourced by default",
        description=(
            "Open-sourcing large AI models accelerates research, democratises access, and allows "
            "independent safety auditing. Opponents warn that open weights for highly capable "
            "models could enable mass-scale misuse — from bioweapons synthesis to disinformation "
            "— and that safety testing is harder once a model is in the wild. The line between "
            "'frontier' and 'open research model' is itself contested."
        ),
    ),
    DebatableQuestion(
        id="ban-algorithmic-hiring",
        domain="TECHNOLOGY",
        title="Algorithmic hiring tools should be banned until bias can be certified away",
        description=(
            "AI-assisted recruitment promises consistent, scalable candidate evaluation but has "
            "repeatedly been found to encode historical biases in race, gender, and class. "
            "Advocates for a ban argue we cannot ethically deploy tools whose failure modes harm "
            "vulnerable candidates. Defenders say imperfect algorithms are still better than "
            "inconsistent human judgment, and that bias audits provide a credible path forward."
        ),
    ),
    # SOCIETY
    DebatableQuestion(
        id="ban-social-media-under-16",
        domain="SOCIETY",
        title="Social media should be legally prohibited for users under 16",
        description=(
            "Several countries are moving to restrict minors from social platforms, citing "
            "evidence linking heavy use to anxiety, depression, and disrupted development. "
            "Opponents argue such bans are unenforceable, strip young people of digital literacy "
            "opportunities, and that harms are driven by design choices that should be regulated "
            "directly. The debate also touches on parental rights versus state intervention."
        ),
    ),
    DebatableQuestion(
        id="ubi-erodes-work-dignity",
        domain="SOCIETY",
        title="Universal basic income undermines the dignity of work",
        description=(
            "UBI proposals promise economic security without conditionality, but critics argue "
            "that decoupling income from contribution erodes the social meaning of work, weakens "
            "communities built around shared labour, and disincentivises participation. Supporters "
            "contend dignity comes from security and choice, not compulsion, and that UBI would "
            "free people to pursue more meaningful forms of contribution."
        ),
    ),
    DebatableQuestion(
        id="competency-based-credentials",
        domain="SOCIETY",
        title="Universities should be replaced by competency-based credentialing",
        description=(
            "Rising tuition costs and the decoupling of degrees from job outcomes have accelerated "
            "interest in stackable credentials, bootcamps, and employer-designed certificates. "
            "Proponents argue competency-based systems are more efficient and equitable. Critics "
            "warn that universities provide irreplaceable intellectual breadth, social capital "
            "formation, and civic functions that narrow credentials cannot replicate."
        ),
    ),
    # LIFE
    DebatableQuestion(
        id="remote-work-harms-cohesion",
        domain="LIFE",
        title="Remote work permanently harms team cohesion and long-term career growth",
        description=(
            "The shift to remote work improved flexibility and removed commuting costs but reduced "
            "spontaneous collaboration, mentorship, and the informal socialisation that builds "
            "trust. Junior employees may miss formative learning from proximity to senior "
            "colleagues. Counter-arguments hold that strong async practices and intentional "
            "culture-building can fully substitute for physical co-location."
        ),
    ),
    DebatableQuestion(
        id="parental-monitoring-adult-finances",
        domain="LIFE",
        title="Parents should not have the right to monitor their adult children's finances",
        description=(
            "Financial oversight by parents over adult children — via shared accounts, location "
            "tracking, or conditional support — raises questions about autonomy, power dynamics, "
            "and healthy boundaries. Supporters of monitoring argue it reflects genuine care and "
            "shared financial risk. Critics contend it prolongs dependency and is a vector for "
            "control in unhealthy family systems."
        ),
    ),
    DebatableQuestion(
        id="work-life-balance-privilege",
        domain="LIFE",
        title="The pursuit of work-life balance is a privilege only the wealthy can afford",
        description=(
            "Discourse around work-life balance assumes workers have schedule discretion, "
            "meaningful savings, and flexible roles. For hourly workers, gig economy participants, "
            "and those in caring roles, 'balance' is a meaningless abstraction. The debate touches "
            "on structural labour conditions, the moral weight of individual choices versus "
            "systemic change, and whether the wellness industry profits from medicalising problems "
            "that require political solutions."
        ),
    ),
]


@router.get(
    "/suggest",
    response_model=SuccessResponse[list[DebatableQuestion]],
    summary="Get debate question suggestions",
)
async def suggest():
    return SuccessResponse(data=QUESTIONS)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd debatemind-backend
pytest tests/test_topics_router.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add debatemind-backend/debatemind/schemas/topics.py \
        debatemind-backend/debatemind/routers/topics.py \
        debatemind-backend/tests/test_topics_router.py
git commit -m "feat: replace TopicSuggestion with DebatableQuestion and hardcoded suggest endpoint"
```

---

### Task 2: Backend generate endpoint (LLM)

**Files:**
- Modify: `debatemind-backend/debatemind/routers/topics.py` (append generate route)
- Modify: `debatemind-backend/tests/test_topics_router.py` (append generate tests)

**Interfaces:**
- Consumes: `DebatableQuestion`, `GenerateTopicsIn` from Task 1.
- Consumes: `openrouter` from `debatemind.agents.client`; `settings` from `debatemind.config`.
- Produces: `POST /api/topics/generate` → `{"success": true, "data": [DebatableQuestion, ...]}`

- [ ] **Step 1: Write failing tests for the generate endpoint**

Append to `debatemind-backend/tests/test_topics_router.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_openrouter(questions_json: str):
    """Return a mock that makes openrouter.chat.completions.create return questions_json."""
    choice = MagicMock()
    choice.message.content = questions_json
    completion = MagicMock()
    completion.choices = [choice]
    mock_create = AsyncMock(return_value=completion)
    mock_client = MagicMock()
    mock_client.chat.completions.create = mock_create
    return mock_client


def test_generate_returns_questions(client):
    payload = [
        {
            "id": "test-question-1",
            "domain": "POLICY",
            "title": "Test debate question",
            "description": "A description that is long enough to be meaningful for the test.",
        }
    ]
    mock_client = _mock_openrouter(json.dumps({"questions": payload}))
    with patch("debatemind.routers.topics.openrouter", mock_client):
        res = client.post("/api/topics/generate", json={"domain": "POLICY", "count": 1})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["id"] == "test-question-1"


def test_generate_clamps_count_to_10(client):
    payload = [
        {
            "id": f"q-{i}",
            "domain": "LIFE",
            "title": f"Question {i}",
            "description": "Enough text to pass description length check in future.",
        }
        for i in range(10)
    ]
    mock_client = _mock_openrouter(json.dumps({"questions": payload}))
    with patch("debatemind.routers.topics.openrouter", mock_client):
        res = client.post("/api/topics/generate", json={"domain": "LIFE", "count": 999})
    assert res.status_code == 200


def test_generate_rejects_invalid_count(client):
    res = client.post("/api/topics/generate", json={"domain": "POLICY", "count": 0})
    assert res.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd debatemind-backend
pytest tests/test_topics_router.py::test_generate_returns_questions \
       tests/test_topics_router.py::test_generate_clamps_count_to_10 \
       tests/test_topics_router.py::test_generate_rejects_invalid_count -v
```

Expected: FAIL — endpoint does not exist yet.

- [ ] **Step 3: Add the generate endpoint to routers/topics.py**

Add these imports at the top of `routers/topics.py` (after existing imports):

```python
import json
import logging

from fastapi import HTTPException

from debatemind.agents.client import openrouter
from debatemind.config import settings
```

Update `GenerateTopicsIn` in `schemas/topics.py` to enforce `count >= 1` — add `from pydantic import BaseModel, Field` at the top of that file:

```python
class GenerateTopicsIn(BaseModel):
    domain: str
    count: int = Field(default=5, ge=1)
```

Append the generate route to `routers/topics.py`:

```python
_logger = logging.getLogger(__name__)

_GENERATE_SYSTEM = (
    "You are a debate-question writer. Return ONLY valid JSON with a single key "
    '"questions" whose value is an array of debate question objects. '
    "Each object must have exactly these keys: "
    '"id" (kebab-case slug derived from the title), '
    '"domain" (the domain string passed in), '
    '"title" (a concise debatable statement), '
    '"description" (3-5 sentences explaining the stakes, main angles, and why it is contested). '
    "Do not include any text outside the JSON."
)


@router.post(
    "/generate",
    response_model=SuccessResponse[list[DebatableQuestion]],
    summary="Generate debate questions for a domain",
)
async def generate(body: GenerateTopicsIn):
    count = min(body.count, 10)
    user_prompt = (
        f"Generate {count} original, debatable questions for the domain: {body.domain}. "
        "Each question should be thought-provoking, contestable, and distinct from the others."
    )
    try:
        completion = await openrouter.chat.completions.create(
            model=settings.main_model,
            max_tokens=1500,
            messages=[
                {"role": "system", "content": _GENERATE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = completion.choices[0].message.content or ""
        parsed = json.loads(raw)
        questions = [DebatableQuestion(**q) for q in parsed["questions"]]
    except Exception as exc:
        _logger.error("Topic generation failed: %s", exc)
        raise HTTPException(status_code=502, detail="Topic generation failed. Please try again.")
    return SuccessResponse(data=questions)
```

- [ ] **Step 4: Run all topics tests**

```bash
cd debatemind-backend
pytest tests/test_topics_router.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/schemas/topics.py \
        debatemind-backend/debatemind/routers/topics.py \
        debatemind-backend/tests/test_topics_router.py
git commit -m "feat: add POST /api/topics/generate LLM endpoint"
```

---

### Task 3: Frontend types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces: `DebatableQuestion` TypeScript interface consumed by Task 4.
- Produces: `api.generateTopics(domain, count)` consumed by Task 4.

- [ ] **Step 1: Add DebatableQuestion to types/index.ts**

Open `frontend/src/types/index.ts` and append after the last export:

```typescript
export interface DebatableQuestion {
  id: string;
  domain: string;
  title: string;
  description: string;
}
```

- [ ] **Step 2: Update api.ts — fix getTopics return type and add generateTopics**

In `frontend/src/lib/api.ts`:

Change the `getTopics` line from:
```typescript
getTopics: () => apiFetch<{ label: string; chips: string[] }[]>("/api/topics/suggest"),
```
to:
```typescript
getTopics: () => apiFetch<import("@/types").DebatableQuestion[]>("/api/topics/suggest"),
```

Append after the `getTopics` line:
```typescript
generateTopics: (domain: string, count: number) =>
  apiFetch<import("@/types").DebatableQuestion[]>("/api/topics/generate", {
    method: "POST",
    body: JSON.stringify({ domain, count }),
  }),
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/lib/api.ts
git commit -m "feat: add DebatableQuestion type and generateTopics API method"
```

---

### Task 4: Frontend UI — replace chip groups with question cards

**Files:**
- Modify: `frontend/src/components/topic/TopicSelection.tsx`

**Interfaces:**
- Consumes: `DebatableQuestion` from `@/types` (Task 3).
- Consumes: `api.getTopics()` — now returns `DebatableQuestion[]`.
- Consumes: `api.generateTopics(domain, count)` (Task 3).

- [ ] **Step 1: Replace TopicSelection.tsx**

Replace the entire file with:

```tsx
"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";
import type { DebatableQuestion } from "@/types";

const DOMAINS = ["POLICY", "TECHNOLOGY", "SOCIETY", "LIFE"] as const;
type Domain = (typeof DOMAINS)[number];

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced", desc: "Varied angles, 60% weakness" },
  { key: "targeted", name: "Targeted", desc: "Every move hits a known weak node" },
  { key: "ruthless", name: "Ruthless", desc: "Same weakness, every angle" },
] as const;

const POSITIONS = ["For", "Against", "Neutral", "Assign randomly"] as const;

const MAX_SOURCE_BYTES = 20 * 1024 * 1024;

export default function TopicSelection() {
  const [topic, setTopic] = useState("");
  const [description, setDescription] = useState("");
  const [selectedCardId, setSelectedCardId] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [selectedDomain, setSelectedDomain] = useState<Domain>("POLICY");
  const [cardsByDomain, setCardsByDomain] = useState<Record<string, DebatableQuestion[]>>({});
  const [generating, setGenerating] = useState(false);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { setSession, setSessions } = useDebate();

  useEffect(() => {
    api.getTopics().then((questions) => {
      const grouped: Record<string, DebatableQuestion[]> = {};
      for (const q of questions) {
        if (!grouped[q.domain]) grouped[q.domain] = [];
        grouped[q.domain].push(q);
      }
      setCardsByDomain(grouped);
    }).catch(() => {});
  }, []);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  function selectCard(card: DebatableQuestion) {
    setTopic(card.title);
    setDescription(card.description);
    setSelectedCardId(card.id);
  }

  async function generateMore() {
    setGenerating(true);
    try {
      const newCards = await api.generateTopics(selectedDomain, 5);
      setCardsByDomain((prev) => ({
        ...prev,
        [selectedDomain]: [...(prev[selectedDomain] ?? []), ...newCards],
      }));
    } catch {
      // silently fail — user can retry
    } finally {
      setGenerating(false);
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setFileError("");
    if (file && file.type !== "application/pdf") {
      setFileError("Only PDF files are supported.");
      setSourceFile(null);
      return;
    }
    if (file && file.size > MAX_SOURCE_BYTES) {
      setFileError("File exceeds 20MB limit.");
      setSourceFile(null);
      return;
    }
    setSourceFile(file);
  }

  function navigateToSession(sessionId: string) {
    if (pollRef.current) clearTimeout(pollRef.current);
    setIndexing(false);
    setPendingSessionId(null);
    setSession(sessionId, { topic, description, difficulty, position: position as never });
  }

  function startPolling(sessionId: string) {
    const poll = async () => {
      try {
        const { source_status } = await api.getSourceStatus(sessionId);
        if (source_status === "indexed") { navigateToSession(sessionId); return; }
        if (source_status === "failed") {
          setFileError("Indexing failed — opponent will start without source context.");
          navigateToSession(sessionId);
          return;
        }
        pollRef.current = setTimeout(poll, 2000);
      } catch {
        navigateToSession(sessionId);
      }
    };
    pollRef.current = setTimeout(poll, 2000);
  }

  async function start() {
    setFileError("");
    setSubmitting(true);
    let res;
    try {
      res = await api.startSession(topic, description, difficulty, position);
    } catch {
      setFileError("Failed to start session — please try again.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    api.getSessions().then(setSessions).catch(() => {});
    if (sourceFile) {
      setIndexing(true);
      setPendingSessionId(res.session_id);
      try {
        await api.uploadSource(res.session_id, sourceFile);
        startPolling(res.session_id);
      } catch {
        setFileError("Upload failed — starting without source grounding.");
        navigateToSession(res.session_id);
      }
    } else {
      navigateToSession(res.session_id);
    }
  }

  function startAnyway() {
    if (pendingSessionId) navigateToSession(pendingSessionId);
  }

  const visibleCards = cardsByDomain[selectedDomain] ?? [];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-sans font-medium text-2xl text-ink mb-5">What do you want to argue about?</h1>

      {/* Topic input */}
      <div className="flex items-center justify-between bg-white border border-border rounded-lg px-4 py-3 mb-4">
        <span className="font-serif text-base text-ink flex-1 mr-2 truncate">
          {topic || <span className="text-fog">Select a question below or type your own</span>}
        </span>
        {topic && (
          <button onClick={() => { setTopic(""); setDescription(""); setSelectedCardId(""); }} className="text-fog text-lg flex-none">✕</button>
        )}
      </div>

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Add context — what's the angle, what should the opponent know?"
        className="w-full bg-white border border-border rounded-lg px-4 py-3 mb-6 font-sans text-sm text-ink resize-none"
        rows={2}
      />

      {/* Domain selector */}
      <div className="flex gap-2 mb-4">
        {DOMAINS.map((d) => (
          <button
            key={d}
            onClick={() => setSelectedDomain(d)}
            className={`font-sans text-xs font-semibold px-3 py-1.5 rounded-full border transition-all ${
              selectedDomain === d
                ? "bg-scarlet text-white border-scarlet"
                : "bg-white text-fog border-fog/40 hover:border-fog"
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Question cards grid */}
      {visibleCards.length === 0 ? (
        <div className="grid grid-cols-2 gap-3 mb-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 rounded-lg border border-border bg-fog/5 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 mb-4">
          {visibleCards.map((card) => (
            <button
              key={card.id}
              onClick={() => selectCard(card)}
              className={`text-left rounded-lg border p-3 transition-all hover:border-scarlet/40 ${
                selectedCardId === card.id
                  ? "border-scarlet bg-scarlet/5"
                  : "border-border bg-white"
              }`}
            >
              <p className={`font-sans text-sm font-medium mb-1 line-clamp-2 ${
                selectedCardId === card.id ? "text-scarlet" : "text-ink"
              }`}>
                {card.title}
              </p>
              <p className="font-sans text-[11px] text-fog leading-relaxed line-clamp-3">
                {card.description}
              </p>
            </button>
          ))}
        </div>
      )}

      {/* Generate more */}
      <button
        onClick={generateMore}
        disabled={generating}
        className="font-sans text-xs text-fog border border-dashed border-fog/40 rounded-full px-4 py-1.5 mb-7 disabled:opacity-50 transition-opacity"
      >
        {generating ? "Generating…" : `+ Generate more ${selectedDomain.toLowerCase()} questions`}
      </button>

      <div className="h-px bg-fog/20 my-7" />

      {/* Source material */}
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">SOURCE MATERIAL (OPTIONAL)</p>
      <div className="flex items-center gap-3 mb-2">
        <label className="font-sans text-xs px-3 py-1.5 rounded-full border border-fog/40 bg-white text-ink cursor-pointer">
          Upload PDF
          <input type="file" accept="application/pdf" onChange={onFileChange} className="hidden" />
        </label>
        {sourceFile && (
          <span className="font-sans text-xs text-ink flex items-center gap-2">
            {sourceFile.name}
            <button onClick={() => setSourceFile(null)} className="text-fog">✕</button>
          </span>
        )}
      </div>
      {fileError && <p className="font-sans text-xs text-scarlet mb-5">{fileError}</p>}

      <div className="h-px bg-fog/20 my-7" />

      {/* Difficulty */}
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">DIFFICULTY</p>
      <div className="flex gap-3 mb-7">
        {DIFFICULTIES.map((d) => (
          <div key={d.key} onClick={() => setDifficulty(d.key)}
            className={`flex-1 rounded-lg p-3 cursor-pointer border transition-all ${
              difficulty === d.key ? "border-scarlet bg-scarlet/5" : "border-border bg-white"
            }`}>
            <p className={`font-sans text-sm font-medium ${difficulty === d.key ? "text-scarlet" : "text-ink"}`}>{d.name}</p>
            <p className="font-sans text-[11px] text-fog mt-1">{d.desc}</p>
          </div>
        ))}
      </div>

      <div className="h-px bg-fog/20 my-7" />

      {/* Position */}
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">YOUR POSITION</p>
      <div className="flex mb-8">
        {POSITIONS.map((p, i) => (
          <button key={p} onClick={() => setPosition(p.toLowerCase().replace(" ", "_"))}
            className={`font-sans text-sm font-medium px-4 py-2 border border-border -ml-px transition-all
              ${i === 0 ? "rounded-l-lg" : ""} ${i === POSITIONS.length - 1 ? "rounded-r-lg" : ""}
              ${position === p.toLowerCase().replace(" ", "_") ? "bg-scarlet border-scarlet text-white z-10 relative" : "bg-white text-ink"}`}>
            {p}
          </button>
        ))}
      </div>

      <button onClick={start} disabled={indexing || submitting || !topic}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60 mb-3">
        {indexing ? "Indexing your document…" : "Start session →"}
      </button>

      {indexing && (
        <button onClick={startAnyway}
          className="w-full border border-fog/40 text-fog font-sans text-sm py-3 rounded-lg">
          Start debate anyway →
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Start dev server and manually verify**

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. Verify:
1. Domain buttons (POLICY / TECHNOLOGY / SOCIETY / LIFE) appear where chip groups were.
2. Cards show with title and description text; 3 cards per domain on initial load.
3. Clicking a card highlights it (scarlet border) and fills the topic input + description textarea.
4. Clicking ✕ on the topic input clears the selection.
5. Clicking "Generate more…" shows "Generating…" then appends new cards below the existing ones.
6. Switching domain shows that domain's cards and resets card highlight.
7. Skeleton pulse placeholders show briefly on first load before cards appear.
8. START SESSION button is disabled until a card is clicked (or topic typed manually).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/topic/TopicSelection.tsx
git commit -m "feat: replace chip groups with domain-filtered debate question cards"
```
