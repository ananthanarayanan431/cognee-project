import { useCallback } from "react";
import { useDebate } from "@/store/debate";
import { JudgeScore, GraphData } from "@/types";
import { v4 as uuid } from "uuid";
import { handleExpiredSession } from "@/lib/api";

/**
 * Stream the opponent's AI-generated opening message for a fresh session.
 * Mirrors useSendMessage's SSE token handling, but there is no user message,
 * judge, or graph — just the opening line streamed into a single opponent bubble.
 */
export function useStreamOpening() {
  const { addMessage, updateLastOpponent, setThinking, setCurrentStage } = useDebate();
  const token = useDebate((s) => s.token);
  const mainModel = useDebate((s) => s.mainModel);

  return useCallback(async (sessionId: string) => {
    setThinking(true);
    setCurrentStage("opponent");

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/sessions/${sessionId}/opening`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(mainModel ? { "X-Model": mainModel } : {}),
      },
    });

    if (res.status === 401) {
      setThinking(false);
      setCurrentStage(null);
      handleExpiredSession();
      return;
    }
    if (!res.ok || !res.body) {
      setThinking(false);
      setCurrentStage(null);
      return;
    }

    const openingId = uuid();
    let opponentAdded = false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const evt = JSON.parse(raw);
          if (evt.type === "token") {
            if (!opponentAdded) {
              addMessage({ id: openingId, role: "opponent", text: "" });
              opponentAdded = true;
              setThinking(false);
              setCurrentStage(null);
            }
            const current = useDebate.getState().messages.find((m) => m.id === openingId);
            updateLastOpponent((current?.text ?? "") + evt.text);
          }
          if (evt.type === "error") {
            setThinking(false);
            setCurrentStage(null);
            if (!opponentAdded) {
              addMessage({
                id: openingId,
                role: "opponent",
                text: "Something went wrong starting the debate. Make your opening argument to begin.",
              });
              opponentAdded = true;
            }
          }
        } catch {
          // ignore malformed SSE events
        }
      }
    }

    // Stream ended before any token arrived — clear the thinking state.
    if (!opponentAdded) {
      setThinking(false);
      setCurrentStage(null);
    }
  }, [token, mainModel, addMessage, updateLastOpponent, setThinking, setCurrentStage]);
}

export function useStreamContinuation() {
  const { addMessage, updateLastOpponent, setThinking, setCurrentStage } = useDebate();
  const token = useDebate((s) => s.token);
  const mainModel = useDebate((s) => s.mainModel);

  return useCallback(async (sessionId: string) => {
    setThinking(true);
    setCurrentStage("opponent");

    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/sessions/${sessionId}/continue`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          ...(mainModel ? { "X-Model": mainModel } : {}),
        },
      }
    );

    if (res.status === 401) {
      setThinking(false);
      setCurrentStage(null);
      handleExpiredSession();
      return;
    }
    if (!res.ok || !res.body) {
      setThinking(false);
      setCurrentStage(null);
      return;
    }

    const continuationId = uuid();
    let opponentAdded = false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const evt = JSON.parse(raw);
          if (evt.type === "token") {
            if (!opponentAdded) {
              addMessage({ id: continuationId, role: "opponent", text: "" });
              opponentAdded = true;
              setThinking(false);
              setCurrentStage(null);
            }
            const current = useDebate.getState().messages.find((m) => m.id === continuationId);
            updateLastOpponent((current?.text ?? "") + evt.text);
          }
          if (evt.type === "error") {
            setThinking(false);
            setCurrentStage(null);
          }
        } catch {
          // ignore malformed SSE events
        }
      }
    }

    if (!opponentAdded) {
      setThinking(false);
      setCurrentStage(null);
    }
  }, [token, mainModel, addMessage, updateLastOpponent, setThinking, setCurrentStage]);
}

export function useSendMessage() {
  const { sessionId, addMessage, updateLastOpponent, revealJudge, setThinking, setGraph, setCurrentStage } =
    useDebate();
  const token = useDebate((s) => s.token);
  const mainModel = useDebate((s) => s.mainModel);
  const judgeModel = useDebate((s) => s.judgeModel);

  return useCallback(async (text: string) => {
    if (!sessionId || !text.trim()) return;
    addMessage({ id: uuid(), role: "user", text });
    setThinking(true);
    setCurrentStage(null);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(mainModel ? { "X-Model": mainModel } : {}),
        ...(judgeModel ? { "X-Judge-Model": judgeModel } : {}),
      },
      body: JSON.stringify({ text }),
    });

    if (res.status === 401) {
      setThinking(false);
      setCurrentStage(null);
      handleExpiredSession();
      return;
    }

    if (!res.body) {
      setThinking(false);
      setCurrentStage(null);
      return;
    }

    const opponentId = uuid();
    let opponentAdded = false;

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") break;
        try {
          const evt = JSON.parse(raw);
          if (evt.type === "stage") {
            setCurrentStage(evt.stage);
          }
          if (evt.type === "token") {
            if (!opponentAdded) {
              addMessage({ id: opponentId, role: "opponent", text: "" });
              opponentAdded = true;
              setThinking(false);
              setCurrentStage(null);
            }
            const current = useDebate.getState().messages.find((m) => m.id === opponentId);
            updateLastOpponent((current?.text ?? "") + evt.text);
          }
          if (evt.type === "judge") {
            setTimeout(() => revealJudge(evt as JudgeScore, evt.mastery as string[] | undefined), 2000);
          }
          if (evt.type === "graph") {
            setGraph(evt.data as GraphData);
          }
          if (evt.type === "error") {
            setThinking(false);
            setCurrentStage(null);
            if (!opponentAdded) {
              addMessage({
                id: opponentId,
                role: "opponent",
                text: "Something went wrong generating a response. Please try again.",
              });
              opponentAdded = true;
            }
          }
        } catch {
          // ignore malformed SSE events
        }
      }
    }
  }, [sessionId, token, mainModel, judgeModel, addMessage, updateLastOpponent, revealJudge, setThinking, setGraph, setCurrentStage]);
}
