"use client";
import { useEffect } from "react";
import { useDebate } from "@/store/debate";
import LandingPage from "@/components/auth/LandingPage";
import AuthModal from "@/components/auth/AuthModal";
import TopicSelection from "@/components/topic/TopicSelection";
import SessionSidebar from "@/components/sidebar/SessionSidebar";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
const CalibrationSession = dynamic(() => import("@/components/calibration/CalibrationSession"), { ssr: false });
const SessionTranscript = dynamic(() => import("@/components/session/SessionTranscript"), { ssr: false });

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

  useEffect(() => { hydrate(); }, []);

  if (!token) {
    return screen === "auth" ? <AuthModal /> : <LandingPage />;
  }
  if (screen === "calibration") return <CalibrationSession />;

  return (
    <AuthenticatedShell>
      {screen === "topic" && <TopicSelection />}
      {screen === "debate" && <DebateView />}
      {screen === "end" && <SessionEnd />}
      {screen === "progress" && <ProgressDashboard />}
      {screen === "transcript" && <SessionTranscript />}
      {!["topic", "debate", "end", "progress", "transcript"].includes(screen) && <TopicSelection />}
    </AuthenticatedShell>
  );
}
