# Cognee Background Worker — Design

**Date:** 2026-07-03
**Status:** Approved for planning

## Problem

The voice bot needs to support at least 5 concurrent users on a single small
cloud instance. Investigating that goal surfaced a correctness bug that
blocks it, independent of instance sizing:

Every write into a user's cognee fingerprint (`cognee.add()` /
`cognee.cognify()`, defined in `debatemind/cognee/fingerprint.py`) ends up
inside `cognee/tasks/ingestion/ingest_data.py`, which calls
`pipeline.run(...)` (lines 170/178) **synchronously, with no `await` and no
thread offload**. That `pipeline.run()` uses dlt's sqlalchemy destination,
which opens a plain blocking `psycopg2` connection. Because this call sits
inside an `async def` with no thread/process isolation, it **freezes the
entire asyncio event loop** of the FastAPI process for its duration — not
just the request that triggered it, but every other concurrent request
(other users' voice tool calls, token minting, chat turns, health checks).

This is not fixable with `asyncio.to_thread()`: cognee's own relational
engine (`create_relational_engine()`, `@lru_cache`d, asyncpg-backed) is a
process-wide singleton bound to whichever event loop first touches it — the
main FastAPI loop, created at app startup. Running the enclosing coroutine in
a different thread's event loop would eventually touch that same cached
engine from a foreign loop and raise ("Future attached to a different
loop"). The only safe isolation is a genuinely separate **process**.

## Scope: every call site into fingerprint.py

The bug is in shared library code, not any one caller, so scoping the fix to
"voice only" wouldn't work — any concurrent caller elsewhere in the process
can still freeze the loop for voice users. Five call sites hit this path
today (re-verified against the current code, which has moved since this
scope was first drafted):

| Call site | Function(s) | Current pattern |
|---|---|---|
| `voice_agent/tools.py` (`_save_debate_observation`, `_end_voice_session`) | `remember_argument`, `forget_pattern`, `remember_session_summary`, `improve_fingerprint` | `asyncio.create_task(...)`, fire-and-forget. `_end_voice_session` fires `remember_session_summary` and `improve_fingerprint` as two **independent, unordered** tasks — same race the `sessions.py` comment below already warns about, just not yet fixed here. |
| `agents/pipeline.py` (`_remember_node`) | `remember_argument` | `asyncio.create_task(...)` + done-callback that also invalidates `_weakness_cache` (`agents/opponent.py`) |
| `agents/pipeline.py` (`_remember_facts_node`) | `remember_personal_fact` | `asyncio.create_task(...)` per new fact + done-callback that invalidates `_facts_cache` (`agents/opponent.py`) — same shape as `_remember_node`, separate cache |
| `agents/pipeline.py` (`_mastery_prune_node`) | `forget_pattern` | `await`ed **inline**, per pattern. As of the current code there is no retry-next-turn bookkeeping (a prior version tracked failed patterns in `state["mastery_events"]`; the current version just logs and continues, "must not erase the achieved-mastery list"). This is still the worst of the five: it blocks the chat response directly for the full `add()+cognify()` duration, not just the background. |
| `routers/calibration.py:99-113` | `remember_argument` | `asyncio.create_task(...)`, fire-and-forget |
| `routers/sessions.py:553` (`_finalize_session_fingerprint`) | `remember_session_summary` then `improve_fingerprint`, **in order** | one `asyncio.create_task(...)` wrapping both sequentially |

**Explicitly out of scope:** `routers/sessions.py:214` (`_write_title`) is a
background task too, but it only calls an LLM and writes through the app's
own async SQLAlchemy engine — it never touches cognee, so it doesn't have
this problem and isn't touched.

Also out of scope (per earlier discussion in this design pass): horizontal
scaling / multi-replica deployment. A single instance is sufficient for the
5-concurrent-user target; DB pool sizing was checked and is not the
bottleneck.

## Design

### 1. Revive the existing (dormant) Celery worker

`debatemind/worker/celery_app.py` already defines a `Celery("debatemind",
broker=redis_url, backend=redis_url)` instance with a `worker_init` signal
handler that calls `cognee.setup()`. It has zero registered tasks today and
isn't run anywhere except a `Makefile` dev target. A `redis` service already
exists in the root `docker-compose.yml`.

- Extend `worker_init` to also call `configure_cognee(settings)` (same call
  `main.py`'s lifespan makes), so each worker process gets its own
  independent cognee engine, bound to that process's own event loop — never
  shared with the API process.
- Add the worker as a real deployed process: a service in
  `docker-compose.yml` and, for the actual cloud deployment, a second
  process/container running `celery -A debatemind.worker.celery_app worker`.

### 2. Define one Celery task per fingerprint operation

`debatemind/worker/tasks.py` already exists, is already the `include=[...]`
target in `celery_app.py`, and already has a `worker_init` signal handler —
it just registers zero tasks today. Add the task definitions there (no new
module needed) wrapping the existing `fingerprint.py` functions with
`asyncio.run(...)` (safe here because each task runs in a fresh worker
process with no pre-existing event loop or cached engine from another loop):

`remember_session_summary` and `improve_fingerprint` are, on inspection,
never called standalone anywhere in the codebase — every call site pairs
them (summary then reindex), so they don't need their own tasks, only the
two ordered "finalize" tasks below need to exist:

- `remember_argument_task` — used by `voice_agent/tools.py`,
  `agents/pipeline.py` (`_remember_node`), `routers/calibration.py`
- `remember_personal_fact_task` — used by `agents/pipeline.py`
  (`_remember_facts_node`)
- `forget_pattern_task` — used by `agents/pipeline.py`
  (`_mastery_prune_node`), `voice_agent/tools.py` (voice mastery prune)
- `finalize_session_fingerprint_task` — wraps a new
  `services/fingerprint_finalize_svc.finalize_session_fingerprint(user_id,
  session_id)` (moved out of `routers/sessions.py`'s private
  `_finalize_session_fingerprint`, same ordered summary-then-reindex body),
  used by `routers/sessions.py`
- `finalize_voice_session_fingerprint_task` — wraps a new
  `services/fingerprint_finalize_svc.finalize_voice_session_fingerprint(...)`,
  used by `voice_agent/tools.py`. Voice's `_end_voice_session` currently
  fires `remember_session_summary` and `improve_fingerprint` as two
  independent, unordered tasks (see scope table above); this task fixes
  that same ordering race while moving the work off the event loop, mirroring
  the chat-side fix.
- `improve_fingerprint_task` — a standalone reindex-only task, needed
  because `_end_voice_session` currently runs `improve_fingerprint`
  unconditionally even when there's no `debate_session` to summarize (in
  which case the finalize task above doesn't apply); this preserves that
  fallback path.

Both finalize functions live together in one new module,
`debatemind/services/fingerprint_finalize_svc.py`, following the existing
`services/*_svc.py` convention — keeps `worker/tasks.py` from having to
import private helpers out of a router module.

### 3. Update call sites

`voice_agent/tools.py`, `routers/calibration.py`, and
`routers/sessions.py` swap `asyncio.create_task(remember_argument(...))` /
etc. for `<task>.delay(...)` — a fast, non-blocking Redis publish, same
fire-and-forget shape as today, just without the shared-loop risk.

`agents/pipeline.py` needs two specific changes:

- **`_remember_node`**: dispatch via `remember_argument_task.delay(...)`,
  then (to preserve the existing "invalidate cache the moment the write
  lands" behavior) keep wrapping this in `asyncio.create_task(...)` where the
  task body does `await asyncio.to_thread(async_result.get, timeout=...)`
  followed by `invalidate_weakness_cache(user_id)`. This is safe: the thread
  only blocks on Celery's Redis result polling, it never runs a coroutine or
  touches cognee's engine, so it doesn't hit the loop-binding problem this
  design is fixing.
- **`_remember_facts_node`**: same shape as `_remember_node` — dispatch via
  `remember_personal_fact_task.delay(...)` per fact, keep the existing
  `asyncio.create_task(...)` + `asyncio.to_thread(async_result.get, ...)` +
  `invalidate_facts_cache(user_id)` wrapper so cache invalidation still
  happens the moment the write lands.
- **`_mastery_prune_node`**: change from `await forget_pattern(...)` per
  pattern to `forget_pattern_task.delay(...)` per pattern. No retry
  bookkeeping to preserve here — the current code already just logs
  failures and continues (no `state["mastery_events"]` retry tracking left
  to carry over), so this is a direct swap with no behavior change beyond
  no longer blocking the chat turn on the write.

### 4. Error handling

Each Celery task logs its own exceptions (mirroring the existing
`_log_remember_exc` / `_log_finalize_exc` callback pattern) so failures are
still visible in logs; Celery's own retry/backoff can be layered on later if
needed but isn't required for this pass.

## Testing

- Unit: each new Celery task function, called directly (Celery tasks are
  plain callables in tests), asserts it invokes the right `fingerprint.py`
  function with the right arguments.
- Integration: with a real Redis + Celery worker running, dispatch each of
  the four call sites and assert the underlying cognee write lands, and that
  the API process's event loop is not blocked for the duration (e.g. a
  concurrent health-check request completes quickly while a dispatched task
  is still running).
- Regression: `_remember_node`'s cache invalidation still occurs after the
  write completes; `_finalize_session_fingerprint`'s ordering (summary
  before reindex) still holds.
