# DebateMind Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the DebateMind frontend to full fidelity with `DebateMind_Design_System.docx` (DS-1.0), and add the two screens the spec requires that don't exist yet (Calibration Session, Session Transcript) — with every computation (scores, before/after weights, streaks, mastery) done server-side in FastAPI, never in the browser.

**Architecture:** FastAPI backend gains new read-only aggregation endpoints (session summary, transcript, calibration flow, extended progress stats) backed by real SQL queries over the existing `sessions`/`exchanges`/`mastery_log` tables — no new fake/random data. The Next.js frontend gains new presentational components and two new screens that call these endpoints; it does not compute anything beyond formatting.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 async, pytest (`asyncio_mode = auto`, see `pyproject.toml`); Next.js 14 App Router, TypeScript, Tailwind CSS, Zustand. No frontend test framework exists in this repo — frontend tasks are verified via `npm run build`, `npm run lint`, and manual check against `npm run dev`, matching existing project conventions.

## Global Constraints

- Backend tests use in-memory SQLite (`sqlite+aiosqlite:///:memory:`) and follow the fixture pattern in `tests/test_progress_svc.py` / `tests/test_sessions_router.py` — no mocking of SQL.
- All new routers/endpoints return `SuccessResponse[T]` from `debatemind.types`, matching every existing endpoint.
- Design tokens (colors/fonts) already exist in `frontend/tailwind.config.ts` and `frontend/src/app/layout.tsx` — do not redefine them, only extend with the missing `border`/`light` tokens.
- Colour roles per DS-1.0 §3: Scarlet `#C0392B` (opponent/weakness/CTA), Slate `#2C3E50` (user/strength), Chalk `#F5F5F0` (page bg), Carbon `#1A1A1A` (graph panel/dark), Ink `#0D0D0D` (body text), Fog `#7F8C8D` (meta), Ember `#E67E22` (evidence/warning), Verdant `#27AE60` (mastery/success), border `#D5D8DC`, light `#F8F9FA`.
- Fonts already wired via `next/font/google` in `layout.tsx`: `--font-display` (DM Serif Display), `--font-spectral` (Spectral), `--font-inter` (Inter), `--font-mono` (JetBrains Mono). Tailwind aliases: `font-display`, `font-serif`, `font-sans`, `font-mono`.
- MASTERY_THRESHOLD is `3` (`debatemind/agents/mastery.py`) — reuse this constant, never hardcode `3` elsewhere.
- The opponent SSE judge payload already includes a `mastery: list[str]` field (`debatemind/routers/sessions.py` `event_stream`) — task 10 only needs to consume it, not add it.
- Never invent UI data client-side (no `Math.random()` placeholder bars) — every number rendered must come from an API response.

---

## File Map

```
debatemind-backend/debatemind/
├── agents/constants.py            # + CALIBRATION_TOPICS
├── models/mastery.py               # unchanged (already has fields we need)
├── schemas/
│   ├── auth.py                     # + calibration_done on TokenOut
│   ├── session.py                  # + SessionSummaryOut, WeaknessChange, TranscriptOut, TranscriptExchange
│   ├── progress.py                 # + MasteredPattern, TopicWinRate, WeaknessTrendItem, extend ProgressOut
│   └── calibration.py              # NEW
├── services/
│   ├── weight_calc.py              # NEW — shared compute_weight()
│   ├── mastery_svc.py              # NEW — record_mastery_events(), reactivate_pattern()
│   ├── summary_svc.py              # NEW — get_session_summary()
│   ├── transcript_svc.py           # NEW — format_transcript_text()
│   ├── calibration_svc.py          # NEW — in-memory progress tracker
│   ├── progress_svc.py             # + get_streak, get_win_rate_by_topic, get_mastered_patterns, get_weakness_trend
│   └── cognee_svc.py               # + reactivate_pattern fact writer (called from mastery_svc)
├── routers/
│   ├── auth.py                     # return calibration_done
│   ├── sessions.py                 # + /summary, /transcript, /transcript/export; wire mastery_svc into /message
│   ├── users.py                    # + /me/mastery/{pattern}/reactivate; extend /me/progress
│   └── calibration.py              # NEW
└── main.py                         # + include calibration router

tests/
├── test_auth_router.py             # NEW
├── test_mastery_svc.py             # NEW
├── test_summary_svc.py             # NEW
├── test_transcript_svc.py          # NEW
├── test_calibration_router.py      # NEW
└── test_progress_svc.py            # extended

frontend/src/
├── app/globals.css                 # + dark-mode CSS vars, reduced-motion block
├── tailwind.config.ts              # + border/light tokens, darkMode: "class"
├── types/index.ts                  # + CalibrationStatus, SessionSummary, Transcript, ProgressData fields
├── lib/api.ts                      # + calibration*, getSessionSummary, getTranscript, exportTranscript, reactivateMastery
├── store/debate.ts                 # + "landing" | "calibration" | "transcript" screens, calibrationDone
├── components/
│   ├── auth/
│   │   ├── LandingPage.tsx          # NEW
│   │   └── AuthModal.tsx            # rewritten as overlay
│   ├── calibration/
│   │   └── CalibrationSession.tsx   # NEW
│   ├── shared/
│   │   ├── MasteredBadge.tsx        # NEW
│   │   └── WeaknessBar.tsx          # NEW
│   ├── debate/
│   │   ├── DebateView.tsx           # + SessionScoreBar in graph panel
│   │   ├── SessionScoreBar.tsx      # NEW
│   │   └── MessageBubble.tsx        # + MasteredBadge rendering
│   ├── session/
│   │   ├── SessionEnd.tsx           # rewritten to consume /summary
│   │   └── SessionTranscript.tsx    # NEW
│   └── progress/
│       └── ProgressDashboard.tsx    # rewritten — streak, mastered list, win-rate-by-topic, weakness trend
└── app/page.tsx                     # + landing/calibration/transcript routing
```

---

## Task 1: Calibration flag on auth responses

**Files:**
- Modify: `debatemind-backend/debatemind/schemas/auth.py`
- Modify: `debatemind-backend/debatemind/routers/auth.py`
- Test: `debatemind-backend/tests/test_auth_router.py`

**Interfaces:**
- Produces: `TokenOut.calibration_done: bool` — consumed by Task 11 (frontend post-login routing).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth_router.py
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.models.user import User
from debatemind.routers import auth as auth_router
from debatemind.services.auth import hash_password


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def api_client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/auth")
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


