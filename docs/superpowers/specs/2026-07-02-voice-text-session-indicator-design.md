# Voice/Text Session Indicator in Sidebar

## Problem

The sidebar session list (`SessionSidebar.tsx`) shows a small colored badge per
session that looks like it could indicate session type, but it actually shows
debate **difficulty** (`balanced`/`targeted`/`ruthless` → B/T/R). There is
currently no way to tell, at a glance in the sidebar, whether a session was
conducted via voice or via text chat.

Voice and text interactions share a single `DebateSession` row; voice usage is
only tracked in a separate child table (`voice_sessions`, keyed by
`debate_session_id`), created lazily the first time voice is used for that
session. There is no `has_voice_session`-like field currently exposed on the
list endpoint (`GET /api/sessions`) or on the frontend `SessionListItem` type.

## Goal

Add a small mic icon next to a session's title in the sidebar when that
session has ever used voice. Text-only sessions show no icon. The existing
difficulty badge is unchanged.

## Design

### Backend

- `debatemind-backend/debatemind/routers/sessions.py::list_sessions`: add a
  per-row `has_voice_session: bool` computed via a SQL `EXISTS` subquery
  against `voice_sessions.debate_session_id == sessions.id`, evaluated in the
  same query that lists sessions (no N+1 queries).
- `debatemind-backend/debatemind/schemas/session.py::SessionListItemOut`: add
  `has_voice_session: bool` field.

### Frontend

- `frontend/src/types/index.ts::SessionListItem`: add
  `has_voice_session: boolean`.
- `frontend/src/components/sidebar/SessionSidebar.tsx::SessionCard`: import
  `IconMicrophone` from `@tabler/icons-react` (already a project dependency,
  consistent with other icons already imported in this file). Render it at
  14px, muted color (e.g. `text-fog`), directly before the title text, only
  when `session.has_voice_session` is `true`. No icon is rendered for
  text-only sessions — absence of the mic icon signals "text".

Row layout becomes:
`[difficulty badge] [mic icon, if voice] [title, truncated] [active dot, if active]`

### Out of scope

- No filter/grouping by mode (per user decision — icon-only, not a filter).
- No "primary/dominant mode" computation for mixed sessions — presence of any
  voice sub-session is sufficient (per user decision).
- No new DB migration — `voice_sessions` table and its FK already exist.
- No change to `VoiceSession.tsx`'s own difficulty color badge.

## Testing

- Backend: verify `list_sessions` response includes `has_voice_session: true`
  for a session with a `voice_sessions` row, and `false` for one without.
- Frontend: manually verify in the browser that a session that has used voice
  shows the mic icon, and one that hasn't does not.
