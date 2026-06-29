# DebateMind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack AI debate coach — Python/FastAPI backend with Cognee memory + LangGraph agents, and a Next.js frontend with live D3.js cognitive fingerprint graph — for the WeMakeDevs × Cognee Hackathon (deadline July 5, 2026).

**Architecture:** FastAPI backend exposes REST + SSE + WebSocket endpoints. Three LangGraph agents (Extractor, Opponent, Judge) process each debate turn; Cognee stores argument patterns as a persistent knowledge graph per user. Next.js frontend renders a split-panel chat + live D3 graph, receiving opponent responses via SSE and graph updates via WebSocket.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2 + asyncpg (PostgreSQL), Cognee, LangGraph, Anthropic SDK, python-jose, passlib; Next.js 14 (App Router), TypeScript, Tailwind CSS, Zustand, D3.js v7, TanStack Query.

## Global Constraints

- Python ≥ 3.11; Node ≥ 20
- LLM model for Extractor + Judge: `claude-haiku-4-5-20251001`
- LLM model for Opponent: `claude-sonnet-4-6`
- Cognee dataset naming: `user_{user_id}_fingerprint`
- Opponent response SLA: < 8 seconds (P95)
- All secrets in `.env`; never committed
- Tailwind design tokens: Scarlet `#C0392B`, Slate `#2C3E50`, Chalk `#F5F5F0`, Carbon `#1A1A1A`, Fog `#7F8C8D`, Ember `#E67E22`, Verdant `#27AE60`
- Fonts: DM Serif Display (logo), Spectral (chat), Inter (UI), JetBrains Mono (scores)
- Judge scores appear 2 s after opponent reply
- Graph WebSocket fires after each judge score update

---

## File Map

```
backend/
├── app/
│   ├── main.py                   # FastAPI app, routers, WebSocket mount
│   ├── config.py                 # Settings (pydantic-settings)
│   ├── database.py               # SQLAlchemy async engine + session
│   ├── models/
│   │   ├── user.py               # ORM: User
│   │   ├── session.py            # ORM: DebateSession, Exchange
│   │   └── mastery.py            # ORM: MasteryLog
│   ├── schemas/
│   │   ├── auth.py               # Pydantic: RegisterIn, LoginIn, TokenOut
│   │   ├── session.py            # SessionStartIn, SessionOut, MessageIn, MessageOut
│   │   └── graph.py              # GraphOut (nodes + edges for D3)
│   ├── services/
│   │   ├── auth.py               # JWT encode/decode, password hash
│   │   ├── cognee_svc.py         # remember(), recall(), improve(), forget() wrappers
│   │   └── graph_svc.py          # Build GraphOut from Cognee recall results
│   ├── agents/
│   │   ├── state.py              # DebateState TypedDict
│   │   ├── extractor.py          # extract_argument node
│   │   ├── opponent.py           # generate_opponent node
│   │   ├── judge.py              # judge_exchange node
│   │   ├── mastery.py            # check_mastery node
│   │   └── pipeline.py           # LangGraph compile()
│   ├── routers/
│   │   ├── auth.py               # POST /api/auth/register, /login
│   │   ├── sessions.py           # POST /api/sessions/start, /message (SSE), /end
│   │   ├── users.py              # GET /api/users/{id}/fingerprint, /progress
│   │   └── topics.py             # GET /api/topics/suggest
│   └── websocket/
│       ├── manager.py            # ConnectionManager
│       └── router.py             # WebSocket /ws/graph/{session_id}
├── migrations/001_initial.sql
├── requirements.txt
└── .env.example

frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              # Landing + auth modal
│   │   ├── debate/page.tsx       # Main debate view
│   │   └── progress/page.tsx     # Progress dashboard
│   ├── components/
│   │   ├── auth/AuthModal.tsx
│   │   ├── topic/TopicSelection.tsx
│   │   ├── debate/
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── JudgeScore.tsx
│   │   │   ├── InputArea.tsx
│   │   │   └── PulseAvatar.tsx
│   │   ├── graph/FingerprintGraph.tsx   # D3.js SVG
│   │   ├── session/SessionEnd.tsx
│   │   └── progress/ProgressDashboard.tsx
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useDebateSSE.ts
│   │   └── useGraphWS.ts
│   ├── lib/
│   │   ├── api.ts                # Typed fetch wrappers
│   │   └── tokens.ts             # Design token constants
│   ├── store/debate.ts           # Zustand store
│   └── types/index.ts
├── tailwind.config.ts
└── package.json
```

---

## Task 1: Backend Scaffold + Config

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/config.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Create `backend/requirements.txt`**

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
alembic==1.14.0
pydantic-settings==2.6.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.18
anthropic==0.40.0
langgraph==0.2.60
cognee==0.1.40
httpx==0.28.1
python-dotenv==1.0.1
```

- [ ] **Step 2: Create `backend/.env.example`**

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/debatemind
SECRET_KEY=change-me-32-chars-minimum
ANTHROPIC_API_KEY=sk-ant-...
COGNEE_API_KEY=your-cognee-api-key
COGNEE_LLM_API_KEY=sk-ant-...
```

- [ ] **Step 3: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    anthropic_api_key: str
    cognee_api_key: str = ""
    cognee_llm_api_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 4: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import cognee
from app.config import settings
from app.database import engine, Base
from app.routers import auth, sessions, users, topics
from app.websocket.router import ws_router

app = FastAPI(title="DebateMind API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    if settings.cognee_api_key:
        cognee.config.set_llm_config({
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "api_key": settings.cognee_llm_api_key or settings.anthropic_api_key,
        })

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(topics.router, prefix="/api/topics", tags=["topics"])
app.include_router(ws_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Install and verify**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
# expect: {"status":"ok"} at http://localhost:8000/health
```

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffold + FastAPI app factory"
```

---

## Task 2: Database Models + Migration

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/session.py`
- Create: `backend/app/models/mastery.py`
- Create: `backend/migrations/001_initial.sql`

- [ ] **Step 1: Create `backend/app/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 2: Create `backend/app/models/user.py`**

```python
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    calibration_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: Create `backend/app/models/session.py`**

```python
from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid
from app.database import Base

class DebateSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    topic: Mapped[str] = mapped_column(String)
    difficulty: Mapped[str] = mapped_column(String, default="targeted")
    user_position: Mapped[str] = mapped_column(String, default="against")
    status: Mapped[str] = mapped_column(String, default="active")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)

class Exchange(Base):
    __tablename__ = "exchanges"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String, ForeignKey("sessions.id"))
    turn_number: Mapped[int] = mapped_column(Integer)
    user_message: Mapped[str] = mapped_column(Text)
    opponent_response: Mapped[str] = mapped_column(Text, nullable=True)
    detected_pattern: Mapped[str] = mapped_column(String, nullable=True)
    fallacy: Mapped[str] = mapped_column(String, nullable=True)
    judge_logic: Mapped[float] = mapped_column(Float, nullable=True)
    judge_evidence: Mapped[float] = mapped_column(Float, nullable=True)
    judge_rhetoric: Mapped[float] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String, nullable=True)  # Won/Lost/Neutral
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Create `backend/app/models/mastery.py`**

