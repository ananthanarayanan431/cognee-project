"use client";
import { useDebate } from "@/store/debate";

export default function ProgressDashboard() {
  const setScreen = useDebate((s) => s.setScreen);
  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <div className="flex items-baseline justify-between mb-6">
        <h1 className="font-display text-3xl text-ink">Your progress</h1>
        <button onClick={() => setScreen("topic")} className="font-sans text-sm text-fog">← Back</button>
      </div>
      <div className="grid grid-cols-3 gap-4 mb-9">
        {[
          { label: "Sessions", value: "—", sub: "Start debating to track" },
          { label: "Win rate", value: "—", sub: "Calculated after sessions" },
          { label: "Mastered", value: "0", sub: "patterns" },
        ].map(({ label, value, sub }) => (
          <div key={label} className="bg-white border border-fog/20 rounded-lg p-5">
            <div className="font-sans text-[11px] text-fog">{label}</div>
            <div className="font-display text-4xl text-ink my-1">{value}</div>
            <div className="font-sans text-[11px] text-fog">{sub}</div>
          </div>
        ))}
      </div>
      <p className="font-sans text-sm text-fog text-center mt-12 italic">
        Complete a debate session to see your cognitive fingerprint evolve.
      </p>
    </div>
  );
}
