---
name: local-machine-access
description: |
  You have direct access to Tony's local Mac machine via multiple tools. Use this skill whenever the user asks you to interact with their computer, take screenshots, control applications, run shell commands, or access files on disk. This includes opening apps, clicking UI elements, capturing screen state, running builds, executing code, and managing the file system directly.
compatibility: macOS (Tony's personal MacBook Air), requires computer-use MCP for full access
---

# Local Machine Access

You have **direct programmatic access** to Tony's MacBook Air. This means you can not only read and write files, but actively control the computer—taking screenshots, clicking buttons, typing, running commands, and managing applications.

## Available Tools & Their Purposes

### 1. **File System Access** (Read, Write, Edit)
Access Tony's files directly on disk.

**Use for:**
- Reading files: `Read("/Users/tonyseneadza/Codehome/AgenticOS/some/file.py")`
- Writing new files: `Write("/path/to/file", "content")`
- Editing existing files: `Edit("/path/to/file", old_string, new_string)`

**Mounted folders:**
- `/Users/tonyseneadza/Codehome/AgenticOS` — Main AgenticOS project workspace
- `/Users/tonyseneadza/.agentic-os/` — Configuration and runtime data

**Key directories to know:**
```
~/Codehome/AgenticOS/
├── gui/                    # Tauri desktop app + sidecar
├── core/                   # Orchestration, agents, constitution
├── config/                 # YAML configs (workflows, constitution)
├── scripts/                # Setup and utility scripts
├── skills/                 # Reusable skill documentation (like this one)
└── docs/                   # CONTINUATION.md, roadmap, architecture

~/.agentic-os/
├── config.yaml             # User configuration
├── shell.log               # Shell event logs
├── diagnostics_cache.json  # Self-diagnostics output
└── mysql_health.log        # MySQL health check logs
```

### 2. **Shell Access** (mcp__MacOS-MCP__Shell or mcp__workspace__bash)
Run commands on the Mac directly.

**Use for:**
- Running builds: `npm run tauri dev`, `npm run build`
- Checking processes: `ps aux | grep mysql`
- File operations: `mkdir`, `chmod`, `rm`, etc.
- Installing packages: `brew install`, `npm install`, etc.
- Verifying system state: `ls -la`, `cat`, `grep`, etc.

**Limitations:**
- `sudo` commands may require password (will fail in automation)
- Some commands need `sudo` access that may not work in shell context

**Pattern for long-running commands:**
```bash
# Start in background with output capture
nohup <command> > /tmp/output.log 2>&1 &
sleep 2
# Check if running
ps aux | grep <process_name>
```

### 3. **Computer Control** (mcp__MacOS-MCP__* or mcp__computer-use__*)
Take screenshots, click UI, type, control applications, interact with GUI.

**Use for:**
- Taking screenshots: See current desktop state
- Opening applications: Launch Terminal, MySQL Workbench, Finder, etc.
- Clicking buttons: Navigate menus, press buttons, interact with dialogs
- Typing: Enter text into focused fields (password prompts, forms, etc.)
- Managing windows: Resize, move, switch between apps
- Keyboard shortcuts: Send Cmd+S, Cmd+Q, etc. (some require system permissions)

**Access flow:**
1. Call `request_access()` with list of app names (once per session start)
2. User approves in dialog
3. Use screenshot, click, type, etc. tools freely after approval

**Tier system** (important to understand):
- **Read tier** (Browsers): Can see in screenshots, but can't click or type
- **Click tier** (Terminal, IDEs): Can click, but not type (for security)
- **Full tier** (Most apps): Can do everything

### 4. **Application Management**
Open, switch between, and control macOS applications.

**Available apps on this machine:**
```
Agentic OS              # Main desktop app
Terminal               # Shell access
Finder                 # File manager
MySQLWorkbench         # Database management
VS Code                # Code editor
Cursor                 # AI code editor
Activity Monitor       # Process manager
System Settings        # System preferences
TextEdit               # Text editor
```

**Pattern:**
```python
# Open or bring to front
mcp__MacOS-MCP__App(name="Agentic OS", mode="launch")

# Switch to already-open app
mcp__MacOS-MCP__App(name="Terminal", mode="switch")
```

## Common Task Patterns

### Pattern 1: Verify Something on Disk

```python
# Read a config file
Read("/Users/tonyseneadza/.agentic-os/config.yaml")

# Check if something exists
Read("/Users/tonyseneadza/Codehome/AgenticOS/scripts/setup.sh")

# Grep for a pattern
Grep(pattern="mysql", path="/Users/tonyseneadza/Codehome/AgenticOS")
```

### Pattern 2: Check System State Without Screenshots

```bash
# Is MySQL running?
ps aux | grep mysqld | grep -v grep

# Is port 3306 listening?
lsof -i :3306

# What's in the home directory?
ls -la ~
```

### Pattern 3: Modify a File

```python
# Read it first (required)
Read("/Users/tonyseneadza/Codehome/AgenticOS/file.py")

# Then edit
Edit(
  file_path="/Users/tonyseneadza/Codehome/AgenticOS/file.py",
  old_string="# TODO: fix this",
  new_string="# Fixed!"
)

# Or create new
Write("/Users/tonyseneadza/Codehome/AgenticOS/new_file.py", "content")
```

### Pattern 4: Take a Screenshot & Interact

```python
# Request access first (once per session)
request_access(apps=["Agentic OS", "Terminal"])

# Take screenshot
screenshot()

# Click a button (use coordinates from screenshot)
left_click([100, 200])

# Type text
type("hello world")

# Use keyboard shortcuts
key("cmd+s")
```

### Pattern 5: Run a Build

```bash
cd /Users/tonyseneadza/Codehome/AgenticOS
npm run tauri dev
# or
npm run build
# or
.venv/bin/python -m pytest gui/sidecar/tests/ -v
```

### Pattern 6: Check Application State with Screenshots

```python
# First request access to the app
request_access(apps=["Agentic OS"])

# Take screenshot to see current state
screenshot()

# If something's wrong, navigate/fix it
left_click([coordinates])
type("input")
key("Return")

# Verify the change
screenshot()
```

## Special Capabilities

### Full Git Access
Can commit, push, branch locally:
```bash
cd ~/Codehome/AgenticOS
git status
git add .
git commit -m "message"
git push origin branch-name
```
SSH auth is configured, no credential entry needed.

### Python Execution
Can run Python scripts with access to project venv:
```bash
cd ~/Codehome/AgenticOS
.venv/bin/python script.py
.venv/bin/python -m pytest tests/
.venv/bin/python -m gui.sidecar
```

### NPM/Node
Can run npm commands from GUI directories:
```bash
cd ~/Codehome/AgenticOS/gui/desktop
npm install
npm run build
npm run tauri dev
```

### Database Access
MySQL is installed at `/usr/local/mysql/`:
```bash
/usr/local/mysql/bin/mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SELECT * FROM ..."
```

## Key Constraints & Patterns

### 1. **Request Access Each Session**
Computer-use tools need approval:
```python
request_access(apps=["App Name 1", "App Name 2"])
```

### 2. **Screenshots Show Filtered View**
Some apps (browsers, terminals, IDEs) don't render sensitive content in screenshots for security. In these cases, use shell commands directly instead of trying to read UI.

### 3. **Terminal is Click-Only** (Tier restrictions)
You can click buttons in Terminal, but can't type directly. Use shell commands via `bash` tool instead:
```python
# ✅ Works: shell command
bash_command("echo 'hello'")

# ❌ Doesn't work: typing in Terminal
type("echo 'hello'")  # Will error because Terminal is click-tier
```

### 4. **Coordinate System**
Screenshots return full-screen coordinates. When you click, use coordinates from the screenshot itself—no need to translate.

### 5. **File Paths**
Always use absolute paths starting with `/Users/tonyseneadza/`:
```python
Read("/Users/tonyseneadza/Codehome/AgenticOS/file.py")  # ✅
Read("~/Codehome/AgenticOS/file.py")                     # ❌ Won't work
Read("./file.py")                                        # ❌ Wrong path
```

## Related Skills & Tools

When working on AgenticOS, these skills are relevant:

- **mysql-recovery** — Diagnose and fix MySQL connection issues
- **agentic-mcp-tools** — Build, test, and git operations for AgenticOS
- **debug** — Structured debugging for errors and failures

## Session Continuity

Key state files for resuming work:
- `/Users/tonyseneadza/Codehome/AgenticOS/docs/CONTINUATION.md` — What was being worked on
- `/Users/tonyseneadza/.agentic-os/config.yaml` — User configuration
- Git log: `git log --oneline -10` for recent commits

## Example: Complete Workflow

Here's a full example of diagnosing an issue on Tony's machine:

```python
# 1. Check if MySQL is running
bash("ps aux | grep mysqld | grep -v grep")

# 2. Take a screenshot of the desktop
request_access(apps=["Agentic OS"])
screenshot()

# 3. Check application logs
Read("/Users/tonyseneadza/.agentic-os/diagnostics_cache.json")

# 4. Look for errors in code
Grep(pattern="error", path="/Users/tonyseneadza/Codehome/AgenticOS/gui/sidecar", type="py")

# 5. Fix something in a file
Read("/Users/tonyseneadza/Codehome/AgenticOS/file.py")
Edit(file_path="/Users/tonyseneadza/Codehome/AgenticOS/file.py", 
     old_string="broken code", 
     new_string="fixed code")

# 6. Run tests to verify
bash("cd /Users/tonyseneadza/Codehome/AgenticOS && .venv/bin/python -m pytest -v")

# 7. Commit changes
bash("""
cd /Users/tonyseneadza/Codehome/AgenticOS
git add .
git commit -m "Fixed the thing"
git push origin main
""")
```

## When NOT to Use This

- **Don't screenshot every step** — Use shell commands and file reads when possible; they're faster
- **Don't type passwords** — Use config files or environment variables instead
- **Don't click around aimlessly** — Take one screenshot, plan clicks, batch them

## Always Available

This access is **always available** across sessions. There's no setup needed—just use the tools directly. If you hit a permission error (e.g., "Application not in allowlist"), call `request_access()` with that app.

The goal: **Claude can do on Tony's machine exactly what Tony could do manually, but faster.**
