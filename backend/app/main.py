from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1.router import v1_router
from app.ws.socketio_server import sio

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure runtime directories exist. Schema is managed by Alembic —
    # run `alembic upgrade head` before starting the server.
    Path("data").mkdir(exist_ok=True)
    Path("storage/screenshots").mkdir(parents=True, exist_ok=True)
    Path("storage/exports").mkdir(parents=True, exist_ok=True)

    yield

    # Shut down the shared browser (if one was ever launched).
    from app.engine.browser import shutdown_shared_browser
    await shutdown_shared_browser()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS — restrict to configured frontend origins (see settings.cors_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(v1_router, prefix="/api/v1")

# Serve screenshots as static files
screenshots_path = Path("storage/screenshots")
screenshots_path.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(screenshots_path)), name="screenshots")

import socketio as sio_lib

# ── Socket.IO integration ──
# Mount the Socket.IO ASGI app on a non-conflicting path.
# Frontend uses: io('/', { path: '/ws/socket.io' })
sio_asgi = sio_lib.ASGIApp(sio, other_asgi_app=app, socketio_path="/ws/socket.io")

# Replace the module-level app with the combined ASGI app
# so uvicorn picks up the Socket.IO-wrapped version
app = sio_asgi
