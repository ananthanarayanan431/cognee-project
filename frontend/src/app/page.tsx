"use client";

import AuthModal from "@/components/auth/AuthModal";
import { useDebate } from "@/store/debate";

export default function Home() {
  const screen = useDebate((s) => s.screen);

  if (screen === "auth") return <AuthModal />;

  return <div>{screen}</div>;
}
