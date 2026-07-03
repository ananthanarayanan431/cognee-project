# Voice Session: Fix AI Transcript Capture + Proactive Opening Line

## Problem

Two bugs in the voice debate session, both surfaced by the user after the
recent GA Realtime migration (`aad746e`):

1. **AI transcript never persists.** `useVoiceAgent.ts` listens for
   `response.audio_transcript.delta` / `response.audio_transcript.done` to
   capture and save the AI's spoken lines. These are the **beta** Realtime
   API event names. The app now uses the GA `/v1/realtime/calls` endpoint
   with `session.type: "realtime"`, which renamed these events to
   `response.output_audio_transcript.delta` / `.done`. Since the old names
   never fire, `saveTranscriptLine(..., "ai", ...)` is never called, and the
   AI's side of the debate is silently dropped from both the live UI
   transcript and the persisted `voice_session_notes` rows. The user's own
   speech still works because `conversation.item.input_audio_transcription.completed`
   was not renamed in GA.
2. **The bot never speaks first.** The system prompt
   (`voice_agent/prompts.py`) instructs the AI to "open with your first
   spoken challenge" at session start, but nothing triggers a response until
   the user speaks. `turn_detection` is `server_vad`, which only
   auto-generates a response after detecting the *user's* speech ending —
   it does not fire on its own when the data channel opens. The result: the
   user connects and is met with silence until they speak first, even though
   the prompt assumes the AI opens.

## Goal

- AI transcript lines are captured and persisted exactly like user lines
  already are — both sides of the debate show up in the live transcript and
  in `GET /api/voice/{id}/summary`.
- The instant the WebRTC data channel is ready, the AI proactively opens the
  conversation: a brief, warm check-in (no user name — none is stored in the
  `User` model, and adding one is out of scope) that flows into its first
  debate challenge, still within the prompt's existing 60-word cap.

## Design

### Frontend — `frontend/src/hooks/useVoiceAgent.ts`

- Rename the two event-type string matches in `handleMessage`:
  - `"response.audio_transcript.delta"` → `"response.output_audio_transcript.delta"`
  - `"response.audio_transcript.done"` → `"response.output_audio_transcript.done"`
  - No other logic in those branches changes — accumulation, live-UI append,
    and `api.saveTranscriptLine(sessionIdRef.current, vsId, "ai", text)` are
    already correct and start working once the event names match.
- In `connect()`, after `dc.onmessage = handleMessage;`, add
  `dc.onopen = () => dc.send(JSON.stringify({ type: "response.create" }));`
  so the AI is nudged to generate its opening turn as soon as the channel is
  usable, rather than waiting on `server_vad` to hear the user first.

### Backend — `debatemind-backend/debatemind/voice_agent/prompts.py`

- Update the "At session START" section of `build_voice_system_prompt` so
  the instruction is: open with a brief, energetic conversational check-in
  (e.g. "Hey, ready to get into this?") that immediately transitions into
  the first spoken challenge in the same turn — not two separate turns, and
  still under the existing 60-word response cap. No placeholder for a user
  name is introduced.

### Out of scope

- No change to `voice_session.py` models, `router.py`, or the summary
  endpoint — persistence and retrieval logic for `speaker: "ai"` already
  exists and is correct; it was simply never triggered.
- No `User.name`/display-name field or migration (per user decision — skip
  personalization rather than add schema).
- No change to `turn_detection` VAD settings (threshold/silence duration)
  beyond the one-time `response.create` kick on connect.

## Testing

- Manual: start a voice session, confirm the AI speaks first within ~1-2s of
  connecting without the user saying anything.
- Manual: after a short back-and-forth, check the Transcript tab shows both
  "O" (AI) and "U" (user) bubbles interleaved, not just user bubbles.
- Manual: end the session, reload, confirm `GET /api/voice/{id}/summary`
  returns transcript lines for both speakers (via the Summary/Transcript tab
  rehydration path already in `useVoiceAgent.ts`).
