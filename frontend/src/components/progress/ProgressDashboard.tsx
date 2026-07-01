"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { ProgressData } from "@/types";
import MasteredBadge from "@/components/shared/MasteredBadge";

const STYLE_LABELS: { key: keyof ProgressData["thinking_style"]; label: string }[] = [
  { key: "logic", label: "Logic" },
  { key: "evidence", label: "Evidence" },
  { key: "rhetoric", label: "Rhetoric" },
];

export default function ProgressDashboard() {
  const setScreen = useDebate((s) => s.setScreen);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [reactivateError, setReactivateError] = useState<string | null>(null);

  function reload() {
    api.getProgress().then(setProgress).catch(() => setProgress(null));
  }

  useEffect(reload, []);

  async function reactivate(pattern: string) {
    setReactivateError(null);
    try {
      await api.reactivateMastery(pattern);
      reload();
    } catch {
      setReactivateError(`Failed to reactivate ${pattern}. Please try again.`);
    }
  }

  const stats = [
    { label: "Sessions", value: progress ? String(progress.sessions) : "—", sub: progress ? `${progress.streak}-day streak` : "Start debating to track" },
    { label: "Win rate", value: progress ? `${Math.round(progress.win_rate * 100)}%` : "—", sub: progress ? "of decided rounds" : "Calculated after sessions" },
    { label: "Mastered", value: progress ? String(progress.mastered.filter((m) => !m.reactivated).length) : "0", sub: "patterns" },
  ];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-display text-3xl text-ink">Your progress</h1>
        <button onClick={() => setScreen("topic")} className="font-sans text-sm text-fog">← Back</button>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-9">
        {stats.map(({ label, value, sub }) => (
          <div key={label} className="bg-white border border-border rounded-lg p-5">
            <div className="font-sans text-[11px] text-fog">{label}</div>
            <div className="font-display text-4xl text-ink my-1">{value}</div>
            <div className="font-sans text-[11px] text-fog">{sub}</div>
          </div>
        ))}
      </div>

      {progress && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Thinking style</p>
          {STYLE_LABELS.map(({ key, label }) => {
            const score = progress.thinking_style[key];
            return (
              <div key={key} className="mb-3">
                <div className="flex justify-between font-sans text-sm text-ink mb-1">
                  <span>{label}</span>
                  <span className="font-mono text-[11px] text-fog">{score.toFixed(1)}/10</span>
                </div>
                <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                  <div className="h-full bg-scarlet rounded-full" style={{ width: `${Math.min(100, (score / 10) * 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {progress && progress.weakness_trend.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Weakness trend</p>
          {progress.weakness_trend.map((w) => (
            <div key={w.pattern} className="mb-3">
              <div className="flex justify-between font-sans text-sm text-ink mb-1">
                <span>{w.pattern}</span>
                <span className="font-mono text-[11px] text-fog">{w.weight.toFixed(2)}</span>
              </div>
              <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                <div className="h-full bg-scarlet rounded-full" style={{ width: `${w.weight * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {progress && progress.mastered.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Mastered patterns</p>
          {progress.mastered.map((m) => (
            <div key={`${m.pattern}-${m.mastered_at}`} className="flex items-center justify-between mb-2.5">
              <div className="flex items-center gap-2.5">
                {m.reactivated ? (
                  <span className="font-sans text-sm text-ink">{m.pattern}</span>
                ) : (
                  <>
                    <span className="font-sans text-sm text-ink">{m.pattern}</span>
                    <MasteredBadge />
                  </>
                )}
                <span className="font-sans text-[11px] text-fog">
                  {new Date(m.mastered_at).toLocaleDateString()} · {m.rounds_to_mastery} rounds to master
                </span>
              </div>
              {!m.reactivated && (
                <button onClick={() => reactivate(m.pattern)} className="font-sans text-[11px] text-fog">
                  Reactivate →
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {progress && progress.win_rate_by_topic.length > 0 && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">Win rate by topic</p>
          {progress.win_rate_by_topic.map((t) => (
            <div key={t.topic} className="mb-3">
              <div className="flex justify-between font-sans text-sm text-ink mb-1">
                <span>{t.topic}</span>
                <span className="font-mono text-[11px] text-fog">{Math.round(t.win_rate * 100)}%</span>
              </div>
              <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${t.win_rate >= 0.5 ? "bg-verdant" : "bg-scarlet"}`}
                  style={{ width: `${t.win_rate * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {reactivateError && (
        <p className="font-sans text-sm text-scarlet mb-4">{reactivateError}</p>
      )}

      {!progress && (
        <p className="font-sans text-sm text-fog text-center mt-12 italic">
          Complete a debate session to see your cognitive fingerprint evolve.
        </p>
      )}
    </div>
  );
}
