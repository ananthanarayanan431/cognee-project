import { ProgressData, CalibrationStatus, CalibrationAnswerResult, SessionSummary, Transcript, SessionListItem, VoiceSessionSummary, TranscriptLineSaved } from "@/types";
import { useDebate } from "@/store/debate";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export function handleExpiredSession() {
  localStorage.removeItem("dm_token");
  localStorage.removeItem("dm_uid");
  localStorage.removeItem("dm_calibration");
  // Clear token only — page.tsx's exchange effect detects isSignedIn && !token
  // and automatically fetches a fresh backend token from Clerk. No redirect needed.
  useDebate.setState({ token: null, userId: null });
}

function authHeader(): Record<string, string> {
  const token = typeof window !== "undefined" ? localStorage.getItem("dm_token") : null;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authHeader(), ...(init?.headers ?? {}) },
  });
  if (res.status === 401 || res.status === 403) {
    handleExpiredSession();
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    const text = await res.text();
    let message = text;
    try {
      const json = JSON.parse(text);
      message = json.detail ?? json.message ?? text;
    } catch {
      // not JSON, use raw text
    }
    throw new Error(message);
  }
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
  exchangeToken: (authToken: string) =>
    apiFetch<{ access_token: string; user_id: string; calibration_done: boolean }>("/api/auth/clerk-exchange", {
      method: "POST",
      body: JSON.stringify({ clerk_token: authToken }),
    }),
  startSession: (topic: string, description: string, difficulty: string, user_position: string, topic_id?: string | null) =>
    apiFetch<{ session_id: string; topic_id: string | null; topic: string; description: string; has_source: boolean; source_status: string }>(
      "/api/sessions/start",
      {
        method: "POST",
        body: JSON.stringify({ topic_id: topic_id ?? null, topic, description, difficulty, user_position }),
      }
    ),
  endSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}/end`, { method: "POST" }),
  /** Fire-and-forget end for use in beforeunload / tab-close scenarios. */
  endSessionBeacon: (sessionId: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("dm_token") : null;
    const url = `${BASE}/api/sessions/${sessionId}/end`;
    fetch(url, {
      method: "POST",
      keepalive: true,
      headers: { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" },
    }).catch(() => {});
  },
  getTopics: () => apiFetch<import("@/types").DebatableQuestion[]>("/api/topics/suggest"),
  getSavedTopics: () => apiFetch<import("@/types").DebatableQuestion[]>("/api/topics/saved"),
  saveQuestion: (q: import("@/types").DebatableQuestion) =>
    apiFetch<import("@/types").DebatableQuestion>("/api/topics/save", {
      method: "POST",
      body: JSON.stringify(q),
    }),
  generateTopics: (domain: string, count: number, focus = "") =>
    apiFetch<import("@/types").DebatableQuestion[]>("/api/topics/generate", {
      method: "POST",
      body: JSON.stringify({ domain, count, focus }),
    }),
  deleteSavedTopic: (questionId: string) =>
    apiFetch<null>(`/api/topics/saved/${encodeURIComponent(questionId)}`, { method: "DELETE" }),
  getGraph: (sessionId: string) =>
    apiFetch<{ nodes: unknown[]; edges: unknown[] }>(`/api/sessions/${sessionId}/graph`),
  getTopicSessionCounts: () => apiFetch<Record<string, number>>("/api/users/me/topic-session-counts"),
  getProgress: () => apiFetch<ProgressData>("/api/users/me/progress"),
  uploadSource: async (sessionId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/api/sessions/${sessionId}/source`, {
      method: "POST",
      headers: authHeader(),
      body: form,
    });
    if (res.status === 401) {
      handleExpiredSession();
      throw new Error("Session expired. Please log in again.");
    }
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
  getSessions: () => apiFetch<SessionListItem[]>("/api/sessions"),
  deleteSession: (sessionId: string) =>
    apiFetch<{ status: string }>(`/api/sessions/${sessionId}`, { method: "DELETE" }),
  describeUser: () => apiFetch<{ description: string }>("/api/users/me/describe"),
  exportProfileUrl: () => `${BASE}/api/users/me/export`,
  getBrainGraph: () => apiFetch<{ nodes: import("@/types").GraphNode[]; edges: import("@/types").GraphEdge[] }>("/api/users/me/brain"),
  getKnowledgeGraph: () => apiFetch<import("@/types").KnowledgeGraphData>("/api/users/me/knowledge-graph"),
  forgetFact: (nodeId: string) =>
    apiFetch<{ node_id: string; status: string }>(`/api/users/me/facts/${nodeId}`, { method: "DELETE" }),
  getModels: () => apiFetch<{ models: { id: string; name: string; provider: string; context_length: number | null; prompt_price_per_m: number }[]; default_opponent: string; default_judge: string }>("/api/users/models"),
  getVoiceToken: (sessionId: string) =>
    apiFetch<import("@/types").VoiceTokenResponse>(`/api/voice/${sessionId}/token`, { method: "POST" }),
  executeVoiceTool: (sessionId: string, voiceSessionId: string, tool: string, args: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`/api/voice/${sessionId}/tools`, {
      method: "POST",
      body: JSON.stringify({ voice_session_id: voiceSessionId, tool, arguments: args }),
    }),
  getVoiceSummary: (sessionId: string) =>
    apiFetch<VoiceSessionSummary>(`/api/voice/${sessionId}/summary`),
  saveTranscriptLine: (sessionId: string, voiceSessionId: string, speaker: "user" | "ai", text: string) =>
    apiFetch<TranscriptLineSaved>(`/api/voice/${sessionId}/transcript-line`, {
      method: "POST",
      body: JSON.stringify({ voice_session_id: voiceSessionId, speaker, text }),
    }),
};
