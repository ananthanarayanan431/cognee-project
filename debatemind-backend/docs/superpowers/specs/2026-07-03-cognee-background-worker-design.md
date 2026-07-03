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
can still freeze the loop for voice users. Four call sites hit this path
today:

| Call site | Function(s) | Current pattern |
|---|---|---|
| `voice_agent/tools.py:418-429,441,545-559,564` | `remember_argument`, `remember_session_summary`, `forget_pattern`, `improve_fingerprint` | `asyncio.create_task(...)`, fire-and-forget |
| `agents/pipeline.py` (`_remember_node`) | `remember_argument` | `asyncio.create_task(...)` + done-callback that also invalidates `_weakness_cache` (`agents/opponent.py`) |
| `agents/pipeline.py` (`_mastery_prune_node`) | `forget_pattern` | `await`ed **inline**, per-pattern try/except with retry-next-turn bookkeeping (`state["mastery_events"]`) — the worst of the four, since it blocks the chat response directly, not just the background |
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

New module `debatemind/cognee/tasks.py` defines Celery tasks that wrap the
existing `fingerprint.py` functions with `asyncio.run(...)` (safe here
because each task runs in a fresh worker process with no pre-existing event
loop or cached engine from another loop):

- `remember_argument_task`
- `remember_session_summary_task`
- `forget_pattern_task`
- `improve_fingerprint_task`
- `finalize_session_fingerprint_task` — wraps the existing ordered
  summary-then-reindex sequence as a single task, preserving the current
  ordering guarantee (splitting into two independent Celery dispatches would
  reintroduce the race the current code comment warns about).

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
- **`_mastery_prune_node`**: change from synchronous `await forget_pattern(...)`
  with per-pattern retry tracking to `forget_pattern_task.delay(...)` per
  pattern, clearing `mastery_events` immediately after dispatch. This is an
  intentional behavior change: today a failed prune is retried on the very
  next graph run via `_should_prune`; after this change, a silently-failed
  Celery task relies on `check_mastery` naturally re-flagging the same
  pattern on some future turn instead of an immediate retry. Accepted
  because it matches how `_remember_node` already treats failures (log and
  move on, no inline retry), and because the alternative (blocking the graph
  on Celery result polling) would reintroduce the exact latency problem
  being removed.

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
