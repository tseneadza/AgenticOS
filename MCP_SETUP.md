# AgenticOS MCP Server Setup

**Status:** ✅ Ready to register (one-time setup, ~5 minutes)

This MCP server lets Claude run build/test commands directly on your Mac without approval dialogs.

---

## What This Server Provides

Claude can now run:
- ✅ `run_tests` — Run full test suite (238 tests)
- ✅ `build_app` — Build Tauri app for distribution
- ✅ `build_debug` — Build debug bundle locally
- ✅ `dev_server` — Start dev server with hot reload
- ✅ `verify_build` — Quick build verification
- ✅ `git_status` — Check uncommitted changes
- ✅ `git_log_recent` — View last 20 commits
- ✅ `check_components` — List all extracted components
- ✅ `count_lines` — Count lines per component file

---

## How to Register (Cowork Mode)

### Step 1: Open Cowork Settings
1. Click ⚙️ (Settings) in Cowork toolbar
2. Navigate to **Capabilities** → **MCP Servers**

### Step 2: Add MCP Server

Choose one of these options:

#### Option A: Command-based (Recommended)
```
Name: agentiços-cli
Type: Command
Command: python3 /Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py
```

#### Option B: Using Node (if you prefer)
```
Name: agentiços-cli
Type: Node Package
Package: agentiços-cli
```

#### Option C: Using Docker (Advanced)
```
Name: agentiços-cli
Type: Docker
Image: agentiços:latest
```

### Step 3: Test Connection
After registering, ask Claude:
> "Run the check_components tool to verify the MCP server is working"

Claude should respond with a list of 13 components.

---

## What Claude Can Do Now

### Example 1: Run Tests
```
User: Run the test suite and tell me if all 238 tests pass
Claude: (runs tests automatically, reports results)
```

### Example 2: Build & Verify
```
User: Build the app and verify it compiles
Claude: (runs build_debug, checks for errors, reports status)
```

### Example 3: Check Status
```
User: Is there anything uncommitted in git?
Claude: (runs git_status, shows any uncommitted changes)
```

### Example 4: Multi-Step Workflows
```
User: Run tests, then build debug bundle, then show me component count
Claude: (executes all three commands in sequence, reports results)
```

---

## Server Code Reference

**Location:** `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`

**Available Functions:**
- `run_tests()` — Full test suite
- `run_tests_watch()` — Tests in watch mode (interactive)
- `build_app()` — Production build
- `build_debug()` — Debug build
- `dev_server()` — Dev server with hot reload
- `verify_build()` — Quick verification
- `git_status()` — Git status
- `git_log_recent()` — Recent commits
- `check_components()` — List components
- `count_lines()` — Count lines per file

Each function returns `{success, stdout, stderr, exit_code}`.

---

## Troubleshooting

### "Server not found"
- Make sure file path is correct: `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`
- Check that Python 3 is installed: `python3 --version`
- Restart Cowork after registering

### "Command timed out"
- Build/test commands can take 1-2 minutes
- Server has 5-minute timeout limit (can increase if needed)

### "Permission denied"
- Make sure the script has execute permissions: `chmod +x mcp_server.py`
- Or run via python3 explicitly (which the config does)

### "Path not found"
- Server assumes project root is `/Users/tonyseneadza/Codehome/AgenticOS`
- Edit the `PROJECT_ROOT` variable in `mcp_server.py` if you moved it

---

## Future Enhancements

Once registered and working, we can add:
- [ ] `open_app` — Launch the Tauri app directly
- [ ] `screenshot` — Take screenshot of running app
- [ ] `deploy` — Deploy to production
- [ ] `sync_github` — Push/pull from GitHub
- [ ] `restart_sidecar` — Restart backend server
- [ ] `profiler` — Run performance profiler

---

## Quick Setup Checklist

- [ ] File exists: `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`
- [ ] Python 3 installed: `python3 --version`
- [ ] Cowork Settings → Capabilities open
- [ ] Add MCP Server registration (copy command above)
- [ ] Test: Ask Claude to run `check_components`
- [ ] Verify: Should see 13 components listed

**Estimated time:** 5 minutes  
**Difficulty:** Easy (copy/paste)  
**Value:** 10x productivity boost for Claude automation

---

## After Registration: Next Session

Once registered, future sessions can:
- Automatically run tests before each task
- Build and verify the app without asking
- Check git status and report uncommitted changes
- Count components and measure progress
- Run complex multi-step workflows instantly

No approval dialogs, no manual scripts—just Claude doing the work.

**Ready to set this up?** Tell me when you've registered it in Cowork Settings, and I'll verify it works! 🚀
