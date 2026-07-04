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
}

export interface VoiceSummary {
  duration_seconds: number | null;
  closing_summary: string | null;
  fallacies: string[];
  strong_arguments: string[];
  concessions: string[];
  position_flips: string[];
  // Populated by the backend voice scorer a few seconds after the session ends;
  // null until then. Surfaced in the SessionScoreBar via the debate store.
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
  error: string | null;
}

// GA Realtime WebRTC SDP-exchange endpoint. The old beta endpoint
// (/v1/realtime?model=...) is disabled and returns beta_api_shape_disabled.
// In GA the model is bound to the ephemeral key from /client_secrets, so it is
// NOT passed as a query param (adding ?model= to /calls yields an empty 400).
const OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime/calls";

let _idCounter = 0;
function nextId() {
  return `vl-${Date.now()}-${_idCounter++}`;
}

export function useVoiceAgent(debateSessionId: string): UseVoiceAgentReturn {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [summary, setSummary] = useState<VoiceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const voiceSessionIdRef = useRef<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  // Accumulates AI transcript deltas so we can persist the full utterance on done.
  const aiDeltaRef = useRef<string>("");
  // Set once `end_voice_session` fires; hang up once the AI's closing remarks
  // finish playing (or after a timeout, in case that event never arrives).
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

  // Re-fetch just the summary (observations + Logic/Evidence/Rhetoric scores)
  // without disturbing the live transcript. Called after the session ends so
  // the score bar picks up the backend voice scorer's result once it lands.
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
        score_logic: data.score_logic ?? null,
        score_evidence: data.score_evidence ?? null,
        score_rhetoric: data.score_rhetoric ?? null,
      }));
    } catch {
      /* transient — the caller retries on a schedule */
    }
  }, [debateSessionId]);

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

  const handleMessage = useCallback(async (event: MessageEvent) => {
    let msg: Record<string, unknown>;
    try {
      msg = JSON.parse(event.data as string);
    } catch {
      return;
    }

    const type = msg.type as string;

    // ── User speech transcript (final) ────────────────────────────────────────
    if (type === "conversation.item.input_audio_transcription.completed") {
      const text = ((msg.transcript as string) ?? "").trim();
      if (text) {
        setTranscript((prev) => [...prev, { id: nextId(), speaker: "user", text, timestamp: Date.now() }]);
        const vsId = voiceSessionIdRef.current;
        if (vsId) {
          api.saveTranscriptLine(sessionIdRef.current, vsId, "user", text).catch(() => {});
        }
      }
    }

    // ── AI speech transcript (streaming delta) ────────────────────────────────
    // GA Realtime renamed this from "response.audio_transcript.delta" (beta).
    if (type === "response.output_audio_transcript.delta") {
      const delta = (msg.delta as string) ?? "";
      if (delta) {
        aiDeltaRef.current += delta;
        setTranscript((prev) => {
          const last = prev[prev.length - 1];
          if (last?.speaker === "ai") {
            return [...prev.slice(0, -1), { ...last, text: last.text + delta }];
          }
          return [...prev, { id: nextId(), speaker: "ai", text: delta, timestamp: Date.now() }];
        });
      }
    }

    // ── AI speech transcript (complete utterance) — persist to DB ─────────────
    // GA Realtime renamed this from "response.audio_transcript.done" (beta).
    if (type === "response.output_audio_transcript.done") {
      const text = ((msg.transcript as string) ?? aiDeltaRef.current).trim();
      aiDeltaRef.current = "";
      const vsId = voiceSessionIdRef.current;
      if (text && vsId) {
        api.saveTranscriptLine(sessionIdRef.current, vsId, "ai", text).catch(() => {});
      }
    }

    // ── Tool call ─────────────────────────────────────────────────────────────
    if (type === "response.function_call_arguments.done") {
      const toolName = msg.name as string;
      const callId = msg.call_id as string;
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(msg.arguments as string);
      } catch { /* ignore malformed args */ }

      const vsId = voiceSessionIdRef.current;
      if (!vsId) return;

      // Disable barge-in the instant we know the session is ending, before
      // awaiting the tool round-trip below — otherwise continued input audio
      // (background noise, the user talking again) keeps clearing the AI's
      // closing response via interrupt_response, it never reaches
      // "output_audio_buffer.stopped", and hangup falls back to the 15s timer
      // instead of ending right after the closing line. Values mirror the
      // turn_detection block in voice_agent/session.py except the two flipped
      // flags: this is the session's last response, so let it play out and
      // don't spawn any more from further detected speech.
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
          // Scores are computed async on the backend after end; the component
          // polls refreshSummary() to fill these in once the judge lands.
          score_logic: prev?.score_logic ?? null,
          score_evidence: prev?.score_evidence ?? null,
          score_rhetoric: prev?.score_rhetoric ?? null,
        }));

        // Hang up once the AI's closing remarks finish playing (see the
        // "output_audio_buffer.stopped" handler below). Fall back to a fixed
        // delay in case that event never arrives, so the call never hangs open.
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

    // ── AI finished speaking — if this was the end-of-session response, hang up ──
    // WebRTC-only event (undocumented but widely relied on) signalling the
    // assistant's audio output has fully drained on the client side.
    if (type === "output_audio_buffer.stopped" && endingRef.current) {
      endingRef.current = false;
      if (endingTimeoutRef.current) {
        clearTimeout(endingTimeoutRef.current);
        endingTimeoutRef.current = null;
      }
      cleanup();
      setStatus("ended");
    }
  }, [cleanup]);

  const connect = useCallback(async () => {
    if (status === "connecting" || status === "connected") return;
    setStatus("connecting");
    setError(null);
    setTranscript([]);
    setSummary(null);
    aiDeltaRef.current = "";
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

      // 8. POST offer to OpenAI Realtime (GA /calls endpoint; model is bound to
      // the ephemeral key server-side, so no ?model= query param).
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
    // If the call was live and the AI hasn't already finalized it, tell the
    // backend so duration/summary get persisted instead of leaving the voice
    // session open server-side.
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

  return { status, transcript, summary, connect, disconnect, refreshSummary, error };
}
