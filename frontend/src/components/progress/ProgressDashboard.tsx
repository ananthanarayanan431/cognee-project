"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { ProgressData } from "@/types";

const STYLE_LABELS: { key: keyof ProgressData["thinking_style"]; label: string }[] = [
  { key: "logic", label: "Logic" },
  { key: "evidence", label: "Evidence" },
  { key: "rhetoric", label: "Rhetoric" },
];

export default function ProgressDashboard() {
  const setScreen = useDebate((s) => s.setScreen);
  const [progress, setProgress] = useState<ProgressData | null>(null);

  useEffect(() => {
    api.getProgress().then(setProgress).catch(() => setProgress(null));
  }, []);

  const stats = [
    {
      label: "Sessions",
      value: progress ? String(progress.sessions) : "—",
      sub: progress ? "total" : "Start debating to track",
    },
    {
      label: "Win rate",
      value: progress ? `${Math.round(progress.win_rate * 100)}%` : "—",
      sub: progress ? "of decided rounds" : "Calculated after sessions",
    },
    { label: "Mastered", value: "0", sub: "patterns" },
  ];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-display text-3xl text-ink">Your progress</h1>
        <button onClick={() => setScreen("topic")} className="font-sans text-sm text-fog">← Back</button>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-9">
        {stats.map(({ label, value, sub }) => (
          <div key={label} className="bg-white border border-fog/20 rounded-lg p-5">
            <div className="font-sans text-[11px] text-fog">{label}</div>
            <div className="font-display text-4xl text-ink my-1">{value}</div>
            <div className="font-sans text-[11px] text-fog">{sub}</div>
          </div>
        ))}
      </div>

      {progress && (
        <div className="mb-9">
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">
            Thinking style
          </p>
          {STYLE_LABELS.map(({ key, label }) => {
            const score = progress.thinking_style[key];
            return (
              <div key={key} className="mb-3">
                <div className="flex justify-between font-sans text-sm text-ink mb-1">
                  <span>{label}</span>
                  <span className="font-mono text-[11px] text-fog">{score.toFixed(1)}/10</span>
                </div>
                <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-scarlet rounded-full"
                    style={{ width: `${Math.min(100, (score / 10) * 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <p className="font-sans text-sm text-fog text-center mt-12 italic">
        Complete a debate session to see your cognitive fingerprint evolve.
      </p>
    </div>
  );
}
