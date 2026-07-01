"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

const DURATION = 90;

export default function CalibrationSession() {
  const setScreen = useDebate((s) => s.setScreen);
  const [topic, setTopic] = useState("");
  const [index, setIndex] = useState(1);
  const [total, setTotal] = useState(3);
  const [text, setText] = useState("");
  const [seconds, setSeconds] = useState(DURATION);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCalibrationStatus().then((s) => {
      if (!s.needed) {
        setScreen("topic");
        return;
      }
      setTopic(s.topic ?? "");
      setIndex(s.index);
      setTotal(s.total);
      setLoading(false);
    });
  }, [setScreen]);

  useEffect(() => {
    if (loading) return;
    setSeconds(DURATION);
    const id = setInterval(() => setSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(id);
  }, [topic, loading]);

  async function submit() {
    if (!text.trim()) return;
    const res = await api.submitCalibrationAnswer(text);
    setText("");
    if (res.done) {
      setScreen("topic");
      return;
    }
    setTopic(res.next_topic ?? "");
    setIndex(res.index);
    setTotal(res.total);
  }

  if (loading) return null;

  const mins = String(Math.floor(seconds / 60)).padStart(1, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  const dots = Array.from({ length: total }, (_, i) => i < index);

  return (
    <div className="max-w-2xl mx-auto px-7 py-12">
      <div className="flex items-center justify-between mb-5">
        <h1 className="font-display text-3xl text-ink">Let&apos;s see how you think.</h1>
        <div className="flex items-center gap-3">
          <span className="flex gap-1">
            {dots.map((filled, i) => (
              <span
                key={i}
                className={`w-1.5 h-1.5 rounded-full ${filled ? "bg-scarlet" : "bg-fog/30"}`}
              />
            ))}
          </span>
          <span className="font-sans text-[11px] text-fog">Calibration {index}/{total}</span>
        </div>
      </div>

      <p className="font-sans text-[11px] font-semibold text-fog uppercase tracking-wide mb-1">
        Getting to know your thinking…
      </p>
      <p className="font-serif text-lg text-slate mb-6">{topic}</p>

      <div className="bg-white border border-border rounded-lg px-4 py-3 mb-6 flex items-center justify-between">
        <p className="font-serif text-base text-ink">What&apos;s your opening position on this topic?</p>
        <span className="font-mono text-xs text-fog flex-none ml-4">{mins}:{secs}</span>
      </div>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Make your argument…"
        rows={4}
        className="w-full bg-white border border-border rounded-lg px-4 py-3 mb-4 font-serif text-sm text-ink resize-none outline-none focus:border-scarlet placeholder:italic placeholder:text-fog"
      />

      <div className="h-1.5 bg-fog/20 rounded-full overflow-hidden mb-6">
        <div
          className="h-full bg-scarlet rounded-full transition-[width] duration-500 ease-out"
          style={{ width: `${((index - 1) / total) * 100}%` }}
        />
      </div>

      <button
        onClick={submit}
        disabled={!text.trim()}
        className="w-full bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-4 rounded-lg disabled:opacity-60"
      >
        Continue →
      </button>
    </div>
  );
}
