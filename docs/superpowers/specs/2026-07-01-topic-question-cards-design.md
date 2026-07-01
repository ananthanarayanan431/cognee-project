# Topic Question Cards — Design Spec

**Date:** 2026-07-01
**Status:** Approved

## Summary

Replace the current POLICY/TECHNOLOGY/SOCIETY chip groups on the topic selection page with a browsable panel of **debate question cards**. Each card has a short title (the debate statement) and a 3–5 line description so the user knows what they're walking into. A domain dropdown filters cards by category. A "Generate more" button calls the LLM to append N new cards for the selected domain.

---

## Backend

### 1. Schema (`schemas/topics.py`)

Replace `TopicSuggestion` with `DebatableQuestion`:

```python
class DebatableQuestion(BaseModel):
    id: str          # kebab-case slug, stable identifier for React key
    domain: str      # one of: POLICY | TECHNOLOGY | SOCIETY | LIFE
    title: str       # the debate statement
    description: str # 3–5 sentences explaining angles, stakes, context
```

Keep `TopicSuggestion` for any backward-compat imports, or remove if unused.

### 2. Updated `GET /api/topics/suggest`

Returns `SuccessResponse[list[DebatableQuestion]]` — a flat list of ~12 hardcoded questions across 4 domains:

**POLICY (3)**
- EU AI Act: Should the EU AI Act set the global standard for AI governance?
- Carbon pricing: Should carbon taxes replace emissions trading schemes?
- Platform liability: Should social platforms bear legal liability for algorithmic amplification of harmful content?

**TECHNOLOGY (3)**
- AI safety vs. progress: Should AI capability research be paused until alignment is solved?
- Open source AI: Should frontier AI models be open-sourced by default?
- Algorithmic bias: Should algorithmic hiring tools be banned until bias can be certified away?

**SOCIETY (3)**
- Social media age bans: Should social media be legally prohibited for under-16s?
- UBI dignity: Does universal basic income undermine the dignity of work?
- Education reform: Should universities be replaced by competency-based credentialing?

**LIFE (3)**
- Remote work: Does remote work permanently harm team cohesion and career growth?
- Parental monitoring: Should parents have the right to monitor their adult children's finances?
- Work-life balance: Is the pursuit of work-life balance a privilege only the wealthy can afford?

### 3. New `POST /api/topics/generate`

**Request body:**
```python
class GenerateTopicsIn(BaseModel):
    domain: str
    count: int = 5
```

**Response:** `SuccessResponse[list[DebatableQuestion]]`

**Logic:**
- Uses the existing LLM client (`agents/client.py`)
- Prompt asks for `count` debatable questions in `domain`, each with a unique id (slugified title), title, and 3–5 sentence description
- LLM returns structured JSON; parse into `list[DebatableQuestion]`
- Stateless — no DB writes
- `count` is clamped to 1–10 server-side to prevent abuse

---

## Frontend

### Components changed

**`components/topic/TopicSelection.tsx`** — replaces chip section with:

1. **Domain dropdown** — pill-style row of domain buttons (POLICY / TECHNOLOGY / SOCIETY / LIFE). Defaults to POLICY on mount. Switching domain filters to that domain's cards. Follows existing scarlet active style.

2. **Question cards grid** — 2-column grid. Each card:
   - Bold title (the debate statement)
   - Muted description text (capped at 4 lines via `line-clamp-4`)
   - Hover: light border highlight
   - Selected: scarlet border + `bg-scarlet/5`
   - Clicking: sets `topic = card.title`, `description = card.description`

3. **"Generate more" button** — below the grid. Calls `api.generateTopics(domain, 5)`. Appends results to the current domain's card list. Shows spinner and disables while loading.

### State additions

```ts
selectedDomain: string                         // currently filtered domain
cardsByDomain: Record<string, DebatableQuestion[]>  // cards loaded per domain
generating: boolean                            // generate-more loading state
```

### API addition (`lib/api.ts`)

```ts
generateTopics: (domain: string, count: number) =>
  apiFetch<DebatableQuestion[]>("/api/topics/generate", {
    method: "POST",
    body: JSON.stringify({ domain, count }),
  })
```

### Type addition (`types/index.ts`)

```ts
export interface DebatableQuestion {
  id: string;
  domain: string;
  title: string;
  description: string;
}
```

---

## Data flow

1. Mount: `GET /api/topics/suggest` → populate `cardsByDomain` → default to POLICY
2. Domain switch: filter shown cards to `cardsByDomain[selectedDomain]`
3. Card click: `setTopic(card.title); setDescription(card.description)`
4. Generate more: `POST /api/topics/generate { domain, count: 5 }` → append to `cardsByDomain[domain]`

---

## Out of scope

- Web search integration (deferred)
- Persisting generated questions to DB
- Per-user question history
