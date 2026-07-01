# AgenticOS MCP Server API Reference

## Server Location
- **Path:** `/Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py`
- **Project Root:** `/Users/tonyseneadza/Codehome/AgenticOS`
- **GUI Desktop:** `/Users/tonyseneadza/Codehome/AgenticOS/gui/desktop`

## Invocation

```bash
python /Users/tonyseneadza/Codehome/AgenticOS/mcp_server.py <tool_name> [args]
```

## Response Format

All tools return JSON:

```json
{
  "success": true|false,
  "stdout": "command output",
  "stderr": "error output (if any)",
  "exit_code": 0
}
```

Special responses (check_components, count_lines):

```json
{
  "success": true,
  "components": ["Component1", "Component2", ...],
  "count": 13
}
```

## Tool Specifications

### run_tests

**Purpose:** Execute full test suite

**Command:**
```bash
python mcp_server.py run_tests
```

**Behavior:**
- Runs `npm test -- --run` in gui/desktop
- Captures all test output
- Returns exit code 0 on success

**Timeout:** 5 minutes

**Expected Output Contains:**
- Test file names
- Pass/fail counts
- Coverage summary

---

### run_tests_watch

**Purpose:** Run tests in watch mode

**Command:**
```bash
python mcp_server.py run_tests_watch
```

