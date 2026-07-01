import { create } from "zustand";
import { Message, GraphData, SessionConfig } from "@/types";

interface DebateStore {
  screen: "landing" | "auth" | "topic" | "calibration" | "debate" | "end" | "transcript" | "progress";
  token: string | null;
  userId: string | null;
  calibrationDone: boolean;
  sessionId: string | null;
  sessionConfig: SessionConfig | null;
  messages: Message[];
  graph: GraphData;
  thinking: boolean;
  currentStage: string | null;
  sessionScores: { logic: number; evidence: number; rhetoric: number };

  setScreen: (s: DebateStore["screen"]) => void;
  setAuth: (token: string, userId: string, calibrationDone: boolean) => void;
  setSession: (id: string, config: SessionConfig) => void;
  addMessage: (m: Message) => void;
  updateLastOpponent: (text: string) => void;
  revealJudge: (judge: Message["judge"], mastery?: string[]) => void;
  setThinking: (v: boolean) => void;
  setCurrentStage: (stage: string | null) => void;
  setGraph: (g: GraphData) => void;
  reset: () => void;
}

export const useDebate = create<DebateStore>((set) => ({
  screen: "landing",
  token: typeof window !== "undefined" ? localStorage.getItem("dm_token") : null,
  userId: typeof window !== "undefined" ? localStorage.getItem("dm_uid") : null,
  calibrationDone: typeof window !== "undefined" ? localStorage.getItem("dm_calibration") === "1" : false,
  sessionId: null,
  sessionConfig: null,
  messages: [],
  graph: { nodes: [], edges: [] },
  thinking: false,
  currentStage: null,
  sessionScores: { logic: 0, evidence: 0, rhetoric: 0 },

  setScreen: (screen) => set({ screen }),
  setAuth: (token, userId, calibrationDone) => {
    localStorage.setItem("dm_token", token);
    localStorage.setItem("dm_uid", userId);
    localStorage.setItem("dm_calibration", calibrationDone ? "1" : "0");
    set({
      token,
      userId,
      calibrationDone,
      screen: calibrationDone ? "topic" : "calibration",
    });
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
  revealJudge: (judge, mastery) =>
    set((s) => {
      const msgs = [...s.messages];
      const last = msgs[msgs.length - 1];
      if (last?.role === "opponent") {
        msgs[msgs.length - 1] = { ...last, judge, showJudge: true, mastery };
      }
      const scores = judge
        ? { logic: judge.logic, evidence: judge.evidence, rhetoric: judge.rhetoric }
        : s.sessionScores;
      return { messages: msgs, sessionScores: scores };
    }),
  setThinking: (thinking) => set({ thinking }),
  setCurrentStage: (currentStage) => set({ currentStage }),
  setGraph: (graph) => set({ graph }),
  reset: () => set({ sessionId: null, sessionConfig: null, messages: [], screen: "topic" }),
}));
