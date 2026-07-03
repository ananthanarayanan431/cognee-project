# DebateMind — 3-Minute Demo Kit

Three deliverables:
1. **Video edit plan** — which screen to show at each timestamp
2. **Voiceover script** — timed to 3:00 (~430 words, ~150 wpm)
3. **Pitch slides** — 10 slides of ready-to-drop content

> **One-liner:** *DebateMind is an AI debate trainer with a memory — it learns how you think, remembers the fallacies you keep making, and hunts your weak spots harder every session, whether you argue by text or by voice.*

---

## PART 1 — VIDEO EDIT PLAN (screen cues)

Total runtime **3:00**. The left column is the clock; record your screen actions to line up with the voiceover lines in Part 2. "Cut to" = hard cut; "Push in" = slow zoom for emphasis.

| Time | On screen | Editing note |
|------|-----------|--------------|
| **0:00–0:08** | **Title card** — logo + "DebateMind — the debate coach that remembers you" | Static title over subtle motion. Optional: a face-cam corner if you present. |
| **0:08–0:25** | **B-roll of the Landing page**, slow scroll | Establishes the product. Keep it moving; don't dwell. |
| **0:25–0:45** | **Topic Selection screen** — hover the domain tabs (Policy/Tech/Society/Life), then hit **"Generate topic"** | Show the AI-generated topic appear. Highlight the **chat icon** and **phone icon** on a topic row with a callout arrow. |
| **0:45–1:10** | **Debate view — TEXT.** Type an argument and submit. | **This is the money shot.** Capture the stage labels animating: "Analysing your argument…" → "Building a counterargument…" Then the opponent reply streaming word-by-word. |
| **1:10–1:30** | **Judge scores + live Fingerprint graph** (right panel) | Push in on the **Logic / Evidence / Rhetoric** score bar as it fills. Then cut to the **D3 fingerprint graph** — point out a red **Weakness** node. |
| **1:30–1:38** | Callout overlay on the graph legend: **Weakness / Strength / Mastered** | Freeze-frame + text label. This sells the "it's learning you" idea. |
| **1:38–2:05** | **Voice debate.** Nav toggle → **Voice**, click **Connect**, speak one line. | Show the live **transcript** filling in. **The key beat:** the voice opponent references a weakness you showed *in the text debate*. Add a caption: *"Same memory. Different mode."* |
| **2:05–2:22** | **Session End screen** — overall score /10 + **before/after fingerprint changes** (WeaknessBar) | Push in on a pattern's before→after bar. This is proof of measurable change. |
| **2:22–2:35** | **Progress Dashboard** — day streak, win rate, thinking-style bars, **Mastered patterns** | Quick pan. Land on a "Mastered" pill to set up the "Forget" point. |
| **2:35–2:48** | **Architecture diagram** (from Slide 5) OR the raw **Knowledge Graph view** | Cut away from the app to show there's real engineering underneath. |
| **2:48–3:00** | **Closing title card** — logo + tagline + "Built at [Hackathon name]" | End on the one-liner. Hold 3s of silence at the end for a clean cut. |

**Recording tips**
- Pre-seed a user account that already has 2–3 past sessions so the fingerprint graph and dashboard look populated (an empty graph kills the demo).
- Do the text debate and voice debate on the **same topic** so the cross-modal memory moment is obvious.
- Record at 1920×1080, hide bookmarks bar, use a clean browser profile.
- Capture each segment as its own clip — easier to trim to the voiceover than one long take.

---

## PART 2 — VOICEOVER SCRIPT (3:00)

Read at a relaxed ~150 wpm. Timestamps match Part 1. `[beat]` = short pause.

**[0:00 — Problem / hook]**
> Everyone says the way to get better at arguing is to practice against someone smarter than you. But every AI debate partner has the same flaw — it forgets you the moment the conversation ends. [beat] It can't see that you lean on the same logical fallacy every single time, or that you crumble on economic topics but dominate on ethics.

**[0:25 — Solution]**
> So we built **DebateMind** — an AI debate trainer that actually *remembers how you think*. You pick a topic, or let it generate one, and you can debate by text… or by voice. [beat] Let's argue.

**[0:45 — Text demo]**
> I make my argument. Behind the scenes, DebateMind isn't just replying — it's *analysing*. It classifies my reasoning, detects the fallacy I just used, and then builds a counterargument aimed straight at my weak spot. [beat] And it comes back hard.

**[1:10 — Scoring + graph]**
> Every turn is scored on three axes — logic, evidence, and rhetoric. [beat] And on the right, this is the part we're proud of: a live **cognitive fingerprint** — a knowledge graph of how *I* argue. Red nodes are weaknesses it's found. The more we debate, the sharper this picture gets.

**[1:38 — Voice + cross-modal]**
> Now watch this. I'll switch to **voice** — a real-time spoken debate. [beat] And listen — the voice opponent already knows the weakness I showed a minute ago *in text*. One memory, two modes. A slip-up in voice makes your next text debate harder, and the reverse.

