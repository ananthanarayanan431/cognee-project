"use client";

export default function PulseAvatar({ thinking }: { thinking: boolean }) {
  return (
    <span
      className={`w-5 h-5 rounded-full bg-scarlet flex items-center justify-center font-sans text-[9px] font-bold text-white${thinking ? " animate-pulse" : ""}`}
    >
      O
    </span>
  );
}
