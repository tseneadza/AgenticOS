#!/bin/bash
# Setup script for MySQL automatic health check and recovery
# Run this once to set up launchd service for automatic MySQL recovery
# Usage: bash ./setup-mysql-recovery.sh

set -e

echo "═══════════════════════════════════════════════════════════"
echo "AgenticOS MySQL Health Check Setup"
echo "═══════════════════════════════════════════════════════════"
echo ""

PLIST_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/mysql-health-check.plist"
PLIST_DST="${HOME}/Library/LaunchAgents/com.tonyseneadza.mysql-health-check.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Step 1: Creating LaunchAgents directory..."
mkdir -p "${HOME}/Library/LaunchAgents" || true
echo "✓ Directory created/verified"
echo ""

echo "Step 2: Copying launchd plist..."
if [ -f "$PLIST_SRC" ]; then
    cp "$PLIST_SRC" "$PLIST_DST"
    chmod 644 "$PLIST_DST"
    echo "✓ Plist installed to: $PLIST_DST"
else
    echo "✗ Error: Plist file not found at $PLIST_SRC"
    exit 1
fi
echo ""

echo "Step 3: Fixing MySQL data directory permissions..."
if [ -d "/usr/local/mysql/data" ]; then
    echo "  Attempting to fix ownership (may need sudo)..."
    sudo chown -R _mysql:_mysql /usr/local/mysql/data || echo "  ⚠ Ownership change may need manual intervention"
    sudo chmod 755 /usr/local/mysql/data || echo "  ⚠ Permission change may need manual intervention"
    echo "✓ MySQL data directory permissions updated"
else
    echo "⚠ MySQL data directory not found at /usr/local/mysql/data"
fi
echo ""

echo "Step 4: Unloading any existing health check service..."
launchctl unload "$PLIST_DST" 2>/dev/null || true
echo "✓ Previous service unloaded"
echo ""

echo "Step 5: Loading launchd service..."
if launchctl load "$PLIST_DST"; then
    echo "✓ Launchd service loaded successfully"
    echo "  Service will:"
    echo "  - Run health check every 5 minutes (300 seconds)"
    echo "  - Auto-start MySQL if it crashes"
    echo "  - Run at boot time"
else
    echo "✗ Failed to load launchd service"
    exit 1
fi
echo ""

echo "Step 6: Verifying service installation..."
if launchctl list | grep -q "com.tonyseneadza.mysql-health-check"; then
    echo "✓ Service is installed and active"
else
    echo "⚠ Service may not be active yet (try restarting)"
fi
echo ""

echo "Step 7: Running initial health check..."
if bash "${SCRIPT_DIR}/check_mysql_health.sh"; then
    echo "✓ Initial health check passed"
else
    echo "⚠ Initial health check detected issue (this is expected if MySQL was down)"
fi
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "Setup Complete!"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Logs:"
echo "  Health check logs: ${HOME}/.agentic-os/mysql_health.log"
echo "  Launchd logs: ${HOME}/Library/Logs/mysql-health-check.log"
echo ""
echo "To check service status:"
echo "  launchctl list | grep mysql-health-check"
echo ""
echo "To manually run health check:"
echo "  bash ${SCRIPT_DIR}/check_mysql_health.sh"
echo ""
echo "To uninstall service:"
echo "  launchctl unload ${PLIST_DST}"
echo "  rm ${PLIST_DST}"