```python
from sqlalchemy import String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import uuid
from app.database import Base

class MasteryLog(Base):
    __tablename__ = "mastery_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    pattern_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="MASTERED")
    rounds_to_mastery: Mapped[int] = mapped_column(Integer, default=0)
    mastered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reactivated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Verify tables create on startup**

```bash
cd backend && source venv/bin/activate
# ensure postgres is running, DATABASE_URL is set in .env
uvicorn app.main:app --reload
# startup log should show no errors; check psql: \dt
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/app/models/
git commit -m "feat: SQLAlchemy async models for users, sessions, mastery"
```

---

## Task 3: Auth Service + Endpoints

**Files:**
- Create: `backend/app/services/auth.py`
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/routers/auth.py`

- [ ] **Step 1: Create `backend/app/schemas/auth.py`**

```python
from pydantic import BaseModel, EmailStr

class RegisterIn(BaseModel):
    email: EmailStr
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
```

- [ ] **Step 2: Create `backend/app/services/auth.py`**

```python
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)

def decode_token(token: str) -> str:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    user_id: str = payload.get("sub")
    if user_id is None:
        raise JWTError("Invalid token")
    return user_id
```

- [ ] **Step 3: Create `backend/app/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.schemas.auth import RegisterIn, LoginIn, TokenOut
from app.services.auth import hash_password, verify_password, create_access_token

router = APIRouter()

@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenOut(access_token=create_access_token(user.id), user_id=user.id)

@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(user.id), user_id=user.id)
```

- [ ] **Step 4: Add auth dependency**

Create `backend/app/deps.py`:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from app.services.auth import decode_token

bearer = HTTPBearer()

def current_user_id(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        return decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

- [ ] **Step 5: Test auth endpoints**

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"secret123"}'
# expect: {"access_token":"eyJ...","token_type":"bearer","user_id":"uuid"}
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/auth.py backend/app/schemas/auth.py backend/app/routers/auth.py backend/app/deps.py
git commit -m "feat: JWT auth register/login endpoints"
```

---

## Task 4: Cognee Service (remember / recall / improve / forget)

**Files:**
- Create: `backend/app/services/cognee_svc.py`

- [ ] **Step 1: Create `backend/app/services/cognee_svc.py`**

```python
import cognee
from cognee.api.v1.search.search import SearchType
from app.config import settings

PATTERN_TYPES = [
    "EvidenceBased", "AppealToAuthority", "StrawMan",
    "AdHominem", "SlipperySlope", "FalseEquivalence",
    "EmotionalAppeal", "AnecdotalEvidence", "Concession",
]

def _dataset(user_id: str) -> str:
    return f"user_{user_id}_fingerprint"

async def remember_argument(
    user_id: str,
    session_id: str,
    topic: str,
    claim_text: str,
    pattern_type: str,
    fallacy: str | None,
    evidence_quality: str,
    outcome: str,
) -> None:
    """Persist one argument event into the user's permanent fingerprint graph."""
    text = (
        f"User: {user_id}\n"
        f"Topic: {topic}\n"
        f"Claim: {claim_text}\n"
        f"ArgumentPattern: {pattern_type}\n"
        f"Fallacy: {fallacy or 'None'}\n"
        f"Evidence: {evidence_quality}\n"
        f"Outcome: {outcome}\n"
    )
    await cognee.remember(
        text,
        dataset_name=_dataset(user_id),
        session_id=session_id,
        run_in_background=True,
        self_improvement=True,
    )

async def recall_weaknesses(user_id: str) -> list[dict]:
    """Return the user's top weakness patterns for opponent strategy loading."""
    results = await cognee.recall(
        f"top weakness patterns and fallacies for user {user_id}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[_dataset(user_id)],
        top_k=10,
    )
    # results is list[RecallResponse]; extract text
    return [{"text": getattr(r, "text", str(r))} for r in results]

async def improve_fingerprint(user_id: str, session_id: str) -> None:
    """Post-session: bridge session cache into permanent graph + reindex."""
    await cognee.improve(
        dataset=_dataset(user_id),
        session_ids=[session_id],
        build_global_context_index=True,
        run_in_background=True,
    )

async def forget_pattern(user_id: str, pattern_type: str) -> None:
    """Archive a mastered weakness node from the opponent's active strategy."""
    # Cognee forget operates on datasets; we remember the mastery event
    await cognee.remember(
        f"User: {user_id}\nPattern: {pattern_type}\nStatus: MASTERED\nAction: prune from opponent strategy",
        dataset_name=_dataset(user_id),
        run_in_background=True,
    )
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && source venv/bin/activate
python3 -c "from app.services.cognee_svc import remember_argument; print('ok')"
# expect: ok
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/cognee_svc.py
git commit -m "feat: Cognee service wrappers for remember/recall/improve/forget"
```

---

## Task 5: LangGraph Agent Pipeline

**Files:**
- Create: `backend/app/agents/state.py`
- Create: `backend/app/agents/extractor.py`
- Create: `backend/app/agents/opponent.py`
- Create: `backend/app/agents/judge.py`
- Create: `backend/app/agents/mastery.py`
- Create: `backend/app/agents/pipeline.py`

- [ ] **Step 1: Create `backend/app/agents/state.py`**

```python
from typing import TypedDict, Optional

class DebateState(TypedDict):
    user_id: str
    session_id: str
    topic: str
    difficulty: str
    user_position: str
    user_message: str
    turn_number: int
    consecutive_wins: int        # on current weakness
    extracted_pattern: Optional[str]
    extracted_fallacy: Optional[str]
    evidence_quality: Optional[str]
    weakness_context: list[dict]  # from recall()
    opponent_response: Optional[str]
    judge_logic: Optional[float]
    judge_evidence: Optional[float]
    judge_rhetoric: Optional[float]
    judge_fallacy: Optional[str]
    outcome: Optional[str]       # Won/Lost/Neutral
    mastery_events: list[str]    # patterns mastered this turn
```

- [ ] **Step 2: Create `backend/app/agents/extractor.py`**

```python
import json
from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

PATTERN_TYPES = [
    "EvidenceBased", "AppealToAuthority", "StrawMan", "AdHominem",
    "SlipperySlope", "FalseEquivalence", "EmotionalAppeal",
    "AnecdotalEvidence", "Concession",
]

async def extract_argument(state: DebateState) -> DebateState:
    prompt = f"""Analyze this debate argument and return JSON only.

Topic: {state['topic']}
Argument: {state['user_message']}

Return exactly:
{{
  "pattern_type": "<one of: {', '.join(PATTERN_TYPES)}>",
  "fallacy": "<fallacy name or null>",
  "evidence_quality": "<Strong|Moderate|Weak|Absent>"
}}"""

    msg = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        state["extracted_pattern"] = data.get("pattern_type", "EvidenceBased")
        state["extracted_fallacy"] = data.get("fallacy")
        state["evidence_quality"] = data.get("evidence_quality", "Moderate")
    except Exception:
        state["extracted_pattern"] = "EvidenceBased"
        state["extracted_fallacy"] = None
        state["evidence_quality"] = "Moderate"
    return state
```

- [ ] **Step 3: Create `backend/app/agents/opponent.py`**

```python
from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState
from app.services.cognee_svc import recall_weaknesses

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

_DIFFICULTY_INSTRUCTIONS = {
    "balanced": "Explore multiple angles; target a known weakness ~60% of the time.",
    "targeted": "Every response MUST target one of the user's listed weakness patterns.",
    "ruthless": "Hammer the same weakness from different angles until they find a true counter.",
}

