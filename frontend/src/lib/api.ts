import { ProgressData } from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeader(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("dm_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

export const api = {
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  startSession: (topic: string, difficulty: string, user_position: string) =>
    apiFetch<{ session_id: string; topic: string }>("/api/sessions/start", {
      method: "POST",
      body: JSON.stringify({ topic, difficulty, user_position }),
    }),
  endSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}/end`, { method: "POST" }),
  getTopics: () => apiFetch<{ label: string; chips: string[] }[]>("/api/topics/suggest"),
  getGraph: (sessionId: string) =>
    apiFetch<{ nodes: unknown[]; edges: unknown[] }>(`/api/sessions/${sessionId}/graph`),
  getProgress: () => apiFetch<ProgressData>("/api/users/me/progress"),
};
