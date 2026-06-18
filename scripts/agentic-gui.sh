#!/bin/bash
# agentic-gui — manage the Agentic OS desktop stack.
#
#   agentic-gui install   one-time setup: register launchd agents (run once after clone)
#   agentic-gui start     start everything (launchd agents + Tauri app)
#   agentic-gui stop      stop everything (unload agents so they don't auto-restart)
#   agentic-gui restart   restart sidecar and hub without touching the Tauri app
#   agentic-gui status    show what's running
#
# After `install`, the sidecar and hub are supervised by launchd:
#   • They start automatically at login.
#   • launchd restarts them within 10 s if they crash.
#   • `stop` unloads them so they stay down until next `start`.

set -euo pipefail

ROOT="$HOME/Codehome/AgenticOS"
LOGDIR="$ROOT/data/logs"
SCRIPTS="$ROOT/scripts"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
UID_VAL=$(id -u)
DOMAIN="gui/$UID_VAL"

SIDECAR_LABEL="com.agentcos.sidecar"
HUB_LABEL="com.agentcos.hub"
SIDECAR_PLIST="$LAUNCH_AGENTS/$SIDECAR_LABEL.plist"
HUB_PLIST="$LAUNCH_AGENTS/$HUB_LABEL.plist"

mkdir -p "$LOGDIR" "$LAUNCH_AGENTS"

# ── helpers ──────────────────────────────────────────────────────────────────

agent_loaded() {
  launchctl list "$1" &>/dev/null
}

bootstrap_agent() {
  local plist="$1" label="$2"
  if agent_loaded "$label"; then
    # Already loaded — just make sure it's running (kickstart is idempotent).
    launchctl kickstart "$DOMAIN/$label" &>/dev/null || true
  else
    launchctl bootstrap "$DOMAIN" "$plist"
  fi
}

bootout_agent() {
  local plist="$1" label="$2"
  if agent_loaded "$label"; then
    launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  fi
}

# ── commands ─────────────────────────────────────────────────────────────────

do_install() {
  echo "Installing launchd agents..."

  cp "$SCRIPTS/$SIDECAR_LABEL.plist" "$SIDECAR_PLIST"
  cp "$SCRIPTS/$HUB_LABEL.plist"     "$HUB_PLIST"

  # Unload first in case stale versions are loaded.
  bootout_agent "$SIDECAR_PLIST" "$SIDECAR_LABEL"
  bootout_agent "$HUB_PLIST"     "$HUB_LABEL"

  launchctl bootstrap "$DOMAIN" "$SIDECAR_PLIST"
  launchctl bootstrap "$DOMAIN" "$HUB_PLIST"

  echo "✓ launchd agents registered and started."
  echo "  Sidecar and hub will now auto-restart on crash and start at login."
  echo ""
  echo "  To start the full GUI:  agentic-gui start"
}

do_start() {
  # Ensure agents are loaded and running.
  if ! agent_loaded "$SIDECAR_LABEL" || ! agent_loaded "$HUB_LABEL"; then
    echo "launchd agents not installed — running install first..."
    do_install
  else
    echo "starting services..."
    launchctl kickstart "$DOMAIN/$SIDECAR_LABEL" &>/dev/null || true
    launchctl kickstart "$DOMAIN/$HUB_LABEL"     &>/dev/null || true
  fi

  # Wait for sidecar health (up to 15 s).
  echo -n "waiting for sidecar"
  for _ in $(seq 1 30); do
    if curl -s -m 1 http://localhost:5130/api/health >/dev/null 2>&1; then
      echo " ✓"
      break
    fi
    echo -n "."
    sleep 0.5
  done
  if ! curl -s -m 1 http://localhost:5130/api/health >/dev/null 2>&1; then
    echo ""
    echo "ERROR: sidecar failed to start — see $LOGDIR/sidecar.log"
    exit 1
  fi

  # Launch Tauri app if not already running.
  if pgrep -f "target/debug/desktop" >/dev/null 2>&1; then
    echo "app already running."
  else
    echo "starting app..."
    source "$HOME/.cargo/env" 2>/dev/null || true
    cd "$ROOT/gui/desktop"
    nohup npm run tauri dev > "$LOGDIR/tauri.log" 2>&1 &
    echo "app launching — window appears after compile (logs: $LOGDIR/tauri.log)"
  fi
}

do_stop() {
  echo "stopping app..."
  pkill -f "target/debug/desktop" 2>/dev/null || true
  pkill -f "tauri dev"            2>/dev/null || true
  sleep 0.5
  pkill -9 -f "target/debug/desktop" 2>/dev/null || true

  echo "unloading launchd agents (sidecar + hub stay down until next start)..."
  bootout_agent "$SIDECAR_PLIST" "$SIDECAR_LABEL"
  bootout_agent "$HUB_PLIST"     "$HUB_LABEL"

  echo "stopped."
}

do_restart() {
  echo "restarting sidecar..."
  launchctl kickstart -k "$DOMAIN/$SIDECAR_LABEL" &>/dev/null || {
    echo "sidecar agent not loaded — run: agentic-gui install"; exit 1
  }

  echo "restarting hub..."
  launchctl kickstart -k "$DOMAIN/$HUB_LABEL" &>/dev/null || true

  # Wait for sidecar.
  echo -n "waiting for sidecar"
  for _ in $(seq 1 30); do
    if curl -s -m 1 http://localhost:5130/api/health >/dev/null 2>&1; then
      echo " ✓"; break
    fi
    echo -n "."; sleep 0.5
  done
}

do_status() {
  echo "── Services ──────────────────────────────────"
  if curl -s -m 2 http://localhost:5130/api/health >/dev/null 2>&1; then
    echo "sidecar:  ● running on :5130"
  else
    echo "sidecar:  ○ not running"
  fi

  if curl -s -m 2 http://localhost:8085/api/cards >/dev/null 2>&1; then
    echo "hub:      ● running on :8085"
  else
    echo "hub:      ○ not running"
  fi

  if pgrep -f "target/debug/desktop" >/dev/null 2>&1; then
    echo "app:      ● running"
  else
    echo "app:      ○ not running"
  fi

  echo ""
  echo "── launchd agents ────────────────────────────"
  for label in "$SIDECAR_LABEL" "$HUB_LABEL"; do
    if agent_loaded "$label"; then
      echo "$label: loaded (auto-restart enabled)"
    else
      echo "$label: NOT loaded  ← run: agentic-gui install"
    fi
  done
}

# ── dispatch ─────────────────────────────────────────────────────────────────

case "${1:-start}" in
  install) do_install ;;
  start)   do_start   ;;
  stop)    do_stop    ;;
  restart) do_restart ;;
  status)  do_status  ;;
  *)
    echo "usage: agentic-gui [install|start|stop|restart|status]"
    exit 1
    ;;
esac