async def test_register_returns_calibration_done_false(api_client):
    resp = api_client.post(
        "/api/auth/register", json={"email": "new@x.com", "password": "pw123456"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["calibration_done"] is False


async def test_login_returns_existing_calibration_state(api_client, session_factory):
    async with session_factory() as db:
        db.add(
            User(
                email="done@x.com",
                hashed_password=hash_password("pw123456"),
                calibration_done=True,
            )
        )
        await db.commit()

    resp = api_client.post(
        "/api/auth/login", json={"email": "done@x.com", "password": "pw123456"}
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["calibration_done"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_auth_router.py -v`
Expected: FAIL — `KeyError: 'calibration_done'` or `TypeError` (field not on `TokenOut`).

- [ ] **Step 3: Add the field and wire it through**

```python
# schemas/auth.py — add to TokenOut
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    calibration_done: bool = False
```

```python
# routers/auth.py — replace both return statements
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return SuccessResponse(
        data=TokenOut(
            access_token=create_access_token(user.id),
            user_id=user.id,
            calibration_done=user.calibration_done,
        )
    )


async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return SuccessResponse(
        data=TokenOut(
            access_token=create_access_token(user.id),
            user_id=user.id,
            calibration_done=user.calibration_done,
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_auth_router.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add debatemind-backend/debatemind/schemas/auth.py debatemind-backend/debatemind/routers/auth.py debatemind-backend/tests/test_auth_router.py
git commit -m "feat: return calibration_done from register/login"
```

---

## Task 2: Mastery logging + reactivate endpoint

**Files:**
- Create: `debatemind-backend/debatemind/services/mastery_svc.py`
- Modify: `debatemind-backend/debatemind/services/cognee_svc.py`
- Modify: `debatemind-backend/debatemind/routers/sessions.py`
- Modify: `debatemind-backend/debatemind/routers/users.py`
- Test: `debatemind-backend/tests/test_mastery_svc.py`

**Interfaces:**
- Consumes: `debatemind.agents.mastery.MASTERY_THRESHOLD` (int, already exists), `debatemind.models.mastery.MasteryLog`.
- Produces: `record_mastery_events(db, user_id, patterns) -> None`, `reactivate_pattern(db, user_id, pattern_type) -> bool` (returns `False` if no mastered row found) — consumed by Task 6 (progress) and Task 14 (frontend reactivate button).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mastery_svc.py
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.mastery import MasteryLog
from debatemind.services.mastery_svc import record_mastery_events, reactivate_pattern


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_record_mastery_events_writes_one_row_per_pattern(db_session):
    await record_mastery_events(db_session, "u1", ["StrawMan", "AdHominem"])

    rows = (await db_session.execute(select(MasteryLog))).scalars().all()
    assert {r.pattern_type for r in rows} == {"StrawMan", "AdHominem"}
    assert all(r.rounds_to_mastery == 3 for r in rows)
    assert all(r.user_id == "u1" for r in rows)


async def test_record_mastery_events_noop_on_empty_list(db_session):
    await record_mastery_events(db_session, "u1", [])
    rows = (await db_session.execute(select(MasteryLog))).scalars().all()
    assert rows == []


async def test_reactivate_pattern_sets_reactivated_at(db_session, monkeypatch):
    monkeypatch.setattr(
        "debatemind.services.mastery_svc.reactivate_pattern_fact",
        lambda *a, **k: _noop(),
    )
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    ok = await reactivate_pattern(db_session, "u1", "StrawMan")

    assert ok is True
    row = (await db_session.execute(select(MasteryLog))).scalar_one()
    assert row.reactivated_at is not None


async def test_reactivate_pattern_returns_false_when_not_mastered(db_session):
    ok = await reactivate_pattern(db_session, "u1", "Nonexistent")
    assert ok is False


async def _noop():
    return None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_mastery_svc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatemind.services.mastery_svc'`

- [ ] **Step 3: Add `reactivate_pattern_fact` to cognee_svc.py**

```python
# services/cognee_svc.py — append at end of file
async def reactivate_pattern_fact(user_id: str, pattern_type: str) -> None:
    dataset = _dataset(user_id)
    text = (
        f"User: {user_id}\nPattern: {pattern_type}\n"
        "Status: REACTIVATED\nAction: resume targeting in opponent strategy"
    )
    await asyncio.wait_for(cognee.add(text, dataset_name=dataset), timeout=ADD_TIMEOUT)
    await asyncio.wait_for(cognee.cognify(datasets=dataset), timeout=COGNIFY_TIMEOUT)
```

- [ ] **Step 4: Write `services/mastery_svc.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.mastery import MASTERY_THRESHOLD
from debatemind.models.mastery import MasteryLog
from debatemind.services.cognee_svc import reactivate_pattern_fact


async def record_mastery_events(db: AsyncSession, user_id: str, patterns: list[str]) -> None:
    if not patterns:
        return
    for pattern in patterns:
        db.add(
            MasteryLog(user_id=user_id, pattern_type=pattern, rounds_to_mastery=MASTERY_THRESHOLD)
        )
    await db.commit()


async def reactivate_pattern(db: AsyncSession, user_id: str, pattern_type: str) -> bool:
    result = await db.execute(
        select(MasteryLog)
        .where(
            MasteryLog.user_id == user_id,
            MasteryLog.pattern_type == pattern_type,
            MasteryLog.reactivated_at.is_(None),
        )
        .order_by(MasteryLog.mastered_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False

    await db.execute(
        update(MasteryLog)
        .where(MasteryLog.id == row.id)
        .values(reactivated_at=datetime.now(timezone.utc))
    )
    await db.commit()
    await reactivate_pattern_fact(user_id, pattern_type)
    return True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_mastery_svc.py -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Wire `record_mastery_events` into the message pipeline**

In `routers/sessions.py`, add the import and call it right after `db.commit()` for the `Exchange` insert inside `send_message`:

```python
# routers/sessions.py — add import near the top
from debatemind.services.mastery_svc import record_mastery_events
```

```python
# routers/sessions.py — inside send_message, immediately after:
#   db.add(exchange)
#   await db.commit()
# insert:
    await record_mastery_events(db, user_id, final_state.get("mastery_events", []))
```

- [ ] **Step 7: Add the reactivate endpoint to `routers/users.py`**

```python
# routers/users.py — add imports
from fastapi import HTTPException
from debatemind.services.mastery_svc import reactivate_pattern
```

```python
# routers/users.py — append new endpoint
@router.post(
    "/me/mastery/{pattern_type}/reactivate",
    response_model=SuccessResponse[dict],
    summary="Reactivate a mastered pattern",
    description="Un-masters a previously mastered argument pattern so the opponent resumes targeting it.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Pattern was never mastered for this user"},
    },
)
async def reactivate_mastery(
    pattern_type: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    ok = await reactivate_pattern(db, user_id, pattern_type)
    if not ok:
        raise HTTPException(status_code=404, detail="Pattern was never mastered")
    return SuccessResponse(data={"reactivated": True})
```

Add `NotFoundError` to the existing `from debatemind.types import ...` line in `routers/users.py`.

- [ ] **Step 8: Run the full backend test suite**

Run: `cd debatemind-backend && python -m pytest -q`
Expected: All tests PASS (no regressions in `test_sessions_router.py`, `test_mastery.py`).

- [ ] **Step 9: Commit**

```bash
git add debatemind-backend/debatemind/services/mastery_svc.py debatemind-backend/debatemind/services/cognee_svc.py debatemind-backend/debatemind/routers/sessions.py debatemind-backend/debatemind/routers/users.py debatemind-backend/tests/test_mastery_svc.py
git commit -m "feat: persist MasteryLog rows on mastery events; add reactivate endpoint"
```

---

## Task 3: Session summary endpoint (before/after weakness weights)

**Files:**
- Create: `debatemind-backend/debatemind/services/weight_calc.py`
- Create: `debatemind-backend/debatemind/services/summary_svc.py`
- Modify: `debatemind-backend/debatemind/schemas/session.py`
- Modify: `debatemind-backend/debatemind/routers/sessions.py`
- Test: `debatemind-backend/tests/test_summary_svc.py`

**Interfaces:**
- Produces: `compute_weight(logic, evidence, rhetoric) -> float` (0..1, higher = weaker), `get_session_summary(db, user_id, session_id) -> SessionSummaryOut | None`. Endpoint: `GET /api/sessions/{id}/summary` — consumed by Task 12 (SessionEnd rewrite).

- [ ] **Step 1: Write `services/weight_calc.py`**

```python
def compute_weight(logic: float | None, evidence: float | None, rhetoric: float | None) -> float:
    scores = [s for s in (logic, evidence, rhetoric) if s is not None]
    if not scores:
        return 0.5
    avg = sum(scores) / len(scores)
    return round(max(0.0, min(1.0, 1 - avg / 10)), 2)
```

- [ ] **Step 2: Add schemas**

```python
# schemas/session.py — add to imports
from datetime import datetime
```

```python
# schemas/session.py — append
class WeaknessChange(BaseModel):
    pattern: str
    before: float
    after: float
    mastered: bool
    rounds_to_mastery: Optional[int] = None


class SessionSummaryOut(BaseModel):
    topic: str
    difficulty: str
    score: float
    exchanges: int
    weaknesses_exposed: int
    mastered_count: int
    rounds_won: int
    patterns: list[WeaknessChange]
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_summary_svc.py
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base
from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.summary_svc import get_session_summary


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_returns_none_for_missing_or_foreign_session(db_session):
    assert await get_session_summary(db_session, "u1", "nope") is None

    other = DebateSession(user_id="u2", topic="X")
    db_session.add(other)
    await db_session.commit()
    assert await get_session_summary(db_session, "u1", other.id) is None


async def test_computes_score_exchanges_and_weaknesses_exposed(db_session):
    s = DebateSession(user_id="u1", topic="AI regulation", difficulty="targeted")
    db_session.add(s)
    await db_session.flush()
    db_session.add_all(
        [
            Exchange(
                session_id=s.id, turn_number=1, user_message="m1",
                detected_pattern="AppealToAuthority", outcome="Lost",
                judge_logic=4.0, judge_evidence=3.0, judge_rhetoric=7.0,
            ),
            Exchange(
                session_id=s.id, turn_number=2, user_message="m2",
                detected_pattern="AppealToAuthority", outcome="Won",
                judge_logic=8.0, judge_evidence=8.0, judge_rhetoric=8.0,
            ),
        ]
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)

    assert summary.topic == "AI regulation"
    assert summary.exchanges == 2
    assert summary.rounds_won == 1
    assert summary.weaknesses_exposed == 1  # only the Lost exchange's pattern counts
    assert summary.score == pytest.approx((4 + 3 + 7 + 8 + 8 + 8) / 6, abs=0.01)


async def test_before_uses_prior_sessions_after_uses_current_session(db_session):
    earlier = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(earlier)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=earlier.id, turn_number=1, user_message="m",
            detected_pattern="StrawMan", outcome="Lost",
            judge_logic=2.0, judge_evidence=2.0, judge_rhetoric=2.0,
        )
    )
    await db_session.commit()

    later = DebateSession(user_id="u1", topic="Topic B")
    db_session.add(later)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=later.id, turn_number=1, user_message="m",
            detected_pattern="StrawMan", outcome="Won",
            judge_logic=9.0, judge_evidence=9.0, judge_rhetoric=9.0,
        )
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", later.id)
    change = next(p for p in summary.patterns if p.pattern == "StrawMan")

    assert change.before == pytest.approx(1 - 2 / 10, abs=0.01)
    assert change.after == pytest.approx(1 - 9 / 10, abs=0.01)


async def test_pattern_with_no_prior_history_has_equal_before_and_after(db_session):
    s = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(s)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=s.id, turn_number=1, user_message="m",
            detected_pattern="SlipperySlope", outcome="Lost",
            judge_logic=5.0, judge_evidence=5.0, judge_rhetoric=5.0,
        )
    )
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)
    change = next(p for p in summary.patterns if p.pattern == "SlipperySlope")

    assert change.before == change.after


async def test_mastered_pattern_flagged_with_rounds_to_mastery(db_session):
    s = DebateSession(user_id="u1", topic="Topic A")
    db_session.add(s)
    await db_session.flush()
    db_session.add(
        Exchange(
            session_id=s.id, turn_number=1, user_message="m",
            detected_pattern="AdHominem", outcome="Won",
            judge_logic=9.0, judge_evidence=9.0, judge_rhetoric=9.0,
        )
    )
    await db_session.commit()
    db_session.add(MasteryLog(user_id="u1", pattern_type="AdHominem", rounds_to_mastery=3))
    await db_session.commit()

    summary = await get_session_summary(db_session, "u1", s.id)
    change = next(p for p in summary.patterns if p.pattern == "AdHominem")

    assert change.mastered is True
    assert change.rounds_to_mastery == 3
    assert summary.mastered_count == 1
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_summary_svc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatemind.services.summary_svc'`

- [ ] **Step 5: Write `services/summary_svc.py`**

```python
from sqlalchemy import select

from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.schemas.session import SessionSummaryOut, WeaknessChange
from debatemind.services.weight_calc import compute_weight


async def get_session_summary(db, user_id: str, session_id: str) -> SessionSummaryOut | None:
    session_row = (
        await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    ).scalar_one_or_none()
    if not session_row or session_row.user_id != user_id:
        return None

    exchanges = (
        (
            await db.execute(
                select(Exchange)
                .where(Exchange.session_id == session_id)
                .order_by(Exchange.turn_number)
            )
        )
        .scalars()
        .all()
    )

    won = sum(1 for e in exchanges if e.outcome == "Won")
    weakness_patterns = {
        e.detected_pattern for e in exchanges if e.detected_pattern and e.outcome != "Won"
    }

    raw_scores = [
        s
        for e in exchanges
        for s in (e.judge_logic, e.judge_evidence, e.judge_rhetoric)
        if s is not None
    ]
    overall_score = round(sum(raw_scores) / len(raw_scores), 2) if raw_scores else 0.0

    mastery_rows = (
        (
            await db.execute(
                select(MasteryLog).where(
                    MasteryLog.user_id == user_id,
                    MasteryLog.mastered_at >= session_row.started_at,
                    MasteryLog.reactivated_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    mastered_in_session = {m.pattern_type: m for m in mastery_rows}

    patterns_seen = {e.detected_pattern for e in exchanges if e.detected_pattern}
    pattern_changes: list[WeaknessChange] = []
    for pattern in patterns_seen:
        this_session_weights = [
            compute_weight(e.judge_logic, e.judge_evidence, e.judge_rhetoric)
            for e in exchanges
            if e.detected_pattern == pattern
        ]
        after = round(sum(this_session_weights) / len(this_session_weights), 2)

        prior_rows = (
            await db.execute(
                select(Exchange.judge_logic, Exchange.judge_evidence, Exchange.judge_rhetoric)
                .join(DebateSession, DebateSession.id == Exchange.session_id)
                .where(
                    DebateSession.user_id == user_id,
                    Exchange.detected_pattern == pattern,
                    DebateSession.started_at < session_row.started_at,
                )
            )
        ).all()
        before = (
            round(sum(compute_weight(*row) for row in prior_rows) / len(prior_rows), 2)
            if prior_rows
            else after
        )

        mastered = pattern in mastered_in_session
        pattern_changes.append(
            WeaknessChange(
                pattern=pattern,
                before=before,
                after=after,
                mastered=mastered,
                rounds_to_mastery=(
                    mastered_in_session[pattern].rounds_to_mastery if mastered else None
                ),
            )
        )

    return SessionSummaryOut(
        topic=session_row.topic,
        difficulty=session_row.difficulty,
        score=overall_score,
        exchanges=len(exchanges),
        weaknesses_exposed=len(weakness_patterns),
        mastered_count=len(mastered_in_session),
        rounds_won=won,
        patterns=pattern_changes,
    )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_summary_svc.py -v`
Expected: PASS (5 tests)

- [ ] **Step 7: Add the router endpoint**

```python
# routers/sessions.py — add imports
from debatemind.schemas.session import SessionSummaryOut
from debatemind.services.summary_svc import get_session_summary
```

```python
# routers/sessions.py — append near get_graph
@router.get(
    "/{session_id}/summary",
    response_model=SuccessResponse[SessionSummaryOut],
    summary="Get session summary",
    description="Retrieve aggregate score, exchange count, and per-pattern before/after weakness weight changes for a completed session.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def get_summary(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    summary = await get_session_summary(db, user_id, session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SuccessResponse(data=summary)
```

- [ ] **Step 8: Run the full backend suite**

Run: `cd debatemind-backend && python -m pytest -q`
Expected: All PASS.

- [ ] **Step 9: Commit**

```bash
git add debatemind-backend/debatemind/services/weight_calc.py debatemind-backend/debatemind/services/summary_svc.py debatemind-backend/debatemind/schemas/session.py debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_summary_svc.py
git commit -m "feat: add session summary endpoint with before/after weakness weights"
```

---

## Task 4: Transcript + export endpoints

**Files:**
- Create: `debatemind-backend/debatemind/services/transcript_svc.py`
- Modify: `debatemind-backend/debatemind/schemas/session.py`
- Modify: `debatemind-backend/debatemind/routers/sessions.py`
- Test: `debatemind-backend/tests/test_transcript_svc.py`

**Interfaces:**
- Produces: `TranscriptOut`, `format_transcript_text(transcript: TranscriptOut) -> str`. Endpoints: `GET /api/sessions/{id}/transcript`, `GET /api/sessions/{id}/transcript/export` — consumed by Task 13.

