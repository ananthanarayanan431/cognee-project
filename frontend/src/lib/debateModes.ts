// Debate opponent modes ("difficulty"). Keys must match the backend's
// _DIFFICULTY_INSTRUCTIONS in debatemind/agents/prompts/opponent.py.

export type DebateMode =
  | "gentle"
  | "balanced"
  | "targeted"
  | "ruthless"
  | "relentless"
  | "socratic"
  | "devils_advocate";

export const DEFAULT_DEBATE_MODE: DebateMode = "targeted";

export interface DebateModeMeta {
  key: DebateMode;
  name: string;
  blurb: string;
}

export const DEBATE_MODES: DebateModeMeta[] = [
  { key: "gentle",          name: "Gentle",          blurb: "Collaborative warm-up — rarely presses your weaknesses." },
  { key: "balanced",        name: "Balanced",        blurb: "Explores many angles; targets a weakness now and then." },
  { key: "targeted",        name: "Targeted",        blurb: "Every turn exploits one specific weakness of yours." },
  { key: "ruthless",        name: "Ruthless",        blurb: "Hammers the same weakness until you truly close the gap." },
  { key: "relentless",      name: "Relentless",      blurb: "Maximum compounding pressure — never lets a gap close." },
  { key: "socratic",        name: "Socratic",        blurb: "Interrogates your assumptions through pointed questions." },
  { key: "devils_advocate", name: "Devil's Advocate", blurb: "Takes the most contrarian defensible stance available." },
];

export function debateModeName(key: string): string {
  return DEBATE_MODES.find((m) => m.key === key)?.name ?? key;
}

export function isDebateMode(v: string | null | undefined): v is DebateMode {
  return !!v && DEBATE_MODES.some((m) => m.key === v);
}
