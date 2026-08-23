// Screen ↔ URL routing (single source of truth). "landing" owns "/", every
// other screen lives under "/?screen=<name>".

export type Screen =
  | "landing"
  | "topic"
  | "debate"
  | "end"
  | "transcript"
  | "progress"
  | "topic-detail"
  | "settings";

// Screens addressable via `?screen=X`. "landing" owns "/" so it is absent here.
const ADDRESSABLE: ReadonlySet<Screen> = new Set<Screen>([
  "topic",
  "topic-detail",
  "debate",
  "end",
  "progress",
  "transcript",
  "settings",
]);

// Screens safe to restore on a cold load — they need no ephemeral in-memory state.
const COLD_RESTORABLE: ReadonlySet<Screen> = new Set<Screen>([
  "landing",
  "topic",
  "progress",
  "settings",
]);

// Screens that carry the active session id in the URL (display/trace-only).
const SESSION_SCOPED: ReadonlySet<Screen> = new Set<Screen>([
  "debate",
  "end",
  "transcript",
]);

export function isScreen(s: string): s is Screen {
  return s === "landing" || ADDRESSABLE.has(s as Screen);
}

/**
 * Screen → URL path. "landing" is "/"; everything else is "/?screen=<name>".
 * Session-scoped screens append `&session=<id>` when a session id is supplied
 * so the active session is traceable from the URL.
 */
export function screenToPath(screen: Screen, sessionId?: string | null): string {
  if (screen === "landing") return "/";
  const base = `/?screen=${screen}`;
  if (sessionId && SESSION_SCOPED.has(screen)) {
    return `${base}&session=${sessionId}`;
  }
  return base;
}

/**
 * Resolve the screen for a COLD page load (first mount / refresh / direct link).
 * Enforces auth gates and only restores screens that don't depend on ephemeral
 * in-memory state. Bare "/" (no ?screen param) resolves to the landing page.
 */
export function resolveInitialScreen(
  urlScreen: string | null | undefined,
  auth: { token: string | null },
): Screen {
  if (!auth.token) return "landing";
  if (urlScreen && COLD_RESTORABLE.has(urlScreen as Screen)) {
    return urlScreen as Screen;
  }
  return "landing";
}

/**
 * Resolve the screen for an in-session back/forward (popstate) event. Ephemeral
 * screens are honored here because their in-memory state still exists within the
 * same SPA session; anything unrecognized falls back to the landing page (the
 * root URL).
 */
export function resolveNavScreen(candidate: string): Screen {
  if (candidate === "landing") return "landing";
  if (ADDRESSABLE.has(candidate as Screen)) return candidate as Screen;
  return "landing";
}
