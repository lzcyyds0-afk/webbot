#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../backend"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"

echo "========================================"
echo "  WebBot Dev Starter"
echo "========================================"

# Start backend in background
echo "Starting backend..."
cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" uv run uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

sleep 3

# Start frontend
echo "Starting frontend..."
cd "$FRONTEND_DIR"
pnpm dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "  Services started!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "========================================"
echo ""
echo "Press Ctrl+C to stop both services"

wait
