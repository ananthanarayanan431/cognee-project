# Voice/Text Session Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a mic icon in the sidebar session list for any session that has ever used voice, so voice sessions are visually distinguishable from text-only sessions.

**Architecture:** Backend computes `has_voice_session` as a boolean via an `EXISTS`-style outer join against the `voice_sessions` table in the existing `list_sessions` query (no N+1 queries, no migration). The field flows through the Pydantic response schema to the frontend `SessionListItem` type, and `SessionSidebar.tsx` renders a small `IconMicrophone` next to the title when the flag is `true`.

**Tech Stack:** FastAPI + SQLAlchemy (async, SQLite via `aiosqlite` in tests) on the backend; Next.js + TypeScript + `@tabler/icons-react` on the frontend.

## Global Constraints

- No DB migration — `voice_sessions` table and its `debate_session_id` FK already exist (spec: "No new DB migration needed").
- Icon-only indicator — no filter/grouping/tabs by mode (spec: "Out of scope").
- "Ever used voice" semantics — presence of any `voice_sessions` row is sufficient; do not compute dominant/primary mode (spec: user decision).
- Absence of the mic icon signals text-only — do not add a separate "text" icon (spec: user decision).
- Backend tests run with `cd debatemind-backend && uv run pytest`. No frontend test framework exists in this repo — the frontend task is verified manually in the browser, not via an automated test.

---

### Task 1: Backend — add `has_voice_session` to the sessions list endpoint

**Files:**
- Modify: `debatemind-backend/debatemind/schemas/session.py:79-89` (`SessionListItemOut`)
- Modify: `debatemind-backend/debatemind/routers/sessions.py:1-40` (imports), `:135-169` (`list_sessions`)
- Test: `debatemind-backend/tests/test_sessions_router.py`

**Interfaces:**
- Consumes: existing `VoiceSession` model (`debatemind/models/voice_session.py`) — fields `id`, `debate_session_id`, `user_id`; existing `DebateSession` model, existing `list_sessions` query structure (the `count_subq` outerjoin pattern already in the file).
- Produces: `SessionListItemOut.has_voice_session: bool`, present on every item returned by `GET /api/sessions`. Task 2 (frontend) consumes this exact field name and type.

- [ ] **Step 1: Write the failing test**

