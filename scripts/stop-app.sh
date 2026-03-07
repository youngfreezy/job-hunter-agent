#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUNTIME_DIR="$ROOT/.runtime"
PID_FILE="$RUNTIME_DIR/launcher.pid"
BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"

kill_tree() {
  local pid="${1:-}"
  if [ -z "$pid" ]; then
    return 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  local children
  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  if [ -n "$children" ]; then
    while IFS= read -r child; do
      [ -n "$child" ] && kill_tree "$child"
    done <<< "$children"
  fi

  kill -TERM "$pid" 2>/dev/null || true
  sleep 0.5
  kill -KILL "$pid" 2>/dev/null || true
}

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE" || true)"
  [ -n "${pid:-}" ] && kill_tree "$pid"
fi

for service_pid_file in "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"; do
  if [ -f "$service_pid_file" ]; then
    service_pid="$(cat "$service_pid_file" || true)"
    [ -n "${service_pid:-}" ] && kill_tree "$service_pid"
  fi
done

lsof -ti:3000,8000 | xargs kill -9 2>/dev/null || true
pkill -9 -f "node scripts/start.js" 2>/dev/null || true
pkill -9 -f "backend.gateway.main:app" 2>/dev/null || true
pkill -9 -f "python.*uvicorn" 2>/dev/null || true
pkill -9 -f "next dev" 2>/dev/null || true
pkill -9 -f "node.*next" 2>/dev/null || true
rm -f "$PID_FILE" "$BACKEND_PID_FILE" "$FRONTEND_PID_FILE"

echo "JobHunter Agent stopped"
