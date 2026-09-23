"""WebSocket manager for real-time agent execution traces."""

import json
import logging
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.job_store import jobs, job_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws")


class ConnectionManager:
    """Manages active WebSocket connections by job ID."""

    def __init__(self):
        # job_id -> list of active connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept a new connection and add it to the manager."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = []
        self.active_connections[job_id].append(websocket)
        logger.info("WebSocket connected for job %s", job_id)

    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove a connection from the manager."""
        if job_id in self.active_connections:
            if websocket in self.active_connections[job_id]:
                self.active_connections[job_id].remove(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        logger.info("WebSocket disconnected for job %s", job_id)

    async def broadcast(self, job_id: str, message: dict):
        """Broadcast a message to all connections listening to a specific job."""
        if job_id in self.active_connections:
            msg_str = json.dumps(message, default=str)
            disconnected = []
            for connection in list(self.active_connections[job_id]):
                try:
                    await connection.send_text(msg_str)
                except Exception as e:
                    logger.warning("Failed to send WebSocket message to client: %s", e)
                    disconnected.append(connection)

            # Clean up broken connections
            for conn in disconnected:
                self.disconnect(conn, job_id)


manager = ConnectionManager()


@router.websocket("/trace/{job_id}")
async def trace_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for streaming agent trace events to the frontend.

    The pipeline starts before the browser can connect, so each new connection first
    receives a snapshot of everything so far. The snapshot is built right after the
    connection is registered (no await in between), so no event can fall in the gap;
    clients dedupe the possible overlap using each trace event's `seq`.
    """
    await manager.connect(websocket, job_id)
    try:
        if job_id in jobs:
            await websocket.send_text(json.dumps({"type": "snapshot", **job_snapshot(job_id)}, default=str))
        else:
            await websocket.send_text(json.dumps({"type": "error", "message": "Job not found"}))
        while True:
            # We don't expect messages from the client, just keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
    except Exception as e:
        logger.error("WebSocket error for job %s: %s", job_id, e)
        manager.disconnect(websocket, job_id)