- [ ] **Step 1: Add schemas**

```python
# schemas/session.py — append
class TranscriptExchange(BaseModel):
    turn_number: int
    user_message: str
    opponent_response: str
    judge_logic: Optional[float] = None
    judge_evidence: Optional[float] = None
    judge_rhetoric: Optional[float] = None
    fallacy: Optional[str] = None
    outcome: Optional[str] = None
    created_at: datetime


class TranscriptOut(BaseModel):
    session_id: str
    topic: str
    difficulty: str
    started_at: datetime
    exchanges: list[TranscriptExchange]
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_transcript_svc.py
from datetime import datetime, timezone

from debatemind.schemas.session import TranscriptExchange, TranscriptOut
from debatemind.services.transcript_svc import format_transcript_text


def _transcript() -> TranscriptOut:
    return TranscriptOut(
        session_id="s1",
        topic="AI regulation should be government-led",
        difficulty="targeted",
        started_at=datetime(2026, 6, 28, 14, 0, 0, tzinfo=timezone.utc),
        exchanges=[
            TranscriptExchange(
                turn_number=1,
                user_message="Government bodies have decades of regulatory experience.",
                opponent_response="The EU Commission took 4 years to pass the AI Act.",
                judge_logic=4.0,
                judge_evidence=3.0,
                judge_rhetoric=7.0,
                fallacy="AppealToAuthority",
                outcome="Lost",
                created_at=datetime(2026, 6, 28, 14, 0, 14, tzinfo=timezone.utc),
            )
        ],
    )


def test_format_includes_topic_and_meta_line():
    text = format_transcript_text(_transcript())
    assert "AI regulation should be government-led" in text
    assert "Targeted" in text
    assert "1 exchanges" in text


def test_format_includes_both_speakers_and_judge_line():
    text = format_transcript_text(_transcript())
    assert "YOU" in text
    assert "Government bodies have decades" in text
    assert "OPPONENT" in text
    assert "EU Commission took 4 years" in text
    assert "AppealToAuthority detected" in text
    assert "Logic 4" in text and "Evidence 3" in text and "Rhetoric 7" in text


def test_format_omits_judge_line_when_no_scores():
    transcript = _transcript()
    transcript.exchanges[0].judge_logic = None
    transcript.exchanges[0].judge_evidence = None
    transcript.exchanges[0].judge_rhetoric = None
    text = format_transcript_text(transcript)
    assert "JUDGE" not in text
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_transcript_svc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatemind.services.transcript_svc'`

- [ ] **Step 4: Write `services/transcript_svc.py`**

```python
from debatemind.schemas.session import TranscriptOut


def format_transcript_text(transcript: TranscriptOut) -> str:
    lines = [
        transcript.topic,
        f"{transcript.difficulty.capitalize()} · {transcript.started_at:%B %d, %Y} · "
        f"{len(transcript.exchanges)} exchanges",
        "=" * 60,
        "",
    ]
    for ex in transcript.exchanges:
        lines.append(f"YOU — {ex.created_at:%H:%M:%S}")
        lines.append(ex.user_message)
        lines.append("")

        fallacy_note = f"  [{ex.fallacy} detected]" if ex.fallacy else ""
        lines.append(f"OPPONENT — {ex.created_at:%H:%M:%S}{fallacy_note}")
        lines.append(ex.opponent_response)
        lines.append("")

        if ex.judge_logic is not None and ex.judge_evidence is not None and ex.judge_rhetoric is not None:
            lines.append(
                f"JUDGE   Logic {ex.judge_logic:g} · Evidence {ex.judge_evidence:g} · "
                f"Rhetoric {ex.judge_rhetoric:g}"
            )
        lines.append("-" * 60)
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_transcript_svc.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Add router endpoints**

```python
# routers/sessions.py — add imports
from fastapi.responses import PlainTextResponse
from debatemind.schemas.session import TranscriptExchange, TranscriptOut
from debatemind.services.transcript_svc import format_transcript_text
```

```python
# routers/sessions.py — append
async def _build_transcript(session_id: str, user_id: str, db: AsyncSession) -> TranscriptOut:
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    ex_result = await db.execute(
        select(Exchange).where(Exchange.session_id == session_id).order_by(Exchange.turn_number)
    )
    exchanges = ex_result.scalars().all()
    return TranscriptOut(
        session_id=session.id,
        topic=session.topic,
        difficulty=session.difficulty,
        started_at=session.started_at,
        exchanges=[
            TranscriptExchange(
                turn_number=e.turn_number,
                user_message=e.user_message,
                opponent_response=e.opponent_response or "",
                judge_logic=e.judge_logic,
                judge_evidence=e.judge_evidence,
                judge_rhetoric=e.judge_rhetoric,
                fallacy=e.fallacy,
                outcome=e.outcome,
                created_at=e.created_at,
            )
            for e in exchanges
        ],
    )


