"use client";
import { useEffect, useCallback } from "react";
import { useDebate } from "@/store/debate";
import { useClerkExchange } from "@/hooks/useClerkExchange";
import { screenToPath, resolveNavScreen } from "@/lib/screens";
import LandingPage from "@/components/auth/LandingPage";
import TopicSelection from "@/components/topic/TopicSelection";
import TopicDetail from "@/components/topic/TopicDetail";
import SessionSidebar from "@/components/sidebar/SessionSidebar";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
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
  useClerkExchange();
  const screen = useDebate((s) => s.screen);
  const sessionId = useDebate((s) => s.sessionId);
  const token = useDebate((s) => s.token);
  const hydrate = useDebate((s) => s.hydrate);
  const setScreen = useDebate((s) => s.setScreen);

  // Pass the current URL screen param into hydrate so refreshing restores the right screen
  useEffect(() => {
    const urlScreen = new URLSearchParams(window.location.search).get("screen") ?? undefined;
    hydrate(urlScreen);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Mirror the active screen into the URL; only push when the URL actually
  // differs so popstate-driven changes don't create duplicate entries.
  useEffect(() => {
    if (!token) return;
    const target = screenToPath(screen, sessionId);
    const current = window.location.pathname + window.location.search;
    if (current === target) return;
    window.history.pushState({ screen, sessionId }, "", target);
  }, [screen, sessionId, token]);

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
  return (
    <AuthenticatedShell>
      {screen === "topic" && <TopicSelection />}
      {screen === "topic-detail" && <TopicDetail />}
      {screen === "debate" && <DebateView />}
      {screen === "end" && <SessionEnd />}
      {screen === "progress" && <ProgressDashboard />}
      {screen === "transcript" && <SessionTranscript />}
      {screen === "settings" && <SettingsPage />}
      {!["topic", "topic-detail", "debate", "end", "progress", "transcript", "settings"].includes(screen) && <TopicSelection />}
    </AuthenticatedShell>
  );
}
