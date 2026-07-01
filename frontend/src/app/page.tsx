"use client";
import { useDebate } from "@/store/debate";
import LandingPage from "@/components/auth/LandingPage";
import AuthModal from "@/components/auth/AuthModal";
import TopicSelection from "@/components/topic/TopicSelection";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });
const ProgressDashboard = dynamic(() => import("@/components/progress/ProgressDashboard"), { ssr: false });
const CalibrationSession = dynamic(() => import("@/components/calibration/CalibrationSession"), { ssr: false });

export default function Home() {
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);

  if (!token) {
    return screen === "auth" ? <AuthModal /> : <LandingPage />;
  }
  if (screen === "calibration") return <CalibrationSession />;
  if (screen === "topic") return <TopicSelection />;
  if (screen === "debate") return <DebateView />;
  if (screen === "end") return <SessionEnd />;
  if (screen === "progress") return <ProgressDashboard />;
  return <TopicSelection />;
}