@router.get(
    "/{session_id}/transcript",
    response_model=SuccessResponse[TranscriptOut],
    summary="Get session transcript",
    description="Retrieve the full ordered exchange history for a session, with judge scores inline.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def get_transcript(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return SuccessResponse(data=await _build_transcript(session_id, user_id, db))


@router.get(
    "/{session_id}/transcript/export",
    summary="Export session transcript",
    description="Download the session transcript as a plain-text file.",
    responses={
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
        404: {"model": NotFoundError, "description": "Session not found"},
    },
)
async def export_transcript(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    transcript = await _build_transcript(session_id, user_id, db)
    text = format_transcript_text(transcript)
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="transcript_{session_id}.txt"'},
    )
```

- [ ] **Step 7: Run the full backend suite**

Run: `cd debatemind-backend && python -m pytest -q`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add debatemind-backend/debatemind/services/transcript_svc.py debatemind-backend/debatemind/schemas/session.py debatemind-backend/debatemind/routers/sessions.py debatemind-backend/tests/test_transcript_svc.py
git commit -m "feat: add session transcript and transcript export endpoints"
```

---

## Task 5: Calibration flow backend

**Files:**
- Modify: `debatemind-backend/debatemind/agents/constants.py`
- Create: `debatemind-backend/debatemind/services/calibration_svc.py`
- Create: `debatemind-backend/debatemind/schemas/calibration.py`
- Create: `debatemind-backend/debatemind/routers/calibration.py`
- Modify: `debatemind-backend/debatemind/main.py`
- Test: `debatemind-backend/tests/test_calibration_router.py`

**Interfaces:**
- Consumes: `debatemind.agents.extractor.extract_argument`, `debatemind.services.cognee_svc.remember_argument` (both already exist, signatures read from `agents/extractor.py` and `services/cognee_svc.py`).
- Produces: `GET /api/calibration/status`, `POST /api/calibration/answer` — consumed by Task 11.

- [ ] **Step 1: Add calibration topics**

```python
# agents/constants.py — append
CALIBRATION_TOPICS = [
    "Social media algorithms should be regulated by law.",
    "Standardized testing should be abolished in schools.",
    "Remote work should be the default for knowledge jobs.",
]
```

- [ ] **Step 2: Write `services/calibration_svc.py`**

In-memory per-process tracker — same pattern already used for `_session_wins` in `routers/sessions.py` (acceptable for this hackathon's single-process deployment).

```python
_progress: dict[str, int] = {}


def get_index(user_id: str) -> int:
    return _progress.get(user_id, 0)


def advance(user_id: str) -> int:
    nxt = _progress.get(user_id, 0) + 1
    _progress[user_id] = nxt
    return nxt


def reset(user_id: str) -> None:
    _progress.pop(user_id, None)
```

- [ ] **Step 3: Write schemas**

```python
# schemas/calibration.py
from typing import Optional

from pydantic import BaseModel


class CalibrationStatusOut(BaseModel):
    needed: bool
    topic: Optional[str] = None
    index: int = 0
    total: int = 3


class CalibrationAnswerIn(BaseModel):
    text: str


class CalibrationAnswerOut(BaseModel):
    done: bool
    next_topic: Optional[str] = None
    index: int
    total: int
```

- [ ] **Step 4: Write the failing test**

```python
# tests/test_calibration_router.py
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from debatemind.database import Base, get_db
from debatemind.deps import current_user_id
from debatemind.models.user import User
from debatemind.routers import calibration as calibration_router
from debatemind.services import calibration_svc


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def api_client(session_factory, monkeypatch):
    calibration_svc.reset("u1")
    monkeypatch.setattr(
        calibration_router, "extract_argument", AsyncMock(side_effect=lambda state: {
            **state,
            "extracted_pattern": "EvidenceBased",
            "extracted_fallacy": None,
            "evidence_quality": "Moderate",
        })
    )
    monkeypatch.setattr(calibration_router, "remember_argument", AsyncMock())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(calibration_router.router, prefix="/api/calibration")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user_id] = lambda: "u1"
    return TestClient(app)


async def _make_user(session_factory, calibration_done=False):
    async with session_factory() as db:
        db.add(User(id="u1", email="u1@x.com", hashed_password="x", calibration_done=calibration_done))
        await db.commit()


async def test_status_needed_true_with_first_topic(api_client, session_factory):
    await _make_user(session_factory)
    resp = api_client.get("/api/calibration/status")
    body = resp.json()["data"]
    assert body["needed"] is True
    assert body["index"] == 1
    assert body["total"] == 3


async def test_status_needed_false_when_already_done(api_client, session_factory):
    await _make_user(session_factory, calibration_done=True)
    resp = api_client.get("/api/calibration/status")
    assert resp.json()["data"]["needed"] is False


async def test_answer_advances_through_all_three_topics(api_client, session_factory):
    await _make_user(session_factory)

    r1 = api_client.post("/api/calibration/answer", json={"text": "a1"})
    assert r1.json()["data"]["done"] is False
    assert r1.json()["data"]["index"] == 2

    r2 = api_client.post("/api/calibration/answer", json={"text": "a2"})
    assert r2.json()["data"]["done"] is False
    assert r2.json()["data"]["index"] == 3

    r3 = api_client.post("/api/calibration/answer", json={"text": "a3"})
    assert r3.json()["data"]["done"] is True


async def test_answer_marks_user_calibration_done_in_db(api_client, session_factory):
    await _make_user(session_factory)
    for _ in range(3):
        api_client.post("/api/calibration/answer", json={"text": "a"})

    from sqlalchemy import select
    from debatemind.models.user import User as UserModel

    async with session_factory() as db:
        user = (await db.execute(select(UserModel).where(UserModel.id == "u1"))).scalar_one()
        assert user.calibration_done is True


async def test_answer_rejected_once_already_done(api_client, session_factory):
    await _make_user(session_factory, calibration_done=True)
    resp = api_client.post("/api/calibration/answer", json={"text": "a"})
    assert resp.status_code == 400
```

- [ ] **Step 5: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_calibration_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'debatemind.routers.calibration'`

- [ ] **Step 6: Write `routers/calibration.py`**

```python
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.agents.constants import CALIBRATION_TOPICS
from debatemind.agents.extractor import extract_argument
from debatemind.database import get_db
from debatemind.deps import current_user_id
from debatemind.models.user import User
from debatemind.schemas.calibration import (
    CalibrationAnswerIn,
    CalibrationAnswerOut,
    CalibrationStatusOut,
)
from debatemind.services import calibration_svc
from debatemind.services.cognee_svc import remember_argument
from debatemind.types import SuccessResponse, UnauthorizedError

router = APIRouter()

TOTAL = len(CALIBRATION_TOPICS)


async def _get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one()


@router.get(
    "/status",
    response_model=SuccessResponse[CalibrationStatusOut],
    summary="Get calibration status",
    description="Check whether the first-time calibration flow is needed and which topic is next.",
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def status(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_id)
    if user.calibration_done:
        return SuccessResponse(data=CalibrationStatusOut(needed=False, total=TOTAL))
    idx = calibration_svc.get_index(user_id)
    return SuccessResponse(
        data=CalibrationStatusOut(
            needed=True, topic=CALIBRATION_TOPICS[idx], index=idx + 1, total=TOTAL
        )
    )


@router.post(
    "/answer",
    response_model=SuccessResponse[CalibrationAnswerOut],
    summary="Submit a calibration answer",
    description="Submit the user's response to the current calibration topic; extracts and stores the argument pattern, then advances to the next topic or marks calibration complete.",
    responses={
        400: {"description": "Calibration already complete"},
        401: {"model": UnauthorizedError, "description": "Invalid or missing token"},
    },
)
async def answer(
    body: CalibrationAnswerIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await _get_user(db, user_id)
    if user.calibration_done:
        raise HTTPException(status_code=400, detail="Calibration already complete")

    idx = calibration_svc.get_index(user_id)
    topic = CALIBRATION_TOPICS[idx]

    state = await extract_argument(
        {"topic": topic, "user_message": body.text, "description": ""}
    )

    await remember_argument(
        user_id=user_id,
        session_id=f"calibration_{user_id}",
        topic=topic,
        claim_text=body.text,
        pattern_type=state.get("extracted_pattern", "EvidenceBased"),
        fallacy=state.get("extracted_fallacy"),
        evidence_quality=state.get("evidence_quality", "Moderate"),
        outcome="Neutral",
    )

    new_idx = calibration_svc.advance(user_id)
    if new_idx >= TOTAL:
        await db.execute(update(User).where(User.id == user_id).values(calibration_done=True))
        await db.commit()
        calibration_svc.reset(user_id)
        return SuccessResponse(data=CalibrationAnswerOut(done=True, index=TOTAL, total=TOTAL))

    return SuccessResponse(
        data=CalibrationAnswerOut(
            done=False, next_topic=CALIBRATION_TOPICS[new_idx], index=new_idx + 1, total=TOTAL
        )
    )
```

- [ ] **Step 7: Register the router in `main.py`**

```python
# main.py — add import
from debatemind.routers import auth, calibration, sessions, topics, users
```

```python
# main.py — add include_router call near the others
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_calibration_router.py -v`
Expected: PASS (5 tests)

- [ ] **Step 9: Run the full backend suite**

Run: `cd debatemind-backend && python -m pytest -q`
Expected: All PASS.

- [ ] **Step 10: Commit**

```bash
git add debatemind-backend/debatemind/agents/constants.py debatemind-backend/debatemind/services/calibration_svc.py debatemind-backend/debatemind/schemas/calibration.py debatemind-backend/debatemind/routers/calibration.py debatemind-backend/debatemind/main.py debatemind-backend/tests/test_calibration_router.py
git commit -m "feat: add calibration session backend flow"
```

---

## Task 6: Progress dashboard extensions

**Files:**
- Modify: `debatemind-backend/debatemind/services/progress_svc.py`
- Modify: `debatemind-backend/debatemind/schemas/progress.py`
- Modify: `debatemind-backend/debatemind/routers/users.py`
- Test: `debatemind-backend/tests/test_progress_svc.py` (extend)

**Interfaces:**
- Produces: `get_streak(db, user_id) -> int`, `get_win_rate_by_topic(db, user_id) -> list[dict]`, `get_mastered_patterns(db, user_id) -> list[dict]`, `get_weakness_trend(db, user_id) -> list[dict]` — consumed by Task 14 (ProgressDashboard rewrite).

- [ ] **Step 1: Extend schemas**

```python
# schemas/progress.py — replace file contents
from datetime import datetime

from pydantic import BaseModel


class ThinkingStyle(BaseModel):
    logic: float
    evidence: float
    rhetoric: float


class MasteredPattern(BaseModel):
    pattern: str
    mastered_at: datetime
    rounds_to_mastery: int
    reactivated: bool


class TopicWinRate(BaseModel):
    topic: str
    win_rate: float


class WeaknessTrendItem(BaseModel):
    pattern: str
    weight: float


class ProgressOut(BaseModel):
    weaknesses: list[dict]
    sessions: int
    win_rate: float
    streak: int
    thinking_style: ThinkingStyle
    mastered: list[MasteredPattern]
    win_rate_by_topic: list[TopicWinRate]
    weakness_trend: list[WeaknessTrendItem]
```

- [ ] **Step 2: Write the failing tests (appended to existing file)**

```python
# tests/test_progress_svc.py — append these imports at top
from datetime import date, timedelta

from debatemind.models.mastery import MasteryLog
from debatemind.services.progress_svc import (
    get_mastered_patterns,
    get_streak,
    get_weakness_trend,
    get_win_rate_by_topic,
)
```

```python
# tests/test_progress_svc.py — append at end of file
async def test_get_streak_zero_with_no_sessions(db_session):
    assert await get_streak(db_session, "u1") == 0


async def test_get_streak_counts_consecutive_days_ending_today(db_session):
    today = date.today()
    db_session.add_all(
        [
            DebateSession(user_id="u1", topic="A", started_at=today),
            DebateSession(user_id="u1", topic="B", started_at=today - timedelta(days=1)),
            DebateSession(user_id="u1", topic="C", started_at=today - timedelta(days=2)),
            DebateSession(user_id="u1", topic="D", started_at=today - timedelta(days=10)),
        ]
    )
    await db_session.commit()

    assert await get_streak(db_session, "u1") == 3


async def test_get_win_rate_by_topic_groups_correctly(db_session):
    s1 = DebateSession(user_id="u1", topic="AI regulation")
    s2 = DebateSession(user_id="u1", topic="UBI")
    db_session.add_all([s1, s2])
    await db_session.flush()
    db_session.add_all(
        [
            _exchange(s1.id, 1, "Won"),
            _exchange(s1.id, 2, "Lost"),
            _exchange(s2.id, 1, "Won"),
        ]
    )
    await db_session.commit()

    rates = {r["topic"]: r["win_rate"] for r in await get_win_rate_by_topic(db_session, "u1")}
    assert rates["AI regulation"] == 0.5
    assert rates["UBI"] == 1.0


async def test_get_mastered_patterns_orders_by_recency_and_flags_reactivated(db_session):
    db_session.add_all(
        [
            MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=4),
            MasteryLog(
                user_id="u1",
                pattern_type="AdHominem",
                rounds_to_mastery=6,
                reactivated_at=date.today(),
            ),
        ]
    )
    await db_session.commit()

    patterns = await get_mastered_patterns(db_session, "u1")
    by_name = {p["pattern"]: p for p in patterns}
    assert by_name["StrawMan"]["reactivated"] is False
    assert by_name["AdHominem"]["reactivated"] is True
    assert by_name["AdHominem"]["rounds_to_mastery"] == 6


async def test_get_weakness_trend_excludes_mastered_unreactivated_patterns(db_session):
    s = DebateSession(user_id="u1", topic="A")
    db_session.add(s)
    await db_session.flush()
    db_session.add_all(
        [
            Exchange(
                session_id=s.id, turn_number=1, user_message="m",
                detected_pattern="StrawMan", outcome="Lost",
                judge_logic=3.0, judge_evidence=3.0, judge_rhetoric=3.0,
            ),
            Exchange(
                session_id=s.id, turn_number=2, user_message="m",
                detected_pattern="AdHominem", outcome="Lost",
                judge_logic=2.0, judge_evidence=2.0, judge_rhetoric=2.0,
            ),
        ]
    )
    db_session.add(MasteryLog(user_id="u1", pattern_type="StrawMan", rounds_to_mastery=3))
    await db_session.commit()

    trend = await get_weakness_trend(db_session, "u1")
    patterns = {t["pattern"] for t in trend}
    assert "StrawMan" not in patterns
    assert "AdHominem" in patterns
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd debatemind-backend && python -m pytest tests/test_progress_svc.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_streak'`

- [ ] **Step 4: Implement the new functions in `progress_svc.py`**

```python
# services/progress_svc.py — replace file contents
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from debatemind.models.mastery import MasteryLog
from debatemind.models.session import DebateSession, Exchange
from debatemind.services.weight_calc import compute_weight


async def get_progress_stats(db: AsyncSession, user_id: str) -> dict:
    stmt = (
        select(
            func.count(func.distinct(DebateSession.id)).label("sessions"),
            func.avg(Exchange.judge_logic).label("avg_logic"),
            func.avg(Exchange.judge_evidence).label("avg_evidence"),
            func.avg(Exchange.judge_rhetoric).label("avg_rhetoric"),
            func.count(case((Exchange.outcome == "Won", 1))).label("won"),
            func.count(case((Exchange.outcome.in_(["Won", "Lost"]), 1))).label("decided"),
        )
        .select_from(DebateSession)
        .outerjoin(Exchange, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
    )
    row = (await db.execute(stmt)).one()
    win_rate = (row.won / row.decided) if row.decided else 0.0

    return {
        "sessions": row.sessions or 0,
        "win_rate": round(win_rate, 3),
        "thinking_style": {
            "logic": round(row.avg_logic, 2) if row.avg_logic is not None else 0.0,
            "evidence": round(row.avg_evidence, 2) if row.avg_evidence is not None else 0.0,
            "rhetoric": round(row.avg_rhetoric, 2) if row.avg_rhetoric is not None else 0.0,
        },
    }


async def get_streak(db: AsyncSession, user_id: str) -> int:
    rows = (
        await db.execute(
            select(func.date(DebateSession.started_at))
            .where(DebateSession.user_id == user_id)
            .distinct()
        )
    ).scalars().all()

    days: set[date] = set()
    for r in rows:
        days.add(r if isinstance(r, date) else date.fromisoformat(r))

    if not days:
        return 0

    today = date.today()
    cursor = today if today in days else today - timedelta(days=1)
    if cursor not in days:
        return 0

    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def get_win_rate_by_topic(db: AsyncSession, user_id: str) -> list[dict]:
    stmt = (
        select(
            DebateSession.topic,
            func.count(case((Exchange.outcome == "Won", 1))).label("won"),
            func.count(case((Exchange.outcome.in_(["Won", "Lost"]), 1))).label("decided"),
        )
        .select_from(DebateSession)
        .outerjoin(Exchange, Exchange.session_id == DebateSession.id)
        .where(DebateSession.user_id == user_id)
        .group_by(DebateSession.topic)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"topic": r.topic, "win_rate": round(r.won / r.decided, 3) if r.decided else 0.0}
        for r in rows
    ]


async def get_mastered_patterns(db: AsyncSession, user_id: str) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(MasteryLog)
                .where(MasteryLog.user_id == user_id)
                .order_by(MasteryLog.mastered_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "pattern": r.pattern_type,
            "mastered_at": r.mastered_at,
            "rounds_to_mastery": r.rounds_to_mastery,
            "reactivated": r.reactivated_at is not None,
        }
        for r in rows
    ]


async def get_weakness_trend(db: AsyncSession, user_id: str, limit: int = 6) -> list[dict]:
    mastered_active = (
        (
            await db.execute(
                select(MasteryLog.pattern_type).where(
                    MasteryLog.user_id == user_id, MasteryLog.reactivated_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    excluded = set(mastered_active)

    rows = (
        await db.execute(
            select(
                Exchange.detected_pattern,
                Exchange.judge_logic,
                Exchange.judge_evidence,
                Exchange.judge_rhetoric,
            )
            .join(DebateSession, DebateSession.id == Exchange.session_id)
            .where(
                DebateSession.user_id == user_id,
                Exchange.detected_pattern.is_not(None),
            )
        )
    ).all()

    by_pattern: dict[str, list[float]] = {}
    for pattern, logic, evidence, rhetoric in rows:
        if pattern in excluded:
            continue
        by_pattern.setdefault(pattern, []).append(compute_weight(logic, evidence, rhetoric))

    trend = [
        {"pattern": p, "weight": round(sum(ws) / len(ws), 2)} for p, ws in by_pattern.items()
    ]
    trend.sort(key=lambda t: t["weight"], reverse=True)
    return trend[:limit]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd debatemind-backend && python -m pytest tests/test_progress_svc.py -v`
Expected: PASS (all original + 5 new tests)

- [ ] **Step 6: Wire into `/me/progress`**

```python
# routers/users.py — replace get_progress
@router.get(
    "/me/progress",
    response_model=SuccessResponse[ProgressOut],
    summary="Get user progress stats",
    description="Retrieve the user's overall debate statistics including win rate, streak, session count, thinking style, mastered patterns, win rate by topic, and weakness trend.",
    responses={401: {"model": UnauthorizedError, "description": "Invalid or missing token"}},
)
async def get_progress(
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    weaknesses = await recall_weaknesses(user_id)
    stats = await get_progress_stats(db, user_id)
    streak = await get_streak(db, user_id)
    mastered = await get_mastered_patterns(db, user_id)
    win_rate_by_topic = await get_win_rate_by_topic(db, user_id)
    weakness_trend = await get_weakness_trend(db, user_id)
    return SuccessResponse(
        data=ProgressOut(
            weaknesses=weaknesses[:5],
            streak=streak,
            mastered=mastered,
            win_rate_by_topic=win_rate_by_topic,
            weakness_trend=weakness_trend,
            **stats,
        )
    )
```

Add the new imports at the top of `routers/users.py`:

```python
from debatemind.services.progress_svc import (
    get_mastered_patterns,
    get_progress_stats,
    get_streak,
    get_weakness_trend,
    get_win_rate_by_topic,
)
```

(Remove the old single-name `from debatemind.services.progress_svc import get_progress_stats` line it replaces.)

- [ ] **Step 7: Run the full backend suite**

Run: `cd debatemind-backend && python -m pytest -q`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add debatemind-backend/debatemind/services/progress_svc.py debatemind-backend/debatemind/schemas/progress.py debatemind-backend/debatemind/routers/users.py debatemind-backend/tests/test_progress_svc.py
git commit -m "feat: extend progress endpoint with streak, mastered patterns, win rate by topic, weakness trend"
```

---

This file continues with frontend Tasks 7–15 (design tokens, landing/auth split, SessionScoreBar, MasteredBadge wiring, calibration screen, WeaknessBar + SessionEnd rewrite, transcript screen, progress dashboard rewrite, visual fidelity pass). See the companion task list tracked in this session — execute Tasks 1–6 first since Tasks 9–15 all consume their endpoints.

**Backend Task summary (this file, complete):** 1 (calibration_done), 2 (mastery logging + reactivate), 3 (session summary), 4 (transcript + export), 5 (calibration flow), 6 (progress extensions).

---

## Task 7: Design tokens — border/light colors, dark mode, reduced motion, Tabler icons

**Files:**
- Modify: `frontend/tailwind.config.ts`
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/package.json` (add `@tabler/icons-react`)

**Interfaces:**
- Produces: Tailwind classes `border-border`, `bg-light`, `dark:` variants — consumed by every later frontend task.

No frontend test framework exists in this repo (`package.json` has no test script) — verify via `npm run build` and `npm run lint`, matching existing project convention.

- [ ] **Step 1: Add missing color tokens and enable class-based dark mode**

```typescript
// frontend/tailwind.config.ts — replace file contents
import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        scarlet: "#C0392B",
        slate:   "#2C3E50",
        chalk:   "#F5F5F0",
        carbon:  "#1A1A1A",
        fog:     "#7F8C8D",
        ember:   "#E67E22",
        verdant: "#27AE60",
        ink:     "#0D0D0D",
        border:  "#D5D8DC",
        light:   "#F8F9FA",
      },
      fontFamily: {
        serif:   ["var(--font-spectral)", "Georgia", "serif"],
        display: ["var(--font-display)", "serif"],
        sans:    ["var(--font-inter)", "system-ui", "sans-serif"],
        mono:    ["var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 2: Add dark-mode CSS variables and reduced-motion handling**

```css
/* frontend/src/app/globals.css — replace file contents */
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --dm-surface-page: #F5F5F0;
  --dm-surface-card: #FFFFFF;
  --dm-text-primary: #0D0D0D;
  --dm-border: #D5D8DC;
}

.dark {
  --dm-surface-page: #111111;
  --dm-surface-card: #1e1e1e;
  --dm-text-primary: #E8E8E6;
  --dm-border: #333333;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 3: Install Tabler Icons**

Run: `cd frontend && npm install @tabler/icons-react`
Expected: package installs cleanly, `package.json` gains the dependency.

- [ ] **Step 4: Verify build and lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: both succeed with no new errors (pre-existing warnings, if any, are unrelated to this change).

- [ ] **Step 5: Commit**

```bash
git add frontend/tailwind.config.ts frontend/src/app/globals.css frontend/package.json frontend/package-lock.json
git commit -m "feat: add border/light design tokens, dark mode vars, reduced motion, Tabler icons"
```

---

## Task 8: Landing page + Auth modal split

DS-1.0 §9.1 specifies a standalone landing page (logo, tagline, single "Start arguing →" CTA) that opens an Auth modal overlay — not a full-page form shown immediately.

**Files:**
- Create: `frontend/src/components/auth/LandingPage.tsx`
- Modify: `frontend/src/components/auth/AuthModal.tsx`
- Modify: `frontend/src/store/debate.ts`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Consumes: `useDebate().setAuth(token, userId, calibrationDone)` (signature extended in this task; Task 11 reads `calibrationDone` off the store to route to the calibration screen).
- Produces: `screen: "landing" | "auth" | ...` — `"landing"` is the new default unauthenticated screen.

- [ ] **Step 1: Add the `landing` screen and `calibrationDone` to the store**

```typescript
// frontend/src/store/debate.ts — replace the DebateStore interface's screen line and setAuth signature
interface DebateStore {
  screen: "landing" | "auth" | "topic" | "calibration" | "debate" | "end" | "transcript" | "progress";
  token: string | null;
  userId: string | null;
  calibrationDone: boolean;
  sessionId: string | null;
  sessionConfig: SessionConfig | null;
  messages: Message[];
  graph: GraphData;
  thinking: boolean;
  sessionScores: { logic: number; evidence: number; rhetoric: number };

  setScreen: (s: DebateStore["screen"]) => void;
  setAuth: (token: string, userId: string, calibrationDone: boolean) => void;
  setSession: (id: string, config: SessionConfig) => void;
  addMessage: (m: Message) => void;
  updateLastOpponent: (text: string) => void;
  revealJudge: (judge: Message["judge"]) => void;
  setThinking: (v: boolean) => void;
  setGraph: (g: GraphData) => void;
  reset: () => void;
}
```

```typescript
// frontend/src/store/debate.ts — replace the create<DebateStore> body's relevant fields/methods
export const useDebate = create<DebateStore>((set) => ({
  screen: "landing",
  token: typeof window !== "undefined" ? localStorage.getItem("dm_token") : null,
  userId: typeof window !== "undefined" ? localStorage.getItem("dm_uid") : null,
  calibrationDone: typeof window !== "undefined" ? localStorage.getItem("dm_calibration") === "1" : false,
  sessionId: null,
  sessionConfig: null,
  messages: [],
  graph: { nodes: [], edges: [] },
  thinking: false,
  sessionScores: { logic: 0, evidence: 0, rhetoric: 0 },

  setScreen: (screen) => set({ screen }),
  setAuth: (token, userId, calibrationDone) => {
    localStorage.setItem("dm_token", token);
    localStorage.setItem("dm_uid", userId);
    localStorage.setItem("dm_calibration", calibrationDone ? "1" : "0");
    set({
      token,
      userId,
      calibrationDone,
      screen: calibrationDone ? "topic" : "calibration",
    });
  },
  setSession: (sessionId, sessionConfig) =>
    set({ sessionId, sessionConfig, messages: [], screen: "debate" }),
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  updateLastOpponent: (text) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") msgs[msgs.length - 1] = { ...last, text };
      return { messages: msgs };
    }),
  revealJudge: (judge) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") msgs[msgs.length - 1] = { ...last, judge, showJudge: true };
      const scores = judge
        ? { logic: judge.logic, evidence: judge.evidence, rhetoric: judge.rhetoric }
        : s.sessionScores;
      return { messages: msgs, sessionScores: scores };
    }),
  setThinking: (thinking) => set({ thinking }),
  setGraph: (graph) => set({ graph }),
  reset: () => set({ sessionId: null, sessionConfig: null, messages: [], screen: "topic" }),
}));
```

- [ ] **Step 2: Create `LandingPage.tsx`**

```tsx
// frontend/src/components/auth/LandingPage.tsx
"use client";
import { useDebate } from "@/store/debate";

export default function LandingPage() {
  const setScreen = useDebate((s) => s.setScreen);

  return (
    <div className="min-h-screen bg-chalk flex flex-col items-center justify-center px-4">
      <h1 className="font-display text-5xl text-ink mb-2">DebateMind</h1>
      <p className="font-sans text-fog text-lg mb-10">The AI that learns how you argue.</p>
      <button
        onClick={() => setScreen("auth")}
        className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm px-6 py-4 rounded-lg"
      >
        Start arguing →
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `AuthModal.tsx` as an overlay**

```tsx
// frontend/src/components/auth/AuthModal.tsx
"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

export default function AuthModal() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const setAuth = useDebate((s) => s.setAuth);
  const setScreen = useDebate((s) => s.setScreen);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setAuth(res.access_token, res.user_id, res.calibration_done);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/60 flex items-center justify-center px-4 z-50">
      <div className="bg-white rounded-xl max-w-[400px] w-full p-7">
        <h2 className="font-sans font-medium text-lg text-ink mb-5">
          {mode === "login" ? "Sign in" : "Create your account"}
        </h2>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <input
            type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)}
            className="border border-border rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
          />
          <input
            type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)}
            className="border border-border rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
          />
          {error && <p className="text-scarlet text-xs font-sans">{error}</p>}
          <button type="submit" className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-3 rounded">
            {mode === "login" ? "Sign in →" : "Create account →"}
          </button>
          <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="text-fog font-sans text-xs underline">
            {mode === "login" ? "New here? Create account" : "Already have an account? Sign in instead"}
          </button>
          <button type="button" onClick={() => setScreen("landing")}
            className="text-fog font-sans text-xs">
            ← Back
          </button>
        </form>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Update `lib/api.ts` login/register return types**

