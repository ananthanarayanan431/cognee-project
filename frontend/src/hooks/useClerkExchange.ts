"use client";
import { useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { useDebate } from "@/store/debate";

/**
 * Exchanges the active Clerk session for a backend access token.
 * Shared by the app shell (auto-attempt on mount) and the landing page
 * (manual retry) so an already-signed-in user with a stuck exchange never
 * gets routed back through the Google/email sign-up flow, which Clerk
 * rejects with "You're already signed in".
 */
export function useClerkExchange() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const token = useDebate((s) => s.token);
  const setAuth = useDebate((s) => s.setAuth);
  const exchangeStatus = useDebate((s) => s.exchangeStatus);
  const setExchangeStatus = useDebate((s) => s.setExchangeStatus);

  const attempt = useCallback(async () => {
    if (!isLoaded || !isSignedIn || token) return;
    setExchangeStatus("pending");
    try {
      const authToken = await getToken();
      if (!authToken) throw new Error("No Clerk session token");
      const { api } = await import("@/lib/api");
      const res = await api.exchangeToken(authToken);
      setAuth(res.access_token, res.user_id, res.calibration_done);
      setExchangeStatus("idle");
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Clerk -> backend token exchange failed:", err);
      setExchangeStatus("failed");
    }
  }, [isLoaded, isSignedIn, token, getToken, setAuth, setExchangeStatus]);

  useEffect(() => {
    attempt();
  }, [attempt]);

  return {
    isSignedIn: !!isSignedIn,
    isAuthLoaded: isLoaded,
    exchangeStatus,
    retry: attempt,
  };
}
