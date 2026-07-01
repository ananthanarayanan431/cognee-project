"use client";
import { useEffect, useState } from "react";
import {
  IconBrain,
  IconChevronDown,
  IconChevronRight,
  IconDownload,
  IconFileText,
  IconHistory,
  IconPlayerPlay,
  IconSparkles,
} from "@tabler/icons-react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { SessionListItem } from "@/types";

const DIFFICULTY_COLOR: Record<string, string> = {
  balanced: "bg-blue-500/20 text-blue-300",
  targeted: "bg-amber-500/20 text-amber-300",
  ruthless: "bg-scarlet/20 text-scarlet",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function SessionCard({
  session,
  onResume,
  onTranscript,
  onSummary,
}: {
  session: SessionListItem;
  onResume: () => void;
  onTranscript: () => void;
  onSummary: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const difficultyClass = DIFFICULTY_COLOR[session.difficulty] ?? "bg-white/10 text-white/50";

  return (
    <div className="border border-white/10 rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 px-3 py-2.5 hover:bg-white/5 transition-colors text-left"
      >
        <span className="mt-0.5 flex-shrink-0 text-white/30">
          {expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-sans text-[12px] text-white/80 leading-snug truncate">{session.topic}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span className={`font-sans text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${difficultyClass}`}>
              {session.difficulty}
            </span>
            <span className="font-sans text-[10px] text-white/30">{session.exchanges} turns</span>
            <span className="font-sans text-[10px] text-white/30 ml-auto">{formatDate(session.started_at)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-white/10 px-3 py-2 flex gap-2">
          <button
            onClick={onSummary}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-white/5 hover:bg-white/10 transition-colors font-sans text-[10px] text-white/60 hover:text-white/90"
          >
            <IconChevronDown size={11} />
            Summary
          </button>
          <button
            onClick={onTranscript}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-white/5 hover:bg-white/10 transition-colors font-sans text-[10px] text-white/60 hover:text-white/90"
          >
            <IconFileText size={11} />
            Transcript
          </button>
          {session.status === "active" && (
            <button
              onClick={onResume}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-scarlet/20 hover:bg-scarlet/30 transition-colors font-sans text-[10px] text-scarlet"
            >
              <IconPlayerPlay size={11} />
              Resume
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function BrainSection({ winRate }: { winRate: number | null }) {
  const { sessions } = useDebate();
  const [description, setDescription] = useState<string | null>(null);
  const [loadingDesc, setLoadingDesc] = useState(false);
  const [showDesc, setShowDesc] = useState(false);

  const totalSessions = sessions.length;

  async function handleDescribe() {
    if (description) {
      setShowDesc((v) => !v);
      return;
    }
    setLoadingDesc(true);
    try {
      const data = await api.describeUser();
      setDescription(data.description);
      setShowDesc(true);
    } finally {
      setLoadingDesc(false);
    }
  }

  function handleExport() {
    const url = api.exportProfileUrl();
    const a = document.createElement("a");
    a.href = url;
    const token = localStorage.getItem("dm_token");
    // Trigger fetch with auth header via window.open workaround isn't possible;
    // use a quick fetch-and-blob approach instead.
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        a.href = URL.createObjectURL(blob);
        a.download = "debatemind_profile.json";
        a.click();
        URL.revokeObjectURL(a.href);
      });
  }

  return (
    <div className="px-4 py-3 border-b border-white/10">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <IconBrain size={14} className="text-scarlet" />
          <span className="font-sans text-[11px] font-semibold uppercase tracking-widest text-white/60">
            Your Brain
          </span>
        </div>
        <button
          onClick={handleExport}
          title="Export profile"
          className="text-white/30 hover:text-white/60 transition-colors"
        >
          <IconDownload size={13} />
        </button>
      </div>

      <div className="flex gap-3 mb-2.5">
        <div className="flex-1 bg-white/5 rounded-lg px-2.5 py-2 text-center">
          <p className="font-mono text-[15px] font-bold text-white">{totalSessions}</p>
          <p className="font-sans text-[9px] text-white/40 uppercase tracking-wide mt-0.5">Sessions</p>
        </div>
        <div className="flex-1 bg-white/5 rounded-lg px-2.5 py-2 text-center">
          <p className="font-mono text-[15px] font-bold text-white">{winRate !== null ? `${winRate}%` : "—"}</p>
          <p className="font-sans text-[9px] text-white/40 uppercase tracking-wide mt-0.5">Win rate</p>
        </div>
      </div>

      <button
        onClick={handleDescribe}
        disabled={loadingDesc}
        className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded bg-scarlet/15 hover:bg-scarlet/25 transition-colors font-sans text-[11px] text-scarlet disabled:opacity-50"
      >
        <IconSparkles size={12} />
        {loadingDesc ? "Analyzing…" : showDesc ? "Hide profile" : "Describe me"}
      </button>

      {showDesc && description && (
        <p className="mt-2.5 font-sans text-[11px] text-white/55 leading-relaxed">{description}</p>
      )}
    </div>
  );
}

export default function SessionSidebar() {
  const { token, sessions, setSessions, setScreen, setSession } = useDebate();
  const [loading, setLoading] = useState(false);
  const [winRate, setWinRate] = useState<number | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    Promise.all([
      api.getSessions().then(setSessions),
      api.getProgress().then((p) => setWinRate(Math.round(p.win_rate * 100))),
    ])
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, setSessions]);

  function handleResume(session: SessionListItem) {
    setSession(session.session_id, {
      topic: session.topic,
      description: "",
      difficulty: session.difficulty as "balanced" | "targeted" | "ruthless",
      position: "against",
    });
  }

  function handleTranscript(session: SessionListItem) {
    useDebate.setState({ sessionId: session.session_id });
    setScreen("transcript");
  }

  function handleSummary(session: SessionListItem) {
    useDebate.setState({ sessionId: session.session_id });
    setScreen("end");
  }

  return (
    <aside className="w-[260px] min-w-[220px] bg-carbon border-r border-white/10 flex flex-col text-white overflow-hidden">
      {/* Logo */}
      <div className="px-4 py-3.5 border-b border-white/10 flex items-center gap-2">
        <span className="font-display text-[18px] text-white leading-none">DebateMind</span>
      </div>

      <BrainSection winRate={winRate} />

      {/* Session history */}
      <div className="flex items-center gap-1.5 px-4 pt-3 pb-1.5">
        <IconHistory size={13} className="text-white/30" />
        <span className="font-sans text-[11px] font-semibold uppercase tracking-widest text-white/40">
          Sessions
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 flex flex-col gap-2">
        {loading && (
          <p className="font-sans text-[11px] text-white/30 text-center py-4">Loading…</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="font-sans text-[11px] text-white/30 text-center py-4">No sessions yet.</p>
        )}
        {sessions.map((s) => (
          <SessionCard
            key={s.session_id}
            session={s}
            onResume={() => handleResume(s)}
            onTranscript={() => handleTranscript(s)}
            onSummary={() => handleSummary(s)}
          />
        ))}
      </div>
    </aside>
  );
}
