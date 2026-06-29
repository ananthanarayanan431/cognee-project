"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useDebate } from "@/store/debate";

export default function AuthModal() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const setAuth = useDebate((s) => s.setAuth);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setAuth(res.access_token, res.user_id);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="min-h-screen bg-chalk flex flex-col items-center justify-center px-4">
      <h1 className="font-display text-5xl text-ink mb-2">DebateMind</h1>
      <p className="font-sans text-fog text-base mb-10 italic">The AI that learns how you argue.</p>
      <form onSubmit={submit} className="w-full max-w-sm flex flex-col gap-4">
        <input
          type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)}
          className="border border-fog/40 rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
        />
        <input
          type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)}
          className="border border-fog/40 rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
        />
        {error && <p className="text-scarlet text-xs font-sans">{error}</p>}
        <button type="submit" className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-3 rounded">
          {mode === "login" ? "Sign in →" : "Create account →"}
        </button>
        <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="text-fog font-sans text-xs underline">
          {mode === "login" ? "New here? Create account" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
