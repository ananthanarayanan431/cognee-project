"use client";
import { useCallback, useEffect } from "react";
import { useAuth } from "@clerk/nextjs";
import { useDebate } from "@/store/debate";

// Shared across every hook instance (the app shell and the landing page both
// mount this hook at once) so a signed-in-but-not-yet-exchanged user only
// ever triggers one POST /api/auth/clerk-exchange, not one per mounted caller.
let inFlightExchange: Promise<void> | null = null;

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
    if (inFlightExchange) {
      await inFlightExchange;
      return;
    }
    setExchangeStatus("pending");
    inFlightExchange = (async () => {
      try {
        const authToken = await getToken();
        if (!authToken) throw new Error("No Clerk session token");
        const { api } = await import("@/lib/api");
        const res = await api.exchangeToken(authToken);
        setAuth(res.access_token, res.user_id);
        setExchangeStatus("idle");
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error("Clerk -> backend token exchange failed:", err);
        setExchangeStatus("failed");
      }
    })();
    try {
      await inFlightExchange;
    } finally {
      inFlightExchange = null;
    }
  }, [isLoaded, isSignedIn, token, getToken, setAuth, setExchangeStatus]);

  useEffect(() => {
    attempt();
  }, [attempt]);

  // Clerk sign-out (e.g. via the UserButton menu) doesn't go through any app
  // code, so the persisted backend session has to be cleared reactively here.
  useEffect(() => {
    if (isLoaded && !isSignedIn && token) {
      localStorage.removeItem("dm_token");
      localStorage.removeItem("dm_uid");
      useDebate.setState({ token: null, userId: null, exchangeStatus: "idle" });
    }
  }, [isLoaded, isSignedIn, token]);

  return {
    isSignedIn: !!isSignedIn,
    isAuthLoaded: isLoaded,
    exchangeStatus,
    retry: attempt,
  };
}
