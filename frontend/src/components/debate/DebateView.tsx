"use client";
import { useEffect, useRef } from "react";
import { IconChartLine, IconHistory, IconMessages, IconPhone } from "@tabler/icons-react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { GraphData, Message } from "@/types";
import { debateModeName } from "@/lib/debateModes";
import MessageBubble from "./MessageBubble";
import InputArea from "./InputArea";
import { useStreamContinuation, useStreamOpening } from "@/hooks/useDebateSSE";
import FingerprintGraph from "@/components/graph/FingerprintGraph";
import SessionScoreBar from "./SessionScoreBar";
import VoiceSession from "@/components/voice/VoiceSession";

const STAGE_LABELS: Record<string, string> = {
  extract: "Analysing your argument…",
  opponent: "Building a counterargument…",
  judge: "Scoring the exchange…",
  mastery: "Updating your fingerprint…",
};

export default function DebateView() {
  const { messages, thinking, currentStage, graph, sessionId, sessionConfig, sessionScores, setScreen, setMessages, setGraph, voiceMode, setVoiceMode } = useDebate();
  const scrollRef    = useRef<HTMLDivElement>(null);
  const hydratedRef  = useRef<string | null>(null);
  const streamOpening = useStreamOpening();
  const streamContinuation = useStreamContinuation();

  // Hydrate chat history and graph when resuming an existing session;
  // stream an AI-generated opening for fresh sessions.
  useEffect(() => {
    if (!sessionId || hydratedRef.current === sessionId) return;
    // Claim this session synchronously so a StrictMode double-mount (or a rapid
    // re-render) can't fire two transcript fetches / opening streams.
    hydratedRef.current = sessionId;

    Promise.allSettled([
      api.getTranscript(sessionId),
      api.getGraph(sessionId),
    ]).then(([transcriptResult, graphResult]) => {
      if (transcriptResult.status === "fulfilled") {
        const transcript = transcriptResult.value;
        const currentMessages = useDebate.getState().messages;

        if (transcript.exchanges.length > 0 && currentMessages.length === 0) {
          // Resumed session — restore full transcript
          const msgs: Message[] = [];
          for (const ex of transcript.exchanges) {
            msgs.push({ id: `h-${ex.turn_number}-user`, role: "user", text: ex.user_message });
            if (ex.opponent_response) {
              const hasScores = ex.judge_logic != null;
              msgs.push({
                id: `h-${ex.turn_number}-opp`,
                role: "opponent",
                text: ex.opponent_response,
                judge: hasScores ? {
                  logic:    ex.judge_logic    ?? 0,
                  evidence: ex.judge_evidence ?? 0,
                  rhetoric: ex.judge_rhetoric ?? 0,
                  fallacy:  ex.fallacy,
                  outcome:  ex.outcome ?? "",
                } : undefined,
                showJudge: hasScores,
              });
            }
          }
          setMessages(msgs);

          // Restore session scores from last scored exchange
          const last = [...transcript.exchanges].reverse().find((e) => e.judge_logic != null);
          if (last) {
            useDebate.setState({
              sessionScores: {
                logic:    last.judge_logic    ?? 0,
                evidence: last.judge_evidence ?? 0,
                rhetoric: last.judge_rhetoric ?? 0,
              },
            });
          }

          // Re-engage the user: opponent picks up from where the debate left off.
          streamContinuation(sessionId);
        } else if (
          transcript.exchanges.length === 0 &&
          currentMessages.length === 0 &&
          useDebate.getState().isFreshSession
        ) {
          // Fresh session (just created) — the AI opponent streams the opening.
          // Reopened empty sessions skip this: the user just starts arguing.
          streamOpening(sessionId);
        } else if (transcript.exchanges.length === 0 && currentMessages.length === 0) {
          // Reopened session with no text history — it may have been argued by
          // voice. Rather than dropping the user onto an empty screen, replay
          // the spoken transcript as chat history and let the opponent pick the
          // debate back up in text (the /continue call is voice-aware server-side).
          api
            .getVoiceSummary(sessionId)
            .then((voice) => {
              if (!voice.has_voice_session || voice.transcript.length === 0) return;
              if (useDebate.getState().messages.length > 0) return; // user already started typing
              const voiceMsgs: Message[] = voice.transcript.map((line, i) => ({
                id: `voice-${i}`,
                role: line.speaker === "ai" ? "opponent" : "user",
                text: line.text,
              }));
              setMessages(voiceMsgs);
              streamContinuation(sessionId);
            })
            .catch(() => {
              /* no voice history either — leave the user to open a fresh argument */
            });
        }
      }

      if (graphResult.status === "fulfilled") {
        setGraph(graphResult.value as unknown as GraphData);
      }
    });
  }, [sessionId, setMessages, setGraph, streamOpening, streamContinuation]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const setSessions = useDebate((s) => s.setSessions);

  // Auto-end the session when the user closes the tab / refreshes the page.
  useEffect(() => {
    if (!sessionId) return;
    const handler = () => api.endSessionBeacon(sessionId);
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sessionId]);

  async function endSession() {
    if (sessionId) await api.endSession(sessionId);
    api.getSessions().then(setSessions).catch(() => {});
    setScreen("end");
  }

  const lastMsg = messages[messages.length - 1];

  const difficultyColors: Record<string, string> = {
    gentle: "bg-emerald-50 text-emerald-700 border-emerald-200",
    balanced: "bg-blue-50 text-blue-700 border-blue-200",
    targeted: "bg-amber-50 text-amber-700 border-amber-200",
    ruthless: "bg-red-50 text-red-700 border-red-200",
    relentless: "bg-purple-50 text-purple-700 border-purple-200",
    socratic: "bg-indigo-50 text-indigo-700 border-indigo-200",
    devils_advocate: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  };
  const positionColors: Record<string, string> = {
    for: "bg-emerald-50 text-emerald-700 border-emerald-200",
    against: "bg-scarlet/10 text-scarlet border-scarlet/20",
    neutral: "bg-fog/10 text-fog border-fog/20",
  };
  const positionLabel: Record<string, string> = {
    for: "Arguing For",
    against: "Arguing Against",
    neutral: "Neutral",
  };

  return (
    <div className="flex h-full flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between h-14 px-5 bg-white border-b border-border sticky top-0 z-20">
        <button
          onClick={() => {
            // End the session (fire-and-forget) then navigate back.
            if (sessionId) api.endSession(sessionId).catch(() => {});
            api.getSessions().then(setSessions).catch(() => {});
            setScreen("topic");
          }}
          className="font-sans text-xs font-medium text-ink border border-border rounded-lg px-3 py-1.5 hover:bg-fog/10 transition-colors flex items-center gap-1.5"
        >
          ← Back
        </button>
        <span className="font-sans text-[11px] font-medium text-fog tracking-wide hidden sm:block">
          {sessionConfig?.topic?.slice(0, 30)}{" "}
          {sessionConfig && (
            <>
              · <span className="text-scarlet">{debateModeName(sessionConfig.difficulty)}</span>
            </>
          )}
        </span>
        <div className="flex items-center gap-3">
          {/* Chat / Voice toggle */}
          <div className="flex items-center rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setVoiceMode(false)}
              aria-label="Text chat"
              aria-pressed={!voiceMode}
              title="Text chat"
              className={`px-2.5 py-1.5 transition-colors ${!voiceMode ? "bg-ink text-white" : "text-fog hover:text-ink hover:bg-fog/10"}`}
            >
              <IconMessages size={15} stroke={1.75} />
            </button>
            <button
              onClick={() => setVoiceMode(true)}
              aria-label="Voice call"
              aria-pressed={voiceMode}
              title="Voice call"
              className={`px-2.5 py-1.5 transition-colors ${voiceMode ? "bg-scarlet text-white" : "text-fog hover:text-ink hover:bg-fog/10"}`}
            >
              <IconPhone size={15} stroke={1.75} />
            </button>
          </div>
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
        <button
          onClick={endSession}
          className="font-sans text-xs font-semibold uppercase tracking-wide text-fog hover:text-ink transition-colors"
        >
          End session
        </button>
      </nav>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Voice panel — replaces chat when voice mode is active */}
        {voiceMode && sessionId && sessionConfig && (
          <VoiceSession
            sessionId={sessionId}
            sessionConfig={sessionConfig}
            onEnd={() => setVoiceMode(false)}
          />
        )}

        {/* Chat panel */}
        <div className={`flex flex-col flex-1 min-w-0 bg-chalk ${voiceMode ? "hidden" : ""}`}>
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-7 py-6 flex flex-col gap-3.5"
          >
            {/* Session greeting card */}
            {sessionConfig && (
              <div className="bg-white rounded-2xl border border-border px-5 py-4 mb-1">
                <p className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog mb-2">
                  Motion
                </p>
                <p className="font-sans text-sm font-semibold text-ink leading-snug mb-3">
                  {sessionConfig.topic}
                </p>
                {sessionConfig.description && (
                  <p className="font-sans text-[11px] text-fog leading-relaxed mb-3">
                    {sessionConfig.description}
                  </p>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`font-sans text-[10px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full border ${
                      positionColors[sessionConfig.position] ?? "bg-fog/10 text-fog border-fog/20"
                    }`}
                  >
                    {positionLabel[sessionConfig.position] ?? sessionConfig.position}
                  </span>
                  <span
                    className={`font-sans text-[10px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full border ${
                      difficultyColors[sessionConfig.difficulty] ?? "bg-fog/10 text-fog border-fog/20"
                    }`}
                  >
                    {debateModeName(sessionConfig.difficulty)}
                  </span>
                </div>
              </div>
            )}
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                msg={m}
                thinking={thinking && m.role === "opponent" && m === lastMsg}
              />
            ))}
            {/* Thinking indicator when no opponent message yet */}
            {thinking && lastMsg?.role !== "opponent" && (
              <div className="flex flex-col items-start">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="w-5 h-5 rounded-full bg-scarlet flex items-center justify-center font-sans text-[9px] font-bold text-white animate-pulse">
                    O
                  </span>
                  <span className="font-sans text-[10px] font-semibold text-scarlet tracking-widest">
                    DEBATEMIND
                  </span>
                </div>
                <span className="font-sans italic text-sm text-fog">
                  {currentStage ? (STAGE_LABELS[currentStage] ?? "Thinking…") : "Thinking…"}
                </span>
              </div>
            )}
          </div>
          <InputArea />
        </div>

        {/* Graph panel — hidden on mobile, shown on large screens */}
        <aside className="w-80 min-w-[280px] max-w-[360px] bg-white border-l border-border flex-col text-ink overflow-y-auto hidden lg:flex">
          <div className="px-5 pt-4 pb-2 flex items-center justify-between">
            <div>
              <span className="font-sans text-[11px] font-semibold uppercase tracking-widest text-ink">
                Cognitive Fingerprint
              </span>
              <p className="font-sans text-[10px] text-fog mt-0.5">Your argument pattern map</p>
            </div>
          </div>
          <FingerprintGraph data={graph} />
          <SessionScoreBar scores={sessionScores} />
          <div className="flex gap-3.5 px-5 pb-4 font-sans text-[10px] text-fog">
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
        </aside>
      </div>
    </div>
  );
}
