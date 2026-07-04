<p align="center">
  <img src="docs/assets/hero.jpg" alt="DebateMind — an AI opponent that remembers how you think" width="100%" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-frontend-000000?logo=nextdotjs&logoColor=white" alt="Next.js" />
  <img src="https://img.shields.io/badge/LangGraph-text%20bot-1C3C3C?logo=langchain&logoColor=white" alt="LangGraph" />
  <img src="https://img.shields.io/badge/OpenAI%20Realtime-voice%20bot-412991?logo=openai&logoColor=white" alt="OpenAI Realtime" />
  <img src="https://img.shields.io/badge/Cognee-memory%20layer-4F8CFF" alt="Cognee" />
  <img src="https://img.shields.io/badge/Neo4j-knowledge%20graph-4581C3?logo=neo4j&logoColor=white" alt="Neo4j" />
  <img src="https://img.shields.io/badge/pgvector-embeddings-336791?logo=postgresql&logoColor=white" alt="pgvector" />
</p>

<p align="center">
  <a href="#why-a-memory-layer"><b>Why</b></a> ·
  <a href="#cognee-as-the-memory-layer--knowledge-graph"><b>Memory Layer</b></a> ·
  <a href="#one-memory-two-bots-text--voice"><b>Text + Voice</b></a> ·
  <a href="#architecture"><b>Architecture</b></a> ·
  <a href="#setup"><b>Quick Start</b></a>
</p>

---

An AI-powered debate trainer that sharpens your argumentation through adversarial practice. You debate an adaptive AI opponent — by **text** or by **voice** — and it learns your logical weaknesses, recurring fallacies, and thinking style over time, then targets them with counterarguments tuned to *you*.

