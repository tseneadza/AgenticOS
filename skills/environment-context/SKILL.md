---
name: environment-context
description: |
  Claude operates in THREE distinct environments with different capabilities and file paths. Use this skill to understand where commands run, which tools work where, how paths map between environments, and how to avoid the common mistake of thinking a sandbox command affects your local machine. Critical for debugging, running builds, and file operations.
compatibility: Applicable to all Claude sessions working with Tony's machine
---

# Three Environments: Sandbox vs Local Machine vs Workspace

**This is critical to understand.** Claude is NOT running directly on your Mac. Instead, there are three separate environments, each with different capabilities, file paths, and tool access.

## The Three Environments

### 1. **Claude's Sandbox** (Isolated Linux VM)
- **What it is**: A temporary, sandboxed Linux environment that Claude runs commands in
- **Where it runs**: Anthropic's cloud infrastructure (not your machine)
- **Lifespan**: Temporary—resets between requests
- **File paths**: `/tmp/`, `/sessions/blissful-affectionate-newton/mnt/`, etc.
- **Access to Tony's files**: Via mounted folders only (see mapping below)
- **Tools available**: 
  - `mcp__workspace__bash` — run bash commands here
  - File read (for mounted folders only)
  - Limited network access

**Key limitation**: Changes made in the sandbox are **temporary** and don't affect your Mac.

### 2. **Tony's Local MacBook Air** (Your Real Computer)
- **What it is**: Your actual MacBook, running macOS
- **Where it runs**: Your desk, in your home network
- **Lifespan**: Permanent—files stay after Claude session ends
- **File paths**: `/Users/tonyseneadza/...`, `~/...`, `/usr/local/...`, etc.
- **Tools available**:
  - `mcp__MacOS-MCP__*` tools (computer-use, click, type, screenshot, etc.)
  - `mcp__MacOS-MCP__Shell` — run bash commands here (on your machine)
  - Full file access via Read/Write/Edit tools
  - Application control (open, click, interact)

**Key capability**: Can take screenshots, control apps, see current desktop state.

### 3. **Mounted Workspace** (Bridge Between Them)
- **What it is**: Your AgenticOS folder, mounted into the sandbox so both environments can access it
- **Local machine path**: `/Users/tonyseneadza/Codehome/AgenticOS`
- **Sandbox path**: `/sessions/blissful-affectionate-newton/mnt/AgenticOS/`
- **Lifespan**: Permanent—changes persist
- **Use**: Shared working directory where Claude can read/write and your local machine sees the changes

## Path Mapping Reference

When the same folder appears in multiple environments, paths are different:

| What | Local Machine | Sandbox | Workspace Mount |
|------|---------------|---------|-----------------|
| **AgenticOS folder** | `/Users/tonyseneadza/Codehome/AgenticOS` | `/sessions/blissful-affectionate-newton/mnt/AgenticOS/` | Shared—same files |
| **Outputs folder** | `/Users/tonyseneadza/Library/Application Support/Claude/local-agent-mode-sessions/.../outputs` | `/sessions/.../mnt/outputs/` | Shared—auto-uploaded |
| **Home directory** | `/Users/tonyseneadza/` | `/root/` (sandbox user) | `/sessions/.../mnt/` (partial) |
| **System binaries** | `/usr/local/mysql/bin/` | Not available | Not available |

**Critical**: The same file at two different paths is **still the same file**—changes in one place appear in the other.

## Which Tool to Use for Each Environment

### For Local Machine (Your Mac)

Use these tools to interact with your actual computer:

| Task | Tool | Example |
|------|------|---------|
| Take screenshot | `screenshot()` | See desktop state |
| Click button | `left_click([100, 200])` | Navigate UI |
| Type text | `type("hello")` | Enter text in apps |
| Open app | `mcp__MacOS-MCP__App(name="Terminal")` | Launch application |
| Run command | `mcp__MacOS-MCP__Shell(command="mysql -u root...")` | Execute on Mac |
| Read file | `Read("/Users/tonyseneadza/...")` | Access local files |
| Write file | `Write("/Users/tonyseneadza/...")` | Modify local files |

### For Sandbox (Linux VM)

Use these tools to run isolated commands:

| Task | Tool | Example |
|------|------|---------|
| Run bash | `mcp__workspace__bash(command="ls /tmp")` | Commands run in sandbox |
| Python script | `mcp__workspace__bash(command="python script.py")` | Runs in sandbox Python |
| Package manager | `mcp__workspace__bash(command="pip install X")` | Installs in sandbox |

**Important**: Changes here are temporary and don't affect your Mac.

### For Shared Workspace (Mounted Folder)

Use file tools with the **local machine path** for persistent changes:

```python
# ✅ Correct: Use local machine path, changes are permanent
Read("/Users/tonyseneadza/Codehome/AgenticOS/file.py")
Write("/Users/tonyseneadza/Codehome/AgenticOS/file.py", "content")
Edit("/Users/tonyseneadza/Codehome/AgenticOS/file.py", old, new)

# ❌ Wrong: Sandbox path is temporary
Read("/sessions/blissful-affectionate-newton/mnt/AgenticOS/file.py")
```

## Common Mistakes & How to Avoid Them

### Mistake 1: "I ran a bash command, why didn't my Mac change?"

**Problem**: You used `mcp__workspace__bash` (sandbox) thinking it affects your Mac.

**Reality**:
- Sandbox bash is **isolated**—it's a different Linux machine in the cloud
- Your Mac doesn't see those changes
- MySQL started in sandbox disappears when session ends

**Fix**: 
- Use `mcp__MacOS-MCP__Shell` to run commands on your actual Mac
- Or use file tools with `/Users/tonyseneadza/...` paths for persistent changes

