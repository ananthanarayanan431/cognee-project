"use client";
import { useDebate } from "@/store/debate";
import AuthModal from "@/components/auth/AuthModal";
import TopicSelection from "@/components/topic/TopicSelection";
import dynamic from "next/dynamic";

const DebateView = dynamic(() => import("@/components/debate/DebateView"), { ssr: false });
const SessionEnd = dynamic(() => import("@/components/session/SessionEnd"), { ssr: false });

export default function Home() {
  const screen = useDebate((s) => s.screen);
  const token = useDebate((s) => s.token);

  if (!token || screen === "auth") return <AuthModal />;
  if (screen === "topic") return <TopicSelection />;
  if (screen === "debate") return <DebateView />;
  if (screen === "end") return <SessionEnd />;
  return <TopicSelection />;
}
