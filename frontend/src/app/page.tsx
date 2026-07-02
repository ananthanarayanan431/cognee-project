"use client";
import { useEffect, useCallback } from "react";
import { useDebate } from "@/store/debate";
import LandingPage from "@/components/auth/LandingPage";
import AuthModal from "@/components/auth/AuthModal";
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

const AUTHENTICATED_SCREENS = ["topic", "topic-detail", "debate", "end", "progress", "transcript", "calibration", "settings"] as const;
type AuthScreen = typeof AUTHENTICATED_SCREENS[number];

function isAuthScreen(s: string): s is AuthScreen {
  return (AUTHENTICATED_SCREENS as readonly string[]).includes(s);
}

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
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);
  const hydrate = useDebate((s) => s.hydrate);
  const setScreen = useDebate((s) => s.setScreen);

  // Pass the current URL screen param into hydrate so refreshing restores the right screen
  useEffect(() => {
    const urlScreen = new URLSearchParams(window.location.search).get("screen") ?? undefined;
    hydrate(urlScreen);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync URL when screen changes.
  // "topic" is the home screen — it lives at "/" (no param).
  // Every other authenticated screen gets "/?screen=<name>".
  useEffect(() => {
    if (!token) return;
    const param = new URLSearchParams(window.location.search).get("screen");
    if (screen === "topic") {
      // Already at home URL — nothing to do
      if (param === null) return;
      window.history.pushState({ screen: "topic" }, "", "/");
    } else {
      if (param === screen) return;
      if (param === null) {
        // First navigation away from home — replace so back goes to "/"
        window.history.replaceState({ screen }, "", `/?screen=${screen}`);
      } else {
        window.history.pushState({ screen }, "", `/?screen=${screen}`);
      }
    }
  }, [screen, token]);

  // Handle browser back / forward
  const handlePopState = useCallback((e: PopStateEvent) => {
    // Prefer history state; fall back to URL param; fall back to "topic" (home)
    const stateScreen = (e.state as { screen?: string } | null)?.screen ?? "";
    const urlScreen = new URLSearchParams(window.location.search).get("screen") ?? "";
    const s = stateScreen || urlScreen;
    setScreen(isAuthScreen(s) ? s : "topic");
  }, [setScreen]);

  useEffect(() => {
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [handlePopState]);

  if (!token) {
    return screen === "auth" ? <AuthModal /> : <LandingPage />;
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
      {!["topic", "topic-detail", "debate", "end", "progress", "transcript", "settings"].includes(screen) && <TopicSelection />}
    </AuthenticatedShell>
  );
}