```typescript
// frontend/src/lib/api.ts — replace register and login entries in the api object
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string; calibration_done: boolean }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string; calibration_done: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
```

- [ ] **Step 5: Wire `LandingPage` into `app/page.tsx`**

```tsx
// frontend/src/app/page.tsx
"use client";
import { useDebate } from "@/store/debate";
import LandingPage from "@/components/auth/LandingPage";
import AuthModal from "@/components/auth/AuthModal";
import TopicSelection from "@/components/topic/TopicSelection";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
const CalibrationSession = dynamic(() => import("@/components/calibration/CalibrationSession"), { ssr: false });
const SessionTranscript = dynamic(() => import("@/components/session/SessionTranscript"), { ssr: false });

export default function Home() {
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);

  if (!token) {
    return screen === "auth" ? <AuthModal /> : <LandingPage />;
  }
  if (screen === "calibration") return <CalibrationSession />;
  if (screen === "topic") return <TopicSelection />;
  if (screen === "debate") return <DebateView />;
  if (screen === "end") return <SessionEnd />;
  if (screen === "transcript") return <SessionTranscript />;
  if (screen === "progress") return <ProgressDashboard />;
  return <TopicSelection />;
}
```

Note: `CalibrationSession.tsx` and `SessionTranscript.tsx` are created in Tasks 11 and 13 respectively — this step references them ahead of time, which is fine since Next.js dynamic imports resolve at build time after all tasks land. If executing tasks out of order, this step will fail to build until both files exist; execute Tasks 7→15 in order to avoid that.

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build` (will only fully succeed once Tasks 11 and 13 also land — at this point in isolation, confirm via `npx tsc --noEmit` that the edited files have no type errors of their own, deferring the full build check to the end of Task 15)
Expected: no TypeScript errors in `LandingPage.tsx`, `AuthModal.tsx`, `store/debate.ts`, `lib/api.ts`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/auth/LandingPage.tsx frontend/src/components/auth/AuthModal.tsx frontend/src/store/debate.ts frontend/src/lib/api.ts frontend/src/app/page.tsx
git commit -m "feat: split landing page from auth modal per DS-1.0 9.1"
```