**[2:05 — Session end / proof]**
> When the session ends, I get a score and — more importantly — a before-and-after of my fingerprint. I can literally see which weaknesses shrank. [beat]

**[2:22 — Progress + forget]**
> Over time, the dashboard tracks my streak, my win rate, and my thinking style. And when I truly *master* a pattern, DebateMind **forgets** it — it's deleted from memory so the opponent stops wasting rounds on a weakness I've already beaten.

**[2:35 — How it's built]**
> Under the hood: a LangGraph pipeline grades every argument, a Cognee-powered knowledge graph on Neo4j and pgvector stores your fingerprint, and everything heavy runs async on Celery so the debate never lags. Voice runs on OpenAI's Realtime API over WebRTC.

**[2:48 — Close]**
> DebateMind doesn't just argue with you. It studies you, targets you, and grows with you. [beat] **A debate coach that finally remembers.** Thanks for watching.

*(Word count ≈ 430. If you run long, trim the 2:35 tech paragraph first — it's the most compressible.)*

---

## PART 3 — PITCH SLIDES (10)

Keep text minimal on screen; the lines below are speaker-facing content you can shorten to bullet fragments.

### Slide 1 — Title
- **DebateMind**
- *The debate coach that remembers you.*
- Logo · Team Avalon · [Hackathon name]

### Slide 2 — The Problem
- To get better at arguing, you need an opponent that pushes your weak spots.
- Every AI debate tool **forgets you** after each session.
- It never notices your **recurring fallacies**, your **weak topics**, or your **reasoning style**.
- Result: generic practice that doesn't compound.

### Slide 3 — The Solution
- An adaptive AI opponent that **learns how you think** and **targets your weaknesses**.
- Debate by **text or voice**.
- Every argument is graded and written into a **persistent cognitive fingerprint**.
- The opponent gets harder over time — *in exactly your weak areas*.

### Slide 4 — How the Memory Works
- A 4-stage memory lifecycle: **Remember → Recall → Improve → Forget**
  - **Remember** — every argument becomes a typed node in your knowledge graph
  - **Recall** — the opponent pulls your weaknesses into its prompt before replying
  - **Improve** — the graph re-cognifies as evidence accumulates
  - **Forget** — master a pattern and it's *truly deleted* — no wasted rounds
- *Diagram: the loop as a circle.*

### Slide 5 — Architecture
- **Frontend:** Next.js · React · TypeScript · Tailwind · Zustand · D3.js
- **Backend:** FastAPI · LangGraph grading pipeline (`extract → opponent → judge → mastery → remember → prune`)
- **Memory:** Cognee knowledge graph on **Neo4j** + **Postgres/pgvector**, guided by a hand-authored **OWL ontology** of how people reason
- **Async:** Celery + Redis keep graph writes off the request path
- **LLMs:** OpenRouter (GPT-4.1-mini) for agents · OpenAI embeddings · OpenAI **Realtime API over WebRTC** for voice
- **Auth:** Clerk
- *Diagram: browser → FastAPI → LangGraph → Cognee → Neo4j/pgvector, with Celery/Redis branch and a WebRTC line straight to OpenAI for voice.*

### Slide 6 — The Novel Bit: One Memory, Two Bots
- The **text bot** and the **voice bot** read and write the *same* fingerprint dataset.
- A weakness you reveal by **voice** surfaces when you next debate by **text** — and vice versa.
- **Cross-modal memory** — genuinely hard to fake, and the core moat.

### Slide 7 — Live Demo
- *(Play the video, or screenshots: Topic → Text debate + live graph → Voice → Session End before/after.)*

### Slide 8 — It's Measurable
- Per-turn scoring on **Logic · Evidence · Rhetoric**.
- **Session-level LLM-as-judge** gives an overall 1–10 with graceful fallback.
- **Before/after fingerprint** per session + a progress dashboard (streak, win rate, thinking-style bars, mastered patterns).
- You can *watch your weaknesses shrink.*

### Slide 9 — What's Next
- More debate formats (parliamentary, cross-examination).
- Team/classroom mode — coaches see student fingerprints.
- Fine-tuned opponent personas per difficulty.
- Exportable "argument health" report.

### Slide 10 — Close
- **DebateMind** — studies you, targets you, grows with you.
- *A debate coach that finally remembers.*
- Team Avalon · github.com/ananthanarayanan431/cognee-project

---

### Quick prep checklist
- [ ] Seed a demo account with 2–3 prior sessions (populated graph + dashboard).
- [ ] Same topic for text + voice run (sells cross-modal memory).
- [ ] Record clips per-segment, 1080p, clean browser.
- [ ] Voiceover recorded separately, then trim clips to match.
- [ ] Slides 4 & 5 need simple diagrams — everything else is text.
