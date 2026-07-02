"use client";
import { useEffect, useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { useDebate } from "@/store/debate";
import { screenToPath, resolveNavScreen } from "@/lib/screens";
import LandingPage from "@/components/auth/LandingPage";
import TopicSelection from "@/components/topic/TopicSelection";
import TopicDetail from "@/components/topic/TopicDetail";
import SessionSidebar from "@/components/sidebar/SessionSidebar";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
const CalibrationSession = dynamic(() => import("@/components/calibration/CalibrationSession"), { ssr: false });
const SessionTranscript = dynamic(() => import("@/components/session/SessionTranscript"), { ssr: false });
const SettingsPage = dynamic(() => import("@/components/settings/SettingsPage"), { ssr: false });

function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <div className="hidden lg:flex flex-shrink-0">
        <SessionSidebar />
      </div>
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {children}
      </main>
    </div>
  );
}

export default function Home() {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);
  const hydrate = useDebate((s) => s.hydrate);
  const setScreen = useDebate((s) => s.setScreen);
  const setAuth = useDebate((s) => s.setAuth);

  // Pass the current URL screen param into hydrate so refreshing restores the right screen
  useEffect(() => {
    const urlScreen = new URLSearchParams(window.location.search).get("screen") ?? undefined;
    hydrate(urlScreen);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Exchange SSO session token for a backend token once the user is signed in
  useEffect(() => {
    if (!isLoaded || !isSignedIn || token) return;
    getToken().then(async (authToken) => {
      if (!authToken) return;
      try {
        const { api } = await import("@/lib/api");
        const res = await api.exchangeToken(authToken);
        setAuth(res.access_token, res.user_id, res.calibration_done);
      } catch {
        // Exchange failed — user will see landing page and can retry
      }
    });
  }, [isLoaded, isSignedIn, token, getToken, setAuth]);

  // Mirror the active screen into the URL. "calibration" is an auth-gated
  // interstitial with no addressable URL, so it is skipped. Every other screen
  // maps to a path via screenToPath ("topic" → "/", else "/?screen=<name>").
  // A push only happens when the URL actually differs, so popstate-driven screen
  // changes (which already updated the URL) never create a duplicate entry.
  useEffect(() => {
    if (!token || screen === "calibration") return;
    const target = screenToPath(screen);
    const current = window.location.pathname + window.location.search;
    if (current === target) return;
    window.history.pushState({ screen }, "", target);
  }, [screen, token]);

  // Handle browser back / forward. Prefer the history entry's stored screen,
  // fall back to the URL param, then to the landing page (bare "/").
  const handlePopState = useCallback((e: PopStateEvent) => {
    const stateScreen = (e.state as { screen?: string } | null)?.screen ?? "";
    const urlScreen = new URLSearchParams(window.location.search).get("screen") ?? "";
    setScreen(resolveNavScreen(stateScreen || urlScreen || "landing"));
  }, [setScreen]);

  useEffect(() => {
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [handlePopState]);

  // Landing page is public — visible to both authenticated and unauthenticated users.
  // Authenticated users land here via the DebateMind logo or navigating to "/".
  if (!token || screen === "landing") {
    return <LandingPage />;
  }
  if (screen === "calibration") return <CalibrationSession />;

  return (
    <AuthenticatedShell>
      {screen === "topic" && <TopicSelection />}
      {screen === "topic-detail" && <TopicDetail />}
      {screen === "debate" && <DebateView />}
      {screen === "end" && <SessionEnd />}
      {screen === "progress" && <ProgressDashboard />}
      {screen === "transcript" && <SessionTranscript />}
      {screen === "settings" && <SettingsPage />}
      {!["topic", "topic-detail", "debate", "end", "progress", "transcript", "settings", "calibration"].includes(screen) && <TopicSelection />}
    </AuthenticatedShell>
  );
}
