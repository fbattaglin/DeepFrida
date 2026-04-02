#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting DeepFrida..."

cd "$SCRIPT_DIR/backend" || exit 1
"$SCRIPT_DIR/.venv/bin/python3" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

cd "$SCRIPT_DIR/frontend" || exit 1
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  DeepFrida is running"
echo "  Frontend : http://localhost:5173"
echo "  Backend  : http://localhost:8000"
echo "  Press Ctrl+C to stop"
echo ""

trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