The thing that makes that adaptation possible is a persistent, cross-session **memory layer built on [Cognee](https://github.com/topoteretes/cognee)**. Every argument you make becomes a typed node in a per-user **knowledge graph**; every new debate — text or voice — recalls that graph to decide how to challenge you. This README focuses on how that memory layer is built, wired, and shared across both bots.

---

## Table of Contents

- [Why a memory layer](#why-a-memory-layer)
- [Cognee as the memory layer & knowledge graph](#cognee-as-the-memory-layer--knowledge-graph)
  - [The memory lifecycle: Remember → Recall → Improve → Forget](#the-memory-lifecycle)
  - [The Cognee functions we use](#the-cognee-functions-we-use)
  - [The public memory API](#the-public-memory-api)
  - [Dual-write: prose + typed nodes](#dual-write-prose--typed-nodes)
  - [Storage backends and how Cognee is wired](#storage-backends-and-how-cognee-is-wired)
  - [Multi-user isolation](#multi-user-isolation)
- [The ontology: what it is and why we need it](#the-ontology-what-it-is-and-why-we-need-it)
- [One memory, two bots (text + voice)](#one-memory-two-bots-text--voice)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Commands](#commands)

---

## Why a memory layer

A debate coach that forgets you after every session is useless. To get better you need an opponent that *remembers*:

- **which fallacies you keep committing** (StrawMan, SlipperySlope, AppealToAuthority …),
- **how you reason** (Logic vs. Evidence vs. Rhetoric),
- **which topics you're weak on**, and
- **which weaknesses you've already mastered** (so it stops beating a dead horse).

A plain database of rows can store those facts, but it can't *relate* them — it can't tell you that your weak-evidence arguments cluster around one knowledge domain, or semantically retrieve "the arguments where you lost on shaky evidence" for the opponent's next move. That is what a **knowledge graph + vector memory** gives us, and Cognee is the engine that builds and serves it.

We use Cognee as a **cognitive fingerprint store**: a living, per-user graph of how that person argues, that both the text bot and the voice bot read from and write to.

---

## Cognee as the memory layer & knowledge graph

All memory code lives in [`debatemind-backend/debatemind/cognee/`](debatemind-backend/debatemind/cognee/) and is exposed through a single stable import surface, [`debatemind/cognee/__init__.py`](debatemind-backend/debatemind/cognee/__init__.py):

```python
from debatemind.cognee import remember_argument, recall_weaknesses, forget_pattern
```

Call sites (the debate pipeline, the voice tools, the routers) import from here so the internal layout can change without breaking them.

### The memory lifecycle

Cognee models memory as a lifecycle, and DebateMind uses all four stages:

| Stage | What happens | Our functions | Cognee primitives |
|-------|--------------|---------------|-------------------|
| **Remember** | An argument / session / personal fact is ingested as prose **and** written as a typed graph node | `remember_argument`, `remember_session_summary`, `remember_personal_fact` | `cognee.add()` → `cognee.cognify()` → `add_data_points()` |
| **Recall** | The opponent retrieves this user's relevant weaknesses / facts, ranked by semantic relevance | `recall_weaknesses`, `recall_topic_weaknesses`, `recall_user_facts` | vector search + `get_graph_data()` + ownership filter |
| **Improve** | The graph is re-cognified so links across a user's records get richer over time | `improve_fingerprint` | `cognee.cognify()` |
| **Forget** | A mastered pattern (or a fact the user retracts) is **truly deleted** from both the graph and the vector store | `forget_pattern`, `forget_personal_fact` | `delete_nodes()` + `delete_data_points()` |

**Forget is real deletion, not a soft flag.** When you master a pattern, [`forget.py`](debatemind-backend/debatemind/cognee/forget.py) removes the node from the Neo4j graph *and* its embedding from pgvector, so it can never resurface through recall again. Postgres' `MasteryLog` remains the source of truth for *gating* the opponent; the Cognee delete makes the underlying evidence actually disappear from recall and from the knowledge-graph explorer.

### The Cognee functions we use

DebateMind deliberately uses Cognee at two levels — the high-level pipeline **and** the low-level engines — because each memory operation needs a different guarantee:

**Ingestion (writes):**
- **`cognee.add(text, dataset_name=f"user_{id}_fingerprint")`** — ingests a natural-language description of an argument/session/fact into that user's own dataset. Each user gets an isolated dataset so prose chunks stay scoped per person.
- **`cognee.cognify(datasets=dataset, ontology_file_path=ontology_file())`** — the graph-building pass. Cognee's LLM extractor reads the prose, extracts entities and relationships, and links them — *guided by our ontology* (see below). This is where a sentence like *"the user made a StrawMan argument with Weak evidence and lost"* becomes typed, linked graph structure.
- **`add_data_points([...])`** ([`cognee.tasks.storage`](debatemind-backend/debatemind/cognee/fingerprint.py)) — writes our **explicitly typed** `DataPoint` nodes (`UserProfile`, `Topic`, `ArgumentRecord`, `SessionSummary`, `PersonalFact`) alongside the LLM-extracted graph, deduped by a deterministic `id`.

**Retrieval (reads):**
- **`get_vector_engine().search(collection, query_text, limit)`** — semantic ranking. We query per-class vector collections (e.g. `ArgumentRecord_summary`) with a natural-language query like *"fallacy weak evidence poor argument outcome lost"* to rank a user's records by relevance.
- **`get_graph_engine().get_graph_data()`** — loads the raw graph so we can filter nodes down to the ones this user owns, and so the knowledge-graph explorer can render the actual entity web.

**Deletion:**
- **`get_graph_engine().delete_nodes(ids)`** + **`get_vector_engine().delete_data_points(collection, ids)`** — the two-store delete that makes *forget* permanent.

**Configuration:**
- **`cognee.config.set_relational_db_config / set_vector_db_config / set_graph_db_config / set_llm_config`** and **`cognee.modules.engine.operations.setup.setup()`** — done once at startup in [`services/cognee_config.py`](debatemind-backend/debatemind/services/cognee_config.py) and in the Celery worker's `worker_init`.

### The public memory API

Everything the rest of the app is allowed to call, from [`cognee/__init__.py`](debatemind-backend/debatemind/cognee/__init__.py):

```python
# Remember
remember_argument(user_id, session_id, topic, claim_text, pattern_type,
                  fallacy, evidence_quality, outcome, reasoning="")
remember_session_summary(user_id, session_id, topic, mode, difficulty,
                         rounds_played, win_rate, avg_logic, avg_evidence,
                         avg_rhetoric, weak_patterns, coaching_note="")
remember_personal_fact(user_id, session_id, fact_text)

# Recall
recall_weaknesses(user_id, exclude_patterns=None)          -> list[dict]
recall_topic_weaknesses(user_id, topic, exclude_patterns)  -> list[dict]
recall_user_facts(user_id, topic="")                       -> list[dict]

# Improve
improve_fingerprint(user_id)

# Forget
forget_pattern(user_id, pattern_type)
forget_personal_fact(user_id, node_id) -> {"status": "forgotten" | "not_found"}
```

Plus [`graph_view.user_graph_view(user_id)`](debatemind-backend/debatemind/cognee/graph_view.py), a read-only, user-scoped projection of the raw Cognee graph that powers the in-app **knowledge-graph explorer** (`GET /api/users/me/knowledge-graph`).

### Dual-write: prose + typed nodes

Every `remember_*` call writes the **same fact twice**, on purpose (see [`fingerprint.py`](debatemind-backend/debatemind/cognee/fingerprint.py)):

1. **Prose + `cognify()`** — a human-readable sentence is `add()`-ed and cognified. This feeds Cognee's LLM extractor the rich, linkable signal it needs to grow the wider entity web (linking an argument to a `KnowledgeDomain`, a `ReasoningApproach`, a `Fallacy`, etc., per the ontology). Terse `key: value` markers alone give the extractor little to work with, so we generate a real sentence like:

   > *In a debate about "AI regulation", the user made a StrawMan argument with Weak evidence and committed the AdHominem fallacy; the outcome was lost. Reasoning: …*

2. **Typed `DataPoint` node via `add_data_points()`** — a structured [`ArgumentRecord`](debatemind-backend/debatemind/cognee/schema.py) (or `SessionSummary` / `PersonalFact`) with exact fields (`pattern_type`, `fallacy`, `evidence_quality`, `outcome`, `user_id`, …).

Why both? The typed node gives `forget()` a **precise node to delete** and gives the graph explorer a **stable vocabulary to render**, independent of whatever the LLM happened to infer. The prose/cognify pass gives us the **rich, fuzzy, semantically-searchable** web on top. If `add_data_points()` fails, the prose write has already succeeded, so a write degrades gracefully instead of being lost.

The typed schema:

| Node | Role |
|------|------|
| `UserProfile` | One per user; anchors every other node in their graph |
| `Topic` | A debate topic, deduped per `(user_id, name)` |
| `ArgumentRecord` | One argument the user made — the durable weakness/strength record |
| `SessionSummary` | Per-session rollup: thinking style, win rate, weak patterns |
| `PersonalFact` | Something the user revealed (name, background, likes) |

### Storage backends and how Cognee is wired

In the default **`local`** mode ([`cognee_config.py`](debatemind-backend/debatemind/services/cognee_config.py) + [`docker-compose.yml`](docker-compose.yml)), Cognee is backed by:

| Concern | Backend | Where |
|---------|---------|-------|
| Relational store | **Postgres** | `cognee-db` service, `pgvector/pgvector:pg16`, port **5433** |
| Vector store | **pgvector** | same `cognee-db` instance |
| Graph store | **Neo4j** | `neo4j:5-community`, bolt **7687**, browser UI **7474** |
| Cognify LLM | **OpenRouter** (`custom` provider, `openai/gpt-4.1-mini`) | shares the debate agents' key |
| Embeddings | **OpenAI direct** (`text-embedding-3-large`, 3072-dim) | `api.openai.com` |

Two wiring details worth calling out:

- **Cognify LLM calls are routed through OpenRouter** so Cognee's internal reasoning reuses the same gateway/key as the debate agents — there is no separate Cognee key.
- **Embeddings must hit OpenAI directly, never OpenRouter.** OpenRouter is a chat-completions gateway with no `/embeddings` endpoint; routing embeddings through it 404s and *silently disables the entire memory layer* (cognify fails in the background, recall returns `[]`). So `OPENAI_API_KEY` is required for memory to function locally.

Set `COGNEE_MODE=cloud` to leave Cognee's storage at its own hosted defaults instead of the self-hosted stack.

### Multi-user isolation

This is a security-critical detail. In Cognee 0.1.40 the **graph store and per-class vector collections are global across every user** — `add_data_points()` has no `dataset_name`, and there is no dataset-scoped graph query. So we never trust the store to isolate users for us:

- Every typed node carries an explicit **`user_id` property**.
- Every reader — [`recall.py`](debatemind-backend/debatemind/cognee/recall.py), [`forget.py`](debatemind-backend/debatemind/cognee/forget.py), [`graph_view.py`](debatemind-backend/debatemind/cognee/graph_view.py) — **filters on `user_id` after loading**, and never trusts a query parameter for isolation.
- Vector search supplies only a **relevance ranking over an already-owned candidate set** — it's a ranking aid, not the isolation boundary. If a user's own records get crowded out of the global top-K, recall falls back to their owned set unranked rather than returning nothing.

---

## The ontology: what it is and why we need it

The ontology is a static, hand-authored OWL file: [`cognee/ontology/debate_domain.owl`](debatemind-backend/debatemind/cognee/ontology/debate_domain.owl). It is passed to every `cognify()` call via `ontology_file_path=ontology_file()`.

### What it is

A **controlled vocabulary of how a person thinks** — a wide, generic model of reasoning, not a subject taxonomy. It declares:

- **Structural classes**: `Thinker`, `Argument` (with `Claim` / `Rebuttal` / `Counterargument` subclasses), `Session`, `Topic`.
- **Cognitive dimensions**: `ThinkingStyle` (Logic / Evidence / Rhetoric), `ReasoningApproach` (Deductive, Inductive, Abductive, Causal, FirstPrinciples …), `ArgumentPattern`, `Fallacy`, `CognitiveBias`.
- **Evidence dimensions**: `EvidenceQuality` (Strong / Moderate / Weak / Absent), `EvidenceType` (Empirical, Statistical, Anecdotal …).
- **Performance dimensions**: `Outcome`, `MasteryStatus`, `SkillLevel`.
- **An OPEN knowledge root**: `KnowledgeDomain`. We deliberately do **not** hardcode subjects — the concrete domains a user debates are created dynamically by the extractor at runtime and hung off this root via `aboutTopic` / `discussesDomain`. The graph grows to fit the person; we never presume what anyone debates about.
- **Object properties** that wire it together: `usesPattern`, `exhibitsFallacy`, `hasEvidenceQuality`, `exhibitsThinkingStyle`, `hasOutcome`, `hasMasteryStatus`, and more.

### Why we need it

Without an ontology, `cognify()`'s LLM extractor invents ad-hoc entity types from the prose — inconsistent, un-joinable, and impossible to query reliably. The ontology turns *"the extractor might mention a fallacy"* into *"the extractor attaches this argument to the `StrawMan` individual of type `ArgumentPattern`+`Fallacy`."* Concretely, it buys us:

1. **A stable, typed graph** the opponent and the graph explorer can rely on.
2. **Semantic linking** — an argument gets connected to its reasoning approach, evidence type, cognitive bias, and knowledge domain, so recall can reason over *relationships*, not just keywords.
3. **An accuracy contract.** The `ArgumentPattern` and `EvidenceQuality` individuals mirror **exactly** the strings the grading pipeline writes (`agents/constants.PATTERN_TYPES`, the extractor's `evidence_quality` enum, and the voice note-map in `voice_agent/tools.py`). `tests/test_ontology.py` enforces this so the vocabulary and the graders can never drift. That alignment is what makes *"the ontology declares a type"* actually become *"the user's data lands on that type."*

The file is **read-only at runtime** — Cognee never writes it. It degrades gracefully: if the asset is missing, `ontology_file()` returns `None` and `cognify()` falls back to an empty ontology instead of crashing.

---

## One memory, two bots (text + voice)

Both bots write to and read from the **same per-user Cognee dataset** (`user_{id}_fingerprint`) and the same global typed graph. This is the payoff: **a weakness you reveal by voice surfaces when you next debate by text, and vice versa.** Memory is cross-modal.

Because Cognee's `add()` + `cognify()` is slow (seconds; up to a 300s timeout), **all writes are dispatched to a Celery worker** ([`worker/tasks.py`](debatemind-backend/debatemind/worker/tasks.py)) so a debate turn never blocks on graph-building. Reads are cached with a TTL and invalidated the moment a write completes.

### Text bot (LangGraph pipeline)

[`agents/pipeline.py`](debatemind-backend/debatemind/agents/pipeline.py) compiles a LangGraph state machine:

```
extract → opponent → judge → mastery → remember → remember_facts → [prune]
```

- **`opponent` node** ([`agents/opponent.py`](debatemind-backend/debatemind/agents/opponent.py)) — **recalls**: calls `recall_weaknesses()` and `recall_user_facts()` (through a 1-hour TTL cache), filters out mastered patterns, and injects the results into the opponent's system prompt so it targets your real weak spots.
- **`remember` node** — **writes**: dispatches `remember_argument_task` to Celery with the judged argument (scores embedded in the claim text so recall can match on thinking-style dimensions), then invalidates the weakness cache so the very next turn sees the fresh write.
- **`remember_facts` node** — dispatches `remember_personal_fact_task` for anything personal you revealed.
- **`prune` node** — on mastery, dispatches `forget_pattern_task` to delete that pattern's evidence from the graph.

### Voice bot (OpenAI Realtime API)

The voice agent runs over WebRTC with the OpenAI Realtime API; the backend mints ephemeral keys and executes tool calls.

- **Session start** ([`voice_agent/session.py`](debatemind-backend/debatemind/voice_agent/session.py)) — **recalls** by calling `recall_weaknesses()` **and** `recall_topic_weaknesses()` in parallel, merging and deduping them (topic-specific first), and baking them into the realtime session's system prompt as internal strategy context.
- **`get_knowledge_context` tool** ([`voice_agent/tools.py`](debatemind-backend/debatemind/voice_agent/tools.py)) — lets the live model **recall** more weaknesses mid-conversation.
- **`save_debate_observation` tool** — **writes**: when the model observes a fallacy / strong argument / position flip, it dispatches `remember_argument_task` into the *same* fingerprint the text bot uses (via the `_COGNEE_NOTE_MAP`).
- **Voice mastery** — when you land enough strong arguments in a voice session, it dispatches `forget_pattern_task` **and** writes a `MasteryLog` row, mirroring the text pipeline exactly.

```
                    ┌──────────────────────────────────────────┐
                    │      Cognee memory layer (per user)        │
   TEXT BOT ──────► │  dataset: user_{id}_fingerprint            │ ◄────── VOICE BOT
   (LangGraph)      │  ┌──────────┐   ┌──────────────┐          │      (OpenAI Realtime)
                    │  │  Neo4j    │   │   pgvector    │          │
   recall_* ◄───────┤  │  graph    │   │  embeddings   │          ├───────► recall_*
   remember_* ─────►│  └──────────┘   └──────────────┘          │◄─────── save_observation
   forget_pattern ─►│         guided by debate_domain.owl        │◄─────── forget_pattern
                    └──────────────────────────────────────────┘
                              ▲ writes dispatched via Celery ▲
```

---

## Architecture

```
┌─────────────┐   SSE / WebRTC    ┌──────────────────────────────┐
│  Frontend   │ ◄───────────────► │        FastAPI backend        │
│  (Next.js)  │                   │  ┌────────────┐  ┌──────────┐ │
└─────────────┘                   │  │ Text bot   │  │ Voice bot│ │
                                  │  │ LangGraph  │  │ Realtime │ │
                                  │  └─────┬──────┘  └────┬─────┘ │
                                  │        │  recall/write │       │
                                  │   ┌────▼───────────────▼────┐  │
                                  │   │  debatemind.cognee API   │  │
                                  │   └────┬───────────────┬────┘  │
                                  └────────┼───────────────┼───────┘
                                    reads  │        writes  │ (Celery)
                                  ┌────────▼────┐   ┌───────▼────────┐
                                  │ Postgres    │   │ Cognee stores  │
                                  │ (app data)  │   │ Neo4j+pgvector │
                                  └─────────────┘   └────────────────┘
```

- **Frontend (Next.js)** — debate UI, streaming responses, D3 fingerprint/knowledge-graph visualizations.
- **Backend (FastAPI)** — debate orchestration, the Cognee memory API, JWT/Clerk auth.
- **Celery worker** — runs all Cognee `add()`/`cognify()`/`forget()` writes off the request path (same image as the API, shares Redis + all `COGNEE_*`/`OPENAI_*`/`OPENROUTER_*` env).
- **App Postgres** (`db`, port 5437) — users, sessions, exchanges, `MasteryLog`.
- **Cognee stores** — Neo4j (graph) + pgvector (embeddings + relational).

---

## Tech stack

**Backend**
- FastAPI (Python), SQLAlchemy async, Alembic
- **Cognee** — knowledge-graph + vector memory layer (Neo4j + pgvector)
- LangGraph — the text debate pipeline
- OpenAI Realtime API — the voice bot
- Celery + Redis — async memory writes
- OpenRouter — debate + cognify LLM calls; OpenAI — embeddings + voice

**Frontend**
- Next.js, React, TypeScript
- TailwindCSS
- D3.js — fingerprint & knowledge-graph visualization
- Server-Sent Events (text streaming) + WebRTC (voice)

---

## Setup

### Prerequisites
- Node.js 18+ and npm
- Python 3.12+ and [`uv`](https://github.com/astral-sh/uv)
- Docker (Postgres, pgvector, Neo4j, Redis)

### Quick start

Bring up all infra (app Postgres, cognee-db/pgvector, Neo4j, Redis) and then run the backend, frontend, and Celery worker together:

```bash
cd debatemind-backend
make start          # = make infra-up && make dev
```

- Frontend → http://localhost:3000
- Backend  → http://localhost:8001
- Neo4j browser → http://localhost:7474

Run pieces individually:

```bash
make infra-up            # docker compose: db, cognee-db, redis, neo4j
make debatemind-backend  # FastAPI on :8001
make frontend            # Next.js on :3000
make celery              # Celery worker (required for memory writes)
```

> The Celery worker is **required** for the memory layer — `remember_*` and `forget_*` are dispatched to it. Without it, recalls still work but nothing new is written to the graph.

---

## Environment variables

### Frontend (`frontend/.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:8001
```

### Backend (`debatemind-backend/.env`)
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5437/debatemind
SECRET_KEY=<random-secret>

# LLM gateway — also used by Cognee's cognify() calls
OPENROUTER_API_KEY=<your-openrouter-key>

# REQUIRED for the Cognee memory layer: embeddings must hit OpenAI directly
# (OpenRouter has no /embeddings endpoint). Also required for the voice bot.
OPENAI_API_KEY=<your-openai-key>

# Redis broker/backend for the Celery worker that runs Cognee writes
REDIS_URL=redis://localhost:6379/0

# Cognee storage backend: "local" (default — self-hosted cognee-db + neo4j
# from docker-compose.yml) or "cloud" (Cognee's own hosted defaults).
COGNEE_MODE=local

# Cognee self-hosted stores (only used when COGNEE_MODE=local; defaults match
# docker-compose.yml — override only if you changed those services)
COGNEE_DB_HOST=localhost
COGNEE_DB_PORT=5433
COGNEE_DB_NAME=cognee
COGNEE_DB_USERNAME=cognee
COGNEE_DB_PASSWORD=cognee
NEO4J_URL=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=debatemind

# Optional: override debate models (any OpenRouter slug)
# FAST_MODEL=openai/gpt-4.1-mini
# MAIN_MODEL=openai/gpt-4.1-mini
```

See `debatemind-backend/.env.example` for the full list.

---

## Commands

| Command | What it does |
|---------|--------------|
| `make start` | Infra up, then backend + frontend + Celery in parallel |
| `make infra-up` / `make infra-down` | Start / stop Postgres, cognee-db, Redis, Neo4j |
| `make dev` | Backend + frontend + Celery worker (no infra) |
| `make debatemind-backend` | FastAPI on :8001 |
| `make frontend` | Next.js on :3000 |
| `make celery` | Celery worker (Cognee memory writes) |
| `make infra-logs` | Tail infra container logs |

### Cloud worker deployment

The Celery worker must run as a **second process from the same image** as the API, with the same environment (especially `REDIS_URL` and all `COGNEE_*`/`OPENAI_*`/`OPENROUTER_*` vars), using:

```bash
celery -A debatemind.worker.celery_app worker --loglevel=info --concurrency=2
```
