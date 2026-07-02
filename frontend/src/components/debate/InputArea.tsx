"use client";
import { useState, useRef, useEffect } from "react";
import { IconSend } from "@tabler/icons-react";
import { useDebate } from "@/store/debate";
import { useSendMessage } from "@/hooks/useDebateSSE";

const POSITION_LABEL: Record<string, string> = {
  for: "Arguing FOR",
  against: "Arguing AGAINST",
  neutral: "Neutral",
  assign_randomly: "Random",
};

export default function InputArea() {
  const [text, setText] = useState("");
  const thinking = useDebate((s) => s.thinking);
  const position = useDebate((s) => s.sessionConfig?.position ?? "");
  const send = useSendMessage();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.height = taRef.current.scrollHeight + "px";
    }
  }, [text]);

  const submit = () => {
    if (!thinking && text.trim()) {
      send(text);
      setText("");
    }
  };

  const hints = [
    { label: "Continue argument", prefix: "To extend that point — " },
    { label: "New point", prefix: "A separate consideration: " },
    { label: "Concede & pivot", prefix: "I'll concede that, but pivot — " },
  ];

  return (
    <div className="border-t border-border bg-white p-3">
      {position && (
        <div className="flex items-center gap-1.5 mb-2">
          <span className="font-sans text-[10px] font-semibold uppercase tracking-widest text-fog">Your position</span>
          <span className="font-sans text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full bg-scarlet/10 text-scarlet border border-scarlet/20">
            {POSITION_LABEL[position] ?? position}
          </span>
          <span className="font-sans text-[10px] text-fog/60">· locked for this session</span>
        </div>
      )}
      <div className="flex gap-2 mb-2.5 flex-wrap">
        {hints.map(({ label, prefix }) => (
          <button
            key={label}
            onClick={() => setText(prefix)}
            className="font-sans text-[11px] text-fog border border-border rounded-full px-3 py-1 hover:border-fog/60 transition-colors"
          >
            {label}
          </button>
        ))}
      </div>
      <div className="flex gap-2.5 items-end">
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Make your argument…"
          rows={1}
          className="flex-1 resize-none font-sans text-sm text-ink bg-white border border-border rounded-lg px-3 py-2.5 min-h-14 leading-relaxed outline-none focus:border-scarlet placeholder:text-fog"
        />
        <button
          onClick={submit}
          disabled={thinking}
          className="h-14 flex items-center gap-1.5 bg-scarlet text-white font-sans font-semibold uppercase tracking-wide text-xs border-none rounded-lg px-4 disabled:opacity-40 hover:bg-scarlet/90 transition-colors"
        >
          <IconSend size={18} stroke={2} />
          Send
        </button>
      </div>
    </div>
  );
}
