"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  IconBrain,
  IconChartBar,
  IconChevronDown,
  IconChevronRight,
  IconDownload,
  IconHistory,
  IconLogout,
  IconNetwork,
  IconPlayerPlay,
  IconSettings,
  IconSparkles,
  IconX,
} from "@tabler/icons-react";
import { useClerk } from "@clerk/nextjs";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { GraphData, SessionListItem } from "@/types";
import BrainGraph from "@/components/graph/BrainGraph";

const DIFFICULTY_COLOR: Record<string, string> = {
  balanced: "bg-blue-50 text-blue-600 border border-blue-100",
  targeted: "bg-amber-50 text-amber-700 border border-amber-100",
  ruthless: "bg-scarlet/10 text-scarlet border border-scarlet/20",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function SessionCard({
  session,
  onResume,
  onMetrics,
}: {
  session: SessionListItem;
  onResume: () => void;
  onMetrics: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const difficultyClass = DIFFICULTY_COLOR[session.difficulty] ?? "bg-fog/10 text-fog border-fog/20";

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 px-3 py-2.5 hover:bg-fog/5 transition-colors text-left"
      >
        <span className="mt-0.5 flex-shrink-0 text-fog/50">
          {expanded ? <IconChevronDown size={14} /> : <IconChevronRight size={14} />}
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-sans text-[12px] text-ink leading-snug truncate">{session.topic}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span className={`font-sans text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${difficultyClass}`}>
              {session.difficulty}
            </span>
            <span className="font-sans text-[10px] text-fog">{session.exchanges} turns</span>
            <span className="font-sans text-[10px] text-fog ml-auto">{formatDate(session.started_at)}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-3 py-2 flex gap-2">
          <button
            onClick={onMetrics}
            className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-fog/5 hover:bg-fog/10 transition-colors font-sans text-[10px] text-fog hover:text-ink"
          >
            <IconChartBar size={11} />
            Metrics
          </button>
          {session.status === "active" && (
            <button
              onClick={onResume}
              className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded bg-scarlet/10 hover:bg-scarlet/20 transition-colors font-sans text-[10px] text-scarlet"
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

// ── Brain Map Modal ───────────────────────────────────────────────────────────

const LEGEND = [
  { color: "#1e3a5f", border: "#3b82f6aa", label: "Topic" },
  { color: "#C0392B", border: "#C0392B88", label: "Weakness" },
  { color: "#27AE60", border: "#27AE6088", label: "Strength" },
  { color: "#3a3a3a", border: "#666",      label: "Mastered" },
];

function BrainMapModal({
  onClose,
  winRate,
  totalSessions,
  description,
}: {
  onClose: () => void;
  winRate: number | null;
  totalSessions: number;
  description: string | null;
}) {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState(false);

  useEffect(() => {
    api.getBrainGraph()
      .then((d) => setGraphData(d))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 pt-4 pb-3 border-b border-border flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <IconBrain size={18} className="text-scarlet" />
          <span className="font-sans text-[15px] font-semibold text-ink">Your Brain Map</span>
        </div>

        <div className="flex items-center gap-5">
          {LEGEND.map((l) => (
            <div key={l.label} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-full border"
                style={{ background: l.color, borderColor: l.border }}
              />
              <span className="font-sans text-[12px] text-fog">{l.label}</span>
            </div>
          ))}
        </div>

        <button onClick={onClose} className="text-fog/60 hover:text-ink transition-colors p-1">
          <IconX size={18} />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex-1 relative overflow-hidden bg-[#0d0d0d]">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <span className="text-4xl opacity-30 animate-pulse">🧠</span>
                <p className="font-sans text-[13px] text-white/30">Building your brain map…</p>
              </div>
            </div>
          )}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="font-sans text-[13px] text-white/30">Failed to load brain map.</p>
            </div>
          )}
          {graphData && !loading && <BrainGraph data={graphData} />}
          <div className="absolute bottom-3 left-0 right-0 flex justify-center pointer-events-none">
            <span className="font-sans text-[10px] text-white/20">
              Scroll to zoom · drag nodes · click topic to expand
            </span>
          </div>
        </div>

        <div className="w-1/2 border-l border-border flex flex-col overflow-y-auto flex-shrink-0">
          <div className="flex border-b border-border">
            <div className="flex-1 px-8 py-6 text-center border-r border-border">
              <p className="font-mono text-[40px] font-bold text-ink leading-none">{totalSessions}</p>
              <p className="font-sans text-[11px] text-fog uppercase tracking-widest mt-2">Sessions</p>
            </div>
            <div className="flex-1 px-8 py-6 text-center">
              <p className="font-mono text-[40px] font-bold text-ink leading-none">
                {winRate !== null ? `${winRate}%` : "—"}
              </p>
              <p className="font-sans text-[11px] text-fog uppercase tracking-widest mt-2">Win Rate</p>
            </div>
          </div>

          <div className="flex-1 p-8">
            {description ? (
              <div className="prose prose-sm max-w-none
                prose-headings:font-sans prose-headings:font-semibold prose-headings:text-ink
                prose-h1:text-[18px] prose-h1:mb-4 prose-h1:mt-0
                prose-h2:text-[15px] prose-h2:mb-3 prose-h2:mt-6
                prose-p:text-[15px] prose-p:text-fog prose-p:leading-[1.8] prose-p:my-3
                prose-strong:text-ink prose-strong:font-semibold
                prose-ul:my-3 prose-li:text-[15px] prose-li:text-fog prose-li:leading-[1.8]
              ">
                <ReactMarkdown>{description}</ReactMarkdown>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 h-full text-center">
                <IconSparkles size={24} className="text-fog/30" />
                <p className="font-sans text-[14px] text-fog leading-relaxed max-w-[260px]">
                  Use &ldquo;Describe me&rdquo; in the sidebar to generate your debate profile.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Brain Section ─────────────────────────────────────────────────────────────

function BrainSection({ winRate, onOpenBrainMap }: { winRate: number | null; onOpenBrainMap: () => void }) {
  const { sessions } = useDebate();
  const [description, setDescription] = useState<string | null>(null);
  const [loadingDesc, setLoadingDesc] = useState(false);
  const [showDesc, setShowDesc]       = useState(false);

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
    const token = localStorage.getItem("dm_token");
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => {
        if (!r.ok) return;
        r.blob().then((blob) => {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = "debatemind_profile.json";
          a.click();
          URL.revokeObjectURL(a.href);
        });
      });
  }

  return (
    <div className="px-4 py-3 border-b border-border">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <IconBrain size={14} className="text-scarlet" />
          <span className="font-sans text-[11px] font-semibold uppercase tracking-widest text-fog">
            Your Brain
          </span>
        </div>
        <button
          onClick={handleExport}
          title="Export profile"
          className="text-fog/50 hover:text-fog transition-colors"
        >
          <IconDownload size={13} />
        </button>
      </div>

      <div className="flex gap-3 mb-2.5">
        <div className="flex-1 bg-fog/5 rounded-lg px-2.5 py-2 text-center">
          <p className="font-mono text-[15px] font-bold text-ink">{totalSessions}</p>
          <p className="font-sans text-[9px] text-fog uppercase tracking-wide mt-0.5">Sessions</p>
        </div>
        <div className="flex-1 bg-fog/5 rounded-lg px-2.5 py-2 text-center">
          <p className="font-mono text-[15px] font-bold text-ink">{winRate !== null ? `${winRate}%` : "—"}</p>
          <p className="font-sans text-[9px] text-fog uppercase tracking-wide mt-0.5">Win rate</p>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleDescribe}
          disabled={loadingDesc}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded bg-scarlet/10 hover:bg-scarlet/20 transition-colors font-sans text-[11px] text-scarlet disabled:opacity-50"
        >
          <IconSparkles size={12} />
          {loadingDesc ? "Analyzing…" : showDesc ? "Hide profile" : "Describe me"}
        </button>
      </div>

      {showDesc && description && (
        <p className="mt-2.5 font-sans text-[11px] text-fog leading-relaxed">{description}</p>
      )}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

export default function SessionSidebar() {
  const { signOut } = useClerk();
  const { token, sessions, setSessions, setScreen, setSession } = useDebate();

  async function handleSignOut() {
    localStorage.removeItem("dm_token");
    localStorage.removeItem("dm_uid");
    localStorage.removeItem("dm_calibration");
    useDebate.setState({ token: null, userId: null, screen: "landing" });
    await signOut({ redirectUrl: "/" });
  }
  const [loading, setLoading]           = useState(false);
  const [winRate, setWinRate]           = useState<number | null>(null);
  const [showBrainMap, setShowBrainMap] = useState(false);

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

  function handleMetrics(session: SessionListItem) {
    useDebate.setState({ sessionId: session.session_id });
    setScreen("end");
  }

  return (
    <aside className="w-[260px] min-w-[220px] bg-white border-r border-border flex flex-col overflow-hidden">
      {/* Logo */}
      <div className="px-4 py-3.5 border-b border-border flex items-center gap-2">
        <button
          onClick={() => {
            setScreen("topic");
            window.history.pushState({ screen: "topic" }, "", "/");
          }}
          className="font-sans font-semibold text-[18px] text-ink leading-none hover:text-scarlet transition-colors text-left"
          title="Home"
        >
          DebateMind
        </button>
      </div>

      <BrainSection winRate={winRate} onOpenBrainMap={() => setShowBrainMap(true)} />

      {/* Session history */}
      <div className="flex items-center gap-1.5 px-4 pt-3 pb-1.5">
        <IconHistory size={13} className="text-fog/50" />
        <span className="font-sans text-[11px] font-semibold uppercase tracking-widest text-fog">
          Sessions
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-4 flex flex-col gap-2">
        {loading && (
          <p className="font-sans text-[11px] text-fog text-center py-4">Loading…</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="font-sans text-[11px] text-fog text-center py-4">No sessions yet.</p>
        )}
        {sessions.map((s) => (
          <SessionCard
            key={s.session_id}
            session={s}
            onResume={() => handleResume(s)}
            onMetrics={() => handleMetrics(s)}
          />
        ))}
      </div>

      {/* Bottom nav */}
      <div className="border-t border-border flex-shrink-0">
        <p className="font-sans text-[9px] font-semibold uppercase tracking-widest text-fog/50 px-4 pt-3 pb-1">
          Platform
        </p>
        <button
          onClick={() => setShowBrainMap(true)}
          className="w-full flex items-center gap-2.5 px-4 py-2 hover:bg-fog/5 transition-colors text-left"
        >
          <IconNetwork size={14} className="text-fog/50" />
          <span className="font-sans text-[12px] text-fog">Knowledge Graph</span>
        </button>
        <button
          onClick={() => setScreen("settings")}
          className="w-full flex items-center gap-2.5 px-4 py-2 hover:bg-fog/5 transition-colors text-left"
        >
          <IconSettings size={14} className="text-fog/50" />
          <span className="font-sans text-[12px] text-fog">Settings</span>
        </button>
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-2.5 px-4 py-2 mb-2 hover:bg-fog/5 transition-colors text-left"
        >
          <IconLogout size={14} className="text-fog/50" />
          <span className="font-sans text-[12px] text-fog">Sign out</span>
        </button>
      </div>

      {showBrainMap && (
        <BrainMapModal
          onClose={() => setShowBrainMap(false)}
          winRate={winRate}
          totalSessions={sessions.length}
          description={null}
        />
      )}
    </aside>
  );
}
