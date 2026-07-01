import { create } from "zustand";
import { Message, GraphData, SessionConfig, SessionListItem } from "@/types";

interface DebateStore {
  screen: "landing" | "auth" | "topic" | "calibration" | "debate" | "end" | "transcript" | "progress" | "topic-detail";
  topicDetailTopic: { title: string; description: string } | null;
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
  sessions: SessionListItem[];

  hydrate: () => void;
  setScreen: (s: DebateStore["screen"]) => void;
  setAuth: (token: string, userId: string, calibrationDone: boolean) => void;
  setSession: (id: string, config: SessionConfig) => void;
  addMessage: (m: Message) => void;
  setMessages: (msgs: Message[]) => void;
  updateLastOpponent: (text: string) => void;
  revealJudge: (judge: Message["judge"], mastery?: string[]) => void;
  setThinking: (v: boolean) => void;
  setCurrentStage: (stage: string | null) => void;
  setGraph: (g: GraphData) => void;
  setSessions: (sessions: SessionListItem[]) => void;
  setTopicDetail: (topic: { title: string; description: string } | null) => void;
  reset: () => void;
}

export const useDebate = create<DebateStore>((set) => ({
  screen: "landing",
  topicDetailTopic: null,
  token: null,
  userId: null,
  calibrationDone: false,
  sessionId: null,
  sessionConfig: null,
  messages: [],
  graph: { nodes: [], edges: [] },
  thinking: false,
  currentStage: null,
  sessionScores: { logic: 0, evidence: 0, rhetoric: 0 },
  sessions: [],

  hydrate: () => {
    const token = localStorage.getItem("dm_token");
    const calibrationDone = localStorage.getItem("dm_calibration") === "1";
    set({
      token,
      userId: localStorage.getItem("dm_uid"),
      calibrationDone,
      screen: token ? (calibrationDone ? "topic" : "calibration") : "landing",
    });
  },
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
  setMessages: (msgs) => set({ messages: msgs }),
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
  setSessions: (sessions) => set({ sessions }),
  setTopicDetail: (topicDetailTopic) => set({ topicDetailTopic, screen: "topic-detail" }),
  reset: () => set({ sessionId: null, sessionConfig: null, messages: [], screen: "topic" }),
}));
