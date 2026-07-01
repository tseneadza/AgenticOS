---
name: agentic-mcp-tools
description: |
  Run AgenticOS build, test, and git commands directly without leaving Claude. Use this skill whenever working on AgenticOS and you need to:
  - Execute the test suite (npm test) to verify Phase 6+ components
  - Build the Tauri desktop app (debug or production)
  - Commit and push changes to GitHub via git
  - Check project status (git history, components, code metrics)
  - Verify builds with one command
  
  This skill provides direct access to the MCP server at /Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py, which orchestrates build, test, and git operations without manual terminal commands. All git operations use SSH authentication (no credentials stored).
---

# AgenticOS MCP Tools

## Overview

The AgenticOS project includes a custom MCP (Model Context Protocol) server that encapsulates common build, test, and deployment operations. This skill exposes **13 tools** for managing the desktop app (Tauri-based React frontend + Rust backend) and git workflow.

**MCP Location:** `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`  
**Authentication:** SSH keys from `~/.ssh/` (no credentials in code)

---

## All 13 Available Tools

### Build & Test Tools (5)

#### `run_tests`
Run the full test suite (Phase 6: 238 unit tests + Phase 7: integration tests)
- **Output:** Test results, pass/fail count, coverage metrics
- **Use when:** Verifying components work, checking for regressions
- **Example:** After refactoring a component, verify tests still pass

#### `run_tests_watch`
Run tests in interactive watch mode for development
- **Output:** Live test output, watches for file changes
- **Use when:** Debugging failing tests iteratively
- **Note:** Runs in background; Ctrl+C to stop

#### `build_app`
Build production Tauri bundle (`npm run build`)
- **Output:** Build logs, success/failure status, bundle location
- **Use when:** Preparing a release or final verification
- **Example:** Before shipping to /Applications

#### `build_debug`
Build debug bundle for local testing
- **Output:** Build logs, path to debug .app bundle
- **Use when:** Testing the GUI without installing to /Applications
- **Example:** Quick verification before submitting changes

#### `verify_build`
Quick build verification using `build-and-verify.sh`
- **Output:** Pass/fail summary with detailed logs
- **Use when:** CI-like validation before commits
- **Example:** One-command verification of project health

### Git Tools (5)

#### `git_status`
Show current git status (short format)
- **Output:** Modified files, untracked files, branch info
- **Use when:** Checking what's uncommitted before work
- **Example:** Verify clean working directory before starting

#### `git_log_recent`
Show last 20 commits
- **Output:** Commit hashes, authors, messages
- **Use when:** Reviewing recent history or finding a specific commit
- **Example:** Track when features were added

#### `git_add [pattern]`
**NEW:** Stage files for commit using `git add`
- **Parameters:**
  - `pattern` (optional, default: ".") — File pattern to stage
  - Examples: "." (all), "docs/" (directory), "src/components/Button.jsx" (specific file)
- **Output:** Success/failure, git response
- **Use when:** Staging changes before commit
- **Example:** Stage only documentation changes with `git_add "docs/"`

#### `git_commit <message>`
**NEW:** Create a commit with the given message
- **Parameters:**
  - `message` (required) — Commit message (quotes auto-escaped)
- **Output:** Success/failure, commit hash
- **Use when:** Saving staged changes with a description
- **Example:** `git_commit "Phase 7: Add 98 integration tests"`

#### `git_push [remote] [branch]`
**NEW:** Push commits to remote repository
- **Parameters:**
  - `remote` (optional, default: "origin") — Remote name (origin, upstream, etc.)
  - `branch` (optional) — Branch name (if omitted, pushes current branch)
- **Output:** Success/failure, push logs
- **Use when:** Sending commits to GitHub
- **Authentication:** Uses your SSH key from ~/.ssh/ (no password needed)
- **Example:** `git_push origin main` or `git_push` (current branch)

### Project Introspection Tools (3)

#### `check_components`
List all extracted React components
- **Output:** Component names (sorted alphabetically), total count
- **Use when:** Verifying Phase 6 component structure
- **Example:** Confirm all 13 components exist after refactor

#### `count_lines`
Count lines of code in each component file
- **Output:** File names with line counts
- **Use when:** Measuring code metrics or component complexity
- **Example:** Identify bloated components that need splitting

#### CLI Reference

All tools are invoked via command line:
```bash
python /Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py <tool_name> [args]
```

**Response format:** JSON with `success`, `stdout`, `stderr`, `exit_code`

---

## Common Workflows

### 1. Verify Phase 6 Unit Tests Pass
```
1. Call: run_tests
2. Parse output for "238 tests passed"
3. If any fail, identify which component broke
4. Fix and repeat
```

### 2. Commit and Push Changes to GitHub
```
1. Call: git_status (verify what changed)
2. Call: git_add "." (stage all changes)
3. Call: git_commit "descriptive message"
4. Call: git_push origin main (push to GitHub)
```