**Behavior:**
- Runs `npm test` (watch mode)
- Does NOT capture output (interactive)
- Returns immediately (doesn't block)

**Use Case:** Development iteration

---

### build_app

**Purpose:** Build production Tauri bundle

**Command:**
```bash
python mcp_server.py build_app
```

**Behavior:**
- Runs `npm run build` in gui/desktop
- Captures build logs
- Creates optimized bundle

**Output Contains:**
- Build steps (webpack, native compilation)
- Final bundle location
- Size information

**Success Indicators:**
- exit_code: 0
- success: true
- stdout contains bundle path

---

### build_debug

**Purpose:** Build debug bundle for testing

**Command:**
```bash
python mcp_server.py build_debug
```

**Behavior:**
- Runs Tauri build with --debug flag
- Creates unoptimized bundle for faster compilation
- Includes debug symbols

**Output Contains:**
- Debug build path (typically src-tauri/target/debug/bundle/macos/Agentic\ OS.app)
- Build time
- Binary size

---

### dev_server

**Purpose:** Start dev server with hot reload

**Command:**
```bash
python mcp_server.py dev_server
```

**Behavior:**
- Runs `npm run tauri dev`
- Does NOT capture output (interactive)
- Returns immediately

**Output:**
- Vite server startup messages
- HMR (Hot Module Reload) status

---

### verify_build

**Purpose:** Quick build verification

**Command:**
```bash
python mcp_server.py verify_build
```

**Behavior:**
- Runs build-and-verify.sh script
- Performs health checks
- Returns overall build status

**Checks:**
- Rust environment
- Node dependencies
- Build artifacts
- Component count

---

### git_status

**Purpose:** Show git status

**Command:**
```bash
python mcp_server.py git_status
```

**Output Format:**
```
 M gui/desktop/src/components/Button.jsx
?? docs/new-file.md
On branch main
```

---

### git_log_recent

**Purpose:** Show recent commits

**Command:**
```bash
python mcp_server.py git_log_recent
```

**Output Format:**
```
abc1234 (HEAD -> main) Phase 7: Add integration tests
def5678 Phase 6: Extract Button component
...
```

**Shows:** Last 20 commits

---

### git_add

**Purpose:** Stage files for commit

**Command:**
```bash
python mcp_server.py git_add [pattern]
```

**Parameters:**
- `pattern` (optional, default: ".")
  - "." → all changes
  - "docs/" → directory
  - "src/components/Button.jsx" → specific file

**Examples:**
```bash
# Stage all
python mcp_server.py git_add .

# Stage docs only
python mcp_server.py git_add docs/

# Stage specific file
python mcp_server.py git_add src/components/Button.jsx
```

**Output:**
```json
{
  "success": true,
  "stdout": "",
  "stderr": "",
  "exit_code": 0
}
```

(git add is silent on success)

---

### git_commit

**Purpose:** Create a commit

**Command:**
```bash
python mcp_server.py git_commit "<message>"
```

**Parameters:**
- `message` (required) — Commit message
  - Quotes are auto-escaped
  - Single or double quotes both work

**Examples:**
```bash
python mcp_server.py git_commit "Phase 7: Add integration tests"
python mcp_server.py git_commit "Fix: Component rendering bug"
```

**Output:**
```json
{
  "success": true,
  "stdout": "[main abc1234] Phase 7: Add integration tests",
  "stderr": "",
  "exit_code": 0
}
```

**Success Indicators:**
- exit_code: 0
- stdout contains commit hash

---

### git_push

**Purpose:** Push commits to remote

**Command:**
```bash
python mcp_server.py git_push [remote] [branch]
```

**Parameters:**
- `remote` (optional, default: "origin")
- `branch` (optional, if omitted pushes current branch)

**Examples:**
```bash
# Push current branch to origin
python mcp_server.py git_push

# Push to specific branch
python mcp_server.py git_push origin main

# Push to different remote
python mcp_server.py git_push upstream develop
```

**Authentication:**
- Uses SSH key from ~/.ssh/id_ed25519 or id_rsa
- No password prompt (key-based auth)
- Fails gracefully if key not found

**Output:**
```json
{
  "success": true,
  "stdout": "Counting objects: 5, done...",
  "stderr": "",
  "exit_code": 0
}
```

**Common Errors:**
- `permission denied (publickey)` → SSH key not in GitHub
- `fatal: not a git repository` → CWD not in git repo
- `fatal: 'origin' does not appear to be a 'git' repository` → Invalid remote

---

### check_components

**Purpose:** List extracted React components

**Command:**
```bash
python mcp_server.py check_components
```

**Output:**
```json
{
  "success": true,
  "components": [
    "CallLogEntry",
    "EndpointListItem",
    "FilterBar",
    "GroupHeader",
    "MethodBadge",
    "ParamInput",
    "PathDisplay",
    "ResponseDisplay",
    "ScriptGroupHeader",
    "ScriptItem",
    "ScriptTypeBadge",
    "StatusIndicator",
    "TabSwitcher"
  ],
  "count": 13
}
```

**Source:** Scans `gui/desktop/src/components/*.jsx`

---

### count_lines

**Purpose:** Count lines in component files

**Command:**
```bash
python mcp_server.py count_lines
```

**Output:**
```json
{
  "success": true,
  "files": {
    "CallLogEntry.jsx": 100,
    "EndpointListItem.jsx": 77,
    "FilterBar.jsx": 40,
    "GroupHeader.jsx": 85,
    "MethodBadge.jsx": 40,
    "ParamInput.jsx": 110,
    "PathDisplay.jsx": 35,
    "ResponseDisplay.jsx": 70,
    "ScriptGroupHeader.jsx": 96,
    "ScriptItem.jsx": 88,
    "ScriptTypeBadge.jsx": 47,
    "StatusIndicator.jsx": 80,
    "TabSwitcher.jsx": 62
  }
}
```

**Total Lines:** Sum of all files ≈ 852 lines

---

## Error Handling

All commands implement consistent error handling:

```json
{
  "success": false,
  "error": "Command timed out after 5 minutes"
}
```

**Timeout:** 5 minutes per command
**Exceptions Caught:** subprocess errors, file not found, permission denied

---

## Common Workflows

### Run Tests and Commit Results

```bash
# 1. Run tests
python mcp_server.py run_tests

# 2. If all pass, commit
python mcp_server.py git_add .
python mcp_server.py git_commit "All tests passing"
python mcp_server.py git_push origin main
```

### Verify Build Before Release

```bash
# 1. Verify overall health
python mcp_server.py verify_build

# 2. Build for release
python mcp_server.py build_app

# 3. Confirm components
python mcp_server.py check_components
```

### Check Status Before Work

```bash
python mcp_server.py git_status
python mcp_server.py check_components
python mcp_server.py count_lines
```

---

## Implementation Details

- **Language:** Python 3
- **Shell:** /bin/bash (via subprocess.run)
- **Encoding:** UTF-8
- **Project Root:** Hardcoded to /Users/tonyseneadza/Codehome/AgenticOS
- **Timeout:** 300 seconds (5 minutes)
- **Capture Output:** True for most; False for interactive commands (dev_server, run_tests_watch)
