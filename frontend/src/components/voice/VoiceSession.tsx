"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  IconMicrophone,
  IconMicrophoneOff,
  IconPhoneOff,
  IconWaveSquare,
  IconClipboardList,
  IconAlertTriangle,
  IconThumbUp,
  IconHandStop,
  IconArrowsShuffle,
  IconBrain,
  IconClock,
} from "@tabler/icons-react";
import { useVoiceAgent, VoiceSummary, TranscriptLine } from "@/hooks/useVoiceAgent";
import { SessionConfig, GraphData } from "@/types";
import { debateModeName } from "@/lib/debateModes";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";

interface Props {
  sessionId: string;
  sessionConfig: SessionConfig;
  onEnd: () => void;
}

type Tab = "transcript" | "summary";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function SummaryPanel({ summary, sessionConfig, elapsedSeconds }: {
  summary: VoiceSummary | null;
  sessionConfig: SessionConfig;
  elapsedSeconds: number;
}) {
  const positionLabel: Record<string, string> = {
    for: "Arguing For",
    against: "Arguing Against",
    neutral: "Neutral",
  };
  const difficultyColors: Record<string, string> = {
    gentle: "text-emerald-600",
    balanced: "text-blue-600",
    targeted: "text-amber-600",
    ruthless: "text-red-600",
    relentless: "text-purple-600",
    socratic: "text-indigo-600",
    devils_advocate: "text-fuchsia-600",
  };

  const duration = summary?.duration_seconds != null
    ? formatDuration(summary.duration_seconds)
    : formatDuration(elapsedSeconds);

  const hasObservations =
    summary &&
    (summary.fallacies.length > 0 ||
      summary.strong_arguments.length > 0 ||
      summary.concessions.length > 0 ||
      summary.position_flips.length > 0);

  return (
    <div className="flex flex-col gap-4 p-5 overflow-y-auto h-full">
      {/* Session Overview */}
      <section>
        <p className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog mb-2">
          Session Overview
        </p>
        <div className="bg-white rounded-xl border border-border p-4 flex flex-col gap-2">
          <div>
            <p className="font-sans text-[10px] text-fog mb-0.5">Motion</p>
            <p className="font-sans text-sm font-semibold text-ink leading-snug">
              {sessionConfig.topic}
            </p>
          </div>
          <div className="flex items-center gap-4 mt-1">
            <div>
              <p className="font-sans text-[10px] text-fog mb-0.5">Position</p>
              <p className="font-sans text-xs font-medium text-ink">
                {positionLabel[sessionConfig.position] ?? sessionConfig.position}
              </p>
            </div>
            <div>
              <p className="font-sans text-[10px] text-fog mb-0.5">Difficulty</p>
              <p className={`font-sans text-xs font-medium ${difficultyColors[sessionConfig.difficulty] ?? "text-ink"}`}>
                {debateModeName(sessionConfig.difficulty)}
              </p>
            </div>
            <div>
              <p className="font-sans text-[10px] text-fog mb-0.5">Duration</p>
              <p className="font-sans text-xs font-medium text-ink flex items-center gap-1">
                <IconClock size={11} stroke={2} />
                {duration}
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Argument Analysis */}
      <section>
        <p className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog mb-2">
          Argument Analysis
        </p>
        <div className="flex flex-col gap-2">
          {/* Fallacies */}
          <ObservationCard
            icon={<IconAlertTriangle size={13} stroke={2} className="text-red-500" />}
            label="Logical Fallacies Caught"
            count={summary?.fallacies.length ?? 0}
            items={summary?.fallacies ?? []}
            emptyText="None detected yet"
            accentClass="text-red-600"
          />
          {/* Strong arguments */}
          <ObservationCard
            icon={<IconThumbUp size={13} stroke={2} className="text-emerald-500" />}
            label="Strong Arguments"
            count={summary?.strong_arguments.length ?? 0}
            items={summary?.strong_arguments ?? []}
            emptyText="None recorded yet"
            accentClass="text-emerald-600"
          />
          {/* Concessions */}
          <ObservationCard
            icon={<IconHandStop size={13} stroke={2} className="text-amber-500" />}
            label="Concessions Made"
            count={summary?.concessions.length ?? 0}
            items={summary?.concessions ?? []}
            emptyText="None recorded yet"
            accentClass="text-amber-600"
          />
          {/* Position flips */}
          {(summary?.position_flips.length ?? 0) > 0 && (
            <ObservationCard
              icon={<IconArrowsShuffle size={13} stroke={2} className="text-scarlet" />}
              label="Position Inconsistencies"
              count={summary?.position_flips.length ?? 0}
              items={summary?.position_flips ?? []}
              emptyText=""
              accentClass="text-scarlet"
            />
          )}
        </div>
      </section>

      {/* Coach Notes */}
      <section>
        <p className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog mb-2 flex items-center gap-1.5">
          <IconBrain size={11} stroke={2} />
          AI Coach Notes
        </p>
        <div className="bg-white rounded-xl border border-border p-4">
          {summary?.closing_summary ? (
            <p className="font-sans text-sm text-ink leading-relaxed">{summary.closing_summary}</p>
          ) : (
            <p className="font-sans text-sm text-fog italic">
              {hasObservations
                ? "Session in progress — coach notes will appear when you end the session."
                : "Start debating — your coach notes will appear here as the session progresses."}
            </p>
          )}
        </div>
      </section>

      {/* Focus Areas */}
      {summary && summary.fallacies.length > 0 && (
        <section>
          <p className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog mb-2">
            Recommended Focus Areas
          </p>
          <div className="bg-white rounded-xl border border-border p-4">
            <ul className="flex flex-col gap-1.5">
              {summary.fallacies.slice(0, 3).map((f, i) => (
                <li key={i} className="font-sans text-xs text-ink flex items-start gap-1.5">
                  <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-scarlet flex-shrink-0" />
                  Practice counter-argumentation for: <span className="font-medium">{f}</span>
                </li>
              ))}
              {summary.concessions.length > 0 && (
                <li className="font-sans text-xs text-ink flex items-start gap-1.5">
                  <span className="mt-0.5 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                  Work on committing to your position under pressure
                </li>
              )}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}

function ObservationCard({
  icon,
  label,
  count,
  items,
  accentClass,
}: {
  icon: ReactNode;
  label: string;
  count: number;
  items: string[];
  // Accepted for call-site compatibility; the card has no empty-state render.
  emptyText?: string;
  accentClass: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-white rounded-xl border border-border p-3">
      <button
        className="w-full flex items-center justify-between"
        onClick={() => items.length > 0 && setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-2">
          {icon}
          <span className="font-sans text-xs font-medium text-ink">{label}</span>
        </div>
        <span className={`font-sans text-xs font-bold ${count > 0 ? accentClass : "text-fog"}`}>
          {count}
        </span>
      </button>
      {expanded && items.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1 pl-1">
          {items.map((item, i) => (
            <li key={i} className="font-sans text-[11px] text-fog leading-snug flex items-start gap-1.5">
              <span className="mt-1 flex-shrink-0 w-1 h-1 rounded-full bg-fog" />
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TranscriptPanel({ lines }: { lines: TranscriptLine[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  if (lines.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="text-center">
          <IconWaveSquare size={32} stroke={1.5} className="text-fog mx-auto mb-3" />
          <p className="font-sans text-sm text-fog">Live transcript will appear here as you speak</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">
      {lines.map((line) => (
        <div
          key={line.id}
          className={`flex gap-2.5 ${line.speaker === "user" ? "flex-row-reverse" : "flex-row"}`}
        >
          {/* Avatar */}
          <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center font-sans text-[9px] font-bold
            ${line.speaker === "ai"
              ? "bg-scarlet text-white"
              : "bg-ink text-white"
            }`}
          >
            {line.speaker === "ai" ? "O" : "U"}
          </div>
          {/* Bubble */}
          <div
            className={`max-w-[78%] rounded-2xl px-3.5 py-2.5 font-sans text-[13px] leading-relaxed
              ${line.speaker === "ai"
                ? "bg-white border border-border text-ink rounded-tl-sm"
                : "bg-ink text-white rounded-tr-sm"
              }`}
          >
            {line.text}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}

export default function VoiceSession({ sessionId, sessionConfig, onEnd }: Props) {
  const { status, transcript, summary, connect, disconnect, refreshSummary, error } = useVoiceAgent(sessionId);
  const [activeTab, setActiveTab] = useState<Tab>("transcript");
  const startTimeRef = useRef<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Pull the latest session-scoped fingerprint into the shared store so the
  // Cognitive Fingerprint panel (rendered by DebateView) reflects voice debates.
  // Voice observations are written to Cognee async (Celery), so the panel has
  // no live SSE feed like text mode — we poll instead.
  const refreshGraph = useCallback(async () => {
    try {
      const g = await api.getGraph(sessionId);
      useDebate.getState().setGraph(g as unknown as GraphData);
    } catch {
      /* transient — the interval / end-schedule retries */
    }
  }, [sessionId]);

  // Poll the fingerprint while the call is live.
  useEffect(() => {
    if (status !== "connected") return;
    refreshGraph();
    const id = setInterval(refreshGraph, 7000);
    return () => clearInterval(id);
  }, [status, refreshGraph]);

  // After the session ends, the score and the fingerprint patterns are still
  // being written async — the score lands in-process within a second or two,
  // but each derived argument pattern is a separate Celery→Neo4j write, so the
  // graph can take longer to fill in. Re-fetch on a decay schedule that runs
  // out past those writes so the graph and score bar catch up without the user
  // having to reopen the session.
  useEffect(() => {
    if (status !== "ended") return;
    const timers = [1500, 5000, 12000, 20000, 30000].map((delay) =>
      setTimeout(() => {
        refreshGraph();
        refreshSummary();
      }, delay)
    );
    return () => timers.forEach(clearTimeout);
  }, [status, refreshGraph, refreshSummary]);

  // Mirror the voice Logic/Evidence/Rhetoric scores into the shared store so the
  // SessionScoreBar shows them instead of 0/0/0 for voice-only sessions.
  useEffect(() => {
    if (summary && summary.score_logic != null) {
      useDebate.getState().setSessionScores({
        logic: summary.score_logic ?? 0,
        evidence: summary.score_evidence ?? 0,
        rhetoric: summary.score_rhetoric ?? 0,
      });
    }
  }, [summary?.score_logic, summary?.score_evidence, summary?.score_rhetoric]);

  // Track elapsed time while connected
  useEffect(() => {
    if (status === "connected") {
      if (!startTimeRef.current) startTimeRef.current = Date.now();
      const interval = setInterval(() => {
        setElapsedSeconds(Math.floor((Date.now() - (startTimeRef.current ?? Date.now())) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
    if (status === "ended") {
      clearInterval(0); // noop — just stop tracking
    }
  }, [status]);

  function handleDisconnect() {
    disconnect();
  }

  function handleConnect() {
    connect();
  }

  const isConnected = status === "connected";
  const isConnecting = status === "connecting";
  const isEnded = status === "ended";

  return (
    <div className="flex flex-col flex-1 min-w-0 h-full bg-chalk">
      {/* Header tabs */}
      <div className="bg-white border-b border-border px-5 py-2 flex items-center gap-1">
        <button
          onClick={() => setActiveTab("transcript")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-sans text-xs font-medium transition-colors
            ${activeTab === "transcript"
              ? "bg-ink text-white"
              : "text-fog hover:text-ink hover:bg-fog/10"}`}
        >
          <IconWaveSquare size={13} stroke={2} />
          Transcript
        </button>
        <button
          onClick={() => setActiveTab("summary")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-sans text-xs font-medium transition-colors
            ${activeTab === "summary"
              ? "bg-ink text-white"
              : "text-fog hover:text-ink hover:bg-fog/10"}`}
        >
          <IconClipboardList size={13} stroke={2} />
          Summary
          {summary &&
            (summary.fallacies.length + summary.strong_arguments.length + summary.concessions.length) > 0 && (
              <span className="ml-0.5 w-4 h-4 rounded-full bg-scarlet text-white font-bold text-[9px] flex items-center justify-center">
                {summary.fallacies.length + summary.strong_arguments.length + summary.concessions.length}
              </span>
            )}
        </button>

        {/* Elapsed timer */}
        {isConnected && (
          <span className="ml-auto font-sans text-[11px] text-fog font-mono">
            {formatDuration(elapsedSeconds)}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex flex-1 overflow-hidden">
        {activeTab === "transcript" ? (
          <TranscriptPanel lines={transcript} />
        ) : (
          <SummaryPanel
            summary={summary}
            sessionConfig={sessionConfig}
            elapsedSeconds={elapsedSeconds}
          />
        )}
      </div>

      {/* Footer: status + controls */}
      <div className="bg-white border-t border-border px-5 py-4">
        {error && (
          <div className="mb-3 flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            <IconAlertTriangle size={14} stroke={2} className="text-red-500 flex-shrink-0 mt-0.5" />
            <p className="font-sans text-xs text-red-600">{error}</p>
          </div>
        )}

        <div className="flex items-center justify-center gap-3">
          {!isConnected && !isConnecting && !isEnded && (
            <button
              onClick={handleConnect}
              className="flex items-center gap-2 bg-scarlet text-white px-6 py-2.5 rounded-full font-sans text-sm font-semibold hover:bg-red-700 transition-colors shadow-sm"
            >
              <IconMicrophone size={16} stroke={2} />
              Connect
            </button>
          )}

          {isConnecting && (
            <button
              disabled
              className="flex items-center gap-2 bg-fog/20 text-fog px-6 py-2.5 rounded-full font-sans text-sm font-medium cursor-not-allowed"
            >
              <span className="w-3.5 h-3.5 rounded-full border-2 border-fog border-t-transparent animate-spin" />
              Connecting…
            </button>
          )}

          {isConnected && (
            <>
              <div className="flex items-center gap-1.5 text-emerald-600 font-sans text-xs font-medium">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                Live
              </div>
              <button
                onClick={handleDisconnect}
                className="flex items-center gap-2 bg-ink text-white px-5 py-2.5 rounded-full font-sans text-sm font-semibold hover:bg-red-700 transition-colors"
              >
                <IconPhoneOff size={15} stroke={2} />
                End Call
              </button>
            </>
          )}

          {isEnded && (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-fog font-sans text-xs">
                <IconMicrophoneOff size={14} stroke={2} />
                Session ended
              </div>
              <button
                onClick={onEnd}
                className="flex items-center gap-2 bg-ink text-white px-5 py-2.5 rounded-full font-sans text-sm font-semibold hover:bg-fog/80 transition-colors"
              >
                Back to Chat
              </button>
            </div>
          )}
        </div>

        {isConnected && (
          <p className="text-center font-sans text-[10px] text-fog mt-2">
            Speak naturally — the AI opponent will respond automatically
          </p>
        )}
      </div>
    </div>
  );
}
