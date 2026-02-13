"""WebSocket connection manager for broadcasting state updates."""

import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(f"WebSocket connected ({len(self._connections)} active)")

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.remove(websocket)
        logger.info(f"WebSocket disconnected ({len(self._connections)} active)")

    async def broadcast(self, message: dict) -> None:
        """Send message to all connected clients, removing stale connections."""
        stale: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.remove(ws)
