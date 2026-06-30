# Per-message pipeline stage progress over SSE — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream pipeline-stage progress (`extract` → `opponent` → `judge` → `mastery`) to the frontend over the already-open SSE connection during `POST /sessions/{id}/message`, instead of leaving the user staring at nothing while the full pipeline runs silently before any response appears.

**Architecture:** Replace the eager `await debate_pipeline.ainvoke(initial_state)` in `send_message` with `debate_pipeline.astream(initial_state, stream_mode="updates")`, consumed from inside the SSE generator. Each yielded `{node_name: state}` update is merged into an accumulated `final_state`; a `stage` SSE event is emitted right before each of the four user-meaningful stages begins. A new `error` SSE event covers mid-pipeline failures. The frontend's `useDebateSSE` hook delays creating the opponent message bubble until the first real token arrives (today it creates it immediately, which would now race ahead of the stage events), and surfaces `currentStage` as dynamic copy in the existing "thinking" placeholder.

**Tech Stack:** FastAPI (`StreamingResponse`/SSE), LangGraph `0.2.60` (`CompiledGraph.astream`), pytest + `TestClient` (backend); Next.js + Zustand (frontend, no test runner present in this repo).

## Global Constraints

- LangGraph `0.2.60` is pinned (`debatemind-backend/pyproject.toml`) — `astream(..., stream_mode="updates")` yields one `{node_name: <node's full return value>}` dict per node, confirmed by direct experimentation against the installed version (the pipeline's nodes mutate-and-return the whole state dict, so each update already contains the full state, not a partial diff — `final_state.update(...)` is still used for safety/clarity).
- No new DB columns, Redis keys, or polling endpoints — per the approved spec, all progress is pushed over the existing SSE connection.
- Visible stages are exactly `extract`, `opponent`, `judge`, `mastery` — `remember`/`prune` are consumed silently (no SSE event), per the approved spec.
- The frontend has no test runner configured (`package.json` only has `dev`/`build`/`start`/`lint`). Frontend tasks are verified via `npm run build` (TypeScript check) and a manual browser pass — do not introduce a test framework as part of this plan (out of scope).
- Error event payloads must not leak raw exception text to the client (`{"type": "error", "detail": "Something went wrong generating a response."}`); the real exception is logged server-side only via `logger.exception(...)`.

---

### Task 1: Backend — stream pipeline stage events over SSE, with error handling

**Files:**
- Modify: `debatemind-backend/debatemind/routers/sessions.py:1-37` (imports, module constants), `debatemind-backend/debatemind/routers/sessions.py:177-267` (`send_message`)
- Test: `debatemind-backend/tests/test_sessions_router.py`

**Interfaces:**
- Consumes: `debate_pipeline.astream(initial_state, stream_mode="updates")` (LangGraph `CompiledGraph`, already imported as `debate_pipeline` at `sessions.py:11`); `build_graph(user_id, topic)` (already imported at `sessions.py:28`).
- Produces: SSE event stream with event types `stage` (`{"type": "stage", "stage": "extract"|"opponent"|"judge"|"mastery"}`), `token` (unchanged), `judge` (unchanged), `graph` (unchanged), `error` (`{"type": "error", "detail": str}`), and the literal `data: [DONE]\n\n` terminator (only sent on success, omitted after an `error` event). This is the contract `useDebateSSE.ts` (Task 3) consumes.

- [ ] **Step 1: Write the failing tests**

Add to the top of `debatemind-backend/tests/test_sessions_router.py`, alongside the existing imports:

```python
import json
from unittest.mock import AsyncMock, MagicMock
```//replace the existing `from unittest.mock import MagicMock` line with the above (adds `AsyncMock` and `json`).

Add these imports alongside the existing `debatemind` imports:

```python
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.graph import GraphOut
```//`Exchange` is new; `DebateSession` is already imported — merge into the existing import line rather than duplicating it. `GraphOut` is new.

Add this helper and the two new tests anywhere after `_make_session`:

```python
def _parse_sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[len("data: ") :]
        if raw == "[DONE]":
            continue
        events.append(json.loads(raw))
    return events


async def test_send_message_streams_stage_events_then_response(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)

    node_updates = [
        ("extract", {"extracted_pattern": "EvidenceBased", "extracted_fallacy": None, "evidence_quality": "Moderate"}),
        ("opponent", {"opponent_response": "Hello there"}),
        ("judge", {"judge_logic": 7.0, "judge_evidence": 6.0, "judge_rhetoric": 8.0, "judge_fallacy": None, "outcome": "Won"}),
        ("mastery", {"mastery_events": [], "consecutive_wins": 1}),
        ("remember", {}),
    ]

    class FakePipeline:
        async def astream(self, initial_state, stream_mode="updates"):
            state = dict(initial_state)
            for node_name, delta in node_updates:
                state.update(delta)
                yield {node_name: dict(state)}

    monkeypatch.setattr(sessions_router, "debate_pipeline", FakePipeline())
    monkeypatch.setattr(
        sessions_router, "build_graph", AsyncMock(return_value=GraphOut(nodes=[], edges=[]))
    )

    with api_client.stream(
        "POST", f"/api/sessions/{session_id}/message", json={"text": "AI is risky"}
    ) as resp:
        body = "".join(resp.iter_text())

    assert resp.status_code == 200
    events = _parse_sse_events(body)
    types = [e["type"] for e in events]
    assert types == ["stage", "stage", "token", "token", "stage", "stage", "judge", "graph"]
    assert [e["stage"] for e in events if e["type"] == "stage"] == [
        "extract",
        "opponent",
        "judge",
        "mastery",
    ]
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Hello there"
    judge_event = next(e for e in events if e["type"] == "judge")
    assert judge_event["outcome"] == "Won"
    assert body.rstrip().endswith("data: [DONE]")

    async with session_factory() as db:
        result = await db.execute(select(Exchange).where(Exchange.session_id == session_id))
        exchange = result.scalar_one()
        assert exchange.opponent_response == "Hello there"
        assert exchange.outcome == "Won"


async def test_send_message_emits_error_event_and_skips_persistence_on_pipeline_failure(
    api_client, session_factory, monkeypatch
):
    session_id = await _make_session(session_factory)

    class FailingPipeline:
        async def astream(self, initial_state, stream_mode="updates"):
            yield {"extract": {**initial_state, "extracted_pattern": "EvidenceBased"}}
            raise RuntimeError("boom")

    monkeypatch.setattr(sessions_router, "debate_pipeline", FailingPipeline())

    with api_client.stream(
        "POST", f"/api/sessions/{session_id}/message", json={"text": "x"}
    ) as resp:
        body = "".join(resp.iter_text())

    events = _parse_sse_events(body)
    assert events[-1] == {
        "type": "error",
        "detail": "Something went wrong generating a response.",
    }
    assert "[DONE]" not in body

    async with session_factory() as db:
        result = await db.execute(select(Exchange).where(Exchange.session_id == session_id))
        assert result.scalar_one_or_none() is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_sessions_router.py -k send_message -v`
Expected: both new tests FAIL — `FakePipeline`/`FailingPipeline` are never invoked because `send_message` still calls `debate_pipeline.ainvoke(...)` (an attribute `FakePipeline` doesn't have), so you should see an `AttributeError` (no `ainvoke`) or a collection error.

- [ ] **Step 3: Rewrite `send_message` to stream stages and handle errors**

In `debatemind-backend/debatemind/routers/sessions.py`, add `import logging` at the top (after `import json`) and a module-level logger + stage order near the existing `MAX_SOURCE_BYTES` constant (line 42):

```python
import asyncio
import json
import logging
from datetime import datetime, timezone
```

```python
MAX_SOURCE_BYTES = 20 * 1024 * 1024

logger = logging.getLogger(__name__)

# User-meaningful pipeline nodes, in execution order. remember/prune are
# internal bookkeeping (memory-graph writes, mastery pruning) with no
# user-facing meaning and are intentionally not surfaced as stage events.
STAGE_ORDER = ["extract", "opponent", "judge", "mastery"]
```

Replace the entire `send_message` function body from `final_state = await debate_pipeline.ainvoke(initial_state)` (the line right after the `initial_state = DebateState(...)` block) through the end of the function (i.e. everything from that line down to and including `return StreamingResponse(event_stream(), media_type="text/event-stream")`) with:

```python
    async def event_stream():
        final_state = dict(initial_state)
        stage_idx = 0
        yield f"data: {json.dumps({'type': 'stage', 'stage': STAGE_ORDER[0]})}\n\n"
        try:
            async for update in debate_pipeline.astream(initial_state, stream_mode="updates"):
                node_name, node_state = next(iter(update.items()))
                final_state.update(node_state)

                if node_name == "opponent":
                    opponent_text = final_state.get("opponent_response") or ""
                    words = opponent_text.split()
                    for i, word in enumerate(words):
                        chunk = word + (" " if i < len(words) - 1 else "")
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                        await asyncio.sleep(0.055)

                stage_idx += 1
                if stage_idx < len(STAGE_ORDER):
                    yield f"data: {json.dumps({'type': 'stage', 'stage': STAGE_ORDER[stage_idx]})}\n\n"
        except Exception:
            logger.exception(
                "debate pipeline failed for session %s turn %s", session_id, turn
            )
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "detail": "Something went wrong generating a response.",
                    }
                )
                + "\n\n"
            )
            return

        _session_wins[session_id] = final_state.get("consecutive_wins", 0)

        exchange = Exchange(
            session_id=session_id,
            turn_number=turn,
            user_message=body.text,
            opponent_response=final_state.get("opponent_response", ""),
            detected_pattern=final_state.get("extracted_pattern"),
            fallacy=final_state.get("judge_fallacy") or final_state.get("extracted_fallacy"),
            judge_logic=final_state.get("judge_logic"),
            judge_evidence=final_state.get("judge_evidence"),
            judge_rhetoric=final_state.get("judge_rhetoric"),
            outcome=final_state.get("outcome"),
        )
        db.add(exchange)
        await db.commit()

        judge_payload = {
            "type": "judge",
            "logic": final_state.get("judge_logic"),
            "evidence": final_state.get("judge_evidence"),
            "rhetoric": final_state.get("judge_rhetoric"),
            "fallacy": final_state.get("judge_fallacy"),
            "outcome": final_state.get("outcome"),
            "mastery": final_state.get("mastery_events", []),
        }
        yield f"data: {json.dumps(judge_payload)}\n\n"
        graph = await build_graph(user_id, session.topic)
        yield f"data: {json.dumps({'type': 'graph', 'data': graph.model_dump()})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

The lookup/auth checks, turn-count query, and `initial_state` construction directly above this (lines 192–225 in the original file) are unchanged — only the code from `final_state = await debate_pipeline.ainvoke(...)` onward is replaced. Using the `db` session (a FastAPI `yield`-dependency from `get_db`) inside this generator is safe: FastAPI keeps `yield`-dependencies open until the `StreamingResponse` body has been fully sent, not just until the endpoint function returns.

- [ ] **Step 4: Run the tests to verify they pass, and run the full suite for regressions**

Run: `cd debatemind-backend && .venv/bin/pytest tests/test_sessions_router.py -v`
Expected: all tests PASS, including the two new ones and the pre-existing ones in this file.

Run: `cd debatemind-backend && .venv/bin/pytest -v`
Expected: full suite PASSES (no regressions in other routers/services).

- [ ] **Step 5: Commit**

```bash
cd /Volumes/External/hackathon
git add debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_sessions_router.py
git commit -m "feat: stream pipeline stage progress over SSE in send_message"
```

---

### Task 2: Frontend — track current pipeline stage in the debate store

**Files:**
- Modify: `frontend/src/store/debate.ts`

**Interfaces:**
- Consumes: nothing new.
- Produces: `currentStage: string | null` (state field) and `setCurrentStage: (stage: string | null) => void` (action) on the `useDebate` store — consumed by Task 3 (`useDebateSSE.ts`) and Task 4 (`DebateView.tsx`).

- [ ] **Step 1: Add the field and action**

In `frontend/src/store/debate.ts`, add `currentStage` to the `DebateStore` interface right after `thinking: boolean;` (line 12):

```typescript
  thinking: boolean;
  currentStage: string | null;
```

Add the setter signature right after `setThinking: (v: boolean) => void;` (line 21):

```typescript
  setThinking: (v: boolean) => void;
  setCurrentStage: (stage: string | null) => void;
```

Add the initial value right after `thinking: false,` (line 34):

```typescript
  thinking: false,
  currentStage: null,
```

Add the setter implementation right after `setThinking: (thinking) => set({ thinking }),` (line 63):

```typescript
  setThinking: (thinking) => set({ thinking }),
  setCurrentStage: (currentStage) => set({ currentStage }),
```

- [ ] **Step 2: Verify the project still type-checks**

Run: `cd frontend && npm run build`
Expected: build SUCCEEDS (no TypeScript errors). This is a pure additive change to the store, so no other file should break yet — `currentStage`/`setCurrentStage` aren't consumed until Tasks 3–4.

- [ ] **Step 3: Commit**

```bash
cd /Volumes/External/hackathon
git add frontend/src/store/debate.ts
git commit -m "feat: add currentStage to debate store"
```

---

### Task 3: Frontend — consume stage/error SSE events, fix premature thinking-cleared state

**Files:**
- Modify: `frontend/src/hooks/useDebateSSE.ts`

**Interfaces:**
- Consumes: `currentStage`/`setCurrentStage` from `useDebate` (Task 2); SSE event shapes from Task 1 (`stage`, `token`, `judge`, `graph`, `error`).
- Produces: same public hook signature (`useSendMessage(): (text: string) => Promise<void>`) — no change to callers (`InputArea.tsx` or wherever it's invoked).

**Context:** Today, `addMessage` creates the empty opponent bubble (line 27) and `setThinking(false)` fires (line 28) immediately after `fetch` resolves headers — before any SSE event is read. With Task 1's change, headers now arrive before the pipeline has even started (extract hasn't run), so doing this immediately would prematurely end the "thinking" UI and create an opponent bubble with nothing to show. Instead, the bubble is created lazily on the first `token` event, and `thinking`/`currentStage` clear at that same point (or on `error`).

- [ ] **Step 1: Rewrite the hook**

Replace the full contents of `frontend/src/hooks/useDebateSSE.ts` with:

```typescript
import { useCallback } from "react";
import { useDebate } from "@/store/debate";
import { JudgeScore, GraphData } from "@/types";
import { v4 as uuid } from "uuid";

export function useSendMessage() {
  const { sessionId, addMessage, updateLastOpponent, revealJudge, setThinking, setGraph, setCurrentStage } =
    useDebate();
  const token = useDebate((s) => s.token);

  return useCallback(async (text: string) => {
    if (!sessionId || !text.trim()) return;
    addMessage({ id: uuid(), role: "user", text });
    setThinking(true);
    setCurrentStage(null);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text }),
    });

    if (!res.body) {
      setThinking(false);
      setCurrentStage(null);
      return;
    }

    const opponentId = uuid();
    let opponentAdded = false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const evt = JSON.parse(raw);
          if (evt.type === "stage") {
            setCurrentStage(evt.stage);
          }
          if (evt.type === "token") {
            if (!opponentAdded) {
              addMessage({ id: opponentId, role: "opponent", text: "" });
              opponentAdded = true;
              setThinking(false);
              setCurrentStage(null);
            }
            const current = useDebate.getState().messages.find((m) => m.id === opponentId);
            updateLastOpponent((current?.text ?? "") + evt.text);
          }
          if (evt.type === "judge") {
            setTimeout(() => revealJudge(evt as JudgeScore), 2000);
          }
          if (evt.type === "graph") {
            setGraph(evt.data as GraphData);
          }
          if (evt.type === "error") {
            setThinking(false);
            setCurrentStage(null);
            if (!opponentAdded) {
              addMessage({
                id: opponentId,
                role: "opponent",
                text: "Something went wrong generating a response. Please try again.",
              });
              opponentAdded = true;
            }
          }
        } catch {
          // ignore malformed SSE events
        }
      }
    }
  }, [sessionId, token, addMessage, updateLastOpponent, revealJudge, setThinking, setGraph, setCurrentStage]);
}
```

- [ ] **Step 2: Verify the project still type-checks**

Run: `cd frontend && npm run build`
Expected: build SUCCEEDS.

- [ ] **Step 3: Commit**

```bash
cd /Volumes/External/hackathon
git add frontend/src/hooks/useDebateSSE.ts
git commit -m "fix: defer opponent bubble creation to first token; consume stage/error SSE events"
```

---

### Task 4: Frontend — show stage-aware copy in the thinking placeholder

**Files:**
- Modify: `frontend/src/components/debate/DebateView.tsx`

**Interfaces:**
- Consumes: `currentStage` from `useDebate` (Task 2).
- Produces: no new exports — visual-only change to the existing placeholder block.

- [ ] **Step 1: Read `currentStage` from the store and map it to copy**

In `frontend/src/components/debate/DebateView.tsx`, change the destructure on line 9 from:

```typescript
  const { messages, thinking, graph, sessionId, sessionConfig, setScreen } = useDebate();
