export interface Message {
  id: string;
  role: "user" | "opponent";
  text: string;
  judge?: JudgeScore;
  showJudge?: boolean;
  mastery?: string[];
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
  type: "weakness" | "strength" | "mastered" | "topic" | "root";
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
  topic_id?: string | null;
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

export interface MasteredPattern {
  pattern: string;
  mastered_at: string;
  rounds_to_mastery: number;
  reactivated: boolean;
}

export interface TopicWinRate {
  topic: string;
  win_rate: number;
}

export interface WeaknessTrendItem {
  pattern: string;
  weight: number;
}

export interface ProgressData {
  weaknesses: { text: string }[];
  sessions: number;
  win_rate: number;
  streak: number;
  thinking_style: ThinkingStyle;
  mastered: MasteredPattern[];
  win_rate_by_topic: TopicWinRate[];
  weakness_trend: WeaknessTrendItem[];
}

export interface CalibrationStatus {
  needed: boolean;
  topic?: string;
  index: number;
  total: number;
}

export interface CalibrationAnswerResult {
  done: boolean;
  next_topic?: string;
  index: number;
  total: number;
}

export interface WeaknessChange {
  pattern: string;
  before: number;
  after: number;
  mastered: boolean;
  rounds_to_mastery: number | null;
}

export interface SessionSummary {
  topic: string;
  difficulty: string;
  score: number;
  exchanges: number;
  weaknesses_exposed: number;
  mastered_count: number;
  rounds_won: number;
  patterns: WeaknessChange[];
}

export interface TranscriptExchange {
  turn_number: number;
  user_message: string;
  opponent_response: string;
  judge_logic: number | null;
  judge_evidence: number | null;
  judge_rhetoric: number | null;
  fallacy: string | null;
  outcome: string | null;
  created_at: string;
}

export interface Transcript {
  session_id: string;
  topic: string;
  difficulty: string;
  started_at: string;
  exchanges: TranscriptExchange[];
}

export interface SessionListItem {
  session_id: string;
  topic_id: string | null;
  topic: string;
  title?: string | null;
  difficulty: string;
  status: "active" | "ended";
  overall_score: number;
  exchanges: number;
  started_at: string;
  ended_at: string | null;
}

export interface DebatableQuestion {
  id: string;
  domain: string;
  title: string;
  description: string;
}

export interface VoiceTokenResponse {
  client_secret: { value: string; expires_at: number };
  id: string;
  model: string;
  voice_session_id: string;
  [key: string]: unknown;
}
