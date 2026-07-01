"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { SessionSummary } from "@/types";
import WeaknessBar from "@/components/shared/WeaknessBar";

export default function SessionEnd() {
  const { sessionId, sessionConfig, setScreen } = useDebate();
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);

  useEffect(() => {
    if (sessionId) {
      api.getSessionSummary(sessionId)
        .then((s) => { setSummary(s); setLoading(false); })
        .catch(() => { setFetchError(true); setLoading(false); });
    }
  }, [sessionId]);

  if (loading) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Loading summary…</div>;
  }
  if (fetchError || !summary) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Failed to load summary.</div>;
  }

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <button onClick={() => setScreen("topic")} className="font-sans text-xs font-medium text-ink border border-border rounded-lg px-3 py-1.5 mb-6 hover:bg-fog/10 transition-colors inline-flex items-center gap-1.5">← Back</button>
      <h1 className="font-display text-3xl text-ink mb-1">Session complete</h1>
      <p className="font-sans text-base text-fog mb-7">{summary.topic} · {summary.difficulty}</p>

      <div className="grid grid-cols-4 gap-3 mb-9">
        {[
          { v: summary.score.toFixed(1), unit: "/10", label: "Score", color: "text-scarlet" },
          { v: summary.exchanges, unit: "", label: "Exchanges", color: "text-ink" },
          { v: summary.weaknesses_exposed, unit: "", label: "Weaknesses exposed", color: "text-ink" },
          { v: summary.rounds_won, unit: "", label: "Rounds won", color: "text-verdant" },
        ].map(({ v, unit, label, color }) => (
          <div key={label} className="bg-white border border-border rounded-lg p-4">
            <div className={`font-display text-3xl ${color}`}>{v}<span className="text-sm text-fog font-sans">{unit}</span></div>
            <div className="font-sans text-[11px] text-fog mt-1">{label}</div>
          </div>
        ))}
      </div>

      {summary.patterns.length > 0 && (
        <>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">
            Fingerprint changes
          </p>
          {summary.patterns.map((p) => (
            <WeaknessBar key={p.pattern} change={p} />
          ))}
        </>
      )}

      <div className="h-px bg-border my-7" />
      <div className="flex gap-3 items-center">
        <button onClick={() => setScreen("debate")}
          className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Debate again →
        </button>
        <button onClick={() => setScreen("topic")}
          className="bg-slate text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Choose new topic
        </button>
        <button onClick={() => setScreen("transcript")}
          className="font-sans text-xs font-medium text-ink border border-border rounded-lg px-3 py-1.5 hover:bg-fog/10 transition-colors inline-flex items-center gap-1.5">
          View full transcript
        </button>
      </div>

      {sessionConfig && null /* sessionConfig kept for the "Debate again" round-trip via store, not rendered here */}
    </div>
  );
}
