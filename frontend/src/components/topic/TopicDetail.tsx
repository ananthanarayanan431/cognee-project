"use client";
import { useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import type { SessionListItem } from "@/types";

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced" },
  { key: "targeted", name: "Targeted" },
  { key: "ruthless", name: "Ruthless" },
] as const;

const POSITIONS = ["For", "Against", "Neutral"] as const;

const DIFFICULTY_BADGE: Record<string, string> = {
  balanced: "bg-blue-50 text-blue-600 border-blue-200",
  targeted: "bg-amber-50 text-amber-700 border-amber-200",
  ruthless: "bg-scarlet/10 text-scarlet border-scarlet/20",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export default function TopicDetail() {
  const { topicDetailTopic, sessions, setScreen, setSession, setSessions } = useDebate();
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");

  const topic = topicDetailTopic;
  if (!topic) return null;

  const topicSessions = sessions.filter(
    (s) => s.topic.toLowerCase() === topic.title.toLowerCase()
  );

  async function startNewSession() {
    if (!topic) return;
    setStartError("");
    setStarting(true);
    try {
      const res = await api.startSession(topic.title, topic.description, difficulty, position, topic.id);
      api.getSessions().then(setSessions).catch(() => {});
      setSession(res.session_id, {
        topic_id: res.topic_id,
        topic: topic.title,
        description: topic.description,
        difficulty,
        position: position as "for" | "against" | "neutral",
      });
    } catch {
      setStartError("Failed to start session — please try again.");
      setStarting(false);
    }
  }

  function resumeSession(session: SessionListItem) {
    setSession(session.session_id, {
      topic_id: session.topic_id,
      topic: session.topic,
      description: "",
      difficulty: session.difficulty as "balanced" | "targeted" | "ruthless",
      position: "against",
    }, false);
  }

  function viewMetrics(session: SessionListItem) {
    useDebate.setState({ sessionId: session.session_id });
    setScreen("end");
  }

  function viewTranscript(session: SessionListItem) {
    useDebate.setState({ sessionId: session.session_id });
    setScreen("transcript");
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-chalk">

      {/* ── Floating topic card ──────────────────────────────── */}
      <div className="flex-none px-6 pt-5 pb-4">
        <div className="bg-white border border-border rounded-xl px-5 py-4 shadow-sm">
          <div className="flex items-start gap-3 mb-4">
            <button
              onClick={() => setScreen("topic")}
              className="flex-none mt-0.5 font-sans text-xs text-fog hover:text-ink transition-colors flex items-center gap-1"
            >
              ← Back
            </button>
            <div className="flex-1 min-w-0">
              <h1 className="font-sans text-[15px] font-semibold text-ink leading-snug">{topic.title}</h1>
              <p className="font-sans text-[12px] text-fog mt-1 leading-relaxed line-clamp-2">{topic.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap pt-3 border-t border-border">
            <div className="flex border border-border rounded-lg overflow-hidden">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d.key}
                  onClick={() => setDifficulty(d.key)}
                  className={`font-sans text-xs px-3 py-1.5 border-r border-border last:border-r-0 transition-colors ${
                    difficulty === d.key ? "bg-scarlet text-white" : "text-fog hover:text-ink"
                  }`}
                >
                  {d.name}
                </button>
              ))}
            </div>

            <div className="flex border border-border rounded-lg overflow-hidden">
              {POSITIONS.map((p) => (
                <button
                  key={p}
                  onClick={() => setPosition(p.toLowerCase())}
                  className={`font-sans text-xs px-3 py-1.5 border-r border-border last:border-r-0 transition-colors ${
                    position === p.toLowerCase() ? "bg-scarlet text-white" : "text-fog hover:text-ink"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>

            <div className="flex-1" />

            <button
              onClick={startNewSession}
              disabled={starting}
              className="font-sans text-sm font-semibold px-5 py-1.5 bg-scarlet text-white rounded-lg disabled:opacity-40 transition-opacity flex items-center gap-2"
            >
              <span className="text-[10px]">▶</span>
              <span>{starting ? "Starting…" : "Start New Session"}</span>
            </button>
          </div>

          {startError && <p className="font-sans text-xs text-scarlet mt-2">{startError}</p>}
        </div>
      </div>

      {/* ── Sessions list header ─────────────────────────────── */}
      <div className="flex-none px-6 pb-3">
        <div className="flex items-center gap-2">
          <span className="font-sans text-[10px] font-semibold text-fog uppercase tracking-widest">Sessions</span>
          <span className="font-sans text-[10px] bg-fog/10 text-fog px-1.5 py-0.5 rounded-full">{topicSessions.length}</span>
          <div className="flex-1 h-px bg-border" />
        </div>
      </div>

      {/* ── Session rows ──────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {topicSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-3xl mb-3">💬</p>
            <p className="font-sans text-sm font-semibold text-ink">No sessions yet</p>
            <p className="font-sans text-xs text-fog mt-1">Start your first debate on this topic above.</p>
          </div>
        ) : (
          <div>
            {topicSessions.map((session) => (
              <SessionRow
                key={session.session_id}
                session={session}
                onResume={() => resumeSession(session)}
                onMetrics={() => viewMetrics(session)}
                onTranscript={() => viewTranscript(session)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SessionRow({
  session,
  onResume,
  onMetrics,
  onTranscript,
}: {
  session: SessionListItem;
  onResume: () => void;
  onMetrics: () => void;
  onTranscript: () => void;
}) {
  const difficultyClass = DIFFICULTY_BADGE[session.difficulty] ?? "bg-fog/10 text-fog border-fog/20";

  return (
    <div className="flex items-center gap-4 px-4 py-3 rounded-lg hover:bg-white border border-transparent hover:border-border transition-all mb-px">

      <div className="flex-none w-28">
        <p className="font-sans text-xs font-semibold text-ink">{formatDate(session.started_at)}</p>
        <p className="font-sans text-[11px] text-fog mt-0.5">{formatTime(session.started_at)}</p>
      </div>

      <span className={`flex-none font-sans text-[10px] font-semibold uppercase tracking-wide px-2.5 py-0.5 rounded-full border ${
        session.status === "active"
          ? "bg-verdant/10 text-verdant border-verdant/20"
          : "bg-fog/8 text-fog border-fog/20"
      }`}>
        {session.status === "active" ? "Active" : "Ended"}
      </span>

      <span className={`flex-none font-sans text-[10px] uppercase tracking-wide px-2.5 py-0.5 rounded-full border ${difficultyClass}`}>
        {session.difficulty}
      </span>

      <div className="flex items-center gap-5 flex-1 min-w-0">
        <div className="text-center">
          <p className="font-mono text-sm font-bold text-ink">
            {session.overall_score > 0 ? session.overall_score : "—"}
          </p>
          <p className="font-sans text-[10px] text-fog">score</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-sm font-bold text-ink">{session.exchanges}</p>
          <p className="font-sans text-[10px] text-fog">turns</p>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-none">
        {session.status === "active" ? (
          <button
            onClick={onResume}
            className="font-sans text-xs font-semibold px-3 py-1.5 bg-scarlet text-white rounded-lg hover:bg-scarlet/80 transition-colors flex items-center gap-1"
          >
            <span className="text-[9px]">▶</span> Resume
          </button>
        ) : (
          <button
            onClick={onTranscript}
            className="font-sans text-xs px-3 py-1.5 border border-border rounded-lg text-fog hover:text-ink hover:border-fog/40 transition-colors"
          >
            Transcript
          </button>
        )}
        <button
          onClick={onMetrics}
          className="font-sans text-xs px-3 py-1.5 border border-border rounded-lg text-fog hover:text-ink hover:border-fog/40 transition-colors"
        >
          Metrics
        </button>
      </div>
    </div>
  );
}
