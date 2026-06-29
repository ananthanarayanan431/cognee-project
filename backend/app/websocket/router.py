from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import ws_manager

ws_router = APIRouter()


@ws_router.websocket("/ws/graph/{session_id}")
async def graph_ws(session_id: str, ws: WebSocket):
    await ws_manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id, ws)