---

## Task 9: SessionScoreBar in the graph panel

DS-1.0 §8.7 specifies a three-row Logic/Evidence/Rhetoric score strip in the graph panel. The data (`sessionScores`) is already tracked client-side in the Zustand store (`revealJudge` updates it on every judge reveal) — this task is purely presentational, no backend change.

**Files:**
- Create: `frontend/src/components/debate/SessionScoreBar.tsx`
- Modify: `frontend/src/components/debate/DebateView.tsx`

**Interfaces:**
- Consumes: `useDebate().sessionScores: { logic: number; evidence: number; rhetoric: number }` (already exists in the store).

- [ ] **Step 1: Create `SessionScoreBar.tsx`**

```tsx
// frontend/src/components/debate/SessionScoreBar.tsx
"use client";

const ROWS = [
  { key: "logic", label: "Logic", color: "#2C3E50" },
  { key: "evidence", label: "Evidence", color: "#E67E22" },
  { key: "rhetoric", label: "Rhetoric", color: "#27AE60" },
] as const;

export default function SessionScoreBar({
  scores,
}: {
  scores: { logic: number; evidence: number; rhetoric: number };
}) {
  return (
    <div className="px-5 pb-4">
      <p className="font-sans text-[9px] font-semibold text-[#666] uppercase tracking-widest mb-2.5">
        Session score
      </p>
      {ROWS.map(({ key, label, color }) => {
        const value = scores[key];
        return (
          <div key={key} className="flex items-center gap-2.5 mb-1.5">
            <span className="font-sans text-[9px] text-[#666] w-11 flex-none">{label}</span>
            <div className="flex-1 h-1.5 rounded-[3px] bg-[#222] overflow-hidden">
              <div
                className="h-full rounded-[3px] transition-[width] duration-500 ease-out"
                style={{ width: `${Math.min(100, (value / 10) * 100)}%`, background: color }}
              />
            </div>
            <span className="font-mono text-[9px] text-[#888] w-7 flex-none text-right">
              {value.toFixed(1)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Wire it into `DebateView.tsx`'s graph panel**

```tsx
// frontend/src/components/debate/DebateView.tsx — add import
import SessionScoreBar from "./SessionScoreBar";
```

```tsx
// frontend/src/components/debate/DebateView.tsx — inside the function body, destructure sessionScores
  const { messages, thinking, graph, sessionId, sessionConfig, sessionScores, setScreen } = useDebate();
