from fastapi import WebSocket
from collections import defaultdict


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self._connections[session_id].append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        self._connections[session_id].remove(ws)

    async def broadcast_graph(self, session_id: str, graph_data: dict):
        for ws in list(self._connections.get(session_id, [])):
            try:
                await ws.send_json({"type": "graph_update", "data": graph_data})
            except Exception:
                pass


ws_manager = ConnectionManager()
