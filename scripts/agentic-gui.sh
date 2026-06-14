#!/bin/bash
# agentic-gui — launch/stop the Agentic OS desktop GUI (sidecar + Tauri app).
# Always kills stale processes before starting, so rerunning is always safe.
#
#   agentic-gui          start (kills any existing instances first)
#   agentic-gui stop     stop everything
#   agentic-gui status   show what's running

ROOT="$HOME/Codehome/AgenticOS"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

kill_all() {
  # by port: sidecar (5130) and Vite dev server (1420)
  lsof -ti :5130 2>/dev/null | xargs kill 2>/dev/null
  lsof -ti :1420 2>/dev/null | xargs kill 2>/dev/null
  # by process: sidecar module, tauri dev wrapper, the app binary itself.
  # [.] keeps the pattern from matching this script's own shell ancestry.
  pkill -f "python -m gui[.]sidecar" 2>/dev/null
  pkill -f "tauri dev" 2>/dev/null
  pkill -f "target/debug/desktop" 2>/dev/null
  # give them a moment, then force-kill stragglers. uvicorn can hang in
  # graceful shutdown when a WebSocket client was attached — SIGTERM frees
  # the port but leaves a zombie process, so always escalate to -9.
  sleep 1
  lsof -ti :5130 2>/dev/null | xargs kill -9 2>/dev/null
  lsof -ti :1420 2>/dev/null | xargs kill -9 2>/dev/null
  pkill -9 -f "python -m gui[.]sidecar" 2>/dev/null
  pkill -9 -f "tauri dev" 2>/dev/null
  pkill -9 -f "target/debug/desktop" 2>/dev/null
}

status() {
  if curl -s -m 2 http://localhost:5130/api/health > /dev/null 2>&1; then
    echo "sidecar:  ● running on :5130"
  else
    echo "sidecar:  ○ not running"
  fi
  if pgrep -f "target/debug/desktop" > /dev/null 2>&1; then
    echo "app:      ● running"
  else
    echo "app:      ○ not running"
  fi
}

case "${1:-start}" in
  stop)
    kill_all
    echo "stopped."
    ;;
  status)
    status
    ;;
  start)
    echo "cleaning up old processes..."
    kill_all

    echo "starting sidecar..."
    cd "$ROOT" || exit 1
    nohup ./.venv/bin/python -m gui.sidecar > "$LOGDIR/sidecar.log" 2>&1 &

    # wait for sidecar health (up to 10s)
    for _ in $(seq 1 20); do
      if curl -s -m 1 http://localhost:5130/api/health > /dev/null 2>&1; then
        break
      fi
      sleep 0.5
    done
    if ! curl -s -m 1 http://localhost:5130/api/health > /dev/null 2>&1; then
      echo "ERROR: sidecar failed to start — see $LOGDIR/sidecar.log"
      exit 1
    fi
    echo "sidecar ready on :5130"

    echo "starting app..."
    source "$HOME/.cargo/env" 2>/dev/null
    cd "$ROOT/gui/desktop" || exit 1
    nohup npm run tauri dev > "$LOGDIR/tauri.log" 2>&1 &
    echo "app launching — window appears after compile (logs: $LOGDIR/tauri.log)"
    ;;
  *)
    echo "usage: agentic-gui [start|stop|status]"
    exit 1
    ;;
esac