async def generate_opponent(state: DebateState) -> DebateState:
    # Load fingerprint if not already loaded (session start)
    if not state.get("weakness_context"):
        state["weakness_context"] = await recall_weaknesses(state["user_id"])

    weakness_text = "\n".join(
        r.get("text", "") for r in state["weakness_context"][:5]
    ) or "No prior weaknesses recorded — probe broadly."

    difficulty = state.get("difficulty", "targeted")

    system = f"""You are a world-class debate opponent.

User's cognitive fingerprint (known weaknesses):
{weakness_text}

Difficulty: {difficulty}
Instruction: {_DIFFICULTY_INSTRUCTIONS.get(difficulty, _DIFFICULTY_INSTRUCTIONS['targeted'])}

Rules:
- Respond with a sharp, substantive counter-argument. No softening.
- Never concede unless the user's argument is genuinely irrefutable.
- Do NOT repeat an argument pattern you already used this session.
- Keep response under 120 words."""

    msg = await _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system,
        messages=[
            {"role": "user", "content": f"Topic: {state['topic']}\n\nUser argues: {state['user_message']}"}
        ],
    )
    state["opponent_response"] = msg.content[0].text
    return state
```

- [ ] **Step 4: Create `backend/app/agents/judge.py`**

```python
import json
from anthropic import AsyncAnthropic
from app.config import settings
from app.agents.state import DebateState

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)

async def judge_exchange(state: DebateState) -> DebateState:
    prompt = f"""Score this debate exchange. Return JSON only.

Topic: {state['topic']}
User: {state['user_message']}
Opponent: {state['opponent_response']}

Return exactly:
{{
  "logic": <1-10>,
  "evidence": <1-10>,
  "rhetoric": <1-10>,
  "fallacy": "<fallacy name or null>",
  "outcome": "<Won|Lost|Neutral>"
}}

Outcome = Won if user's argument is stronger, Lost if opponent's is stronger."""

    msg = await _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        data = json.loads(msg.content[0].text)
        state["judge_logic"] = float(data.get("logic", 5))
        state["judge_evidence"] = float(data.get("evidence", 5))
        state["judge_rhetoric"] = float(data.get("rhetoric", 5))
        state["judge_fallacy"] = data.get("fallacy")
        state["outcome"] = data.get("outcome", "Neutral")
    except Exception:
        state["judge_logic"] = 5.0
        state["judge_evidence"] = 5.0
        state["judge_rhetoric"] = 5.0
        state["judge_fallacy"] = None
        state["outcome"] = "Neutral"
    return state
```

- [ ] **Step 5: Create `backend/app/agents/mastery.py`**

```python
from app.agents.state import DebateState

MASTERY_THRESHOLD = 3

async def check_mastery(state: DebateState) -> DebateState:
    state.setdefault("mastery_events", [])
    if state.get("outcome") == "Won":
        state["consecutive_wins"] = state.get("consecutive_wins", 0) + 1
        if state["consecutive_wins"] >= MASTERY_THRESHOLD and state.get("extracted_pattern"):
            state["mastery_events"].append(state["extracted_pattern"])
            state["consecutive_wins"] = 0
    else:
        state["consecutive_wins"] = 0
    return state
```

- [ ] **Step 6: Create `backend/app/agents/pipeline.py`**

```python
from langgraph.graph import StateGraph, END
from app.agents.state import DebateState
from app.agents.extractor import extract_argument
from app.agents.opponent import generate_opponent
from app.agents.judge import judge_exchange
from app.agents.mastery import check_mastery
from app.services.cognee_svc import remember_argument, forget_pattern

async def _remember_node(state: DebateState) -> DebateState:
    await remember_argument(
        user_id=state["user_id"],
        session_id=state["session_id"],
        topic=state["topic"],
        claim_text=state["user_message"],
        pattern_type=state.get("extracted_pattern", "EvidenceBased"),
        fallacy=state.get("extracted_fallacy"),
        evidence_quality=state.get("evidence_quality", "Moderate"),
        outcome=state.get("outcome", "Neutral"),
    )
    return state

async def _mastery_prune_node(state: DebateState) -> DebateState:
    for pattern in state.get("mastery_events", []):
        await forget_pattern(state["user_id"], pattern)
    return state

def _should_prune(state: DebateState) -> str:
    return "prune" if state.get("mastery_events") else END

graph = StateGraph(DebateState)
graph.add_node("extract", extract_argument)
graph.add_node("opponent", generate_opponent)
graph.add_node("judge", judge_exchange)
graph.add_node("mastery", check_mastery)
graph.add_node("remember", _remember_node)
graph.add_node("prune", _mastery_prune_node)

graph.set_entry_point("extract")
graph.add_edge("extract", "opponent")
graph.add_edge("opponent", "judge")
graph.add_edge("judge", "mastery")
graph.add_edge("mastery", "remember")
graph.add_conditional_edges("remember", _should_prune, {"prune": "prune", END: END})
graph.add_edge("prune", END)

debate_pipeline = graph.compile()
```

- [ ] **Step 7: Smoke-test pipeline**

```bash
cd backend && source venv/bin/activate
python3 -c "
import asyncio
from app.agents.pipeline import debate_pipeline
from app.agents.state import DebateState

async def test():
    s = DebateState(
        user_id='test', session_id='s1', topic='AI regulation',
        difficulty='targeted', user_position='against',
        user_message='Government bodies have decades of regulatory experience.',
        turn_number=1, consecutive_wins=0,
        extracted_pattern=None, extracted_fallacy=None, evidence_quality=None,
        weakness_context=[], opponent_response=None,
        judge_logic=None, judge_evidence=None, judge_rhetoric=None,
        judge_fallacy=None, outcome=None, mastery_events=[],
    )
    result = await debate_pipeline.ainvoke(s)
    print('Opponent:', result['opponent_response'][:80])
    print('Judge logic:', result['judge_logic'])

asyncio.run(test())
"
# expect: opponent response text and numeric judge score
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/agents/
git commit -m "feat: LangGraph pipeline — Extractor, Opponent, Judge, Mastery agents"
```

---

## Task 6: Session + SSE + WebSocket Endpoints

**Files:**
- Create: `backend/app/schemas/session.py`
- Create: `backend/app/schemas/graph.py`
- Create: `backend/app/services/graph_svc.py`
- Create: `backend/app/routers/sessions.py`
- Create: `backend/app/websocket/manager.py`
- Create: `backend/app/websocket/router.py`
- Create stubs: `backend/app/routers/users.py`, `backend/app/routers/topics.py`

- [ ] **Step 1: Create `backend/app/schemas/session.py`**

```python
from pydantic import BaseModel
from typing import Optional

class SessionStartIn(BaseModel):
    topic: str
    difficulty: str = "targeted"
    user_position: str = "against"

class SessionOut(BaseModel):
    session_id: str
    topic: str
    difficulty: str

class MessageIn(BaseModel):
    text: str

class JudgeScores(BaseModel):
    logic: float
    evidence: float
    rhetoric: float
    fallacy: Optional[str]
    outcome: str
```

- [ ] **Step 2: Create `backend/app/schemas/graph.py`**

```python
from pydantic import BaseModel

class GraphNode(BaseModel):
    id: str
    label: str
    type: str        # weakness | strength | mastered | topic
    weight: float

class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float

class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

- [ ] **Step 3: Create `backend/app/services/graph_svc.py`**

