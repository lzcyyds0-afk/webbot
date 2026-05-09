"""Socket.IO server setup for real-time run event broadcasting."""
from __future__ import annotations

import socketio

from app.core.config import settings

# Create ASGI-compatible Socket.IO server
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.debug and ["*"] or ["http://localhost:5173", "http://localhost:5174"],
    logger=settings.debug,
    engineio_logger=settings.debug,
)

# Socket.IO ASGI app (to be mounted in main.py)
# Frontend connects with path='/api/v1/ws'
sio_asgi_app = socketio.ASGIApp(sio)


@sio.on("connect")
async def on_connect(sid, environ):
    pass


@sio.on("disconnect")
async def on_disconnect(sid):
    pass


@sio.on("join_run")
async def on_join_run(sid, data):
    """Client joins a run room to receive events for that run."""
    run_id = data.get("run_id")
    if run_id is not None:
        await sio.enter_room(sid, f"run_{run_id}")


@sio.on("leave_run")
async def on_leave_run(sid, data):
    """Client leaves a run room."""
    run_id = data.get("run_id")
    if run_id is not None:
        await sio.leave_room(sid, f"run_{run_id}")