### 3. Build & Test Release
```
1. Call: verify_build (quick health check)
2. Call: build_app (create production bundle)
3. Check stdout for /Applications path
4. Verify .app exists in Finder
```

### 4. Check Project State Before Starting Work
```
1. Call: git_status (see uncommitted changes)
2. Call: check_components (verify Phase 6 structure)
3. Call: count_lines (measure component sizes)
```

### 5. Run Integration Tests (Phase 7)
```
1. Call: run_tests (runs all 238 unit + 50+ integration tests)
2. Check for >80% coverage maintained
3. If failed, review test output for specific assertions
```

---

## Security & Authentication

### Git Push Security ✅

- **SSH Keys:** Uses your existing `~/.ssh/id_ed25519` or `id_rsa`
- **No Credentials Stored:** GitHub token/password NOT in code
- **No Passwords Passed:** SSH key automatically handles authentication
- **Safe for Claude:** Credentials don't leak to Claude's API (stay local on Mac)

### If SSH Key Needs Setup

If git push fails with auth error:
```bash
# Check if you have an SSH key
ls -la ~/.ssh/

# If not, create one (follow prompts)
ssh-keygen -t ed25519 -C "your-email@example.com"

# Add public key to GitHub
cat ~/.ssh/id_ed25519.pub
# Copy output, go to GitHub Settings > SSH Keys > Add key
```

---

## Edge Cases & Troubleshooting

### Build Fails with "icon.icns not found"
- Run `npm run tauri icon src-tauri/icons/icon.png` (regenerates icons)
- See CLAUDE.md for full icon handling rules

### Tests Fail with "Cannot find module"
- Run `npm install` in gui/desktop
- Check package.json for missing dependencies

### Git Push Fails with "Permission denied"
- Verify SSH key added to GitHub (Settings > SSH Keys)
- Run `ssh -T git@github.com` to test connection

### Changes Don't Appear After Commit
- Verify commit succeeded (look for commit hash in output)
- Run `git_log_recent` to confirm commit exists
- Verify push succeeded (no errors in output)

---

## When NOT to Use This Skill

- **Interactive Debugging:** Use `npm run tauri dev` in Terminal for live debugging
- **File Editing:** Use Read/Write/Edit tools for file operations
- **Complex Git Workflows:** For rebases, merges, or cherry-picks, use Terminal/Git directly
- **Component Development:** For writing new React components, use REACT_COMPONENT_TESTING.md patterns

---

## Integration with AgenticOS Workflow

**Pairs with these docs:**
- `CLAUDE.md` — Project rules (icon handling, Tauri build caveats)
- `CONTINUATION.md` — Session memory and current phase status
- `TESTING_GUIDE.md` — Understand Phase 6 test patterns
- `PHASE7_INTEGRATION_STRATEGY.md` — Integration test coverage details

**Phase context:**
- Phase 6: 13 components, 238 unit tests ✅
- Phase 7: 98 integration tests ✅
- Phase 8+: Polish, performance, additional features

---

## Example Commands

### Run all tests
> "Run the full test suite and tell me if all tests pass"

### Commit and push changes
> "Stage all changes, commit with message 'Phase 7 integration tests complete', and push to main"

### Check what changed
> "Show me the git status and list all components"

### Build and verify
> "Run build verification then build the debug app"

### Review recent commits
> "Show the last 20 commits to see what's been done"

---

## FAQ

**Q: Does this store my GitHub password?**  
A: No. It uses SSH keys which are already on your system. No passwords or tokens stored in the code.

**Q: Can I push to different branches?**  
A: Yes. Use `git_push origin branch-name` to push to any branch.

**Q: What happens if a command times out?**  
A: All commands have a 5-minute timeout. Long builds will return an error.

**Q: Can I run tests in watch mode from Claude?**  
A: Yes, but note that watch mode is interactive—you'll see logs but won't see prompts to filter tests.

**Q: What if I need to revert a commit?**  
A: This skill doesn't include git revert. Use Terminal or pass a `git revert` command via chat if needed.

---

## Output Format

All tools return JSON:

```json
{
  "success": true,
  "stdout": "command output here",
  "stderr": "any errors here",
  "exit_code": 0
}
```

For introspection tools (check_components, count_lines):
```json
{
  "success": true,
  "components": ["Button", "Card", ...],
  "count": 13,
  "files": {
    "Button.jsx": 120,
    "Card.jsx": 95,
    ...
  }
}
```

---

## Reporting Issues

If a tool fails:
1. **Check the stderr** in the JSON output
2. **Run git_status** to see current state
3. **Review CLAUDE.md** for project-specific rules (icons, Tauri build, tray)
4. **Run verify_build** for overall health

---

## Recent Updates (Phase 7+)

- ✅ Added `git_add`, `git_commit`, `git_push` tools
- ✅ SSH authentication for secure commits
- ✅ Integration with Phase 7 (98 integration tests)
- ✅ Support for 238 unit tests + phase-specific integration tests