```

to:

```typescript
  const { messages, thinking, currentStage, graph, sessionId, sessionConfig, setScreen } = useDebate();
```

Add this constant near the top of the file, right after the imports (after line 7):

```typescript
const STAGE_LABELS: Record<string, string> = {
  extract: "Reading your argument…",
  opponent: "Drafting a response…",
  judge: "Judging the exchange…",
  mastery: "Checking mastery…",
};
```

Replace the static placeholder text at line 77-79:

```typescript
                <span className="font-serif italic text-sm text-fog">
                  Studying your argument…
                </span>
```

with:

```typescript
                <span className="font-serif italic text-sm text-fog">
                  {currentStage ? (STAGE_LABELS[currentStage] ?? "Thinking…") : "Thinking…"}
                </span>
```

- [ ] **Step 2: Verify the project still type-checks**

Run: `cd frontend && npm run build`
Expected: build SUCCEEDS.

- [ ] **Step 3: Commit**

```bash
cd /Volumes/External/hackathon
git add frontend/src/components/debate/DebateView.tsx
git commit -m "feat: show pipeline-stage copy in the opponent thinking placeholder"
```

---

### Task 5: Manual end-to-end verification

No automated coverage exists for the full browser flow (no frontend test runner — see Global Constraints). This task is a manual check, not a code change.

**Prerequisite:** the full stack running locally (backend + Celery + Redis + frontend) — use whatever `make`/`docker-compose` target this repo already uses to start everything (check `debatemind-backend/Makefile`, referenced in recent commit `12e164c feat: add infra-logs command and consolidated start target to Makefile`, if unsure which target to run).

- [ ] **Step 1:** Start a debate session, send a message, and confirm the placeholder text changes over time (at minimum "Reading your argument…" then "Drafting a response…") before the opponent's reply starts appearing word-by-word, instead of a long silent wait.
- [ ] **Step 2:** Confirm the judge score panel and the cognitive-fingerprint graph still update after the response finishes, exactly as before this change.
- [ ] **Step 3:** Force a failure (e.g. temporarily set an invalid `OPENROUTER_API_KEY`/model in backend config, or monkeypatch one node to raise, restart the backend) and confirm the frontend shows the "Something went wrong generating a response. Please try again." message instead of hanging indefinitely on the thinking indicator. Revert the temporary breakage afterward.
- [ ] **Step 4:** Send two or three messages in a row in the same session to confirm turn numbering, judge scores, and the graph panel all continue working across multiple turns (no state leaking between requests).