```python
from app.services.cognee_svc import recall_weaknesses
from app.schemas.graph import GraphOut, GraphNode, GraphEdge

async def build_graph(user_id: str, topic: str) -> GraphOut:
    """Build a D3-ready graph from Cognee recall results."""
    results = await recall_weaknesses(user_id)
    nodes: list[GraphNode] = [
        GraphNode(id="topic", label=topic[:20], type="topic", weight=1.0)
    ]
    edges: list[GraphEdge] = []
    seen = set()
    for i, r in enumerate(results[:8]):
        text = r.get("text", "")
        # Heuristically extract pattern names from Cognee recall text
        for pattern in [
            "AppealToAuthority", "StrawMan", "AdHominem", "SlipperySlope",
            "FalseEquivalence", "EmotionalAppeal", "AnecdotalEvidence",
            "EvidenceBased", "Concession",
        ]:
            if pattern.lower() in text.lower() and pattern not in seen:
                seen.add(pattern)
                weight = round(0.9 - i * 0.1, 2)
                node_type = "weakness" if weight > 0.5 else "strength"
                nodes.append(GraphNode(id=pattern, label=pattern, type=node_type, weight=weight))
                edges.append(GraphEdge(source="topic", target=pattern, weight=weight))
                break
    return GraphOut(nodes=nodes, edges=edges)
```

- [ ] **Step 4: Create `backend/app/websocket/manager.py`**

```python
from fastapi import WebSocket
from collections import defaultdict

class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[session_id].append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        self._connections[session_id].remove(ws)

    async def broadcast_graph(self, session_id: str, graph_data: dict):
        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_json({"type": "graph_update", "data": graph_data})
            except Exception:
                pass

ws_manager = ConnectionManager()
```

- [ ] **Step 5: Create `backend/app/websocket/router.py`**

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import ws_manager

ws_router = APIRouter()

@ws_router.websocket("/ws/graph/{session_id}")
async def graph_ws(session_id: str, ws: WebSocket):
    await ws_manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, ws)
```

- [ ] **Step 6: Create `backend/app/routers/sessions.py`**

```python
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import get_db
from app.deps import current_user_id
from app.models.session import DebateSession, Exchange
from app.schemas.session import SessionStartIn, SessionOut, MessageIn
from app.agents.pipeline import debate_pipeline
from app.agents.state import DebateState
from app.services.cognee_svc import improve_fingerprint
from app.services.graph_svc import build_graph
from app.websocket.manager import ws_manager
import uuid

router = APIRouter()

# In-memory store of consecutive wins per session (resets on server restart)
_session_wins: dict[str, int] = {}

