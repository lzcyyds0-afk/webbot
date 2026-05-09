import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.router import v1_router
from app.ws.socketio_server import sio

# Import all models so Base.metadata knows about them
import app.models  # noqa: F401


def _migrate_runs_table(connection):
    from sqlalchemy import inspect, text
    inspector = inspect(connection)
    cols = [c["name"] for c in inspector.get_columns("runs")]
    if "narrative" not in cols:
        connection.execute(text("ALTER TABLE runs ADD COLUMN narrative TEXT"))
    if "narrative_generated_at" not in cols:
        connection.execute(text("ALTER TABLE runs ADD COLUMN narrative_generated_at DATETIME"))


def _migrate_test_cases_table(connection):
    from sqlalchemy import inspect, text
    inspector = inspect(connection)
    cols = [c["name"] for c in inspector.get_columns("test_cases")]
    if "cookies_json" not in cols:
        connection.execute(text("ALTER TABLE test_cases ADD COLUMN cookies_json JSON"))

# Prevent any HTTP library from using the system ALL_PROXY (SOCKS) which
# breaks LLM API calls in this environment.
for _proxy_var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    os.environ.pop(_proxy_var, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data dir exists
    Path("data").mkdir(exist_ok=True)
    Path("storage/screenshots").mkdir(parents=True, exist_ok=True)
    Path("storage/exports").mkdir(parents=True, exist_ok=True)

    # Create all tables (dev mode — use alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_runs_table)
        await conn.run_sync(_migrate_test_cases_table)

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
