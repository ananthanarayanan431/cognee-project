// ── Screen ↔ URL routing (single source of truth) ────────────────────────────
//
// The app is a single Next.js route ("/") whose visible screen is driven by
// Zustand state and mirrored into the URL via the History API. All screen↔URL
// mapping lives here so hydrate (URL→screen), the URL-sync effect (screen→URL),
// and the popstate handler (URL→screen) can never drift out of sync.
//
// "landing" is the public marketing home and owns the clean root URL ("/").
// Every in-app screen lives under "/?screen=<name>" (the topic list is the app
// home at "/?screen=topic"). "calibration" is an auth-gated interstitial with no
// addressable URL.

export type Screen =
  | "landing"
  | "topic"
  | "calibration"
  | "debate"
  | "end"
  | "transcript"
  | "progress"
  | "topic-detail"
  | "settings";

// Screens addressable via `?screen=X`. "landing" owns "/" so it is absent here;
// "calibration" is an auth-gated interstitial and is never URL-addressable.
const ADDRESSABLE: ReadonlySet<Screen> = new Set<Screen>([
  "topic",
  "topic-detail",
  "debate",
  "end",
  "progress",
  "transcript",
  "settings",
]);

// Subset safe to restore on a COLD load (refresh / direct link). These need no
// ephemeral in-memory state. debate/topic-detail/end/transcript require a live
// sessionId or a selected topic that isn't persisted, so a cold load of those
// falls back to the app home (topic list) instead of rendering a blank screen.
const COLD_RESTORABLE: ReadonlySet<Screen> = new Set<Screen>([
  "landing",
  "topic",
  "progress",
  "settings",
]);

// Screens bound to a specific debate session. These carry the session id in the
// URL (`&session=<id>`) so an active session is traceable from the address bar
// and logs. The id is display/trace-only — cold loads still fall back per
// COLD_RESTORABLE and do not resume the session.
const SESSION_SCOPED: ReadonlySet<Screen> = new Set<Screen>([
  "debate",
  "end",
  "transcript",
]);

export function isScreen(s: string): s is Screen {
  return (
    s === "landing" ||
    s === "calibration" ||
    ADDRESSABLE.has(s as Screen)
  );
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
  auth: { token: string | null; calibrationDone: boolean },
): Screen {
  if (!auth.token) return "landing";
  if (!auth.calibrationDone) return "calibration";
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
