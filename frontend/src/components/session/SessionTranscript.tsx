"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api } from "@/lib/api";
import { Transcript } from "@/types";

export default function SessionTranscript() {
  const { sessionId, setScreen } = useDebate();
  const token = useDebate((s) => s.token);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (sessionId) api.getTranscript(sessionId).then(setTranscript).catch(() => setTranscript(null));
  }, [sessionId]);

  async function exportTranscript() {
    if (!sessionId) return;
    const res = await fetch(api.transcriptExportUrl(sessionId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript_${sessionId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!transcript) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Loading transcript…</div>;
  }

  const ex = transcript.exchanges[cursor];

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <button onClick={() => setScreen("end")} className="font-sans text-sm text-fog mb-5">← Back</button>
      <h1 className="font-display text-2xl text-ink mb-1">{transcript.topic}</h1>
      <p className="font-sans text-sm text-fog mb-7">
        {transcript.difficulty} · {new Date(transcript.started_at).toLocaleDateString()} · {transcript.exchanges.length} exchanges
      </p>

      {ex && (
        <div key={ex.turn_number}>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-1">
            YOU — {new Date(ex.created_at).toLocaleTimeString()}
          </p>
          <p className="font-serif text-[15px] text-slate mb-5">{ex.user_message}</p>

          <p className="font-sans text-[11px] font-semibold text-scarlet uppercase tracking-wide mb-1">
            OPPONENT — {new Date(ex.created_at).toLocaleTimeString()}
            {ex.fallacy && <span className="text-fog normal-case font-normal"> · {ex.fallacy} detected</span>}
          </p>
          <p className="font-serif text-[15px] text-ink mb-5">{ex.opponent_response}</p>

          {ex.judge_logic !== null && (
            <p className="font-mono text-[11px] text-fog mb-7">
              JUDGE  Logic {ex.judge_logic} · Evidence {ex.judge_evidence} · Rhetoric {ex.judge_rhetoric}
              {ex.fallacy && <span> · ⚠ {ex.fallacy}</span>}
            </p>
          )}
        </div>
      )}

      <div className="h-px bg-border my-7" />
      <div className="flex items-center justify-between">
        <button
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
          disabled={cursor === 0}
          className="font-sans text-sm text-fog disabled:opacity-30"
        >
          ← Previous exchange
        </button>
        <button onClick={exportTranscript} className="font-sans text-sm text-fog">
          Export transcript ↓
        </button>
        <button
          onClick={() => setCursor((c) => Math.min(transcript.exchanges.length - 1, c + 1))}
          disabled={cursor >= transcript.exchanges.length - 1}
          className="font-sans text-sm text-fog disabled:opacity-30"
        >
          Next exchange →
        </button>
      </div>
    </div>
  );
}
