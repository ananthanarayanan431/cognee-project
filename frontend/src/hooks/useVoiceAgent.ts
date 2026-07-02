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
}

interface UseVoiceAgentReturn {
  status: VoiceStatus;
  transcript: TranscriptLine[];
  summary: VoiceSummary | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  error: string | null;
}

const OPENAI_REALTIME_URL = "https://api.openai.com/v1/realtime";
const MODEL = "gpt-4o-realtime-preview";

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
  // Keep debateSessionId in a ref so the data-channel handler never goes stale.
  const sessionIdRef = useRef(debateSessionId);
  sessionIdRef.current = debateSessionId;

  // Hydrate transcript + summary from DB when the component mounts (resuming a past session).
  useEffect(() => {
    api.getVoiceSummary(debateSessionId).then((data: VoiceSessionSummary) => {
      if (!data.has_voice_session) return;

      setSummary({
        duration_seconds: data.duration_seconds ?? null,
        closing_summary: data.closing_summary ?? null,
        fallacies: data.fallacies,
        strong_arguments: data.strong_arguments,
        concessions: data.concessions,
        position_flips: data.position_flips,
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
    if (type === "response.audio_transcript.delta") {
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
    if (type === "response.audio_transcript.done") {
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
        }));
      }
    }
  }, []);

  const connect = useCallback(async () => {
    if (status === "connecting" || status === "connected") return;
    setStatus("connecting");
    setError(null);
    setTranscript([]);
    setSummary(null);
    aiDeltaRef.current = "";

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

      // 7. SDP offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // 8. POST offer to OpenAI Realtime
      const sdpResp = await fetch(`${OPENAI_REALTIME_URL}?model=${MODEL}`, {
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
    cleanup();
    setStatus("ended");
  }, [cleanup]);

  return { status, transcript, summary, connect, disconnect, error };
}
