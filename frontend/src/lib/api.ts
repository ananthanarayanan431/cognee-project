import { ProgressData, CalibrationStatus, CalibrationAnswerResult, SessionSummary, Transcript } from "@/types";

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
  const body = (await res.json()) as { success: boolean; data: T };
  return body.data;
}

export const api = {
  register: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string; calibration_done: boolean }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string; calibration_done: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  startSession: (topic: string, description: string, difficulty: string, user_position: string) =>
    apiFetch<{ session_id: string; topic: string; description: string; has_source: boolean; source_status: string }>(
      "/api/sessions/start",
      {
        method: "POST",
        body: JSON.stringify({ topic, description, difficulty, user_position }),
      }
    ),
  endSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}/end`, { method: "POST" }),
  getTopics: () => apiFetch<{ label: string; chips: string[] }[]>("/api/topics/suggest"),
  getGraph: (sessionId: string) =>
    apiFetch<{ nodes: unknown[]; edges: unknown[] }>(`/api/sessions/${sessionId}/graph`),
  getProgress: () => apiFetch<ProgressData>("/api/users/me/progress"),
  uploadSource: async (sessionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/sessions/${sessionId}/source`, {
      method: "POST",
      headers: authHeader(),
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    const body = (await res.json()) as {
      success: boolean;
      data: { status: string; source_filename: string };
    };
    return body.data;
  },
  getSourceStatus: (sessionId: string) =>
    apiFetch<{ source_status: string }>(`/api/sessions/${sessionId}/source-status`),
  getSourceFile: (sessionId: string) =>
    apiFetch<{ url: string }>(`/api/sessions/${sessionId}/source-file`),
  getCalibrationStatus: () => apiFetch<CalibrationStatus>("/api/calibration/status"),
  submitCalibrationAnswer: (text: string) =>
    apiFetch<CalibrationAnswerResult>("/api/calibration/answer", {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  getSessionSummary: (sessionId: string) =>
    apiFetch<SessionSummary>(`/api/sessions/${sessionId}/summary`),
  getTranscript: (sessionId: string) =>
    apiFetch<Transcript>(`/api/sessions/${sessionId}/transcript`),
  transcriptExportUrl: (sessionId: string) =>
    `${BASE}/api/sessions/${sessionId}/transcript/export`,
  reactivateMastery: (pattern: string) =>
    apiFetch<{ reactivated: boolean }>(`/api/users/me/mastery/${encodeURIComponent(pattern)}/reactivate`, {
      method: "POST",
    }),
};
