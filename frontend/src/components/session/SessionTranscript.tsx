"use client";
import { useDebate } from "@/store/debate";

export default function SessionTranscript() {
  const { messages, setScreen } = useDebate();

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <h1 className="font-display text-3xl text-ink mb-1">Session Transcript</h1>
      <p className="font-sans text-base text-fog mb-7">Review your debate session</p>

      <div className="space-y-4 mb-7">
        {messages.map((msg) => (
          <div key={msg.id} className="bg-white border border-fog/20 rounded-lg p-4">
            <div className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-2">
              {msg.role}
            </div>
            <div className="font-serif text-base text-ink">{msg.text}</div>
          </div>
        ))}
      </div>

      <button
        onClick={() => setScreen("topic")}
        className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-sm rounded-lg px-6 py-3"
      >
        Back to topics
      </button>
    </div>
  );
}
