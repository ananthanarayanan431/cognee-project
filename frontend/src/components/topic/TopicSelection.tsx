"use client";
import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

const DIFFICULTIES = [
  { key: "balanced", name: "Balanced", desc: "Varied angles, 60% weakness" },
  { key: "targeted", name: "Targeted", desc: "Every move hits a known weak node" },
  { key: "ruthless", name: "Ruthless", desc: "Same weakness, every angle" },
] as const;

const POSITIONS = ["For", "Against", "Neutral", "Assign randomly"] as const;
const SURPRISES = [
  "Nuclear power is the only realistic path to decarbonisation",
  "Universal basic income will erode the dignity of work",
  "Social media should be banned for under-16s",
];

const MAX_SOURCE_BYTES = 20 * 1024 * 1024;

export default function TopicSelection() {
  const [topic, setTopic] = useState("AI regulation should be government-led");
  const [description, setDescription] = useState("");
  const [activeChip, setActiveChip] = useState("");
  const [difficulty, setDifficulty] = useState<"balanced" | "targeted" | "ruthless">("targeted");
  const [position, setPosition] = useState("against");
  const [groups, setGroups] = useState<{ label: string; chips: string[] }[]>([]);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { setSession } = useDebate();

  useEffect(() => { api.getTopics().then(setGroups).catch(() => {}); }, []);

  // Clean up poll timer on unmount
  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setFileError("");
    if (file && file.type !== "application/pdf") {
      setFileError("Only PDF files are supported.");
      setSourceFile(null);
      return;
    }
    if (file && file.size > MAX_SOURCE_BYTES) {
      setFileError("File exceeds 20MB limit.");
      setSourceFile(null);
      return;
    }
    setSourceFile(file);
  }

  function navigateToSession(sessionId: string) {
    if (pollRef.current) clearTimeout(pollRef.current);
    setIndexing(false);
    setPendingSessionId(null);
    setSession(sessionId, { topic, description, difficulty, position: position as never });
  }

  function startPolling(sessionId: string) {
    const poll = async () => {
      try {
        const { source_status } = await api.getSourceStatus(sessionId);
        if (source_status === "indexed") {
          navigateToSession(sessionId);
          return;
        }
        if (source_status === "failed") {
          setFileError("Indexing failed — opponent will start without source context.");
          navigateToSession(sessionId);
          return;
        }
        // Still pending — check again in 2 s
        pollRef.current = setTimeout(poll, 2000);
      } catch {
        // Network error — navigate anyway
        navigateToSession(sessionId);
      }
    };
    pollRef.current = setTimeout(poll, 2000);
  }

  async function start() {
    setFileError("");
    setSubmitting(true);
    let res;
    try {
      res = await api.startSession(topic, description, difficulty, position);
    } catch {
      setFileError("Failed to start session — please try again.");
      setSubmitting(false);
      return;
    }
    setSubmitting(false);
    if (sourceFile) {
      setIndexing(true);
      setPendingSessionId(res.session_id);
      try {
        await api.uploadSource(res.session_id, sourceFile);
        startPolling(res.session_id);
      } catch {
        setFileError("Upload failed — starting without source grounding.");
        navigateToSession(res.session_id);
      }
    } else {
      navigateToSession(res.session_id);
    }
  }

  function startAnyway() {
    if (pendingSessionId) {
      navigateToSession(pendingSessionId);
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-sans font-medium text-2xl text-ink mb-5">What do you want to argue about?</h1>
      <div className="flex items-center justify-between bg-white border border-fog/30 rounded-lg px-4 py-3 mb-6">
        <span className="font-serif text-base text-ink">{topic}</span>
        <button onClick={() => { setTopic(""); setActiveChip(""); }} className="text-fog text-lg">✕</button>
      </div>

      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Add context — what's the angle, what should the opponent know?"
        className="w-full bg-white border border-fog/30 rounded-lg px-4 py-3 mb-6 font-sans text-sm text-ink resize-none"
        rows={2}
      />

      {groups.map((g) => (
        <div key={g.label} className="flex gap-4 mb-3">
          <span className="w-24 flex-none font-sans text-[11px] font-semibold text-fog uppercase tracking-wide pt-1.5">{g.label}</span>
          <div className="flex flex-wrap gap-2">
            {g.chips.map((c) => (
              <button key={c} onClick={() => { setTopic(c); setActiveChip(c); }}
                className={`font-sans text-xs px-3 py-1 rounded-full border transition-all ${
                  activeChip === c ? "bg-scarlet text-white border-scarlet" : "bg-white text-ink border-fog/40"
                }`}>
                {c}
              </button>
            ))}
          </div>
        </div>
      ))}

      <button onClick={() => { const r = SURPRISES[Math.floor(Math.random() * SURPRISES.length)]; setTopic(r); setActiveChip(""); }}
        className="ml-28 font-sans text-xs text-fog border border-dashed border-fog/40 rounded-full px-3 py-1 mb-7">
        🎲 Surprise me
      </button>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">SOURCE MATERIAL (OPTIONAL)</p>
      <div className="flex items-center gap-3 mb-2">
        <label className="font-sans text-xs px-3 py-1.5 rounded-full border border-fog/40 bg-white text-ink cursor-pointer">
          Upload PDF
          <input type="file" accept="application/pdf" onChange={onFileChange} className="hidden" />
        </label>
        {sourceFile && (
          <span className="font-sans text-xs text-ink flex items-center gap-2">
            {sourceFile.name}
            <button onClick={() => setSourceFile(null)} className="text-fog">✕</button>
          </span>
        )}
      </div>
      {fileError && <p className="font-sans text-xs text-scarlet mb-5">{fileError}</p>}

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">DIFFICULTY</p>
      <div className="flex gap-3 mb-7">
        {DIFFICULTIES.map((d) => (
          <div key={d.key} onClick={() => setDifficulty(d.key)}
            className={`flex-1 rounded-lg p-3 cursor-pointer border transition-all ${
              difficulty === d.key ? "border-scarlet bg-scarlet/5" : "border-fog/30 bg-white"
            }`}>
            <p className={`font-sans text-sm font-medium ${difficulty === d.key ? "text-scarlet" : "text-ink"}`}>{d.name}</p>
            <p className="font-sans text-[11px] text-fog mt-1">{d.desc}</p>
          </div>
        ))}
      </div>

      <div className="h-px bg-fog/20 my-7" />
      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-3">YOUR POSITION</p>
      <div className="flex mb-8">
        {POSITIONS.map((p, i) => (
          <button key={p} onClick={() => setPosition(p.toLowerCase().replace(" ", "_"))}
            className={`font-sans text-sm font-medium px-4 py-2 border border-fog/30 -ml-px transition-all
              ${i === 0 ? "rounded-l-lg" : ""} ${i === POSITIONS.length - 1 ? "rounded-r-lg" : ""}
              ${position === p.toLowerCase().replace(" ", "_") ? "bg-scarlet border-scarlet text-white z-10 relative" : "bg-white text-ink"}`}>
            {p}
          </button>
        ))}
      </div>

      <button onClick={start} disabled={indexing || submitting || !topic}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60 mb-3">
        {indexing ? "Indexing your document…" : "Start session →"}
      </button>

      {indexing && (
        <button onClick={startAnyway}
          className="w-full border border-fog/40 text-fog font-sans text-sm py-3 rounded-lg">
          Start debate anyway →
        </button>
      )}
    </div>
  );
}
