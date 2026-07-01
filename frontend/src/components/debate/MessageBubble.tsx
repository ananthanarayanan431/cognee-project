"use client";
import { Message } from "@/types";
import PulseAvatar from "./PulseAvatar";
import JudgeScoreBar from "./JudgeScore";
import MasteredBadge from "@/components/shared/MasteredBadge";

export default function MessageBubble({ msg, thinking }: { msg: Message; thinking?: boolean }) {
  if (msg.role === "user") {
    return (
      <div className="flex flex-col items-end">
        <div className="max-w-[80%] bg-slate/10 text-ink font-serif text-base leading-relaxed px-3.5 py-2.5 rounded-[12px_12px_2px_12px]">
          {msg.text}
        </div>
        <span className="font-sans text-[10px] font-semibold text-fog tracking-widest mt-1.5 mr-0.5">YOU</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start">
      <div className="flex items-center gap-1.5 mb-1.5">
        <PulseAvatar thinking={!!thinking && !msg.text} />
        <span className="font-sans text-[10px] font-semibold text-scarlet tracking-widest">OPPONENT</span>
      </div>
      <div className="max-w-[85%] bg-white text-ink border border-border font-serif text-base leading-relaxed px-3.5 py-2.5 rounded-[2px_12px_12px_12px]">
        {msg.text || <span className="italic text-fog text-sm">Studying your argument…</span>}
      </div>
      {msg.showJudge && msg.judge && <JudgeScoreBar score={msg.judge} />}
      {msg.mastery && msg.mastery.length > 0 && (
        <div className="flex gap-1.5 mt-2 flex-wrap">
          {msg.mastery.map((p) => (
            <MasteredBadge key={p} pattern={p} />
          ))}
        </div>
      )}
    </div>
  );
}