Add to `debatemind-backend/tests/test_sessions_router.py`. First add the import near the top (after line 17's `from debatemind.models.session import DebateSession, Exchange`):

```python
from debatemind.models.voice_session import VoiceSession
```

Then append this test function at the end of the file:

```python
async def test_list_sessions_flags_has_voice_session(api_client, session_factory):
    voice_session_id = await _make_session(session_factory, topic="Voice Topic")
    text_session_id = await _make_session(session_factory, topic="Text Topic")

    async with session_factory() as db:
        db.add(VoiceSession(debate_session_id=voice_session_id, user_id="u1"))
        await db.commit()

    response = api_client.get("/api/sessions")
    assert response.status_code == 200

    items = {item["session_id"]: item for item in response.json()["data"]}
    assert items[voice_session_id]["has_voice_session"] is True
    assert items[text_session_id]["has_voice_session"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && uv run pytest tests/test_sessions_router.py::test_list_sessions_flags_has_voice_session -v`
Expected: FAIL — `KeyError: 'has_voice_session'` (field doesn't exist in the response yet).

- [ ] **Step 3: Add the field to the response schema**

In `debatemind-backend/debatemind/schemas/session.py`, modify `SessionListItemOut` (lines 79-89):

```python
class SessionListItemOut(BaseModel):
    session_id: str
    topic_id: Optional[str] = None
    topic: str
    title: Optional[str] = None
    difficulty: str
    status: str
    overall_score: float
    exchanges: int
    has_voice_session: bool
    started_at: datetime
    ended_at: Optional[datetime] = None
```

- [ ] **Step 4: Compute the field in the query**

In `debatemind-backend/debatemind/routers/sessions.py`, add the import (near line 19, alongside the existing `from debatemind.models.session import DebateSession, Exchange`):

```python
from debatemind.models.voice_session import VoiceSession
```

Then replace the body of `list_sessions` (lines 139-169) with:

```python
    count_subq = (
        select(Exchange.session_id, sqlfunc.count(Exchange.id).label("cnt"))
        .join(DebateSession, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
        .group_by(Exchange.session_id)
        .subquery()
    )
    voice_subq = (
        select(VoiceSession.debate_session_id).distinct().subquery()
    )
    result = await db.execute(
        select(DebateSession, count_subq.c.cnt, voice_subq.c.debate_session_id)
        .outerjoin(count_subq, DebateSession.id == count_subq.c.session_id)
        .outerjoin(voice_subq, DebateSession.id == voice_subq.c.debate_session_id)
        .where(DebateSession.user_id == user_id)
        .order_by(DebateSession.started_at.desc())
    )
    rows = result.all()
    return SuccessResponse(
        data=[
            SessionListItemOut(
                session_id=session.id,
                topic_id=session.topic_id,
                topic=session.topic,
                title=session.title,
                difficulty=session.difficulty,
                status=session.status,
                overall_score=session.overall_score,
                exchanges=cnt or 0,
                has_voice_session=voice_session_marker is not None,
                started_at=session.started_at,
                ended_at=session.ended_at,
            )
            for session, cnt, voice_session_marker in rows
        ]
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd debatemind-backend && uv run pytest tests/test_sessions_router.py -v`
Expected: PASS — all tests in the file, including the new `test_list_sessions_flags_has_voice_session`.

- [ ] **Step 6: Commit**

```bash
git add debatemind-backend/debatemind/schemas/session.py debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_sessions_router.py
git commit -m "feat: expose has_voice_session on session list endpoint"
```

---

### Task 2: Frontend — surface `has_voice_session` and render a mic icon

**Files:**
- Modify: `frontend/src/types/index.ts:131-142` (`SessionListItem`)
- Modify: `frontend/src/components/sidebar/SessionSidebar.tsx:4-16` (imports), `:61-82` (`SessionCard` render)

**Interfaces:**
- Consumes: `SessionListItemOut.has_voice_session: bool` from Task 1's API response (field name/type must match exactly).
- Produces: no new exports; this is a leaf UI change.

- [ ] **Step 1: Add the field to the frontend type**

In `frontend/src/types/index.ts`, modify `SessionListItem` (lines 131-142):

```ts
export interface SessionListItem {
  session_id: string;
  topic_id: string | null;
  topic: string;
  title?: string | null;
  difficulty: string;
  status: "active" | "ended";
  overall_score: number;
  exchanges: number;
  has_voice_session: boolean;
  started_at: string;
  ended_at: string | null;
}
```

- [ ] **Step 2: Import the mic icon**

In `frontend/src/components/sidebar/SessionSidebar.tsx`, add `IconMicrophone` to the existing `@tabler/icons-react` import block (lines 4-16):

```tsx
import {
  IconBrain,
  IconChartBar,
  IconDotsVertical,
  IconDownload,
  IconHistory,
  IconLogout,
  IconMicrophone,
  IconNetwork,
  IconSettings,
  IconSparkles,
  IconTrash,
  IconX,
} from "@tabler/icons-react";
```

- [ ] **Step 3: Render the icon in `SessionCard`**

In the same file, modify the button contents inside `SessionCard` (lines 61-82) to insert the icon between the difficulty badge and the title:

```tsx
  return (
    <div ref={ref} className="relative flex items-center rounded-md hover:bg-fog/5 transition-colors">
      {/* Click row → open / resume the session (single line) */}
      <button
        onClick={onOpen}
        title={`${session.topic} · ${session.difficulty} · ${session.exchanges} turns`}
        className="flex-1 min-w-0 flex items-center gap-2 text-left px-2 py-1.5"
      >
        <span
          className={`flex-none w-4 h-4 rounded flex items-center justify-center font-sans text-[9px] font-bold ${difficultyClass}`}
          title={session.difficulty}
        >
          {session.difficulty.charAt(0).toUpperCase()}
        </span>
        {session.has_voice_session && (
          <IconMicrophone size={14} className="flex-none text-fog" aria-label="Voice session" />
        )}
        <span className="flex-1 min-w-0 font-sans text-[12px] text-ink leading-tight truncate">
          {session.title || session.topic}
        </span>
        {session.status === "active" && (
          <span className="flex-none w-1.5 h-1.5 rounded-full bg-verdant" title="Active" />
        )}
        <span className="flex-none font-sans text-[10px] text-fog">{formatDate(session.started_at)}</span>
      </button>
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (the `SessionListItem` type change is additive and `has_voice_session` is now consumed with a matching type).

- [ ] **Step 5: Manually verify in the browser**

With both the backend (from Task 1) and frontend dev servers running:
1. Open a session that has never used voice — confirm no mic icon appears next to its title in the sidebar.
2. Start or resume a session and use the voice feature at least once (creates a `voice_sessions` row via the existing voice-token flow).
3. Reload the sidebar (or navigate away and back) — confirm the mic icon now appears next to that session's title, and the difficulty badge is unchanged.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/sidebar/SessionSidebar.tsx
git commit -m "feat: show mic icon for sessions that used voice"
```
