export interface Message {
  id: string;
  role: "user" | "opponent";
  text: string;
  judge?: JudgeScore;
  showJudge?: boolean;
}

export interface JudgeScore {
  logic: number;
  evidence: number;
  rhetoric: number;
  fallacy: string | null;
  outcome: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "weakness" | "strength" | "mastered" | "topic";
  weight: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SessionConfig {
  topic: string;
  description: string;
  difficulty: "balanced" | "targeted" | "ruthless";
  position: "for" | "against" | "neutral";
}

export interface ThinkingStyle {
  logic: number;
  evidence: number;
  rhetoric: number;
}

export interface ProgressData {
  weaknesses: { text: string }[];
  sessions: number;
  win_rate: number;
  thinking_style: ThinkingStyle;
}