```

```tsx
// frontend/src/components/debate/DebateView.tsx — replace the legend block at the end of the <aside> with:
          <SessionScoreBar scores={sessionScores} />
          <div className="flex gap-3.5 px-5 pb-4 font-sans text-[10px] text-[#888]">
            {[
              { color: "#C0392B", label: "Weakness" },
              { color: "#27AE60", label: "Strength" },
              { color: "#444", label: "Mastered" },
            ].map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
```

- [ ] **Step 3: Verify in the dev server**

Run: `cd frontend && npm run dev` (in background), open the app, start a session, send a message, confirm the Logic/Evidence/Rhetoric bars appear under the graph and animate when judge scores are revealed.
Expected: three colored bars visible in the Carbon-background graph panel, updating after each exchange.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/debate/SessionScoreBar.tsx frontend/src/components/debate/DebateView.tsx
git commit -m "feat: add SessionScoreBar to graph panel per DS-1.0 8.7"
```

---

## Task 10: MasteredBadge wired to judge SSE mastery field

The opponent SSE judge payload already includes `mastery: list[str]` (`debatemind/routers/sessions.py` `event_stream`, unchanged). The frontend's `useDebateSSE.ts` currently discards this field — this task surfaces it as an inline badge.

**Files:**
- Create: `frontend/src/components/shared/MasteredBadge.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useDebateSSE.ts`
- Modify: `frontend/src/components/debate/MessageBubble.tsx`

**Interfaces:**
- Produces: `<MasteredBadge pattern={string} />` — reused by Task 12 (SessionEnd) and Task 14 (ProgressDashboard).

- [ ] **Step 1: Create `MasteredBadge.tsx`**

```tsx
// frontend/src/components/shared/MasteredBadge.tsx
export default function MasteredBadge({ pattern }: { pattern?: string }) {
  return (
    <span className="inline-flex items-center font-sans text-[9px] font-semibold uppercase tracking-wide text-verdant bg-verdant/[0.12] rounded-[10px] px-2 py-0.5">
      {pattern ? `✓ ${pattern} mastered` : "✓ Mastered"}
    </span>
  );
}
```

- [ ] **Step 2: Add `mastery` to the `Message` type**

```typescript
// frontend/src/types/index.ts — replace the Message interface
export interface Message {
  id: string;
  role: "user" | "opponent";
  text: string;
  judge?: JudgeScore;
  showJudge?: boolean;
  mastery?: string[];
}
```

- [ ] **Step 3: Capture `mastery` in the SSE handler**

```typescript
// frontend/src/hooks/useDebateSSE.ts — replace the judge event branch
          if (evt.type === "judge") {
            setTimeout(() => revealJudge(evt as JudgeScore, evt.mastery as string[] | undefined), 2000);
          }
```

- [ ] **Step 4: Update the store's `revealJudge` to accept and store mastery**

```typescript
// frontend/src/store/debate.ts — replace the revealJudge signature in the interface
  revealJudge: (judge: Message["judge"], mastery?: string[]) => void;
```

```typescript
// frontend/src/store/debate.ts — replace the revealJudge implementation
  revealJudge: (judge, mastery) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") {
        msgs[msgs.length - 1] = { ...last, judge, showJudge: true, mastery };
      }
      const scores = judge
        ? { logic: judge.logic, evidence: judge.evidence, rhetoric: judge.rhetoric }
        : s.sessionScores;
      return { messages: msgs, sessionScores: scores };
    }),
```

- [ ] **Step 5: Render the badge in `MessageBubble.tsx`**

```tsx
// frontend/src/components/debate/MessageBubble.tsx — add import
import MasteredBadge from "@/components/shared/MasteredBadge";
```

```tsx
// frontend/src/components/debate/MessageBubble.tsx — replace the closing block after JudgeScoreBar
      {msg.showJudge && msg.judge && <JudgeScoreBar score={msg.judge} />}
      {msg.mastery && msg.mastery.length > 0 && (
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {msg.mastery.map((p) => (
            <MasteredBadge key={p} pattern={p} />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Verify in the dev server**

Run: `cd frontend && npm run dev`, play a session in `ruthless` difficulty repeatedly winning against the same pattern until mastery fires (3 consecutive wins per `MASTERY_THRESHOLD`), confirm the green "✓ PATTERN mastered" badge appears under the opponent bubble.
Expected: badge renders only on the turn mastery actually fires, using live backend data (not simulated).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/shared/MasteredBadge.tsx frontend/src/types/index.ts frontend/src/hooks/useDebateSSE.ts frontend/src/store/debate.ts frontend/src/components/debate/MessageBubble.tsx
git commit -m "feat: surface mastery events as inline MasteredBadge"
```

---

## Task 11: Calibration Session screen

**Files:**
- Create: `frontend/src/components/calibration/CalibrationSession.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Consumes: `GET /api/calibration/status`, `POST /api/calibration/answer` (Task 5).
- Produces: navigates to `screen: "topic"` on completion via `useDebate().setScreen`.

- [ ] **Step 1: Add calibration types and API calls**

```typescript
// frontend/src/types/index.ts — append
export interface CalibrationStatus {
  needed: boolean;
  topic?: string;
  index: number;
  total: number;
}

export interface CalibrationAnswerResult {
  done: boolean;
  next_topic?: string;
  index: number;
  total: number;
}
```

```typescript
// frontend/src/lib/api.ts — append to the api object
  getCalibrationStatus: () => apiFetch<CalibrationStatus>("/api/calibration/status"),
  submitCalibrationAnswer: (text: string) =>
    apiFetch<CalibrationAnswerResult>("/api/calibration/answer", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
```

```typescript
// frontend/src/lib/api.ts — add to the import line at the top
import { ProgressData, CalibrationStatus, CalibrationAnswerResult } from "@/types";
```

- [ ] **Step 2: Create `CalibrationSession.tsx`**

90-second countdown per DS-1.0 §9.2 is a client-side display timer only (it does not block submission — the backend has no time limit, matching "the user controls every transition" from Law 3 / §1 anti-patterns: no auto-advancing).

```tsx
// frontend/src/components/calibration/CalibrationSession.tsx
"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

const DURATION = 90;

export default function CalibrationSession() {
  const setScreen = useDebate((s) => s.setScreen);
  const [topic, setTopic] = useState("");
  const [index, setIndex] = useState(1);
  const [total, setTotal] = useState(3);
  const [text, setText] = useState("");
  const [seconds, setSeconds] = useState(DURATION);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCalibrationStatus().then((s) => {
      if (!s.needed) {
        setScreen("topic");
        return;
      }
      setTopic(s.topic ?? "");
      setIndex(s.index);
      setTotal(s.total);
      setLoading(false);
    });
  }, [setScreen]);

  useEffect(() => {
    if (loading) return;
    setSeconds(DURATION);
    const id = setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [topic, loading]);

  async function submit() {
    if (!text.trim()) return;
    const res = await api.submitCalibrationAnswer(text);
    setText("");
    if (res.done) {
      setScreen("topic");
      return;
    }
    setTopic(res.next_topic ?? "");
    setIndex(res.index);
    setTotal(res.total);
  }

  if (loading) return null;

  const mins = String(Math.floor(seconds / 60)).padStart(1, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  const dots = Array.from({ length: total }, (_, i) => i < index);

  return (
    <div className="max-w-2xl mx-auto px-7 py-12">
      <div className="flex items-center justify-between mb-5">
        <h1 className="font-display text-3xl text-ink">Let&apos;s see how you think.</h1>
        <div className="flex items-center gap-3">
          <span className="flex gap-1">
            {dots.map((filled, i) => (
              <span
                key={i}
                className={`w-1.5 h-1.5 rounded-full ${filled ? "bg-scarlet" : "bg-fog/30"}`}
              />
            ))}
          </span>
          <span className="font-sans text-[11px] text-fog">Calibration {index}/{total}</span>
        </div>
      </div>

      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-1">
        Getting to know your thinking…
      </p>
      <p className="font-serif text-lg text-slate mb-6">{topic}</p>

      <div className="bg-white border border-border rounded-lg px-4 py-3 mb-6 flex items-center justify-between">
        <p className="font-serif text-base text-ink">What&apos;s your opening position on this topic?</p>
        <span className="font-mono text-xs text-fog flex-none ml-4">{mins}:{secs}</span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Make your argument…"
        rows={4}
        className="w-full bg-white border border-border rounded-lg px-4 py-3 mb-4 font-serif text-sm text-ink resize-none outline-none focus:border-scarlet placeholder:italic placeholder:text-fog"
      />

      <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden mb-6">
        <div
          className="h-full bg-scarlet rounded-full transition-[width] duration-500 ease-out"
          style={{ width: `${((index - 1) / total) * 100}%` }}
        />
      </div>

      <button
        onClick={submit}
        disabled={!text.trim()}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60"
      >
        Continue →
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Verify in the dev server**

Run: `cd frontend && npm run dev`, register a new account, confirm you land on the calibration screen with topic 1/3, submit three answers, confirm it lands on Topic Selection afterward and a second login does not show calibration again.
Expected: calibration only shown once per account, matching backend `calibration_done` state.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/calibration/CalibrationSession.tsx frontend/src/lib/api.ts frontend/src/types/index.ts
git commit -m "feat: add Calibration Session screen per DS-1.0 9.2"
```

---

## Task 12: WeaknessBar component + SessionEnd rewrite

DS-1.0 §8.5 and §9.5 specify before/after weight bars per pattern with a MASTERED badge variant. Backed entirely by Task 3's `/sessions/{id}/summary` endpoint.

**Files:**
- Create: `frontend/src/components/shared/WeaknessBar.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/session/SessionEnd.tsx`

**Interfaces:**
- Consumes: `GET /api/sessions/{id}/summary` (Task 3).
- Produces: navigates to `screen: "transcript"` via the "View full transcript" link (Task 13 implements the destination).

- [ ] **Step 1: Add summary types and API call**

```typescript
// frontend/src/types/index.ts — append
export interface WeaknessChange {
  pattern: string;
  before: number;
  after: number;
  mastered: boolean;
  rounds_to_mastery: number | null;
}

export interface SessionSummary {
  topic: string;
  difficulty: string;
  score: number;
  exchanges: number;
  weaknesses_exposed: number;
  mastered_count: number;
  rounds_won: number;
  patterns: WeaknessChange[];
}
```

```typescript
// frontend/src/lib/api.ts — append to the api object
  getSessionSummary: (sessionId: string) =>
    apiFetch<SessionSummary>(`/api/sessions/${sessionId}/summary`),
```

```typescript
// frontend/src/lib/api.ts — extend the import line
import { ProgressData, CalibrationStatus, CalibrationAnswerResult, SessionSummary } from "@/types";
```

- [ ] **Step 2: Create `WeaknessBar.tsx`**

```tsx
// frontend/src/components/shared/WeaknessBar.tsx
import MasteredBadge from "./MasteredBadge";
import { WeaknessChange } from "@/types";

export default function WeaknessBar({ change }: { change: WeaknessChange }) {
  return (
    <div className="mb-5">
      <div className="flex items-center justify-between mb-2">
        <span className="font-sans text-sm text-ink">{change.pattern}</span>
        {change.mastered && <MasteredBadge />}
      </div>

      <div className="flex items-center gap-2 mb-1">
        <span className="font-sans text-[10px] text-fog w-12 flex-none">Before</span>
        <div className="flex-1 h-1.5 bg-[#E8EAED] rounded-[3px] overflow-hidden">
          <div
            className="h-full bg-fog rounded-[3px] transition-[width] duration-500 ease-out"
            style={{ width: `${change.before * 100}%` }}
          />
        </div>
        <span className="font-mono text-[10px] text-fog w-8 flex-none text-right">
          {change.before.toFixed(2)}
        </span>
      </div>

      {change.mastered ? (
        <p className="font-sans text-[11px] text-fog italic ml-14">
          pruned from opponent strategy
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <span className="font-sans text-[10px] font-semibold text-scarlet w-12 flex-none">After</span>
          <div className="flex-1 h-1.5 bg-[#E8EAED] rounded-[3px] overflow-hidden">
            <div
              className="h-full bg-scarlet rounded-[3px] transition-[width] duration-500 ease-out"
              style={{ width: `${change.after * 100}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-fog w-8 flex-none text-right">
            {change.after.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `SessionEnd.tsx` to consume the summary endpoint**

```tsx
// frontend/src/components/session/SessionEnd.tsx
"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { SessionSummary } from "@/types";
import WeaknessBar from "@/components/shared/WeaknessBar";

export default function SessionEnd() {
  const { sessionId, sessionConfig, setScreen } = useDebate();
  const [summary, setSummary] = useState<SessionSummary | null>(null);

  useEffect(() => {
    if (sessionId) api.getSessionSummary(sessionId).then(setSummary).catch(() => setSummary(null));
  }, [sessionId]);

  if (!summary) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Loading summary…</div>;
  }

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-display text-3xl text-ink mb-1">Session complete</h1>
      <p className="font-sans text-base text-fog mb-7">{summary.topic} · {summary.difficulty}</p>

      <div className="grid grid-cols-4 gap-3 mb-9">
        {[
          { v: summary.score.toFixed(1), unit: "/10", label: "Score", color: "text-scarlet" },
          { v: summary.exchanges, unit: "", label: "Exchanges", color: "text-ink" },
          { v: summary.weaknesses_exposed, unit: "", label: "Weaknesses exposed", color: "text-ink" },
          { v: summary.rounds_won, unit: "", label: "Rounds won", color: "text-verdant" },
        ].map(({ v, unit, label, color }) => (
          <div key={label} className="bg-white border border-border rounded-lg p-4">
            <div className={`font-display text-3xl ${color}`}>{v}<span className="text-sm text-fog font-sans">{unit}</span></div>
            <div className="font-sans text-[11px] text-fog mt-1">{label}</div>
          </div>
        ))}
      </div>

      {summary.patterns.length > 0 && (
        <>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">
            Fingerprint changes
          </p>
          {summary.patterns.map((p) => (
            <WeaknessBar key={p.pattern} change={p} />
          ))}
        </>
      )}

      <div className="h-px bg-border my-7" />
      <div className="flex gap-3 items-center">
        <button onClick={() => setScreen("debate")}
          className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Debate again →
        </button>
        <button onClick={() => setScreen("topic")}
          className="bg-slate text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Choose new topic
        </button>
        <button onClick={() => setScreen("transcript")}
          className="font-sans text-sm text-fog border-none bg-none">
          View full transcript
        </button>
      </div>

      {sessionConfig && null /* sessionConfig kept for the "Debate again" round-trip via store, not rendered here */}
    </div>
  );
}
```

- [ ] **Step 4: Verify in the dev server**

Run: `cd frontend && npm run dev`, complete a debate session, click "End session", confirm the summary loads from `/sessions/{id}/summary` (check Network tab) and shows real before/after bars (not the old static "detected" tag list).
Expected: bars reflect actual judge scores from the exchanges just played.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/shared/WeaknessBar.tsx frontend/src/lib/api.ts frontend/src/types/index.ts frontend/src/components/session/SessionEnd.tsx
git commit -m "feat: rewrite SessionEnd with WeaknessBar before/after from backend summary"
```

---

## Task 13: Session Transcript screen

**Files:**
- Create: `frontend/src/components/session/SessionTranscript.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`

**Interfaces:**
- Consumes: `GET /api/sessions/{id}/transcript`, `GET /api/sessions/{id}/transcript/export` (Task 4).

- [ ] **Step 1: Add transcript types and API calls**

```typescript
// frontend/src/types/index.ts — append
export interface TranscriptExchange {
  turn_number: number;
  user_message: string;
  opponent_response: string;
  judge_logic: number | null;
  judge_evidence: number | null;
  judge_rhetoric: number | null;
  fallacy: string | null;
  outcome: string | null;
  created_at: string;
}

export interface Transcript {
  session_id: string;
  topic: string;
  difficulty: string;
  started_at: string;
  exchanges: TranscriptExchange[];
}
```

```typescript
// frontend/src/lib/api.ts — append to the api object
  getTranscript: (sessionId: string) =>
    apiFetch<Transcript>(`/api/sessions/${sessionId}/transcript`),
  transcriptExportUrl: (sessionId: string) =>
    `${BASE}/api/sessions/${sessionId}/transcript/export`,
```

```typescript
// frontend/src/lib/api.ts — extend the import line
import { ProgressData, CalibrationStatus, CalibrationAnswerResult, SessionSummary, Transcript } from "@/types";
```

The export link needs the auth token attached — since it's a plain anchor download (not a `fetch`), pass the token as a query param the backend already accepts via the `Authorization` header only. Use a `fetch`-then-`Blob`-download approach instead of a raw `<a href>` so the bearer token can be sent properly (Step 2 below).

- [ ] **Step 2: Create `SessionTranscript.tsx`**

```tsx
// frontend/src/components/session/SessionTranscript.tsx
"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { Transcript } from "@/types";

export default function SessionTranscript() {
  const { sessionId, setScreen } = useDebate();
  const token = useDebate((s) => s.token);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (sessionId) api.getTranscript(sessionId).then(setTranscript).catch(() => setTranscript(null));
  }, [sessionId]);

  async function exportTranscript() {
    if (!sessionId) return;
    const res = await fetch(api.transcriptExportUrl(sessionId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript_${sessionId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!transcript) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Loading transcript…</div>;
  }

  const ex = transcript.exchanges[cursor];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <button onClick={() => setScreen("end")} className="font-sans text-sm text-fog mb-5">← Back</button>
      <h1 className="font-display text-2xl text-ink mb-1">{transcript.topic}</h1>
      <p className="font-sans text-sm text-fog mb-7">
        {transcript.difficulty} · {new Date(transcript.started_at).toLocaleDateString()} · {transcript.exchanges.length} exchanges
      </p>

      {ex && (
        <div key={ex.turn_number}>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-1">
            YOU — {new Date(ex.created_at).toLocaleTimeString()}
          </p>
          <p className="font-serif text-[15px] text-slate mb-5">{ex.user_message}</p>

          <p className="font-sans text-[11px] font-semibold text-scarlet uppercase tracking-wide mb-1">
            OPPONENT — {new Date(ex.created_at).toLocaleTimeString()}
            {ex.fallacy && <span className="text-fog normal-case font-normal"> · {ex.fallacy} detected</span>}
          </p>
          <p className="font-serif text-[15px] text-ink mb-5">{ex.opponent_response}</p>

          {ex.judge_logic !== null && (
            <p className="font-mono text-[11px] text-fog mb-7">
              JUDGE  Logic {ex.judge_logic} · Evidence {ex.judge_evidence} · Rhetoric {ex.judge_rhetoric}
              {ex.fallacy && <span> · ⚠ {ex.fallacy}</span>}
            </p>
          )}
        </div>
      )}

      <div className="h-px bg-border my-7" />
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
          disabled={cursor === 0}
          className="font-sans text-sm text-fog disabled:opacity-30"
        >
          ← Previous exchange
        </button>
        <button onClick={exportTranscript} className="font-sans text-sm text-fog">
          Export transcript ↓
        </button>
        <button
          onClick={() => setCursor((c) => Math.min(transcript.exchanges.length - 1, c + 1))}
          disabled={cursor >= transcript.exchanges.length - 1}
          className="font-sans text-sm text-fog disabled:opacity-30"
        >
          Next exchange →
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in the dev server**

Run: `cd frontend && npm run dev`, end a session, click "View full transcript", confirm prev/next navigation works and "Export transcript ↓" downloads a `.txt` file matching `format_transcript_text`'s output.
Expected: downloaded file opens as plain text with `YOU`/`OPPONENT`/`JUDGE` sections matching the on-screen exchange.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/session/SessionTranscript.tsx frontend/src/lib/api.ts frontend/src/types/index.ts
git commit -m "feat: add Session Transcript screen with export per DS-1.0 9.7"
```

---

## Task 14: Progress Dashboard rewrite — streak, mastered list, win rate by topic, weakness trend

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/progress/ProgressDashboard.tsx`

**Interfaces:**
- Consumes: extended `GET /api/users/me/progress` (Task 6), `POST /api/users/me/mastery/{pattern}/reactivate` (Task 2).

- [ ] **Step 1: Extend `ProgressData` type and add the reactivate API call**

```typescript
// frontend/src/types/index.ts — replace the ProgressData interface
export interface MasteredPattern {
  pattern: string;
  mastered_at: string;
  rounds_to_mastery: number;
  reactivated: boolean;
}

export interface TopicWinRate {
  topic: string;
  win_rate: number;
}

export interface WeaknessTrendItem {
  pattern: string;
  weight: number;
}

export interface ProgressData {
  weaknesses: { text: string }[];
  sessions: number;
  win_rate: number;
  streak: number;
  thinking_style: ThinkingStyle;
  mastered: MasteredPattern[];
  win_rate_by_topic: TopicWinRate[];
  weakness_trend: WeaknessTrendItem[];
}
```

```typescript
// frontend/src/lib/api.ts — append to the api object
  reactivateMastery: (pattern: string) =>
    apiFetch<{ reactivated: boolean }>(`/api/users/me/mastery/${encodeURIComponent(pattern)}/reactivate`, {
      method: "POST",
    }),
```

- [ ] **Step 2: Rewrite `ProgressDashboard.tsx`**

```tsx
// frontend/src/components/progress/ProgressDashboard.tsx
"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { ProgressData } from "@/types";
import MasteredBadge from "@/components/shared/MasteredBadge";

const STYLE_LABELS: { key: keyof ProgressData["thinking_style"]; label: string }[] = [
  { key: "logic", label: "Logic" },
  { key: "evidence", label: "Evidence" },
  { key: "rhetoric", label: "Rhetoric" },
];

export default function ProgressDashboard() {
  const setScreen = useDebate((s) => s.setScreen);
  const [progress, setProgress] = useState<ProgressData | null>(null);

  function reload() {
    api.getProgress().then(setProgress).catch(() => setProgress(null));
  }

  useEffect(reload, []);

  async function reactivate(pattern: string) {
    await api.reactivateMastery(pattern);
    reload();
  }

  const stats = [
    { label: "Sessions", value: progress ? String(progress.sessions) : "—", sub: progress ? `${progress.streak}-day streak` : "Start debating to track" },
    { label: "Win rate", value: progress ? `${Math.round(progress.win_rate * 100)}%` : "—", sub: progress ? "of decided rounds" : "Calculated after sessions" },
    { label: "Mastered", value: progress ? String(progress.mastered.filter((m) => !m.reactivated).length) : "0", sub: "patterns" },
  ];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-display text-3xl text-ink">Your progress</h1>
        <button onClick={() => setScreen("topic")} className="font-sans text-sm text-fog">← Back</button>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-9">
        {stats.map(({ label, value, sub }) => (
          <div key={label} className="bg-white border border-border rounded-lg p-5">
            <div className="font-sans text-[11px] text-fog">{label}</div>
            <div className="font-display text-4xl text-ink my-1">{value}</div>
            <div className="font-sans text-[11px] text-fog">{sub}</div>
          </div>
        ))}
      </div>

      {progress && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Thinking style</p>
          {STYLE_LABELS.map(({ key, label }) => {
            const score = progress.thinking_style[key];
            return (
              <div key={key} className="mb-3">
                <div className="flex justify-between font-sans text-sm text-ink mb-1">
                  <span>{label}</span>
                  <span className="font-mono text-[11px] text-fog">{score.toFixed(1)}/10</span>
                </div>
                <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                  <div className="h-full bg-scarlet rounded-full" style={{ width: `${Math.min(100, (score / 10) * 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {progress && progress.weakness_trend.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Weakness trend</p>
          {progress.weakness_trend.map((w) => (
            <div key={w.pattern} className="mb-3">
              <div className="flex justify-between font-sans text-sm text-ink mb-1">
                <span>{w.pattern}</span>
                <span className="font-mono text-[11px] text-fog">{w.weight.toFixed(2)}</span>
              </div>
              <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                <div className="h-full bg-scarlet rounded-full" style={{ width: `${w.weight * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {progress && progress.mastered.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Mastered patterns</p>
          {progress.mastered.map((m) => (
            <div key={`${m.pattern}-${m.mastered_at}`} className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2.5">
                {m.reactivated ? (
                  <span className="font-sans text-sm text-ink">{m.pattern}</span>
                ) : (
                  <>
                    <span className="font-sans text-sm text-ink">{m.pattern}</span>
                    <MasteredBadge />
                  </>
                )}
                <span className="font-sans text-[11px] text-fog">
                  {new Date(m.mastered_at).toLocaleDateString()} · {m.rounds_to_mastery} rounds to master
                </span>
              </div>
              {!m.reactivated && (
                <button onClick={() => reactivate(m.pattern)} className="font-sans text-[11px] text-fog">
                  Reactivate →
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {progress && progress.win_rate_by_topic.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Win rate by topic</p>
          {progress.win_rate_by_topic.map((t) => (
            <div key={t.topic} className="mb-3">
              <div className="flex justify-between font-sans text-sm text-ink mb-1">
                <span>{t.topic}</span>
                <span className="font-mono text-[11px] text-fog">{Math.round(t.win_rate * 100)}%</span>
              </div>
              <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${t.win_rate >= 0.5 ? "bg-verdant" : "bg-scarlet"}`}
                  style={{ width: `${t.win_rate * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {!progress && (
        <p className="font-sans text-sm text-fog text-center mt-12 italic">
          Complete a debate session to see your cognitive fingerprint evolve.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify in the dev server**

Run: `cd frontend && npm run dev`, complete several sessions across different topics, master at least one pattern by repeatedly winning the same pattern, open Progress, confirm streak/win-rate-by-topic/mastered-list/weakness-trend all render real numbers, click "Reactivate →" on a mastered pattern and confirm it disappears from the mastered list and reappears in the weakness trend after reload.
Expected: all sections backed by live data, no hardcoded placeholders.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/types/index.ts frontend/src/components/progress/ProgressDashboard.tsx
git commit -m "feat: rewrite Progress Dashboard with streak, mastered list, win rate by topic, weakness trend"
```

---

## Task 15: Visual fidelity pass — icons, exact borders, hover/transition states

Final pass tightening remaining DS-1.0 deviations now that all data-bearing components exist: Tabler icons (§6), exact `border-border` token instead of `border-fog/20`/`border-fog/30` approximations (§3.2), and documented hover/transition timings (§7.3).

**Files:**
- Modify: `frontend/src/components/debate/InputArea.tsx`
- Modify: `frontend/src/components/debate/DebateView.tsx`
- Modify: `frontend/src/components/topic/TopicSelection.tsx`
- Modify: `frontend/src/components/debate/MessageBubble.tsx`

**Interfaces:** None — pure visual polish, no new data flow.

- [ ] **Step 1: Replace the hand-rolled send arrow with the Tabler send icon**

```tsx
// frontend/src/components/debate/InputArea.tsx — add import
import { IconSend } from "@tabler/icons-react";
```

```tsx
// frontend/src/components/debate/InputArea.tsx — replace the inline <svg> inside the send button with:
          <IconSend size={18} stroke={2} />
```

- [ ] **Step 2: Swap `border-fog/20` and `border-fog/30` for the exact `border-border` token**

Run a repo-wide replace across the four files in scope:

```bash
cd frontend/src/components && grep -rl "border-fog/20\|border-fog/30" debate topic | xargs sed -i '' 's/border-fog\/20/border-border/g; s/border-fog\/30/border-border/g'
```

Manually verify no unintended matches afterward:

Run: `cd frontend && grep -rn "border-fog" src/components/debate src/components/topic`
Expected: no remaining matches in those two directories (any legitimate remaining `border-fog/40` hover-state classes are untouched, since the sed targets only `/20` and `/30`).

- [ ] **Step 3: Add icon imports to nav for progress/transcript affordances**

```tsx
// frontend/src/components/debate/DebateView.tsx — add import
import { IconChartLine, IconHistory } from "@tabler/icons-react";
```

```tsx
// frontend/src/components/debate/DebateView.tsx — inside the <nav>, before the "End session" button, add:
        <div className="flex items-center gap-3">
          <button onClick={() => setScreen("progress")} aria-label="Progress" className="text-fog hover:text-ink transition-colors">
            <IconChartLine size={18} stroke={1.75} />
          </button>
          <button
            onClick={() => setScreen("transcript")}
            aria-label="Transcript"
            className="text-fog hover:text-ink transition-colors"
          >
            <IconHistory size={18} stroke={1.75} />
          </button>
        </div>
```

(Place this `<div>` between the topic/difficulty `<span>` and the "End session" `<button>` in the existing `<nav>` flex row.)

- [ ] **Step 4: Verify build and lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: both succeed — this is the full build check deferred from Task 8 Step 6, now that `CalibrationSession.tsx` and `SessionTranscript.tsx` exist.

- [ ] **Step 5: Manual walkthrough of every screen**

Run: `cd frontend && npm run dev`, walk: Landing → Auth (register) → Calibration (3 topics) → Topic Selection → Live Debate (send 2-3 messages, confirm SessionScoreBar + MasteredBadge if earned) → End session (WeaknessBar) → Transcript (prev/next + export) → Progress (streak/mastered/win-rate-by-topic/weakness-trend) → Debate again.
Expected: no console errors, no broken navigation, every number on screen traceable to a backend response in the Network tab.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components
git commit -m "polish: Tabler icons, exact border token, nav affordances for progress/transcript"
```

---

## Self-Review

**Spec coverage** — every numbered DS-1.0 section maps to a task:
- §1 Principles (no celebrations, no spinners, no breadcrumbs) — respected throughout; Pulse Avatar (existing) stays the only expressive animation, JudgeScore keeps its 2s delay (existing, unchanged), calibration has no auto-advance (Task 11).
- §2 Logo — already correct in `layout.tsx`/`LandingPage.tsx` (Task 8), untouched.
- §3 Colour — Task 7 adds the two missing tokens (`border`, `light`); existing tokens already matched.
- §4 Typography — already wired in `layout.tsx`, untouched.
- §5 Spacing/grid/radius — existing components already match (verified against `MessageBubble.tsx`, `tailwind.config.ts` during research); no task needed beyond Task 15's border-token sweep.
- §6 Iconography — Task 15.
- §7 Motion — Pulse Avatar and 2s judge delay already exist; Task 7 adds `prefers-reduced-motion` handling.
- §8.1–8.4, 8.8–8.10 (MessageBubble, JudgeScore, OpponentAvatar, DifficultyCard, MasteredBadge, TopicChip, ChatInput) — already implemented or covered by Task 10 (MasteredBadge).
- §8.5 WeaknessBar — Task 12.
- §8.6 GraphNode — already implemented in `FingerprintGraph.tsx`, untouched.
- §8.7 SessionScoreBar — Task 9.
- §9.1 Landing/Auth — Task 8.
- §9.2 Calibration — Tasks 5 (backend) + 11 (frontend).
- §9.3 Topic Selection — already implemented, untouched.
- §9.4 Live Debate View — already implemented; Task 9 adds the missing score strip, Task 10 adds mastery badges.
- §9.5 Session End — Task 12.
- §9.6 Progress Dashboard — Tasks 6 (backend) + 14 (frontend).
- §9.7 Session Transcript — Tasks 4 (backend) + 13 (frontend).
- §10 Voice Phase — explicitly out of scope (Phase 2 preview only, spec says "no breaking design changes to Phase 1 screens" required, not Phase 2 implementation).
- §11 Responsive — existing Tailwind responsive classes (`hidden lg:flex` on the graph aside) already partially cover this; full bottom-sheet mobile graph is a larger undertaking not requested in this round — flagged here as a known gap, not silently dropped.
- §12 Accessibility — `aria-label` already present on `PulseAvatar`-adjacent elements; Task 15 adds `aria-label` to new icon buttons. Full WCAG audit not in scope.
- §13 Dark Mode — Task 7 lays the CSS variable foundation; a user-facing toggle and full component dark variants are a known gap (flagged, not silently dropped — would be its own follow-up task if prioritized).
- §14 Design Tokens (CSS) — Task 7.
- §15 Do/Don't — enforced implicitly by following the other sections; no separate task needed.

**Placeholder scan** — no "TBD"/"handle edge cases"/"similar to Task N" found; every step has complete code.

**Type consistency** — `revealJudge(judge, mastery)` signature matches between store interface (Task 10 Step 4) and its call site in `useDebateSSE.ts` (Task 10 Step 3). `SessionSummary`/`Transcript`/`CalibrationStatus` types match their Pydantic schema field names exactly (`snake_case`, matching the rest of the codebase's existing `ProgressData`/`JudgeScore` types, which are also snake_case to mirror the API).

**Known gaps flagged (not silently dropped):** full mobile bottom-sheet graph (§11.2) and a user-facing dark-mode toggle with complete dark variants on every component (§13) are foundation-only in this plan — call this out to the user before considering the design system "fully" implemented if those matter for the hackathon demo.

---

Plan complete and saved to `docs/superpowers/plans/2026-07-01-debatemind-design-system.md`.
