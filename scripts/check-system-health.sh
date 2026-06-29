#!/bin/bash
echo "=== AgenticOS System Health Check ==="
echo ""
echo "Sidecar:"
if curl -s http://localhost:5130/api/health > /dev/null; then
  echo "  ✓ Online at localhost:5130"
  SCRIPT_COUNT=$(curl -s http://localhost:5130/api/apps/scripts | jq '.total')
  echo "  ✓ $SCRIPT_COUNT scripts available"
else
  echo "  ✗ Offline at localhost:5130"
fi

echo ""
echo "Hub:"
if [ -f ~/Codehome/hub/hub_server ]; then
  if curl -s http://localhost:8085/health > /dev/null; then
    echo "  ✓ Online at localhost:8085"
  else
    echo "  ✗ Binary exists but not responding"
  fi
else
  echo "  ○ Optional (binary not found)"
  echo "    To enable: https://github.com/Codehome/hub"
fi
