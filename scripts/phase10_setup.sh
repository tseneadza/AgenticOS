#!/bin/bash
# Phase 10 Setup — Install dependencies and verify Ollama

set -e

PROJECT_DIR="/Users/tonyseneadza/Codehome/AgenticOS"
VENV_DIR="$PROJECT_DIR/.venv"

echo "🚀 Phase 10 Setup — Governing Agent (NF-3)"
echo "==========================================="
echo ""

# Step 1: Verify Python venv
echo "1️⃣  Checking Python venv..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    echo "❌ venv not found at $VENV_DIR"
    echo "   Creating venv..."
    cd "$PROJECT_DIR"
    python3 -m venv .venv
    echo "✅ venv created"
else
    echo "✅ venv found"
fi

# Step 2: Install dependencies
echo ""
echo "2️⃣  Installing Phase 10 dependencies..."
"$VENV_DIR/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt" 2>&1
echo "✅ Dependencies installed"

# Verify key packages
echo ""
echo "3️⃣  Verifying LangChain packages..."
"$VENV_DIR/bin/python" -c "import langchain; import langchain_anthropic; import langchain_ollama; print('✅ LangChain packages ready')" 2>&1

# Step 3: Check Ollama
echo ""
echo "4️⃣  Checking Ollama service..."
if nc -z localhost 11434 2>/dev/null; then
    echo "✅ Ollama running on :11434"

    # Check installed models
    echo ""
    echo "5️⃣  Installed Ollama models:"
    curl -s http://localhost:11434/api/tags | python3 -m json.tool | grep '"name"' | head -10
else
    echo "⚠️  Ollama not running on :11434"
    echo "   Start Ollama manually: ollama serve"
    echo "   Then pull models:"
    echo "   - ollama pull qwen2.5:7b-instruct"
    echo "   - ollama pull llama2:7b"
fi

# Step 4: Register port
echo ""
echo "6️⃣  Registering :11434 in PORT_ASSIGNMENTS.md..."
if grep -q "11434.*Ollama" "$PROJECT_DIR/hub/docs/PORT_ASSIGNMENTS.md" 2>/dev/null; then
    echo "✅ Port 11434 already registered"
else
    echo "⚠️  Need to add to PORT_ASSIGNMENTS.md: TR-10 Ollama service :11434"
fi

# Step 5: Create core/llm.py skeleton
echo ""
echo "7️⃣  Creating core/llm.py skeleton..."
CORE_DIR="$PROJECT_DIR/gui/sidecar"
if [ ! -d "$CORE_DIR" ]; then
    mkdir -p "$CORE_DIR"
fi

echo "✅ Phase 10 setup complete!"
echo ""
echo "Next steps:"
echo "1. Ensure Ollama is running: ollama serve"
echo "2. Pull models: ollama pull qwen2.5:7b-instruct && ollama pull llama2:7b"
echo "3. Verify LLM layer: FR-52 implementation"
echo ""
