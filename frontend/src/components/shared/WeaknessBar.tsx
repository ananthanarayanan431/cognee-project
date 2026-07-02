import MasteredBadge from "./MasteredBadge";
import { WeaknessChange } from "@/types";

export default function WeaknessBar({ change }: { change: WeaknessChange }) {
  return (
    <div className="mb-5">
      <div className="flex items-center justify-between mb-2">
        <span className="font-sans text-sm text-ink">{change.pattern}</span>
        {change.mastered && <MasteredBadge />}
      </div>

      <div className="flex items-center gap-2 mb-1">
        <span className="font-sans text-[10px] text-fog w-12 flex-none">Before</span>
        <div className="flex-1 h-1.5 bg-[#E8EAED] rounded-[3px] overflow-hidden">
          <div
            className="h-full bg-fog rounded-[3px] transition-[width] duration-500 ease-out"
            style={{ width: `${change.before * 100}%` }}
          />
        </div>
        <span className="font-mono text-[10px] text-fog w-8 flex-none text-right">
          {change.before.toFixed(2)}
        </span>
      </div>

      {change.mastered ? (
        <p className="font-sans text-[11px] text-fog italic ml-14">
          pruned from opponent strategy
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <span className="font-sans text-[10px] font-semibold text-scarlet w-12 flex-none">After</span>
          <div className="flex-1 h-1.5 bg-[#E8EAED] rounded-[3px] overflow-hidden">
            <div
              className="h-full bg-scarlet rounded-[3px] transition-[width] duration-500 ease-out"
              style={{ width: `${change.after * 100}%` }}
            />
          </div>
          <span className="font-mono text-[10px] text-fog w-8 flex-none text-right">
            {change.after.toFixed(2)}
          </span>
        </div>
      )}
    </div>
  );
}
