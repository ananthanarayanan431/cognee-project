"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { VoiceSessionSummary } from "@/types";

export type VoiceStatus = "idle" | "connecting" | "connected" | "ended" | "error";

export interface TranscriptLine {
  id: string;
  speaker: "user" | "ai";
  text: string;
  timestamp: number;
  // Realtime item id — groups AI deltas so one utterance stays in one bubble.
  itemId?: string;
}

export interface VoiceSummary {
  duration_seconds: number | null;
  closing_summary: string | null;
  fallacies: string[];
  strong_arguments: string[];
  concessions: string[];
  position_flips: string[];
  // Filled by the backend voice scorer after the session ends; null until then.
  score_logic: number | null;
  score_evidence: number | null;
  score_rhetoric: number | null;
}

interface UseVoiceAgentReturn {
  status: VoiceStatus;
  transcript: TranscriptLine[];
  summary: VoiceSummary | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  refreshSummary: () => Promise<void>;
  muted: boolean;
  toggleMute: () => void;
  error: string | null;
}

// GA Realtime endpoint — the model is bound to the ephemeral key, not a query param.
const OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/calls";

let _idCounter = 0;
function nextId() {
  return `vl-${Date.now()}-${_idCounter++}`;
}

// Bucket for AI transcript deltas that arrive without an item_id.
const NO_ITEM_KEY = "__no_item__";

