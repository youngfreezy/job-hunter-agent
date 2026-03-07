#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME_DIR="$ROOT/.runtime"
PID_FILE="$RUNTIME_DIR/launcher.pid"

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" || true)"
  if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$PID_FILE"
fi

lsof -ti:3000,8000 | xargs kill -9 2>/dev/null || true
pkill -9 -f "uvicorn" 2>/dev/null || true
pkill -9 -f "next dev" 2>/dev/null || true

echo "JobHunter Agent stopped"
