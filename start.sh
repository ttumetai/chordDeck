#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python environment not found: $PYTHON_BIN" >&2
  echo "Run: uv sync --managed-python" >&2
  exit 1
fi

"$PYTHON_BIN" "$ROOT_DIR/scripts/check_env.py"

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

"$PYTHON_BIN" -m uvicorn backend.main:app --host 127.0.0.1 --port "${BACKEND_PORT:-8000}" &
BACKEND_PID=$!
(cd "$ROOT_DIR/frontend" && npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT:-5173}") &
FRONTEND_PID=$!

echo "Backend:  http://127.0.0.1:${BACKEND_PORT:-8000}"
echo "Frontend: http://127.0.0.1:${FRONTEND_PORT:-5173}"
wait "$BACKEND_PID" "$FRONTEND_PID"
