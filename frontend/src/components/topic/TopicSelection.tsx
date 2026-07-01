"use client";
import { useState, useEffect } from "react";
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

const POSITIONS = ["For", "Against", "Neutral"] as const;

export default function TopicSelection() {
  const [topic, setTopic] = useState("");
  const [description, setDescription] = useState("");
  const [selectedCardId, setSelectedCardId] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [selectedDomain, setSelectedDomain] = useState<Domain>("ALL");
  const [cardsByDomain, setCardsByDomain] = useState<Record<string, DebatableQuestion[]>>({});
  const [generating, setGenerating] = useState(false);
  const [startError, setStartError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [favoritesOpen, setFavoritesOpen] = useState(true);
  const [allOpen, setAllOpen] = useState(true);
  const { setSession, setSessions } = useDebate();

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
    setTopic(card.title);
    setDescription(card.description);
    setSelectedCardId(card.id);
  }

  async function doStart(t: string, desc: string) {
    setStartError("");
    setSubmitting(true);
    let res;
    try {
      res = await api.startSession(t, desc, difficulty, position);
    } catch {
      setStartError("Failed to start session — please try again.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    api.getSessions().then(setSessions).catch(() => {});
    setSession(res.session_id, { topic: t, description: desc, difficulty, position: position as never });
  }

  function startWithCard(card: DebatableQuestion, e: React.MouseEvent) {
    e.stopPropagation();
    selectTopic(card);
    doStart(card.title, card.description);
  }

  async function generateMore() {
    const domain = selectedDomain === "ALL" ? "POLICY" : selectedDomain;
    setGenerating(true);
    try {
      const newCards = await api.generateTopics(domain, 5);
      setCardsByDomain((prev) => ({
        ...prev,
        [domain]: [...(prev[domain] ?? []), ...newCards],
      }));
    } catch { /* silently fail */ } finally {
      setGenerating(false);
    }
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
    <div className="flex flex-col h-full min-h-0">

      {/* ── Top input panel ─────────────────────────────────── */}
      <div className="flex-none px-7 pt-8 pb-5 border-b border-border bg-white">
        <textarea
          value={topic}
          onChange={(e) => {
            setTopic(e.target.value);
            if (!e.target.value) { setDescription(""); setSelectedCardId(""); }
          }}
          placeholder="What do you want to argue about?"
          className="w-full bg-transparent font-sans text-base text-ink resize-none outline-none mb-1 placeholder:text-fog"
          rows={2}
        />
        {topic && description && (
          <p className="font-sans text-xs text-fog line-clamp-1 mb-3">{description}</p>
        )}

        <div className="flex items-center gap-2 flex-wrap mt-3">
          {/* Domain dropdown */}
          <select
            value={selectedDomain}
            onChange={(e) => setSelectedDomain(e.target.value as Domain)}
            className="font-sans text-xs text-ink border border-border rounded-lg px-3 py-2 bg-white outline-none cursor-pointer"
          >
            {DOMAINS.map(d => (
              <option key={d} value={d}>{d === "ALL" ? "All domains" : d}</option>
            ))}
          </select>

          {/* Difficulty */}
          <div className="flex border border-border rounded-lg overflow-hidden">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.key}
                onClick={() => setDifficulty(d.key)}
                className={`font-sans text-xs px-3 py-2 border-r border-border last:border-r-0 transition-colors ${
                  difficulty === d.key ? "bg-scarlet text-white" : "bg-white text-fog hover:text-ink"
                }`}
              >
                {d.name}
              </button>
            ))}
          </div>

          {/* Position */}
          <div className="flex border border-border rounded-lg overflow-hidden">
            {POSITIONS.map((p) => (
              <button
                key={p}
                onClick={() => setPosition(p.toLowerCase())}
                className={`font-sans text-xs px-3 py-2 border-r border-border last:border-r-0 transition-colors ${
                  position === p.toLowerCase() ? "bg-scarlet text-white" : "bg-white text-fog hover:text-ink"
                }`}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="flex-1" />

          {/* Voice (coming soon) */}
          <button
            disabled
            title="Coming soon"
            className="font-sans text-xs px-3 py-2 border border-border rounded-lg text-fog opacity-40 cursor-not-allowed flex items-center gap-1.5"
          >
            <span>🎙</span>
            <span>Voice</span>
            <span className="text-[9px] bg-fog/20 px-1 py-0.5 rounded-full uppercase tracking-wide">Soon</span>
          </button>

          {/* Start chat */}
          <button
            onClick={() => doStart(topic, description)}
            disabled={submitting || !topic}
            className="font-sans text-sm font-semibold px-5 py-2 bg-scarlet text-white rounded-lg disabled:opacity-50 transition-opacity flex items-center gap-2"
          >
            <span>▶</span>
            <span>{submitting ? "Starting…" : "Start AI Chat"}</span>
          </button>
        </div>

        {startError && <p className="font-sans text-xs text-scarlet mt-2">{startError}</p>}
      </div>

      {/* ── List header ──────────────────────────────────────── */}
      <div className="flex-none flex items-center gap-3 px-7 py-3 border-b border-border bg-white">
        <span className="font-sans text-[11px] font-semibold text-fog uppercase tracking-widest">All Topics</span>
        <span className="font-sans text-xs font-semibold bg-fog/10 text-fog px-2 py-0.5 rounded-full">{totalCount}</span>
        <div className="flex-1" />
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search"
            className="font-sans text-xs border border-border rounded-lg pl-7 pr-3 py-1.5 bg-white outline-none w-44 placeholder:text-fog"
          />
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fog text-xs pointer-events-none">🔍</span>
        </div>
      </div>

      {/* ── Scrollable list ──────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-7 py-4">

        {/* Favorites group */}
        {favoriteTopics.length > 0 && (
          <div className="mb-5">
            <button
              onClick={() => setFavoritesOpen(v => !v)}
              className="flex items-center gap-2 mb-1 w-full text-left group"
            >
              <span className="font-sans text-xs font-semibold text-scarlet">Favorites</span>
              <span className="text-scarlet text-[10px] group-hover:opacity-70 transition-opacity">
                {favoritesOpen ? "▲" : "▼"}
              </span>
            </button>
            {favoritesOpen && (
              <div>
                {favoriteTopics.map(card => (
                  <TopicRow
                    key={card.id}
                    card={card}
                    selected={selectedCardId === card.id}
                    favorited
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
          <button
            onClick={() => setAllOpen(v => !v)}
            className="flex items-center gap-2 mb-1 w-full text-left group"
          >
            <span className="font-sans text-xs font-semibold text-fog">
              {selectedDomain === "ALL" ? "All Topics" : selectedDomain} ({regularTopics.length})
            </span>
            <span className="text-fog text-[10px] group-hover:opacity-70 transition-opacity">
              {allOpen ? "▲" : "▼"}
            </span>
          </button>

          {allOpen && (
            <>
              {allTopics.length === 0 ? (
                /* skeleton while loading */
                <div>
                  {[...Array(6)].map((_, i) => (
                    <div key={i} className="h-14 rounded-lg border border-border bg-fog/5 animate-pulse mb-px" />
                  ))}
                </div>
              ) : regularTopics.length === 0 ? (
                <p className="font-sans text-xs text-fog py-6 text-center">No topics match your search.</p>
              ) : (
                <div>
                  {regularTopics.map(card => (
                    <TopicRow
                      key={card.id}
                      card={card}
                      selected={selectedCardId === card.id}
                      favorited={false}
                      onSelect={() => selectTopic(card)}
                      onToggleFav={(e) => toggleFavorite(card.id, e)}
                      onStart={(e) => startWithCard(card, e)}
                      submitting={submitting}
                    />
                  ))}
                </div>
              )}

              <button
                onClick={generateMore}
                disabled={generating}
                className="mt-4 font-sans text-xs text-fog border border-dashed border-fog/40 rounded-full px-4 py-1.5 disabled:opacity-50 transition-opacity"
              >
                {generating ? "Generating…" : `+ Generate more ${generateDomain.toLowerCase()} questions`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function TopicRow({
  card,
  selected,
  favorited,
  onSelect,
  onToggleFav,
  onStart,
  submitting,
}: {
  card: DebatableQuestion;
  selected: boolean;
  favorited: boolean;
  onSelect: () => void;
  onToggleFav: (e: React.MouseEvent) => void;
  onStart: (e: React.MouseEvent) => void;
  submitting: boolean;
}) {
  return (
    <div
      onClick={onSelect}
      className={`flex items-center gap-4 px-4 py-3 rounded-lg cursor-pointer border transition-all mb-px ${
        selected
          ? "border-scarlet bg-scarlet/5"
          : "border-transparent hover:border-border hover:bg-fog/5"
      }`}
    >
      <div className="flex-1 min-w-0">
        <p className={`font-sans text-sm font-medium truncate ${selected ? "text-scarlet" : "text-ink"}`}>
          {card.title}
        </p>
        <p className="font-sans text-[11px] text-fog truncate mt-0.5">{card.description}</p>
      </div>

      <div className="flex items-center gap-2 flex-none">
        <span className="font-sans text-[10px] text-fog border border-fog/20 rounded-full px-2 py-0.5 uppercase tracking-wide">
          {card.domain}
        </span>
        <button
          onClick={onToggleFav}
          className={`text-base leading-none transition-colors ${
            favorited ? "text-yellow-400" : "text-fog hover:text-yellow-400"
          }`}
        >
          ★
        </button>
        <button
          onClick={onStart}
          disabled={submitting}
          className="w-7 h-7 rounded-full bg-scarlet text-white flex items-center justify-center text-xs disabled:opacity-50 hover:bg-scarlet/80 transition-colors"
        >
          ▶
        </button>
      </div>
    </div>
  );
}