export function useVoiceAgent(debateSessionId: string): UseVoiceAgentReturn {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [summary, setSummary] = useState<VoiceSummary | null>(null);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const voiceSessionIdRef = useRef<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  // AI transcript deltas per response item, persisted in full on done.
  const aiDeltaRef = useRef<Map<string, string>>(new Map());
  // Ordered persist queue: user transcription lags the AI reply, so lines
  // flush to the DB in conversation order once their text resolves.
  const persistQueueRef = useRef<Array<{ key: string; speaker: "user" | "ai"; text: string | null }>>([]);
  const persistChainRef = useRef<Promise<void>>(Promise.resolve());
  const persistTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  // Set when end_voice_session fires; hang up after closing remarks (or timeout).
  const endingRef = useRef(false);
  const endingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Keep debateSessionId in a ref so the data-channel handler never goes stale.
  const sessionIdRef = useRef(debateSessionId);
  sessionIdRef.current = debateSessionId;

  // Hydrate transcript + summary from DB when the component mounts (resuming a past session).
  useEffect(() => {
    let live = true;
    setSummary(null);
    setTranscript([]);

    api.getVoiceSummary(debateSessionId).then((data: VoiceSessionSummary) => {
      if (!live) return;
      if (!data.has_voice_session) return;

      setSummary({
        duration_seconds: data.duration_seconds ?? null,
        closing_summary: data.closing_summary ?? null,
        fallacies: data.fallacies,
        strong_arguments: data.strong_arguments,
        concessions: data.concessions,
        position_flips: data.position_flips,
        score_logic: data.score_logic ?? null,
        score_evidence: data.score_evidence ?? null,
        score_rhetoric: data.score_rhetoric ?? null,
      });

      if (data.transcript.length > 0) {
        setTranscript(
          data.transcript.map((line, i) => ({
            id: `hist-${i}`,
            speaker: line.speaker,
            text: line.text,
            timestamp: Date.now() - (data.transcript.length - i) * 500,
          }))
        );
      }
    }).catch(() => { /* No past session — start fresh */ });

    return () => {
      live = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debateSessionId]);

  // Re-fetch just the summary without disturbing the live transcript.
  const refreshSummary = useCallback(async () => {
    try {
      const data = await api.getVoiceSummary(debateSessionId);
      if (!data.has_voice_session) return;
      setSummary((prev) => ({
        duration_seconds: data.duration_seconds ?? prev?.duration_seconds ?? null,
        closing_summary: data.closing_summary ?? prev?.closing_summary ?? null,
        fallacies: data.fallacies,
        strong_arguments: data.strong_arguments,
        concessions: data.concessions,
        position_flips: data.position_flips,
        // Keep the last non-null score if a partial response omits it.
        score_logic: data.score_logic ?? prev?.score_logic ?? null,
        score_evidence: data.score_evidence ?? prev?.score_evidence ?? null,
        score_rhetoric: data.score_rhetoric ?? prev?.score_rhetoric ?? null,
      }));
    } catch {
      /* transient — the caller retries on a schedule */
    }
  }, [debateSessionId]);

  // Mute disables the local mic track — server VAD then hears only silence.
  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      streamRef.current?.getAudioTracks().forEach((t) => {
        t.enabled = !next;
      });
      return next;
    });
  }, []);

  const cleanup = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    dcRef.current?.close();
    pcRef.current?.close();
    if (audioElRef.current) {
      audioElRef.current.srcObject = null;
      audioElRef.current.remove();
    }
    streamRef.current = null;
    dcRef.current = null;
    pcRef.current = null;
    audioElRef.current = null;
  }, []);

  // Flush resolved lines one at a time so DB order matches conversation order.
  const flushPersistQueue = useCallback(() => {
    const q = persistQueueRef.current;
    while (q.length > 0 && q[0].text !== null) {
      const { speaker, text } = q.shift()!;
      const vsId = voiceSessionIdRef.current;
      if (text && vsId) {
        const sid = sessionIdRef.current;
        persistChainRef.current = persistChainRef.current
          .then(() => api.saveTranscriptLine(sid, vsId, speaker, text))
          .then(() => undefined, () => undefined);
      }
    }
  }, []);

  // Resolve a pending entry's text (empty = skippable), then flush.
  const resolvePersist = useCallback((key: string | undefined, speaker: "user" | "ai", text: string) => {
    const q = persistQueueRef.current;
    const entry = key ? q.find((e) => e.key === key && e.speaker === speaker && e.text === null) : undefined;
    if (entry) {
      entry.text = text;
      const timer = key ? persistTimersRef.current.get(key) : undefined;
      if (timer) {
        clearTimeout(timer);
        persistTimersRef.current.delete(key!);
      }
    } else if (text) {
      q.push({ key: key ?? nextId(), speaker, text });
    }
    flushPersistQueue();
  }, [flushPersistQueue]);

  // Reserve a slot whose text isn't known yet; resolved empty after 10s if lost.
  const enqueuePendingPersist = useCallback((key: string, speaker: "user" | "ai") => {
    if (persistQueueRef.current.some((e) => e.key === key && e.speaker === speaker)) return;
    persistQueueRef.current.push({ key, speaker, text: null });
    persistTimersRef.current.set(
      key,
      setTimeout(() => resolvePersist(key, speaker, ""), 10000)
    );
  }, [resolvePersist]);

  const handleMessage = useCallback(async (event: MessageEvent) => {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(event.data as string);
    } catch {
      return;
    }

    const type = msg.type as string;

    // User finished speaking — reserve their transcript slot now (transcription
    // lags the AI reply), fill the text in place when it resolves.
    if (type === "input_audio_buffer.committed") {
      const itemId = msg.item_id as string | undefined;
      if (itemId) {
        setTranscript((prev) =>
          prev.some((l) => l.speaker === "user" && l.itemId === itemId)
            ? prev
            : [...prev, { id: nextId(), speaker: "user", text: "", timestamp: Date.now(), itemId }]
        );
        enqueuePendingPersist(itemId, "user");
      }
    }

    // User speech transcript (final) — fill the reserved slot in place.
    if (type === "conversation.item.input_audio_transcription.completed") {
      const text = ((msg.transcript as string) ?? "").trim();
      const itemId = msg.item_id as string | undefined;
      setTranscript((prev) => {
        const idx = itemId ? prev.findIndex((l) => l.speaker === "user" && l.itemId === itemId) : -1;
        if (idx !== -1) {
          const next = [...prev];
          if (text) next[idx] = { ...next[idx], text };
          else next.splice(idx, 1); // silence / noise — drop the reserved slot
          return next;
        }
        // No placeholder (commit event missed) — append as before.
        return text
          ? [...prev, { id: nextId(), speaker: "user", text, timestamp: Date.now(), itemId }]
          : prev;
      });
      resolvePersist(itemId, "user", text);
    }

    // User speech transcription failed — clear the reserved slot.
    if (type === "conversation.item.input_audio_transcription.failed") {
      const itemId = msg.item_id as string | undefined;
      if (itemId) {
        setTranscript((prev) => prev.filter((l) => !(l.speaker === "user" && l.itemId === itemId && !l.text)));
        resolvePersist(itemId, "user", "");
      }
    }

    // AI transcript delta — grouped by item_id so an interleaved user bubble
    // can't split one utterance across two AI bubbles.
    if (type === "response.output_audio_transcript.delta") {
      const delta = (msg.delta as string) ?? "";
      const itemId = msg.item_id as string | undefined;
      if (delta) {
        const key = itemId ?? NO_ITEM_KEY;
        aiDeltaRef.current.set(key, (aiDeltaRef.current.get(key) ?? "") + delta);
        setTranscript((prev) => {
          const idx = itemId
            ? prev.findIndex((l) => l.speaker === "ai" && l.itemId === itemId)
            : prev.reduce((acc, l, i) => (l.speaker === "ai" ? i : acc), -1);
          if (idx !== -1) {
            const target = prev[idx];
            const next = [...prev];
            next[idx] = { ...target, text: target.text + delta };
            return next;
          }
          return [
            ...prev,
            { id: nextId(), speaker: "ai", text: delta, timestamp: Date.now(), itemId },
          ];
        });
      }
    }

    // AI transcript done — reconcile the on-screen line with the authoritative
    // full text, then persist it.
    if (type === "response.output_audio_transcript.done") {
      const full = (msg.transcript as string) ?? "";
      const itemId = msg.item_id as string | undefined;
      const key = itemId ?? NO_ITEM_KEY;
      const text = (full || aiDeltaRef.current.get(key) || "").trim();
      aiDeltaRef.current.delete(key);
      if (text) {
        setTranscript((prev) => {
          const idx = itemId
            ? prev.findIndex((l) => l.speaker === "ai" && l.itemId === itemId)
            : prev.reduce((acc, l, i) => (l.speaker === "ai" ? i : acc), -1);
          if (idx === -1) {
            return [
              ...prev,
              { id: nextId(), speaker: "ai", text, timestamp: Date.now(), itemId },
            ];
          }
          if (prev[idx].text === text) return prev;
          const next = [...prev];
          next[idx] = { ...next[idx], text };
          return next;
        });
      }
      // Persist via the ordered queue, behind any pending user transcription.
      if (text) {
        resolvePersist(itemId ?? nextId(), "ai", text);
      }
    }

    // Tool call
    if (type === "response.function_call_arguments.done") {
      const toolName = msg.name as string;
      const callId = msg.call_id as string;
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(msg.arguments as string);
      } catch { /* ignore malformed args */ }

      const vsId = voiceSessionIdRef.current;
      if (!vsId) return;

      // Session is ending — disable barge-in so the AI's closing line plays out
      // instead of being interrupted by further input audio.
      if (toolName === "end_voice_session" && dcRef.current?.readyState === "open") {
        dcRef.current.send(
          JSON.stringify({
            type: "session.update",
            session: {
              type: "realtime",
              audio: {
                input: {
                  turn_detection: {
                    type: "server_vad",
                    threshold: 0.5,
                    prefix_padding_ms: 300,
                    silence_duration_ms: 800,
                    create_response: false,
                    interrupt_response: false,
                  },
                },
              },
            },
          })
        );
      }

      let result: Record<string, unknown>;
      try {
        result = await api.executeVoiceTool(sessionIdRef.current, vsId, toolName, args);
      } catch (err) {
        result = { error: err instanceof Error ? err.message : "Tool execution failed" };
      }

      // Relay result to OpenAI via the data channel so the AI can continue.
      if (dcRef.current?.readyState === "open") {
        dcRef.current.send(
          JSON.stringify({
            type: "conversation.item.create",
            item: { type: "function_call_output", call_id: callId, output: JSON.stringify(result) },
          })
        );
        dcRef.current.send(JSON.stringify({ type: "response.create" }));
      }

      // Mirror tool results into local summary state for the Summary tab.
      if (toolName === "save_debate_observation") {
        const noteType = args.note_type as string;
        const content = args.content as string;
        if (content) {
          setSummary((prev) => {
            const base: VoiceSummary = prev ?? {
              duration_seconds: null,
              closing_summary: null,
              fallacies: [],
              strong_arguments: [],
              concessions: [],
              position_flips: [],
              score_logic: null,
              score_evidence: null,
              score_rhetoric: null,
            };
            return {
              ...base,
              fallacies: noteType === "fallacy" ? [...base.fallacies, content] : base.fallacies,
              strong_arguments: noteType === "strong_argument" ? [...base.strong_arguments, content] : base.strong_arguments,
              concessions: noteType === "concession" ? [...base.concessions, content] : base.concessions,
              position_flips: noteType === "position_flip" ? [...base.position_flips, content] : base.position_flips,
            };
          });
        }
      }

      if (toolName === "end_voice_session") {
        setSummary((prev) => ({
          duration_seconds: (result.duration_seconds as number) ?? null,
          closing_summary: (result.closing_summary as string) ?? null,
          fallacies: prev?.fallacies ?? [],
          strong_arguments: prev?.strong_arguments ?? [],
          concessions: prev?.concessions ?? [],
          position_flips: prev?.position_flips ?? [],
          // Scores land async; refreshSummary() polls them in.
          score_logic: prev?.score_logic ?? null,
          score_evidence: prev?.score_evidence ?? null,
          score_rhetoric: prev?.score_rhetoric ?? null,
        }));

        // Hang up once closing audio drains, with a fallback timer.
        endingRef.current = true;
        if (endingTimeoutRef.current) clearTimeout(endingTimeoutRef.current);
        endingTimeoutRef.current = setTimeout(() => {
          if (endingRef.current) {
            endingRef.current = false;
            cleanup();
            setStatus("ended");
          }
        }, 15000);
      }
    }

    // Assistant audio fully drained — if the session is ending, hang up now.
    if (type === "output_audio_buffer.stopped" && endingRef.current) {
      endingRef.current = false;
      if (endingTimeoutRef.current) {
        clearTimeout(endingTimeoutRef.current);
        endingTimeoutRef.current = null;
      }
      cleanup();
      setStatus("ended");
    }
  }, [cleanup, enqueuePendingPersist, resolvePersist]);

  const connect = useCallback(async () => {
    if (status === "connecting" || status === "connected") return;
    setStatus("connecting");
    setError(null);
    setTranscript([]);
    setSummary(null);
    aiDeltaRef.current.clear();
    persistQueueRef.current = [];
    persistTimersRef.current.forEach((t) => clearTimeout(t));
    persistTimersRef.current.clear();
    persistChainRef.current = Promise.resolve();
    setMuted(false); // fresh mic tracks start enabled
    endingRef.current = false;
    if (endingTimeoutRef.current) {
      clearTimeout(endingTimeoutRef.current);
      endingTimeoutRef.current = null;
    }

    try {
      // 1. Mic access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 2. Mint ephemeral key (includes voice_session_id)
      const tokenData = await api.getVoiceToken(debateSessionId);
      voiceSessionIdRef.current = tokenData.voice_session_id;
      const ephemeralKey = tokenData.client_secret?.value;
      if (!ephemeralKey) throw new Error("No ephemeral key returned from server");

      // 3. Create peer connection
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // 4. Remote audio → hidden <audio> element
      const audioEl = document.createElement("audio");
      audioEl.autoplay = true;
      document.body.appendChild(audioEl);
      audioElRef.current = audioEl;
      pc.ontrack = (evt) => {
        audioEl.srcObject = evt.streams[0];
      };

      // 5. Add mic track
      stream.getAudioTracks().forEach((track) => pc.addTrack(track, stream));

      // 6. Data channel for events
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;
      dc.onmessage = handleMessage;
      // server_vad only auto-triggers a response after hearing the user speak;
      // nudge the AI to open the conversation as soon as the channel is ready.
      dc.onopen = () => dc.send(JSON.stringify({ type: "response.create" }));

      // 7. SDP offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // 8. POST offer to OpenAI Realtime
      const sdpResp = await fetch(OPENAI_REALTIME_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${ephemeralKey}`,
          "Content-Type": "application/sdp",
        },
        body: offer.sdp,
      });

      if (!sdpResp.ok) {
        const errText = await sdpResp.text();
        throw new Error(`OpenAI Realtime rejected connection: ${sdpResp.status} ${errText}`);
      }

      const answerSdp = await sdpResp.text();
      await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

      setStatus("connected");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Voice connection failed";
      setError(msg);
      setStatus("error");
      cleanup();
    }
  }, [status, debateSessionId, handleMessage, cleanup]);

  const disconnect = useCallback(() => {
    // Tell the backend to finalize if the AI hasn't already done so.
    if (status === "connected" && !endingRef.current) {
      const vsId = voiceSessionIdRef.current;
      if (vsId) {
        api.executeVoiceTool(sessionIdRef.current, vsId, "end_voice_session", {}).catch(() => {
          /* best-effort — local cleanup still proceeds below */
        });
      }
    }
    endingRef.current = false;
    if (endingTimeoutRef.current) {
      clearTimeout(endingTimeoutRef.current);
      endingTimeoutRef.current = null;
    }
    cleanup();
    setStatus("ended");
  }, [status, cleanup]);

  return { status, transcript, summary, connect, disconnect, refreshSummary, muted, toggleMute, error };
}