### Mistake 2: "My file changes didn't persist"

**Problem**: You edited a file in the sandbox, thinking it would persist.

**Reality**:
- Sandbox files are temporary
- Only the mounted workspace folder persists

**Fix**:
- Always use local machine paths: `/Users/tonyseneadza/Codehome/AgenticOS/...`
- These paths work in both Read/Write tools AND are visible on your Mac

### Mistake 3: "Why can't I screenshot in the sandbox?"

**Problem**: You tried to use screenshot() in bash commands.

**Reality**:
- Sandbox is headless (no display)
- Screenshots only work on your Mac via `screenshot()` tool

**Fix**:
- Use `screenshot()` (from computer-use tools) to see your Mac's screen
- Use `bash` commands to check system state without visuals

### Mistake 4: "The command worked in bash but MySQL still won't start"

**Problem**: You started MySQL in the sandbox, then took a screenshot expecting it to be running.

**Reality**:
- Sandbox process is different from Mac process
- MySQL running in sandbox ≠ MySQL running on your Mac
- Sandbox shuts down after session

**Fix**:
- Use `mcp__MacOS-MCP__Shell` to start MySQL on your actual Mac
- Or use `screenshot()` then click MySQL Workbench "Start Server" button

## Decision Tree: Which Tool Should I Use?

```
Is this file/folder I want to modify?
├─ Yes: Is it in ~/Codehome/AgenticOS/ or ~/.agentic-os/?
│  ├─ Yes: Use Read/Write/Edit with local path
│  │        (/Users/tonyseneadza/Codehome/AgenticOS/...)
│  │        Changes WILL persist ✅
│  └─ No: Check if file is elsewhere on Mac
│         Use Read/Write/Edit with full local path
│         (/Users/tonyseneadza/...)
│
Is this a command I want to run?
├─ On my Mac (lasting effect)?
│  └─ Use mcp__MacOS-MCP__Shell or shell commands via script
│
├─ In the sandbox (temporary)?
│  └─ Use mcp__workspace__bash
│
Do I need to see the screen?
├─ Yes: Use screenshot() (shows Mac desktop)
│
Do I need to interact with an app?
├─ Click a button: Use left_click()
├─ Type text: Use type()
├─ Open an app: Use mcp__MacOS-MCP__App()
```

## Real Examples: Correct vs Wrong

### Example 1: Starting MySQL

**❌ WRONG** (uses sandbox, won't persist):
```bash
mcp__workspace__bash(command="/usr/local/mysql/bin/mysqld_safe &")
# MySQL runs in sandbox, disappears after session
```

**✅ CORRECT** (uses Mac directly):
```bash
mcp__MacOS-MCP__Shell(
  command="sudo /usr/local/mysql/support-files/mysql.server start"
)
# MySQL starts on your Mac, persists after session
```

### Example 2: Checking if MySQL is Running

**❌ WRONG** (checks sandbox, not your Mac):
```bash
mcp__workspace__bash(command="ps aux | grep mysqld")
# Checks sandbox processes, doesn't tell you Mac state
```

**✅ CORRECT** (checks your Mac):
```bash
mcp__MacOS-MCP__Shell(command="ps aux | grep mysqld")
# Checks your Mac's processes
```

### Example 3: Modifying a Config File

**❌ WRONG** (temporary sandbox file):
```python
# Sandbox path—changes disappear
Write(
  "/tmp/config.yaml",
  "content"
)
```

**✅ CORRECT** (persistent local file):
```python
# Local machine path—changes persist
Write(
  "/Users/tonyseneadza/.agentic-os/config.yaml",
  "content"
)
```

### Example 4: Running Tests

**❌ WRONG** (runs in sandbox with no access to your project's venv):
```bash
mcp__workspace__bash(command="pytest tests/")
# Sandbox doesn't have your project's Python environment
```

**✅ CORRECT** (runs on Mac with proper environment):
```bash
mcp__MacOS-MCP__Shell(
  command="cd /Users/tonyseneadza/Codehome/AgenticOS && .venv/bin/python -m pytest tests/ -v"
)
# Uses your Mac's venv, tests against your actual code
```

## When You See Errors

### Error: "Command not found: mysql"

**Cause**: Ran in sandbox where `/usr/local/mysql/bin/` doesn't exist.

**Fix**: Use `mcp__MacOS-MCP__Shell` instead of `bash`.

### Error: "File not found: /Users/tonyseneadza/..."

**Cause**: Tried to read local file from sandbox using a Mac path.

**Fix**: Either:
1. Use mounted workspace path: `/sessions/.../mnt/AgenticOS/...`
2. Use Read/Write tools (they handle path translation automatically)

### Error: "Permission denied on /usr/local/mysql/data/"

**Cause**: Sandbox user doesn't have Mac permissions.

**Fix**: Use `mcp__MacOS-MCP__Shell` which runs as your user (or sudo).

## Summary

| | Sandbox | Local Mac | Workspace Mount |
|---|---------|-----------|-----------------|
| **Where** | Cloud Linux VM | Your MacBook | Folder on both |
| **Persistence** | Temporary | Permanent | Permanent |
| **Screenshots** | No (headless) | Yes | Via Mac screenshot |
| **Apps** | None available | Full control | Via Mac |
| **Shell access** | `workspace__bash` | `MacOS-MCP__Shell` | Via workspace paths |
| **File changes** | Disappear | Persist | Persist |
| **Best use** | Testing, isolated work | Real tasks | Shared files |

**Golden rule**: If you want lasting changes on your Mac, use `MacOS-MCP` tools or file tools with `/Users/tonyseneadza/...` paths. Otherwise, you're changing the wrong machine.
