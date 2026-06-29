"use client";
import { useDebate } from "@/store/debate";

export default function SessionEnd() {
  const { messages, sessionConfig, setScreen } = useDebate();
  const exchanges = messages.filter((m) => m.role === "opponent").length;
  const judged = messages.filter((m) => m.judge);
  const avgLogic = judged.length ? judged.reduce((a, m) => a + (m.judge?.logic ?? 0), 0) / judged.length : 0;
  const won = judged.filter((m) => m.judge?.outcome === "Won").length;
  const fallacies = Array.from(new Set(judged.map((m) => m.judge?.fallacy).filter(Boolean)));

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-display text-3xl text-ink mb-1">Session complete</h1>
      <p className="font-sans text-base text-fog mb-7">{sessionConfig?.topic} · {sessionConfig?.difficulty}</p>

      <div className="grid grid-cols-4 gap-3 mb-9">
        {[
          { v: avgLogic.toFixed(1), unit: "/10", label: "Score", color: "text-scarlet" },
          { v: exchanges, unit: "", label: "Exchanges", color: "text-ink" },
          { v: fallacies.length, unit: "", label: "Weaknesses exposed", color: "text-ink" },
          { v: won, unit: "", label: "Rounds won", color: "text-verdant" },
        ].map(({ v, unit, label, color }) => (
          <div key={label} className="bg-white border border-fog/20 rounded-lg p-4">
            <div className={`font-display text-3xl ${color}`}>{v}<span className="text-sm text-fog font-sans">{unit}</span></div>
            <div className="font-sans text-[11px] text-fog mt-1">{label}</div>
          </div>
        ))}
      </div>

      {fallacies.length > 0 && (
        <>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-4">PATTERNS EXPOSED THIS SESSION</p>
          {fallacies.map((f) => (
            <div key={f} className="mb-5">
              <div className="flex justify-between font-sans text-sm text-ink mb-2">
                <span>{f}</span>
                <span className="font-mono text-[10px] text-scarlet">detected</span>
              </div>
            </div>
          ))}
        </>
      )}

      <div className="h-px bg-fog/20 my-7" />
      <div className="flex gap-3 items-center">
        <button onClick={() => setScreen("debate")}
          className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Debate again →
        </button>
        <button onClick={() => setScreen("topic")}
          className="bg-slate text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3">
          Choose new topic
        </button>
        <button onClick={() => setScreen("progress")}
          className="font-sans text-sm text-fog border-none bg-none">
          View progress
        </button>
      </div>
    </div>
  );
}
