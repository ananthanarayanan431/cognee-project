"use client";
import { useEffect, useState } from "react";
import { useDebate } from "@/store/debate";
import { api, handleExpiredSession } from "@/lib/api";
import { Transcript, VoiceSessionSummary } from "@/types";

// Trigger a client-side file download from an in-memory blob. Shared by the text
// and voice export paths so the object-URL lifecycle stays in one place.
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function SessionTranscript() {
  const { sessionId, setScreen } = useDebate();
  const token = useDebate((s) => s.token);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [voice, setVoice] = useState<VoiceSessionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);

  useEffect(() => {
    if (!sessionId) return;
    let live = true;
    // A voice session has no text `Exchange` rows — its dialogue lives in the
    // voice summary. Fetch both; render whichever holds the conversation. The
    // summary endpoint returns has_voice_session=false (not an error) for
    // text-only sessions, so any thrown error here is a real backend/network
    // failure and should surface rather than be swallowed to null.
    Promise.all([api.getTranscript(sessionId), api.getVoiceSummary(sessionId)])
      .then(([t, v]) => {
        if (!live) return;
        setTranscript(t);
        setVoice(v);
        setFetchError(false);
        setLoading(false);
      })
      .catch(() => {
        if (!live) return;
        setFetchError(true);
        setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [sessionId]);

  async function exportTranscript() {
    if (!sessionId) return;
    setExportError(null);
    const res = await fetch(api.transcriptExportUrl(sessionId), {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 401) {
      handleExpiredSession();
      return;
    }
    if (!res.ok) {
      setExportError("Export failed. Please try again.");
      return;
    }
    const blob = await res.blob();
    downloadBlob(blob, `transcript_${sessionId}.txt`);
  }

  // Voice transcripts aren't in the DB export (which reads text exchanges), so
  // build the download client-side from the fetched voice summary.
  function exportVoiceTranscript() {
    if (!transcript || !voice) return;
    const lines = [
      transcript.topic,
      `${transcript.difficulty} · ${new Date(transcript.started_at).toLocaleString()} · voice session`,
      "",
      ...voice.transcript.map(
        (l) => `${l.speaker === "user" ? "YOU" : "OPPONENT"}: ${l.text}`,
      ),
    ];
    if (voice.closing_summary) {
      lines.push("", "CLOSING SUMMARY", voice.closing_summary);
    }
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    downloadBlob(blob, `transcript_${sessionId}.txt`);
  }

  if (loading) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Loading transcript…</div>;
  }
  if (fetchError || !transcript) {
    return <div className="max-w-3xl mx-auto px-7 py-12 font-sans text-fog">Failed to load transcript.</div>;
  }

  const hasText = transcript.exchanges.length > 0;
  const hasVoice = !!voice && voice.has_voice_session && voice.transcript.length > 0;

  return (
    <div className="max-w-3xl mx-auto px-7 py-12">
      <button onClick={() => setScreen("end")} className="font-sans text-xs font-medium text-ink border border-border rounded-lg px-3 py-1.5 mb-5 hover:bg-fog/10 transition-colors inline-flex items-center gap-1.5">← Back</button>
      <h1 className="font-sans font-bold text-2xl text-ink mb-1">{transcript.topic}</h1>
      <p className="font-sans text-sm text-fog mb-7">
        {transcript.difficulty} · {new Date(transcript.started_at).toLocaleDateString()}
        {hasText && ` · ${transcript.exchanges.length} exchanges`}
        {!hasText && hasVoice && ` · voice · ${voice!.transcript.length} lines`}
      </p>

      {/* ── Text debate: paginated exchange navigator ─────────────────────── */}
      {hasText && <TextExchangeView transcript={transcript} cursor={cursor} setCursor={setCursor} onExport={exportTranscript} exportError={exportError} />}

      {/* ── Voice debate: full spoken transcript ──────────────────────────── */}
      {!hasText && hasVoice && <VoiceTranscriptView voice={voice!} onExport={exportVoiceTranscript} />}

      {/* ── Nothing recorded ──────────────────────────────────────────────── */}
      {!hasText && !hasVoice && (
        <p className="font-sans text-[15px] text-fog">No transcript was recorded for this session.</p>
      )}
    </div>
  );
}

function TextExchangeView({
  transcript,
  cursor,
  setCursor,
  onExport,
  exportError,
}: {
  transcript: Transcript;
  cursor: number;
  setCursor: React.Dispatch<React.SetStateAction<number>>;
  onExport: () => void;
  exportError: string | null;
}) {
  const ex = transcript.exchanges[cursor];
  return (
    <>
      {ex && (
        <div key={ex.turn_number}>
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-1">
            YOU — {new Date(ex.created_at).toLocaleTimeString()}
          </p>
          <p className="font-sans text-[15px] text-ink mb-5">{ex.user_message}</p>

          <p className="font-sans text-[11px] font-semibold text-scarlet uppercase tracking-wide mb-1">
            OPPONENT — {new Date(ex.created_at).toLocaleTimeString()}
            {ex.fallacy && <span className="text-fog normal-case font-normal"> · {ex.fallacy} detected</span>}
          </p>
          <p className="font-sans text-[15px] text-ink mb-5">{ex.opponent_response}</p>

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
        <div className="flex flex-col items-center gap-1">
          <button onClick={onExport} className="font-sans text-sm text-fog">
            Export transcript ↓
          </button>
          {exportError && <span className="font-sans text-[11px] text-scarlet">{exportError}</span>}
        </div>
        <button
          onClick={() => setCursor((c) => Math.min(transcript.exchanges.length - 1, c + 1))}
          disabled={cursor >= transcript.exchanges.length - 1}
          className="font-sans text-sm text-fog disabled:opacity-30"
        >
          Next exchange →
        </button>
      </div>
    </>
  );
}

function VoiceTranscriptView({
  voice,
  onExport,
}: {
  voice: VoiceSessionSummary;
  onExport: () => void;
}) {
  return (
    <>
      <div className="flex flex-col gap-5">
        {voice.transcript.map((line, i) => (
          <div key={i}>
            <p
              className={`font-sans text-[11px] font-semibold uppercase tracking-wide mb-1 ${
                line.speaker === "user" ? "text-fog" : "text-scarlet"
              }`}
            >
              {line.speaker === "user" ? "YOU" : "OPPONENT"}
            </p>
            <p className="font-sans text-[15px] text-ink">{line.text}</p>
          </div>
        ))}
      </div>

      {voice.closing_summary && (
        <>
          <div className="h-px bg-border my-7" />
          <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-2">
            Closing summary
          </p>
          <p className="font-sans text-[15px] text-ink leading-relaxed">{voice.closing_summary}</p>
        </>
      )}

      <div className="h-px bg-border my-7" />
      <div className="flex flex-col items-center gap-1">
        <button onClick={onExport} className="font-sans text-sm text-fog">
          Export transcript ↓
        </button>
      </div>
    </>
  );
}
