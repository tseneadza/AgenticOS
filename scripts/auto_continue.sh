#!/bin/bash
# auto_continue.sh — unattended Phase-work continuation via Claude Code headless.
#
# Installed by scripts/setup-auto-continue.sh as launchd job
# com.agenticos.auto-continue (default: every 5 hours — the Claude usage
# window). Each run points Claude Code at docs/CONTINUATION.md and lets it
# work one bounded increment, then checkpoint + commit + push per CLAUDE.md.
#
# Posture: FULL AUTO (--dangerously-skip-permissions) — Tony's explicit
# choice, 2026-07-11. Guardrails: repo-scoped prompt, turn cap, lock file
# (no overlapping runs), kill switch, everything committed so git is the
# recovery net.
#
# KILL SWITCH:  touch ~/Codehome/AgenticOS/data/.auto_continue_off
# UNINSTALL:    launchctl unload ~/Library/LaunchAgents/com.agenticos.auto-continue.plist
# LOGS:         ~/.agentic-os/auto_continue.log
set -u

REPO="$HOME/Codehome/AgenticOS"
LOG_DIR="$HOME/.agentic-os"
LOG="$LOG_DIR/auto_continue.log"
LOCK_DIR="$LOG_DIR/auto_continue.lock"
KILL_SWITCH="$REPO/data/.auto_continue_off"
MAX_TURNS=100

mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1
echo "==================================================================="
echo "auto_continue run: $(date '+%Y-%m-%d %H:%M:%S %Z')"

# --- kill switch -----------------------------------------------------------
if [ -e "$KILL_SWITCH" ]; then
  echo "kill switch present ($KILL_SWITCH) — skipping run."
  exit 0
fi

# --- single-flight lock (mkdir is atomic) ----------------------------------
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "another run holds the lock ($LOCK_DIR) — skipping."
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT INT TERM

# --- resolve the claude binary (launchd has a minimal PATH) -----------------
CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [ -z "$CLAUDE_BIN" ]; then
  for candidate in "$HOME"/.local/share/pi-node/*/bin/claude \
                   "$HOME/.local/bin/claude" \
                   /opt/homebrew/bin/claude /usr/local/bin/claude; do
    if [ -x "$candidate" ]; then CLAUDE_BIN="$candidate"; break; fi
  done
fi
if [ -z "$CLAUDE_BIN" ]; then
  echo "ERROR: claude binary not found — aborting."
  exit 1
fi
echo "using claude: $CLAUDE_BIN ($("$CLAUDE_BIN" --version 2>/dev/null))"

cd "$REPO" || { echo "ERROR: repo missing at $REPO"; exit 1; }

# --- the continuation prompt ------------------------------------------------
PROMPT=$(cat <<'EOP'
You are an unattended continuation session for the AgenticOS repo. Follow
CLAUDE.md strictly (session-budget cycle, glossary rule, docs same-change
policy, ALWAYS commit AND push at session end).

1. Read docs/CONTINUATION.md first. Identify the current phase and its next
   step (currently the Phase 15 / OSA System MCP series).
2. Read skills/osa-system-mcp/SKILL.md and docs/PHASE15_OSA_SYSTEM_MCP.md
   before touching tools/system/.
3. Work ONE bounded increment (e.g. one sub-phase or one coherent slice of
   one). Prefer the smallest diff that holds. Run the relevant pytest
   subset, then the full backend suite; fix regressions before proceeding.
4. HARD LIMITS for unattended runs:
   - Do NOT flip system_mcp.mode to "effect" (that is a human decision).
   - Do NOT grant, script, or work around macOS TCC permissions (FDA /
     Automation) — if a step needs them, write the code with mocked tests,
     flag the on-device grant in CONTINUATION.md, and move on.
   - Do NOT send real iMessages or emails, ever.
   - Do NOT restart the sidecar if Tony may be using it; note it instead.
5. Checkpoint: update docs/CONTINUATION.md (what shipped, live state, exact
   RESUME HERE), update CHANGELOG/roadmap/GLOSSARY in the same change, then
   commit with a clear message and PUSH.
6. If NO automatable Phase 15 work remains (15a-15e done or blocked on
   human-only steps), write that conclusion to docs/CONTINUATION.md, commit,
   push, and then create the file data/.auto_continue_off so these runs stop.
EOP
)

echo "--- claude run start ---"
"$CLAUDE_BIN" -p "$PROMPT" --dangerously-skip-permissions --max-turns "$MAX_TURNS"
RC=$?
echo "--- claude run end (exit $RC) ---"

# Safety net: never leave the tree dirty even if the run died mid-flight.
if [ -n "$(git status --porcelain)" ]; then
  echo "tree dirty after run — checkpoint-committing per CLAUDE.md rule 4"
  git add -A
  git commit -m "chore(auto-continue): checkpoint uncommitted work from unattended run $(date '+%Y-%m-%d %H:%M')"
  git push origin HEAD || echo "WARN: push failed (offline?)"
fi
exit "$RC"
