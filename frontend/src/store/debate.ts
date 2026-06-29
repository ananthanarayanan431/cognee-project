import { create } from "zustand";
import { Message, GraphData, SessionConfig } from "@/types";

interface DebateStore {
  screen: "auth" | "topic" | "debate" | "end" | "progress";
  token: string | null;
  userId: string | null;
  sessionId: string | null;
  sessionConfig: SessionConfig | null;
  messages: Message[];
  graph: GraphData;
  thinking: boolean;
  sessionScores: { logic: number; evidence: number; rhetoric: number };

  setScreen: (s: DebateStore["screen"]) => void;
  setAuth: (token: string, userId: string) => void;
  setSession: (id: string, config: SessionConfig) => void;
  addMessage: (m: Message) => void;
  updateLastOpponent: (text: string) => void;
  revealJudge: (judge: Message["judge"]) => void;
  setThinking: (v: boolean) => void;
  setGraph: (g: GraphData) => void;
  reset: () => void;
}

export const useDebate = create<DebateStore>((set) => ({
  screen: "auth",
  token: typeof window !== "undefined" ? localStorage.getItem("dm_token") : null,
  userId: typeof window !== "undefined" ? localStorage.getItem("dm_uid") : null,
  sessionId: null,
  sessionConfig: null,
  messages: [],
  graph: { nodes: [], edges: [] },
  thinking: false,
  sessionScores: { logic: 0, evidence: 0, rhetoric: 0 },

  setScreen: (screen) => set({ screen }),
  setAuth: (token, userId) => {
    localStorage.setItem("dm_token", token);
    localStorage.setItem("dm_uid", userId);
    set({ token, userId, screen: "topic" });
  },
  setSession: (sessionId, sessionConfig) =>
    set({ sessionId, sessionConfig, messages: [], screen: "debate" }),
  addMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),
  updateLastOpponent: (text) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") msgs[msgs.length - 1] = { ...last, text };
      return { messages: msgs };
    }),
  revealJudge: (judge) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") msgs[msgs.length - 1] = { ...last, judge, showJudge: true };
      const scores = judge
        ? { logic: judge.logic, evidence: judge.evidence, rhetoric: judge.rhetoric }
        : s.sessionScores;
      return { messages: msgs, sessionScores: scores };
    }),
  setThinking: (thinking) => set({ thinking }),
  setGraph: (graph) => set({ graph }),
  reset: () => set({ sessionId: null, sessionConfig: null, messages: [], screen: "topic" }),
}));
