"use client";
import { useState, useEffect, useMemo } from "react";
import {
  IconChevronDown,
  IconChevronRight,
  IconMessageCircle,
  IconPlayerPlay,
  IconSearch,
  IconStar,
  IconX,
} from "@tabler/icons-react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";
import type { DebatableQuestion } from "@/types";

const DOMAINS = ["ALL", "POLICY", "TECHNOLOGY", "SOCIETY", "LIFE"] as const;
type Domain = (typeof DOMAINS)[number];

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced" },
  { key: "targeted", name: "Targeted" },
  { key: "ruthless", name: "Ruthless" },
] as const;

export default function TopicSelection() {
  const [topic, setTopic] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [selectedDomain, setSelectedDomain] = useState<Domain>("ALL");
  const [cardsByDomain, setCardsByDomain] = useState<Record<string, DebatableQuestion[]>>({});
  const [generating, setGenerating] = useState(false);
  const [startError, setStartError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [favoritesOpen, setFavoritesOpen] = useState(true);
  const [allOpen, setAllOpen] = useState(true);
  const [newOpen, setNewOpen] = useState(true);
  const [newQuestions, setNewQuestions] = useState<DebatableQuestion[]>([]);
  const [savingId, setSavingId] = useState<string | null>(null);
  const { setSession, setSessions, setTopicDetail, sessions } = useDebate();

  const storeCountByTopic = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of sessions) {
      const key = s.topic.toLowerCase();
      map[key] = (map[key] ?? 0) + 1;
    }
    return map;
  }, [sessions]);

  const [dbCountByTopic, setDbCountByTopic] = useState<Record<string, number>>({});

  const sessionCountByTopic = useMemo(() => {
    const merged: Record<string, number> = { ...dbCountByTopic };
    for (const [k, v] of Object.entries(storeCountByTopic)) {
      merged[k] = Math.max(merged[k] ?? 0, v);
    }
    return merged;
  }, [dbCountByTopic, storeCountByTopic]);

  useEffect(() => {
    Promise.all([
      api.getTopics(),
      api.getSavedTopics().catch(() => [] as DebatableQuestion[]),
    ]).then(([staticQs, savedQs]) => {
      const seen = new Set<string>();
      const grouped: Record<string, DebatableQuestion[]> = {};
      for (const q of [...staticQs, ...savedQs]) {
        if (seen.has(q.id)) continue;
        seen.add(q.id);
        if (!grouped[q.domain]) grouped[q.domain] = [];
        grouped[q.domain].push(q);
      }
      setCardsByDomain(grouped);
    }).catch(() => {});

    api.getTopicSessionCounts()
      .then((counts) => {
        const normalised: Record<string, number> = {};
        for (const [k, v] of Object.entries(counts)) normalised[k.toLowerCase()] = v;
        setDbCountByTopic(normalised);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("dm_fav_topics");
      if (saved) setFavorites(new Set(JSON.parse(saved)));
    } catch { /* ignore */ }
  }, []);

  function toggleFavorite(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try { localStorage.setItem("dm_fav_topics", JSON.stringify(Array.from(next))); } catch { /* ignore */ }
      return next;
    });
  }

  function selectTopic(card: DebatableQuestion) {
    const count = sessionCountByTopic[card.title.toLowerCase()] ?? 0;
    if (count === 0) {
      doStart(card.title, card.description);
    } else {
      setTopicDetail({ title: card.title, description: card.description });
    }
  }

  async function doStart(t: string, desc: string) {
    const trimmed = t.trim();
    if (!trimmed) return;
    setStartError("");
    setSubmitting(true);
    let res;
    try {
      res = await api.startSession(trimmed, desc, difficulty, "against");
    } catch {
      setStartError("Failed to start session — please try again.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    api.getSessions().then(setSessions).catch(() => {});
    setSession(res.session_id, { topic: trimmed, description: desc, difficulty, position: "against" as never });
  }

  function startWithCard(card: DebatableQuestion, e: React.MouseEvent) {
    e.stopPropagation();
    doStart(card.title, card.description);
  }

  async function generateMore() {
    const domain = selectedDomain === "ALL" ? "POLICY" : selectedDomain;
    setGenerating(true);
    try {
      const generated = await api.generateTopics(domain, 5);
      const existingIds = new Set([
        ...Object.values(cardsByDomain).flat().map(q => q.id),
        ...newQuestions.map(q => q.id),
      ]);
      const fresh = generated.filter(q => !existingIds.has(q.id));
      setNewQuestions(prev => [...prev, ...fresh]);
    } catch { /* silently fail */ } finally {
      setGenerating(false);
    }
  }

  async function addNewQuestion(q: DebatableQuestion) {
    setSavingId(q.id);
    try {
      await api.saveQuestion(q);
      setNewQuestions(prev => prev.filter(n => n.id !== q.id));
      setCardsByDomain(prev => ({
        ...prev,
        [q.domain]: [...(prev[q.domain] ?? []), q],
      }));
    } catch { /* leave */ } finally {
      setSavingId(null);
    }
  }

  function dismissNewQuestion(id: string) {
    setNewQuestions(prev => prev.filter(q => q.id !== id));
  }

  const allTopics = Object.values(cardsByDomain).flat();
  const totalCount = allTopics.length;

  const filtered = allTopics.filter((q) => {
    const domainMatch = selectedDomain === "ALL" || q.domain === selectedDomain;
    const searchMatch = !searchQuery || q.title.toLowerCase().includes(searchQuery.toLowerCase());
    return domainMatch && searchMatch;
  });

  const favoriteTopics = filtered.filter(q => favorites.has(q.id));
  const regularTopics = filtered.filter(q => !favorites.has(q.id));
  const generateDomain = selectedDomain === "ALL" ? "POLICY" : selectedDomain;

  return (
    <div className="flex flex-col h-full min-h-0 bg-chalk">

      {/* ── Floating input card ──────────────────────────────── */}
      <div className="flex-none px-5 pt-5 pb-4">
        <div className="bg-white border border-border rounded-2xl px-5 py-4 shadow-sm">
          <textarea
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Type any topic — politics, ethics, tech, philosophy…"
            className="w-full bg-transparent font-sans text-[15px] text-ink resize-none outline-none placeholder:text-fog leading-snug"
            rows={2}
          />
          <div className="flex items-center gap-2 flex-wrap mt-3 pt-3 border-t border-border">
            <select
              value={selectedDomain}
              onChange={(e) => setSelectedDomain(e.target.value as Domain)}
              className="font-sans text-xs text-ink border border-border rounded-lg px-3 py-1.5 bg-white outline-none cursor-pointer"
            >
              {DOMAINS.map(d => (
                <option key={d} value={d}>{d === "ALL" ? "All domains" : d.charAt(0) + d.slice(1).toLowerCase()}</option>
              ))}
            </select>

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

            <div className="flex-1" />

            <button
              disabled
              title="Coming soon"
              className="font-sans text-xs px-3 py-1.5 border border-border rounded-lg text-fog opacity-40 cursor-not-allowed flex items-center gap-1.5"
            >
              <span>🎙</span>
              <span>Voice</span>
              <span className="text-[9px] bg-fog/15 px-1 py-0.5 rounded-full uppercase tracking-wide">Soon</span>
            </button>

            <button
              onClick={() => doStart(topic, "")}
              disabled={submitting || !topic.trim()}
              className="font-sans text-sm font-semibold px-5 py-1.5 bg-scarlet text-white rounded-lg disabled:opacity-40 transition-opacity flex items-center gap-2"
            >
              <IconPlayerPlay size={11} />
              <span>{submitting ? "Starting…" : "Start debate"}</span>
            </button>
          </div>
        </div>
        {startError && <p className="font-sans text-xs text-scarlet mt-2 px-1">{startError}</p>}
      </div>

      {/* ── List toolbar ──────────────────────────────────────── */}
      <div className="flex-none flex items-center gap-2.5 px-5 pb-3">
        <span className="font-sans text-[11px] font-semibold text-fog/70 uppercase tracking-widest">
          All Topics
        </span>
        <span className="font-sans text-[10px] font-semibold bg-fog/10 text-fog px-1.5 py-0.5 rounded-full">
          {totalCount}
        </span>

        <div className="flex-1" />

        <button
          onClick={generateMore}
          disabled={generating}
          className="font-sans text-xs text-fog border border-dashed border-fog/30 rounded-full px-3 py-1 disabled:opacity-50 hover:border-scarlet/40 hover:text-scarlet transition-all flex-none"
        >
          {generating ? "Generating…" : `+ Generate ${generateDomain.toLowerCase()}`}
        </button>

        {/* Search */}
        <div className="relative flex-none">
          <IconSearch size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fog/50 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search"
            className="font-sans text-xs border border-border rounded-lg pl-7 pr-7 py-1.5 bg-white outline-none w-36 placeholder:text-fog/50 focus:border-scarlet/40 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fog/40 hover:text-fog transition-colors"
            >
              <IconX size={11} />
            </button>
          )}
        </div>
      </div>

      {/* ── Scrollable list ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-5 pb-8">

        {/* New / Generated group */}
        {newQuestions.length > 0 && (
          <div className="mb-6">
            <SectionHeader
              label="New"
              count={newQuestions.length}
              open={newOpen}
              accent
              onToggle={() => setNewOpen(v => !v)}
            />
            {newOpen && (
              <div className="flex flex-col gap-1.5 mt-1">
                {newQuestions.map(card => (
                  <NewTopicRow
                    key={card.id}
                    card={card}
                    saving={savingId === card.id}
                    sessionCount={sessionCountByTopic[card.title.toLowerCase()] ?? 0}
                    onSelect={() => selectTopic(card)}
                    onAdd={() => addNewQuestion(card)}
                    onDismiss={() => dismissNewQuestion(card.id)}
                    onStart={(e) => startWithCard(card, e)}
                    submitting={submitting}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Favorites group */}
        {favoriteTopics.length > 0 && (
          <div className="mb-6">
            <SectionHeader
              label="Favorites"
              count={favoriteTopics.length}
              open={favoritesOpen}
              onToggle={() => setFavoritesOpen(v => !v)}
            />
            {favoritesOpen && (
              <div className="flex flex-col gap-1.5 mt-1">
                {favoriteTopics.map(card => (
                  <TopicRow
                    key={card.id}
                    card={card}
                    favorited
                    sessionCount={sessionCountByTopic[card.title.toLowerCase()] ?? 0}
                    onSelect={() => selectTopic(card)}
                    onToggleFav={(e) => toggleFavorite(card.id, e)}
                    onStart={(e) => startWithCard(card, e)}
                    submitting={submitting}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* All topics group */}
        <div>
          <SectionHeader
            label={selectedDomain === "ALL" ? "All Topics" : selectedDomain.charAt(0) + selectedDomain.slice(1).toLowerCase()}
            count={regularTopics.length}
            open={allOpen}
            onToggle={() => setAllOpen(v => !v)}
          />

          {allOpen && (
            <>
              {allTopics.length === 0 ? (
                <div className="flex flex-col gap-1.5 mt-1">
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="h-[68px] rounded-xl border border-border bg-fog/5 animate-pulse" />
                  ))}
                </div>
              ) : regularTopics.length === 0 ? (
                <p className="font-sans text-xs text-fog py-8 text-center">No topics match your search.</p>
              ) : (
                <div className="flex flex-col gap-1.5 mt-1">
                  {regularTopics.map(card => (
                    <TopicRow
                      key={card.id}
                      card={card}
                      favorited={false}
                      sessionCount={sessionCountByTopic[card.title.toLowerCase()] ?? 0}
                      onSelect={() => selectTopic(card)}
                      onToggleFav={(e) => toggleFavorite(card.id, e)}
                      onStart={(e) => startWithCard(card, e)}
                      submitting={submitting}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionHeader({
  label,
  count,
  open,
  accent,
  onToggle,
}: {
  label: string;
  count: number;
  open: boolean;
  accent?: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center gap-2.5 py-2 group"
    >
      <span className={`font-sans text-[10px] font-semibold uppercase tracking-widest ${accent ? "text-scarlet" : "text-fog/70"}`}>
        {label}
      </span>
      <span className={`font-sans text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${accent ? "bg-scarlet/10 text-scarlet" : "bg-fog/10 text-fog"}`}>
        {count}
      </span>
      <div className="flex-1 h-px bg-border" />
      {open
        ? <IconChevronDown size={13} className="text-fog/40 group-hover:text-fog transition-colors flex-none" />
        : <IconChevronRight size={13} className="text-fog/40 group-hover:text-fog transition-colors flex-none" />
      }
    </button>
  );
}

function TopicRow({
  card,
  favorited,
  sessionCount,
  onSelect,
  onToggleFav,
  onStart,
  submitting,
}: {
  card: DebatableQuestion;
  favorited: boolean;
  sessionCount: number;
  onSelect: () => void;
  onToggleFav: (e: React.MouseEvent) => void;
  onStart: (e: React.MouseEvent) => void;
  submitting: boolean;
}) {
  return (
    <div
      onClick={onSelect}
      className="flex items-center gap-4 px-4 py-3.5 rounded-xl cursor-pointer bg-white border border-border hover:border-scarlet/20 hover:shadow-sm transition-all"
    >
      <div className="flex-1 min-w-0">
        <p className="font-sans text-[13px] font-semibold text-ink leading-snug">{card.title}</p>
        <p className="font-sans text-[11px] text-fog truncate mt-1 leading-snug">{card.description}</p>
      </div>
      <div className="flex items-center gap-2 flex-none">
        <span className="flex items-center gap-1 font-sans text-[10px] text-fog bg-fog/8 border border-border rounded-full px-2.5 py-1 whitespace-nowrap">
          <IconMessageCircle size={10} className="text-fog/60" />
          {sessionCount} {sessionCount === 1 ? "session" : "sessions"}
        </span>
        <span className="font-sans text-[9px] font-semibold text-fog/60 border border-border rounded-full px-2 py-1 uppercase tracking-wide">
          {card.domain}
        </span>
        <button
          onClick={onToggleFav}
          className="p-1 transition-colors"
          title={favorited ? "Remove from favorites" : "Add to favorites"}
        >
          <IconStar
            size={14}
            className={favorited ? "text-yellow-400 fill-yellow-400" : "text-fog/30 hover:text-yellow-400 transition-colors"}
          />
        </button>
        <button
          onClick={onStart}
          disabled={submitting}
          className="w-7 h-7 rounded-full bg-scarlet text-white flex items-center justify-center disabled:opacity-40 hover:bg-scarlet/80 transition-colors"
        >
          <IconPlayerPlay size={11} />
        </button>
      </div>
    </div>
  );
}

function NewTopicRow({
  card,
  saving,
  sessionCount,
  onSelect,
  onAdd,
  onDismiss,
  onStart,
  submitting,
}: {
  card: DebatableQuestion;
  saving: boolean;
  sessionCount: number;
  onSelect: () => void;
  onAdd: () => void;
  onDismiss: () => void;
  onStart: (e: React.MouseEvent) => void;
  submitting: boolean;
}) {
  return (
    <div
      onClick={onSelect}
      className="flex items-center gap-4 px-4 py-3.5 rounded-xl cursor-pointer border border-dashed border-scarlet/25 bg-scarlet/[0.02] hover:border-scarlet/40 hover:bg-white transition-all"
    >
      <div className="flex-1 min-w-0">
        <p className="font-sans text-[13px] font-semibold text-ink leading-snug">{card.title}</p>
        <p className="font-sans text-[11px] text-fog truncate mt-1 leading-snug">{card.description}</p>
      </div>
      <div className="flex items-center gap-2 flex-none">
        <span className="flex items-center gap-1 font-sans text-[10px] text-fog bg-fog/8 border border-border rounded-full px-2.5 py-1">
          <IconMessageCircle size={10} className="text-fog/60" />
          {sessionCount}
        </span>
        <span className="font-sans text-[9px] font-semibold text-fog/60 border border-border rounded-full px-2 py-1 uppercase tracking-wide">
          {card.domain}
        </span>
        <button
          onClick={(e) => { e.stopPropagation(); onAdd(); }}
          disabled={saving}
          className="font-sans text-[11px] font-semibold px-2.5 py-1 rounded-full border border-scarlet/40 text-scarlet hover:bg-scarlet hover:text-white transition-colors disabled:opacity-40"
        >
          {saving ? "…" : "+ Add"}
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); onDismiss(); }}
          className="text-fog/40 hover:text-ink transition-colors p-0.5"
        >
          <IconX size={13} />
        </button>
        <button
          onClick={onStart}
          disabled={submitting}
          className="w-7 h-7 rounded-full bg-scarlet text-white flex items-center justify-center disabled:opacity-40 hover:bg-scarlet/80 transition-colors"
        >
          <IconPlayerPlay size={11} />
        </button>
      </div>
    </div>
  );
}
