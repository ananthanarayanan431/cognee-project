"use client";
import { useDebate } from "@/store/debate";

export default function LandingPage() {
  const setScreen = useDebate((s) => s.setScreen);

  return (
    <div className="min-h-screen bg-chalk flex flex-col items-center justify-center px-4">
      <h1 className="font-display text-5xl text-ink mb-2">DebateMind</h1>
      <p className="font-sans text-fog text-lg mb-10">The AI that learns how you argue.</p>
      <button
        onClick={() => setScreen("auth")}
        className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm px-6 py-4 rounded-lg"
      >
        Start arguing →
      </button>
    </div>
  );
}
