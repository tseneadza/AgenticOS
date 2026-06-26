# Continuation note

**2026-06-25 (latest) — WorkflowsWorkspace committed, env-vars diagnosed, raw notes processed**

## ✅ State now
- Branch `main`, even with `origin/main`. Working tree **clean**.
- Latest commit: `6121875` feat(workflows): WorkflowsWorkspace, SkippedRun pattern, llm env-isolation fix
- **Sidecar healthy** on port 5130, MySQL-backed.
- **No pending changes** — all pre-session work committed and pushed.

## 🔍 Key discovery this session
The running sidecar inherited `ANTHROPIC_BASE_URL=http://localhost:12434` and
`ANTHROPIC_AUTH_TOKEN=ollama` from Claude Code's environment (Claude Code routes
its own SDK calls through a local Ollama proxy on port 12434 — separate from the
Ollama.app instance on 11434). This made the env look like local-LLM-only setup.

**Resolution already in place:** `core/llm.py` `_isolated_anthropic_env()` strips
those vars during both client construction AND `invoke()` time (the call-time fix
was the pre-session commit above). Cloud Anthropic calls go to `api.anthropic.com`
correctly regardless of what the shell environment holds.

Two Ollama instances running:
- `/Applications/Ollama.app` → port 11434 (used by AgenticOS `ollama` provider)
- `/usr/local/bin/ollama` → port 12434 (used by Claude Code only)

## ▶ NEXT SESSION — START HERE
**Goal: UI/design overhaul — make AgenticOS more aesthetically pleasing.**

1. **Take a screenshot** of the running GUI first:
   - `MacOS-MCP:Snapshot` or `Claude in Chrome` to capture current state
   - Or open `http://localhost:5173` in the browser (Vite dev server) and screenshot
2. **Read the frontend-design skill** at `/mnt/skills/public/frontend-design/SKILL.md`
3. **Design targets** (from Tony's intent):
   - Overall aesthetic uplift — current look is functional but utilitarian
   - Consider: typography, color palette, spacing rhythm, component polish
   - Nav/sidebar visual hierarchy
   - Dashboard card design
   - WebNewsView article cards
4. **Optional data copy** (carry-forward): `./.venv/bin/python scripts/migrate_state_db_to_mysql.py`
   to bring 49/11 old rows from `data/state.db.bak` into MySQL.
5. **Clean up stale branches** (carry-forward): `phase2-gui-sprint2`, `phase2-gui-sprint1`,
   `phase2-gui-sidebar` (all merged).

## Carry-forward gotchas (unchanged)
- `agents/brain2_agent.py` `collect_session_summary()` imports a `Memory` class
  that never existed in `memory.py` — pre-existing latent ImportError, untouched.
- MySQL creds: `~/.agentic-os/.env` (`MYSQL_DB=agenticos`; case-insensitive on macOS).
- Runs REQUIRE MySQL up (no offline SQLite fallback). MySQL ≥ 8.0.19 (on 9.4.0).
- Adding a script to the desktop Scripts view: add to `app.json` `scripts[]`,
  then `POST http://localhost:8085/api/discover`.
- Two Ollama instances are normal — don't kill the 12434 one, Claude Code needs it.

