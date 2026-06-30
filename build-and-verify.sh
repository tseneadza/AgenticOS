#!/bin/bash
# Phase 6 Build & Verification Script
# Run this on your Mac to build and test the app after component extraction

set -e

echo "🔨 Phase 6: Build & Verification"
echo "=================================="
echo ""

cd /Users/tonyseneadza/Codehome/AgenticOS/gui/desktop

echo "Step 1: Run all tests..."
npm test -- --run 2>&1 | grep -E "Test Files|Tests|passed|failed" || echo "Tests completed"

echo ""
echo "Step 2: Build the app..."
npm run build

echo ""
echo "Step 3: Verify Tauri..."
npm run tauri -- info

echo ""
echo "✅ Build verification complete!"
echo ""
echo "Next: Run 'npm run tauri dev' to start the dev server"
