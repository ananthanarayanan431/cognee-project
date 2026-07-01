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
  const setScreen = useDebate((s) => s.setScreen);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setAuth(res.access_token, res.user_id, res.calibration_done);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="fixed inset-0 bg-ink/60 flex items-center justify-center px-4 z-50">
      <div className="bg-white rounded-xl max-w-[400px] w-full p-7">
        <h2 className="font-sans font-medium text-lg text-ink mb-5">
          {mode === "login" ? "Sign in" : "Create your account"}
        </h2>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <input
            type="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)}
            className="border border-border rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
          />
          <input
            type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)}
            className="border border-border rounded px-4 py-3 font-sans text-sm bg-white text-ink outline-none focus:border-scarlet"
          />
          {error && <p className="text-scarlet text-xs font-sans">{error}</p>}
          <button type="submit" className="bg-scarlet text-white font-sans font-semibold uppercase tracking-wider text-sm py-3 rounded">
            {mode === "login" ? "Sign in →" : "Create account →"}
          </button>
          <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="text-fog font-sans text-xs underline">
            {mode === "login" ? "New here? Create account" : "Already have an account? Sign in instead"}
          </button>
          <button type="button" onClick={() => setScreen("landing")}
            className="text-fog font-sans text-xs">
            ← Back
          </button>
        </form>
      </div>
    </div>
  );
}
