# Per-message pipeline stage progress over SSE

**Date:** 2026-07-01
**Status:** Approved

## Context

`POST /sessions/{session_id}/message` ([sessions.py:177-267](../../../debatemind-backend/debatemind/routers/sessions.py#L177-L267))
runs a LangGraph pipeline (`debate_pipeline`, defined in
[pipeline.py](../../../debatemind-backend/debatemind/agents/pipeline.py)) with nodes
`extract → opponent → judge → mastery → remember → prune`. Each node is an LLM call or
similar non-trivial work. Today the handler does `await debate_pipeline.ainvoke(initial_state)`
synchronously, to completion, *before* constructing the `StreamingResponse`. Only after the
entire pipeline (all 6 nodes) has finished does the SSE stream open, at which point the
already-computed opponent response is fake-streamed back word-by-word for animation effect.

The frontend ([useDebateSSE.ts](../../../frontend/src/hooks/useDebateSSE.ts)) calls
`setThinking(true)` before the fetch and `setThinking(false)` as soon as response headers
arrive (line 28) — which, given current backend behavior, is also "as soon as the entire
pipeline has already finished." The user sees a blank/silent wait for however long the full
pipeline takes, with no indication of what's happening, then a burst of activity.

This project already has one precedent for surfacing background progress:
`source_status` (`none → pending → indexed → failed`) on `DebateSession`, polled via
`GET /sessions/{id}/source-status` while a Celery worker indexes an uploaded PDF
out-of-process. That pattern requires a DB-backed cache because there is no open
connection between the polling client and the worker doing the work.

The per-message pipeline is different: `send_message` already holds an open SSE
connection to the client for the entire duration of the work. No new cache or polling
endpoint is needed — the backend can push stage progress directly down the existing
connection as each pipeline node runs.

Session-level lifecycle (source uploading, ready, active, ended) is already fully
represented by the existing `status` and `source_status` columns on `DebateSession` — no
gap there, no changes proposed.

## Decision

Restructure `send_message`'s SSE generator to drive the pipeline via
`debate_pipeline.astream(initial_state, stream_mode="updates")` instead of
`ainvoke(...)`, consuming it from *inside* `event_stream()`. As each node's update
arrives, merge it into an accumulated `final_state` dict (equivalent to what `ainvoke`
would have returned) and emit a `stage` SSE event for the four nodes that map to
something a user would recognize: `extract`, `opponent`, `judge`, `mastery`.
`remember`/`prune` are internal bookkeeping (graph-memory writes, pruning mastered
patterns) with no user-facing meaning — their updates are still consumed to keep
`final_state` correct, but no SSE event is emitted for them.

### Wire sequence

```
data: {"type": "stage", "stage": "extract"}        # emitted immediately, before the graph runs
                                                      # (extract node runs)
data: {"type": "stage", "stage": "opponent"}
                                                      # (opponent node runs)
data: {"type": "token", "text": "..."}  x N          # unchanged: fake word-by-word reveal
data: {"type": "stage", "stage": "judge"}
                                                      # (judge node runs)
data: {"type": "stage", "stage": "mastery"}
                                                      # (mastery, then remember/prune run silently)
data: {"type": "judge", "logic": ..., ...}           # unchanged
data: {"type": "graph", "data": {...}}               # unchanged
data: [DONE]                                          # unchanged
```

A `stage` event means "this stage has just started." Because the node sequence is a
static linear chain (`extract → opponent → judge → mastery → remember → prune`), the
generator emits the event for stage *N* right before pulling the update that corresponds
to stage *N* finishing — so `extract`'s event fires immediately, and each subsequent
stage's event fires as soon as the prior stage's update is observed from the iterator,
not after the whole pipeline finishes.

### Error handling

If a node raises mid-stream (e.g. an LLM call times out), the generator catches the
exception, emits `{"type": "error", "detail": "<message>"}`, and closes the stream
(no `[DONE]` after an error). This is new — today there is no try/except around the
pipeline at all, so a failure currently kills the connection with no signal to the
client. Without this, switching to a long-lived progressive stream would mean a mid-pipeline
failure leaves the frontend stuck on "Judging..." forever instead of a clean failed-request
state.

### Persistence

Unchanged in substance: once the `astream` iterator is exhausted, `final_state` holds the
same fields `ainvoke` would have returned, and the existing `Exchange` row construction,
`db.commit()`, and `_session_wins` update proceed exactly as today.

## Frontend changes

- **`store/debate.ts`**: add `currentStage: string | null` and `setCurrentStage`, cleared
  whenever `thinking` is cleared.
- **`useDebateSSE.ts`**: remove the premature `setThinking(false)` that currently fires as
  soon as `fetch` resolves headers (line 28). Instead:
  - handle `evt.type === "stage"` → `setCurrentStage(evt.stage)`
  - clear `thinking` and `currentStage` on the first `token` event (response has started
    rendering) or on `evt.type === "error"`
  - on `evt.type === "error"`, surface a failure state to the user (exact UI left to
    implementation — at minimum, stop the thinking indicator and show an error message in
    place of the opponent bubble)
- **UI** (`PulseAvatar` / `MessageBubble`, wherever the thinking indicator renders): map
  stage keys to copy via a small lookup — `extract → "Reading your argument…"`,
  `opponent → "Drafting a response…"`, `judge → "Judging the exchange…"`,
  `mastery → "Checking mastery…"` — falling back to a generic "Thinking…" when
  `currentStage` is null.

## Out of scope

- No new DB columns, no Redis, no polling endpoint for message-pipeline progress — the
  existing SSE connection is sufficient and strictly lower-latency than a cache+poll
  approach.
- No change to session-lifecycle (`status`/`source_status`) — already adequate.
- No change to how the opponent response itself is generated or fake-streamed
  word-by-word; only *when* that streaming starts relative to the rest of the pipeline
  changes.
