import { useCallback } from "react";
import { useDebate } from "@/store/debate";
import { JudgeScore } from "@/types";
import { v4 as uuid } from "uuid";

export function useSendMessage() {
  const { sessionId, addMessage, updateLastOpponent, revealJudge, setThinking } = useDebate();
  const token = useDebate((s) => s.token);

  return useCallback(async (text: string) => {
    if (!sessionId || !text.trim()) return;
    addMessage({ id: uuid(), role: "user", text });
    setThinking(true);

    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/sessions/${sessionId}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text }),
    });

    if (!res.body) {
      setThinking(false);
      return;
    }

    const opponentId = uuid();
    addMessage({ id: opponentId, role: "opponent", text: "" });
    setThinking(false);

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
            const current = useDebate.getState().messages.find((m) => m.id === opponentId);
            updateLastOpponent((current?.text ?? "") + evt.text);
          }
          if (evt.type === "judge") {
            setTimeout(() => revealJudge(evt as JudgeScore), 2000);
          }
        } catch {
          // ignore malformed SSE events
        }
      }
    }
  }, [sessionId, token, addMessage, updateLastOpponent, revealJudge, setThinking]);
}
