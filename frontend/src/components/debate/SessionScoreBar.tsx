"use client";

const ROWS = [
  { key: "logic", label: "Logic", color: "#0D9488" },
  { key: "evidence", label: "Evidence", color: "#F59E0B" },
  { key: "rhetoric", label: "Rhetoric", color: "#10B981" },
] as const;

export default function SessionScoreBar({
  scores,
}: {
  scores: { logic: number; evidence: number; rhetoric: number } | null;
}) {
  if (!scores) return null;
  return (
    <div className="px-5 pb-4">
      <p className="font-sans text-[9px] font-semibold text-fog uppercase tracking-widest mb-2.5">
        Session score
      </p>
      {ROWS.map(({ key, label, color }) => {
        const value = scores[key];
        return (
          <div key={key} className="flex items-center gap-2.5 mb-1.5">
            <span className="font-sans text-[9px] text-fog w-11 flex-none">{label}</span>
            <div className="flex-1 h-1.5 rounded-[3px] bg-fog/15 overflow-hidden">
              <div
                className="h-full rounded-[3px] transition-[width] duration-500 ease-out"
                style={{ width: `${Math.max(0, Math.min(100, (value / 10) * 100))}%`, background: color }}
              />
            </div>
            <span className="font-mono text-[9px] text-fog w-7 flex-none text-right">
              {value.toFixed(1)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
