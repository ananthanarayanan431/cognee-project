"use client";
import { JudgeScore } from "@/types";

export default function JudgeScoreBar({ score }: { score: JudgeScore }) {
  return (
    <div className="flex items-center gap-3 bg-carbon rounded-md px-3 py-2 mt-2 flex-wrap">
      <span className="font-sans text-[9px] font-semibold text-fog uppercase tracking-widest">JUDGE</span>
      <span className="font-mono text-[10px] text-fog">
        Logic <span className="text-white font-medium">{score.logic}</span>
      </span>
      <span className="font-mono text-[10px] text-fog">
        Evidence <span className="text-white font-medium">{score.evidence}</span>
      </span>
      <span className="font-mono text-[10px] text-fog">
        Rhetoric <span className="text-white font-medium">{score.rhetoric}</span>
      </span>
      {score.fallacy && (
        <span className="font-mono text-[9px] font-medium text-red-300 bg-scarlet/30 rounded-full px-2 py-0.5">
          ⚠ {score.fallacy}
        </span>
      )}
    </div>
  );
}