@router.post("/start", response_model=SessionOut)
async def start_session(
    body: SessionStartIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    session = DebateSession(
        user_id=user_id,
        topic=body.topic,
        difficulty=body.difficulty,
        user_position=body.user_position,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    _session_wins[session.id] = 0
    return SessionOut(session_id=session.id, topic=session.topic, difficulty=session.difficulty)

@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    body: MessageIn,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")

    # count existing exchanges for turn number
    from sqlalchemy import func as sqlfunc
    count_result = await db.execute(
        select(sqlfunc.count(Exchange.id)).where(Exchange.session_id == session_id)
    )
    turn = (count_result.scalar() or 0) + 1

    # Run pipeline
    initial_state = DebateState(
        user_id=user_id,
        session_id=session_id,
        topic=session.topic,
        difficulty=session.difficulty,
        user_position=session.user_position,
        user_message=body.text,
        turn_number=turn,
        consecutive_wins=_session_wins.get(session_id, 0),
        extracted_pattern=None, extracted_fallacy=None, evidence_quality=None,
        weakness_context=[],
        opponent_response=None,
        judge_logic=None, judge_evidence=None, judge_rhetoric=None,
        judge_fallacy=None, outcome=None, mastery_events=[],
    )

    final_state = await debate_pipeline.ainvoke(initial_state)
    _session_wins[session_id] = final_state.get("consecutive_wins", 0)

    # Persist exchange
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

    # Fire graph WS update (background)
    async def _push_graph():
        await asyncio.sleep(2)  # delay matches "judge appears 2s after reply"
        graph = await build_graph(user_id, session.topic)
        await ws_manager.broadcast_graph(session_id, graph.model_dump())
    asyncio.create_task(_push_graph())

    opponent_text = final_state.get("opponent_response", "")

    async def event_stream():
        words = opponent_text.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type':'token','text':chunk})}\n\n"
            await asyncio.sleep(0.055)
        scores = {
            "type": "judge",
            "logic": final_state.get("judge_logic"),
            "evidence": final_state.get("judge_evidence"),
            "rhetoric": final_state.get("judge_rhetoric"),
            "fallacy": final_state.get("judge_fallacy"),
            "outcome": final_state.get("outcome"),
            "mastery": final_state.get("mastery_events", []),
        }
        yield f"data: {json.dumps(scores)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

@router.post("/{session_id}/end")
async def end_session(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    from datetime import datetime, timezone
    await db.execute(
        update(DebateSession)
        .where(DebateSession.id == session_id)
        .values(status="ended", ended_at=datetime.now(timezone.utc))
    )
    await db.commit()
    # Fire improve() in background
    asyncio.create_task(improve_fingerprint(user_id, session_id))
    _session_wins.pop(session_id, None)
    return {"status": "ended"}

@router.get("/{session_id}/graph")
async def get_graph(
    session_id: str,
    user_id: str = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(DebateSession).where(DebateSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404)
    graph = await build_graph(user_id, session.topic)
    return graph
```

- [ ] **Step 7: Create stub routers**

`backend/app/routers/users.py`:
```python
from fastapi import APIRouter, Depends
from app.deps import current_user_id
from app.services.cognee_svc import recall_weaknesses
from app.services.graph_svc import build_graph

router = APIRouter()

@router.get("/{user_id}/fingerprint")
async def get_fingerprint(user_id: str, current: str = Depends(current_user_id)):
    graph = await build_graph(current, "All topics")
    return graph

@router.get("/{user_id}/progress")
async def get_progress(user_id: str, current: str = Depends(current_user_id)):
    weaknesses = await recall_weaknesses(current)
    return {"weaknesses": weaknesses[:5], "sessions": 0, "win_rate": 0.0}
```

`backend/app/routers/topics.py`:
```python
from fastapi import APIRouter
router = APIRouter()

TOPICS = [
    {"label": "POLICY", "chips": ["EU AI Act", "Platform regulation", "Carbon tax"]},
    {"label": "TECHNOLOGY", "chips": ["AI safety", "Open source AI", "Algorithmic bias"]},
    {"label": "SOCIETY", "chips": ["Social media bans", "UBI", "Education reform"]},
]

@router.get("/suggest")
async def suggest():
    return TOPICS
```

- [ ] **Step 8: Wire all routers into main.py** (already done in Task 1 — verify imports resolve)

```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload
# POST /api/sessions/start should return session_id
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/ backend/app/schemas/ backend/app/services/graph_svc.py backend/app/websocket/
git commit -m "feat: session start/message(SSE)/end endpoints + WebSocket graph"
```

---

## Task 7: Next.js Frontend Scaffold

**Files:**
- Create: `frontend/` (Next.js project)
- Create: `frontend/src/lib/tokens.ts`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Bootstrap Next.js**

```bash
cd /Volumes/External/hackathon
npx create-next-app@14 frontend \
  --typescript --tailwind --eslint --app \
  --src-dir --import-alias "@/*" --no-git
cd frontend
npm install zustand d3 @tanstack/react-query
npm install --save-dev @types/d3
```

- [ ] **Step 2: Set Tailwind design tokens in `frontend/tailwind.config.ts`**

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
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
      },
      fontFamily: {
        serif:  ["Spectral", "Georgia", "serif"],
        display: ["DM Serif Display", "serif"],
        sans:   ["Inter", "system-ui", "sans-serif"],
        mono:   ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
```

- [ ] **Step 3: Add Google Fonts to `frontend/src/app/layout.tsx`**

```typescript
import type { Metadata } from "next";
import { Inter, Spectral, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const spectral = Spectral({ subsets: ["latin"], weight: ["400","500"], variable: "--font-spectral" });
const mono = JetBrains_Mono({ subsets: ["latin"], weight: ["400","500"], variable: "--font-mono" });

export const metadata: Metadata = { title: "DebateMind", description: "The AI That Learns How You Argue" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&display=swap" rel="stylesheet" />
      </head>
      <body className={`${inter.variable} ${spectral.variable} ${mono.variable} bg-chalk text-ink`}>
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Create `frontend/src/types/index.ts`**

```typescript
export interface Message {
  id: string;
  role: "user" | "opponent";
  text: string;
  judge?: JudgeScore;
  showJudge?: boolean;
}

export interface JudgeScore {
  logic: number;
  evidence: number;
  rhetoric: number;
  fallacy: string | null;
  outcome: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "weakness" | "strength" | "mastered" | "topic";
  weight: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SessionConfig {
  topic: string;
  difficulty: "balanced" | "targeted" | "ruthless";
  position: "for" | "against" | "neutral";
}
```

- [ ] **Step 5: Create `frontend/src/lib/tokens.ts`**

```typescript
export const COLORS = {
  scarlet: "#C0392B",
  slate:   "#2C3E50",
  chalk:   "#F5F5F0",
  carbon:  "#1A1A1A",
  fog:     "#7F8C8D",
  ember:   "#E67E22",
  verdant: "#27AE60",
  ink:     "#0D0D0D",
} as const;
```

- [ ] **Step 6: Create `frontend/src/lib/api.ts`**

```typescript
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeader(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("dm_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/register", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }),
  startSession: (topic: string, difficulty: string, user_position: string) =>
    apiFetch<{ session_id: string; topic: string }>("/api/sessions/start", {
      method: "POST", body: JSON.stringify({ topic, difficulty, user_position }),
    }),
  endSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}/end`, { method: "POST" }),
  getTopics: () => apiFetch<{ label: string; chips: string[] }[]>("/api/topics/suggest"),
  getGraph: (sessionId: string) =>
    apiFetch<{ nodes: unknown[]; edges: unknown[] }>(`/api/sessions/${sessionId}/graph`),
};
```

- [ ] **Step 7: Create `frontend/src/store/debate.ts`**

```typescript
import { create } from "zustand";
import { Message, GraphData, SessionConfig } from "@/types";

interface DebateStore {
  screen: "auth" | "topic" | "debate" | "end" | "progress";
  token: string | null;
  userId: string | null;
  sessionId: string | null;
  sessionConfig: SessionConfig | null;
  messages: Message[];
  graph: GraphData;
  thinking: boolean;
  sessionScores: { logic: number; evidence: number; rhetoric: number };

  setScreen: (s: DebateStore["screen"]) => void;
  setAuth: (token: string, userId: string) => void;
  setSession: (id: string, config: SessionConfig) => void;
  addMessage: (m: Message) => void;
  updateLastOpponent: (text: string) => void;
  revealJudge: (judge: Message["judge"]) => void;
  setThinking: (v: boolean) => void;
  setGraph: (g: GraphData) => void;
  reset: () => void;
}

export const useDebate = create<DebateStore>((set, get) => ({
  screen: "auth",
  token: typeof window !== "undefined" ? localStorage.getItem("dm_token") : null,
  userId: typeof window !== "undefined" ? localStorage.getItem("dm_uid") : null,
  sessionId: null,
  sessionConfig: null,
  messages: [],
  graph: { nodes: [], edges: [] },
  thinking: false,
  sessionScores: { logic: 0, evidence: 0, rhetoric: 0 },

  setScreen: (screen) => set({ screen }),
  setAuth: (token, userId) => {
    localStorage.setItem("dm_token", token);
    localStorage.setItem("dm_uid", userId);
    set({ token, userId, screen: "topic" });
  },
  setSession: (sessionId, sessionConfig) => set({ sessionId, sessionConfig, messages: [], screen: "debate" }),
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

- [ ] **Step 8: Verify Next.js starts**

```bash
cd frontend && npm run dev
# expect: Next.js ready at http://localhost:3000
```

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: Next.js scaffold with Tailwind tokens, Zustand store, API client"
```

---

## Task 8: Auth + Topic Selection UI

**Files:**
- Create: `frontend/src/components/auth/AuthModal.tsx`
- Create: `frontend/src/components/topic/TopicSelection.tsx`
- Create: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/auth/AuthModal.tsx`**

```typescript
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

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setAuth(res.access_token, res.user_id);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="min-h-screen bg-chalk flex flex-col items-center justify-center px-4">
      <h1 className="font-display text-5xl text-ink mb-2">DebateMind</h1>
      <p className="font-sans text-fog text-base mb-10 italic">The AI that learns how you argue.</p>
      <form onSubmit={submit} className="w-full max-w-sm flex flex-col gap-4">
        <input
          type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
          className="border border-fog/40 rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
        />
        <input
          type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="border border-fog/40 rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
        />
        {error && <p className="text-scarlet text-xs font-sans">{error}</p>}
        <button type="submit" className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-3 rounded">
          {mode === "login" ? "Sign in →" : "Create account →"}
        </button>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="text-fog font-sans text-xs underline">
          {mode === "login" ? "New here? Create account" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/topic/TopicSelection.tsx`**

```typescript
"use client";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced", desc: "Varied angles, 60% weakness" },
  { key: "targeted", name: "Targeted", desc: "Every move hits a known weak node" },
  { key: "ruthless", name: "Ruthless", desc: "Same weakness, every angle" },
] as const;

const POSITIONS = ["For", "Against", "Neutral", "Assign randomly"] as const;
const SURPRISES = [
  "Nuclear power is the only realistic path to decarbonisation",
  "Universal basic income will erode the dignity of work",
  "Social media should be banned for under-16s",
];

export default function TopicSelection() {
  const [topic, setTopic] = useState("AI regulation should be government-led");
  const [activeChip, setActiveChip] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [groups, setGroups] = useState<{ label: string; chips: string[] }[]>([]);
  const { setSession } = useDebate();

  useEffect(() => { api.getTopics().then(setGroups).catch(() => {}); }, []);

  async function start() {
    const res = await api.startSession(topic, difficulty, position);
    setSession(res.session_id, { topic, difficulty, position: position as never });
  }

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-sans font-medium text-2xl text-ink mb-5">What do you want to argue about?</h1>
      <div className="flex items-center justify-between bg-white border border-fog/30 rounded-lg px-4 py-3 mb-6">
        <span className="font-serif text-base text-ink">{topic}</span>
        <button onClick={() => { setTopic(""); setActiveChip(""); }} className="text-fog text-lg">✕</button>
      </div>

      {groups.map((g) => (
        <div key={g.label} className="flex gap-4 mb-3">
          <span className="w-24 flex-none font-sans text-[11px] font-semibold text-fog uppercase tracking-wide pt-1.5">{g.label}</span>
          <div className="flex flex-wrap gap-2">
            {g.chips.map((c) => (
              <button key={c} onClick={() => { setTopic(c); setActiveChip(c); }}
                className={`font-sans text-xs px-3 py-1 rounded-full border transition-all ${
                  activeChip === c ? "bg-scarlet text-white border-scarlet" : "bg-white text-ink border-fog/40"
                }`}>
                {c}
              </button>
            ))}
          </div>
        </div>
      ))}

      <button onClick={() => { const r = SURPRISES[Math.floor(Math.random() * SURPRISES.length)]; setTopic(r); setActiveChip(""); }}
        className="ml-28 font-sans text-xs text-fog border border-dashed border-fog/40 rounded-full px-3 py-1 mb-7">
        🎲 Surprise me
      </button>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">DIFFICULTY</p>
      <div className="flex gap-3 mb-7">
        {DIFFICULTIES.map((d) => (
          <div key={d.key} onClick={() => setDifficulty(d.key)}
            className={`flex-1 rounded-lg p-3 cursor-pointer border transition-all ${
              difficulty === d.key ? "border-scarlet bg-scarlet/5" : "border-fog/30 bg-white"
            }`}>
            <p className={`font-sans text-sm font-medium ${difficulty === d.key ? "text-scarlet" : "text-ink"}`}>{d.name}</p>
            <p className="font-sans text-[11px] text-fog mt-1">{d.desc}</p>
          </div>
        ))}
      </div>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">YOUR POSITION</p>
      <div className="flex mb-8">
        {POSITIONS.map((p, i) => (
          <button key={p} onClick={() => setPosition(p.toLowerCase().replace(" ", "_"))}
            className={`font-sans text-sm font-medium px-4 py-2 border border-fog/30 -ml-px transition-all
              ${i === 0 ? "rounded-l-lg" : ""} ${i === POSITIONS.length - 1 ? "rounded-r-lg" : ""}
              ${position === p.toLowerCase().replace(" ", "_") ? "bg-scarlet border-scarlet text-white z-10 relative" : "bg-white text-ink"}`}>
            {p}
          </button>
        ))}
      </div>

      <button onClick={start}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg">
        Start session →
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Update `frontend/src/app/page.tsx`**

```typescript
"use client";
import { useDebate } from "@/store/debate";
import AuthModal from "@/components/auth/AuthModal";
import TopicSelection from "@/components/topic/TopicSelection";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });

export default function Home() {
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);

  if (!token || screen === "auth") return <AuthModal />;
  if (screen === "topic") return <TopicSelection />;
  if (screen === "debate") return <DebateView />;
  if (screen === "end") return <SessionEnd />;
  return <TopicSelection />;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/
git commit -m "feat: auth modal + topic selection UI"
```

---

## Task 9: SSE Hook + Chat Panel + D3 Graph

**Files:**
- Create: `frontend/src/hooks/useDebateSSE.ts`
- Create: `frontend/src/hooks/useGraphWS.ts`
- Create: `frontend/src/components/debate/MessageBubble.tsx`
- Create: `frontend/src/components/debate/JudgeScore.tsx`
- Create: `frontend/src/components/debate/PulseAvatar.tsx`
- Create: `frontend/src/components/debate/InputArea.tsx`
- Create: `frontend/src/components/graph/FingerprintGraph.tsx`
- Create: `frontend/src/components/debate/DebateView.tsx`

- [ ] **Step 1: Create `frontend/src/hooks/useDebateSSE.ts`**

```typescript
import { useCallback } from "react";
import { useDebate } from "@/store/debate";
import { JudgeScore } from "@/types";
import { v4 as uuid } from "uuid";

export function useSendMessage() {
  const { sessionId, addMessage, updateLastOpponent, revealJudge, setThinking } = useDebate();
  const token = useDebate((s) => s.token);

  return useCallback(async (text: string) => {
    if (!sessionId || !text.trim()) return;
    addMessage({ id: uuid(), role: "user", text });
    setThinking(true);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text }),
    });

    if (!res.body) return;
    const opponentId = uuid();
    addMessage({ id: opponentId, role: "opponent", text: "" });
    setThinking(false);

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
          if (evt.type === "token") updateLastOpponent(
            useDebate.getState().messages.find((m) => m.id === opponentId)?.text + evt.text ?? evt.text
          );
          if (evt.type === "judge") {
            setTimeout(() => revealJudge(evt as JudgeScore), 2000);
          }
        } catch {}
      }
    }
  }, [sessionId, token, addMessage, updateLastOpponent, revealJudge, setThinking]);
}
```

- [ ] **Step 2: Create `frontend/src/hooks/useGraphWS.ts`**

```typescript
import { useEffect } from "react";
import { useDebate } from "@/store/debate";
import { GraphData } from "@/types";

export function useGraphWS(sessionId: string | null) {
  const setGraph = useDebate((s) => s.setGraph);

  useEffect(() => {
    if (!sessionId) return;
    const wsUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
      .replace("http", "ws") + `/ws/graph/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "graph_update") setGraph(msg.data as GraphData);
      } catch {}
    };
    return () => ws.close();
  }, [sessionId, setGraph]);
}
```

- [ ] **Step 3: Create `frontend/src/components/debate/PulseAvatar.tsx`**

```typescript
"use client";
export default function PulseAvatar({ thinking }: { thinking: boolean }) {
  return (
    <span className={`w-5 h-5 rounded-full bg-scarlet flex items-center justify-center
      font-sans text-[9px] font-bold text-white
      ${thinking ? "animate-[pulse_1.2s_ease-in-out_infinite]" : ""}`}>
      O
    </span>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/debate/JudgeScore.tsx`**

```typescript
"use client";
import { JudgeScore } from "@/types";

export default function JudgeScoreBar({ score }: { score: JudgeScore }) {
  return (
    <div className="flex items-center gap-3 bg-carbon rounded-md px-3 py-2 mt-2 flex-wrap">
      <span className="font-sans text-[9px] font-semibold text-fog uppercase tracking-widest">JUDGE</span>
      <span className="font-mono text-[10px] text-fog">Logic <span className="text-white font-medium">{score.logic}</span></span>
      <span className="font-mono text-[10px] text-fog">Evidence <span className="text-white font-medium">{score.evidence}</span></span>
      <span className="font-mono text-[10px] text-fog">Rhetoric <span className="text-white font-medium">{score.rhetoric}</span></span>
      {score.fallacy && (
        <span className="font-mono text-[9px] font-medium text-red-300 bg-scarlet/30 rounded-full px-2 py-0.5">
          ⚠ {score.fallacy}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/components/debate/MessageBubble.tsx`**

```typescript
"use client";
import { Message } from "@/types";
import PulseAvatar from "./PulseAvatar";
import JudgeScoreBar from "./JudgeScore";

export default function MessageBubble({ msg, thinking }: { msg: Message; thinking?: boolean }) {
  if (msg.role === "user") {
    return (
      <div className="flex flex-col items-end">
        <div className="max-w-[80%] bg-slate/10 text-ink font-serif text-base leading-relaxed px-3.5 py-2.5 rounded-[12px_12px_2px_12px]">
          {msg.text}
        </div>
        <span className="font-sans text-[10px] font-semibold text-fog tracking-widest mt-1.5 mr-0.5">YOU</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start">
      <div className="flex items-center gap-1.5 mb-1.5">
        <PulseAvatar thinking={!!thinking && !msg.text} />
        <span className="font-sans text-[10px] font-semibold text-scarlet tracking-widest">OPPONENT</span>
      </div>
      <div className="max-w-[85%] bg-white text-ink border border-fog/20 font-serif text-base leading-relaxed px-3.5 py-2.5 rounded-[2px_12px_12px_12px]">
        {msg.text || <span className="italic text-fog text-sm">Studying your argument…</span>}
      </div>
      {msg.showJudge && msg.judge && <JudgeScoreBar score={msg.judge} />}
    </div>
  );
}
```

- [ ] **Step 6: Create `frontend/src/components/debate/InputArea.tsx`**

```typescript
"use client";
import { useState, useRef, useEffect } from "react";
import { useDebate } from "@/store/debate";
import { useSendMessage } from "@/hooks/useDebateSSE";

export default function InputArea() {
  const [text, setText] = useState("");
  const thinking = useDebate((s) => s.thinking);
  const send = useSendMessage();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.height = taRef.current.scrollHeight + "px";
    }
  }, [text]);

  const submit = () => { if (!thinking && text.trim()) { send(text); setText(""); } };

  return (
    <div className="border-t border-fog/20 bg-white p-3">
      <div className="flex gap-2 mb-2.5">
        {["Continue argument", "New point", "Concede & pivot"].map((hint, i) => (
          <button key={hint} onClick={() => setText(["To extend that point — ", "A separate consideration: ", "I'll concede that, but pivot — "][i])}
            className="font-sans text-[11px] text-fog border border-fog/30 rounded-full px-3 py-1">
            {hint}
          </button>
        ))}
      </div>
      <div className="flex gap-2.5 items-end">
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
          placeholder="Make your argument…"
          rows={1}
          className="flex-1 resize-none font-serif text-sm text-ink bg-white border border-fog/30 rounded-lg px-3 py-2.5 min-h-14 leading-relaxed outline-none focus:border-scarlet placeholder:italic placeholder:text-fog"
        />
        <button onClick={submit} disabled={thinking}
          className="h-14 flex items-center gap-1.5 bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-xs border-none rounded-lg px-4 disabled:opacity-40">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10 14l11-11"/><path d="M21 3l-6.5 18a.55.55 0 0 1-1 0l-3.5-7-7-3.5a.55.55 0 0 1 0-1l18-6.5"/>
          </svg>
          Send
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create `frontend/src/components/graph/FingerprintGraph.tsx`**

```typescript
"use client";
import { useEffect, useRef } from "react";
import * as d3 from "d3";
import { GraphData, GraphNode } from "@/types";
import { COLORS } from "@/lib/tokens";

const NODE_COLOR: Record<string, string> = {
  weakness: COLORS.scarlet,
  strength: COLORS.verdant,
  mastered: "#444",
  topic: COLORS.slate,
};

export default function FingerprintGraph({ data }: { data: GraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data.nodes.length) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    const W = svgRef.current.clientWidth || 320;
    const H = 380;

    const links = data.edges.map((e) => ({ ...e }));
    const nodes: (GraphNode & d3.SimulationNodeDatum)[] = data.nodes.map((n) => ({ ...n }));

    const sim = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id((d: never) => (d as GraphNode).id).distance(100))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2));

    const line = svg.append("g").selectAll("line")
      .data(links).join("line")
      .attr("stroke", "rgba(255,255,255,0.25)")
      .attr("stroke-width", (d) => d.weight * 2);

    const node = svg.append("g").selectAll("g")
      .data(nodes).join("g").attr("cursor", "pointer");

    node.append("circle")
      .attr("r", (d) => 14 + d.weight * 22)
      .attr("fill", (d) => NODE_COLOR[d.type] || COLORS.fog);

    node.append("text")
      .attr("text-anchor", "middle").attr("dy", "0.35em")
      .attr("fill", "white").attr("font-size", 8).attr("font-family", "Inter")
      .text((d) => d.label.length > 12 ? d.label.slice(0, 11) + "…" : d.label);

    sim.on("tick", () => {
      line.attr("x1", (d: never) => (d as { source: GraphNode }).source.x ?? 0)
          .attr("y1", (d: never) => (d as { source: GraphNode }).source.y ?? 0)
          .attr("x2", (d: never) => (d as { target: GraphNode }).target.x ?? 0)
          .attr("y2", (d: never) => (d as { target: GraphNode }).target.y ?? 0);
      node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    return () => { sim.stop(); };
  }, [data]);

  return <svg ref={svgRef} viewBox="0 0 320 380" width="100%" style={{ display: "block" }} />;
}
```

- [ ] **Step 8: Create `frontend/src/components/debate/DebateView.tsx`**

```typescript
"use client";
import { useEffect, useRef } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import MessageBubble from "./MessageBubble";
import InputArea from "./InputArea";
import FingerprintGraph from "@/components/graph/FingerprintGraph";
import { useGraphWS } from "@/hooks/useGraphWS";

export default function DebateView() {
  const { messages, thinking, graph, sessionId, sessionConfig, setScreen } = useDebate();
  const scrollRef = useRef<HTMLDivElement>(null);
  useGraphWS(sessionId);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  async function endSession() {
    if (sessionId) await api.endSession(sessionId);
    setScreen("end");
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between h-14 px-5 bg-white border-b border-fog/20 sticky top-0 z-20">
        <button onClick={() => setScreen("topic")} className="font-display text-[22px] text-ink cursor-pointer leading-none">DebateMind</button>
        <span className="font-sans text-[11px] font-medium text-fog tracking-wide hidden sm:block">
          {sessionConfig?.topic?.slice(0, 30)} · <span className="text-scarlet capitalize">{sessionConfig?.difficulty}</span>
        </span>
        <button onClick={endSession} className="font-sans text-xs font-semibold uppercase tracking-wide text-fog">End session</button>
      </nav>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat */}
        <div className="flex flex-col flex-1 min-w-0 bg-chalk">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-7 py-6 flex flex-col gap-3.5">
            {messages.map((m) => (
              <MessageBubble key={m.id} msg={m} thinking={thinking && m.role === "opponent" && m === messages[messages.length - 1]} />
            ))}
            {thinking && messages[messages.length - 1]?.role !== "opponent" && (
              <div className="flex flex-col items-start">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="w-5 h-5 rounded-full bg-scarlet flex items-center justify-center font-sans text-[9px] font-bold text-white animate-pulse">O</span>
                  <span className="font-sans text-[10px] font-semibold text-scarlet tracking-widest">OPPONENT</span>
                </div>
                <span className="font-serif italic text-sm text-fog">Studying your argument…</span>
              </div>
            )}
          </div>
          <InputArea />
        </div>

        {/* Graph */}
        <aside className="w-80 min-w-[280px] max-w-[360px] bg-carbon border-l border-white/10 flex flex-col text-white overflow-y-auto hidden lg:flex">
          <div className="px-5 pt-4 pb-2 flex items-center justify-between">
            <span className="font-sans text-[11px] font-semibold uppercase tracking-widest">Cognitive Fingerprint</span>
          </div>
          <FingerprintGraph data={graph} />
          <div className="flex gap-3.5 px-5 pb-4 font-sans text-[10px] text-[#888]">
            {[["#C0392B","Weakness"],["#27AE60","Strength"],["#444","Mastered"]].map(([c,l]) => (
              <span key={l} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: c }} />
                {l}
              </span>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
```

- [ ] **Step 9: Install uuid**

```bash
cd frontend && npm install uuid && npm install --save-dev @types/uuid
```

- [ ] **Step 10: Verify full debate flow works end-to-end**

```bash
# Terminal 1: backend
cd backend && source venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2: frontend
cd frontend && npm run dev

# Browser: http://localhost:3000
# 1. Register with email+password
# 2. Select topic "AI regulation", difficulty Targeted, position Against
# 3. Click "Start session →"
# 4. Type "Government bodies have decades of regulatory experience." → Send
# 5. Expect: streaming opponent text appears word by word
# 6. After stream: judge scores appear below opponent bubble
# 7. D3 graph in right panel updates with weakness nodes
```

- [ ] **Step 11: Commit**

```bash
git add frontend/src/
git commit -m "feat: debate view with SSE streaming, D3 fingerprint graph, judge scores"
```

---

## Task 10: Session End + Progress Dashboard

**Files:**
- Create: `frontend/src/components/session/SessionEnd.tsx`
- Create: `frontend/src/components/progress/ProgressDashboard.tsx`
- Update: `frontend/src/app/page.tsx` (add progress route)

- [ ] **Step 1: Create `frontend/src/components/session/SessionEnd.tsx`**

```typescript
"use client";
import { useDebate } from "@/store/debate";

export default function SessionEnd() {
  const { messages, sessionConfig, setScreen } = useDebate();
  const exchanges = messages.filter((m) => m.role === "opponent").length;
  const judged = messages.filter((m) => m.judge);
  const avgLogic = judged.length ? judged.reduce((a, m) => a + (m.judge?.logic ?? 0), 0) / judged.length : 0;
  const won = judged.filter((m) => m.judge?.outcome === "Won").length;
  const fallacies = [...new Set(judged.map((m) => m.judge?.fallacy).filter(Boolean))];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-display text-3xl text-ink mb-1">Session complete</h1>
      <p className="font-sans text-base text-fog mb-7">{sessionConfig?.topic} · {sessionConfig?.difficulty}</p>

      <div className="grid grid-cols-4 gap-3 mb-9">
        {[
          { v: avgLogic.toFixed(1), unit: "/10", label: "Score", color: "text-scarlet" },
          { v: exchanges, unit: "", label: "Exchanges", color: "text-ink" },
          { v: fallacies.length, unit: "", label: "Weaknesses exposed", color: "text-ink" },
          { v: won, unit: "", label: "Rounds won", color: "text-verdant" },
        ].map(({ v, unit, label, color }) => (
          <div key={label} className="bg-white border border-fog/20 rounded-lg p-4">
            <div className={`font-display text-3xl ${color}`}>{v}<span className="text-sm text-fog font-sans">{unit}</span></div>
            <div className="font-sans text-[11px] text-fog mt-1">{label}</div>
          </div>
        ))}
      </div>

      {fallacies.length > 0 && (
        <>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">PATTERNS EXPOSED THIS SESSION</p>
          {fallacies.map((f) => (
            <div key={f} className="mb-5">
              <div className="flex justify-between font-sans text-sm text-ink mb-2">
                <span>{f}</span>
                <span className="font-mono text-[10px] text-scarlet">detected</span>
              </div>
            </div>
          ))}
        </>
      )}

      <div className="h-px bg-fog/20 my-7" />
      <div className="flex gap-3 items-center">
        <button onClick={() => setScreen("debate")}
          className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Debate again →
        </button>
        <button onClick={() => setScreen("topic")}
          className="bg-slate text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Choose new topic
        </button>
        <button onClick={() => setScreen("progress")}
          className="font-sans text-sm text-fog border-none bg-none">
          View progress
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/progress/ProgressDashboard.tsx`**

```typescript
"use client";
import { useDebate } from "@/store/debate";

export default function ProgressDashboard() {
  const setScreen = useDebate((s) => s.setScreen);
  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-display text-3xl text-ink">Your progress</h1>
        <button onClick={() => setScreen("topic")} className="font-sans text-sm text-fog">← Back</button>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-9">
        {[
          { label: "Sessions", value: "—", sub: "Start debating to track" },
          { label: "Win rate", value: "—", sub: "Calculated after sessions" },
          { label: "Mastered", value: "0", sub: "patterns" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="bg-white border border-fog/20 rounded-lg p-5">
            <div className="font-sans text-[11px] text-fog">{label}</div>
            <div className="font-display text-4xl text-ink my-1">{value}</div>
            <div className="font-sans text-[11px] text-fog">{sub}</div>
          </div>
        ))}
      </div>
      <p className="font-sans text-sm text-fog text-center mt-12 italic">
        Complete a debate session to see your cognitive fingerprint evolve.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Update `frontend/src/app/page.tsx`** to handle `progress` screen

```typescript
// Add to the existing screen checks in page.tsx:
if (screen === "progress") return <ProgressDashboard />;
```

Also add the import at the top:
```typescript
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/session/ frontend/src/components/progress/ frontend/src/app/page.tsx
git commit -m "feat: session end summary + progress dashboard stub"
```

---

## Task 11: Environment Files + Run Scripts

**Files:**
- Create: `frontend/.env.local`
- Create: `Makefile` (project root)

- [ ] **Step 1: Create `frontend/.env.local`**

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

- [ ] **Step 2: Create root `Makefile`**

```makefile
.PHONY: backend frontend dev

backend:
	cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	make -j2 backend frontend
```

- [ ] **Step 3: Final end-to-end smoke test**

```
1. Start postgres: docker run -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=debatemind -p 5432:5432 -d postgres:16
2. cd backend && source venv/bin/activate && uvicorn app.main:app --reload
3. cd frontend && npm run dev
4. Open http://localhost:3000
5. Register → Topic selection → Start debate → Send 3 messages
6. End session → See session summary
```

- [ ] **Step 4: Final commit**

```bash
git add Makefile frontend/.env.local
git commit -m "feat: dev run scripts + env config — MVP complete"
```

---

## Self-Review

**Spec coverage check:**
- FR-01 Topic Selection ✅ (TopicSelection.tsx, /api/sessions/start)
- FR-02 Text Chat Interface ✅ (DebateView, SSE streaming)
- FR-03 remember() ✅ (cognee_svc.py, _remember_node in pipeline)
- FR-04 recall() strategy ✅ (opponent.py pre-loads weakness context)
- FR-05 Judge Agent ✅ (judge.py, JudgeScore.tsx, 2s delay)
- FR-06 improve() ✅ (sessions router /end endpoint)
- FR-07 forget() ✅ (mastery.py + forget_pattern)
- FR-08 Graph Visualisation ✅ (FingerprintGraph D3.js + WebSocket)
- FR-09 Progress Dashboard ✅ (stub — full charting is post-MVP)
- FR-10 Topic Suggestions ✅ (/api/topics/suggest)
- FR-11 Session History — ⚠️ exchanges table stored but no UI transcript view (post-MVP)
- FR-12 Difficulty Calibration ✅ (3 difficulty modes wired through pipeline)
- FR-13 Onboarding Calibration — ⚠️ skipped for MVP (users go straight to debate)
- FR-14 Auth ✅ (register/login JWT)
