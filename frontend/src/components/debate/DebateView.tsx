"use client";
import { useEffect, useRef } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import MessageBubble from "./MessageBubble";
import InputArea from "./InputArea";
import FingerprintGraph from "@/components/graph/FingerprintGraph";
import { useGraphWS } from "@/hooks/useGraphWS";

export default function DebateView() {
  const { messages, thinking, graph, sessionId, sessionConfig, setScreen } = useDebate();
  const scrollRef = useRef<HTMLDivElement>(null);
  useGraphWS(sessionId);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  async function endSession() {
    if (sessionId) await api.endSession(sessionId);
    setScreen("end");
  }

  const lastMsg = messages[messages.length - 1];

  return (
    <div className="flex h-screen flex-col">
      {/* Nav */}
      <nav className="flex items-center justify-between h-14 px-5 bg-white border-b border-fog/20 sticky top-0 z-20">
        <button
          onClick={() => setScreen("topic")}
          className="font-display text-[22px] text-ink cursor-pointer leading-none"
        >
          DebateMind
        </button>
        <span className="font-sans text-[11px] font-medium text-fog tracking-wide hidden sm:block">
          {sessionConfig?.topic?.slice(0, 30)}{" "}
          {sessionConfig && (
            <>
              · <span className="text-scarlet capitalize">{sessionConfig.difficulty}</span>
            </>
          )}
        </span>
        <button
          onClick={endSession}
          className="font-sans text-xs font-semibold uppercase tracking-wide text-fog hover:text-ink transition-colors"
        >
          End session
        </button>
      </nav>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Chat panel */}
        <div className="flex flex-col flex-1 min-w-0 bg-chalk">
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-7 py-6 flex flex-col gap-3.5"
          >
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                msg={m}
                thinking={thinking && m.role === "opponent" && m === lastMsg}
              />
            ))}
            {/* Thinking indicator when no opponent message yet */}
            {thinking && lastMsg?.role !== "opponent" && (
              <div className="flex flex-col items-start">
                <div className="flex items-center gap-1.5 mb-1.5">
                  <span className="w-5 h-5 rounded-full bg-scarlet flex items-center justify-center font-sans text-[9px] font-bold text-white animate-pulse">
                    O
                  </span>
                  <span className="font-sans text-[10px] font-semibold text-scarlet tracking-widest">
                    OPPONENT
                  </span>
                </div>
                <span className="font-serif italic text-sm text-fog">
                  Studying your argument…
                </span>
              </div>
            )}
          </div>
          <InputArea />
        </div>

        {/* Graph panel — hidden on mobile, shown on large screens */}
        <aside className="w-80 min-w-[280px] max-w-[360px] bg-carbon border-l border-white/10 flex-col text-white overflow-y-auto hidden lg:flex">
          <div className="px-5 pt-4 pb-2 flex items-center justify-between">
            <span className="font-sans text-[11px] font-semibold uppercase tracking-widest">
              Cognitive Fingerprint
            </span>
          </div>
          <FingerprintGraph data={graph} />
          <div className="flex gap-3.5 px-5 pb-4 font-sans text-[10px] text-[#888]">
            {[
              { color: "#C0392B", label: "Weakness" },
              { color: "#27AE60", label: "Strength" },
              { color: "#444", label: "Mastered" },
            ].map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
