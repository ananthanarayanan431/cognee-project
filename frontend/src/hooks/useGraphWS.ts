import { useEffect } from "react";
import { useDebate } from "@/store/debate";
import { GraphData } from "@/types";

export function useGraphWS(sessionId: string | null) {
  const setGraph = useDebate((s) => s.setGraph);

  useEffect(() => {
    if (!sessionId) return;
    const wsUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
      .replace("http", "ws") + `/ws/graph/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "graph_update") setGraph(msg.data as GraphData);
      } catch {
        // ignore malformed WebSocket messages
      }
    };
    return () => ws.close();
  }, [sessionId, setGraph]);
}
