#!/bin/bash
# setup-auto-continue.sh — one-time install of the auto-continue launchd job.
# Mirrors the mysql-recovery setup pattern.
set -euo pipefail

REPO="$HOME/Codehome/AgenticOS"
PLIST_SRC="$REPO/scripts/com.agenticos.auto-continue.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.agenticos.auto-continue.plist"

chmod +x "$REPO/scripts/auto_continue.sh"
mkdir -p "$HOME/.agentic-os" "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# Reload cleanly if already present.
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "Installed + loaded: com.agenticos.auto-continue (every 5h)."
echo "  status:      launchctl list | grep auto-continue"
echo "  logs:        tail -f ~/.agentic-os/auto_continue.log"
echo "  pause:       touch $REPO/data/.auto_continue_off"
echo "  resume:      rm $REPO/data/.auto_continue_off"
echo "  run now:     launchctl start com.agenticos.auto-continue"
echo "  uninstall:   launchctl unload $PLIST_DST && rm $PLIST_DST"
