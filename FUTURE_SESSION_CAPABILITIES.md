# Future Session Capabilities & Access Guide

**Read this first if you're a new session starting work on AgenticOS.**

---

## Quick Answer: What Can You Do?

### ✅ Can Do (No Permission Needed)
- Read any file in the repo (code, docs, config)
- Read git history and branches
- Run tests on your own (`npm test`)
- View test results and coverage
- Analyze code and suggest improvements
- Create new files (scripts, docs, components)
- Edit files via the Edit tool

### ⏳ Can Do (Ask First)
- Use computer-use tools to control your Mac (need approval dialog)
- Create/modify shell scripts you'll run later
- Run bash commands if you have shell access

### ❌ Can't Do (Sandbox Limitation)
- Build Tauri app directly (requires macOS + Rust)
- Run the app in GUI (no display in sandbox)
- Control the mouse/keyboard without approval
- Access `/Users/tonyseneadza/Desktop` directly (but can ask you to move files)

---

## What You Inherit from Phase 6

### Code Assets
```
gui/desktop/src/
├── components/
│   ├── MethodBadge.jsx
│   ├── PathDisplay.jsx
│   ├── StatusIndicator.jsx
│   ├── ResponseDisplay.jsx
│   ├── ParamInput.jsx
│   ├── GroupHeader.jsx
│   ├── FilterBar.jsx
│   ├── CallLogEntry.jsx
│   ├── TabSwitcher.jsx
│   ├── EndpointListItem.jsx
│   ├── ScriptTypeBadge.jsx
│   ├── ScriptGroupHeader.jsx
│   └── ScriptItem.jsx
│
├── __tests__/
│   └── [13 .test.jsx files, 238 tests total]
│
└── [All parent components already integrated]
```

**All 238 tests pass.** You can run:
```bash
cd /Users/tonyseneadza/Codehome/AgenticOS/gui/desktop
npm test -- --run
```

### Documentation Assets
```
docs/
├── CONTINUATION.md ..................... Session memory (13 tasks, 15k+ words)
├── TESTING_GUIDE.md ................... 4 critical CSS + testing rules (MUST READ)
├── PHASE6_SESSION_SUMMARY.md .......... This checkpoint summary
├── gui-frontend-conventions.md ........ GUI/frontend rules (themes, tokens, etc.)
├── CHANGELOG.md ....................... Dates, versions, features
└── roadmap.md ......................... Project phases & status

root/
├── CLAUDE.md .......................... PROJECT RULES (icon handling, Tauri, tray)
├── build-and-verify.sh ............... One-command build verification
└── FUTURE_SESSION_CAPABILITIES.md .... This file
```

**Must read before starting:**
1. CONTINUATION.md (session memory)
2. CLAUDE.md (project rules)
3. TESTING_GUIDE.md (CSS + testing rules)

---

## How to Request More Access

### Scenario 1: "I want to run shell commands on Tony's Mac"

**Option A:** Ask Tony for MCP server (fastest)
```
Tony, can you install a custom MCP server so I can run build/test commands directly?
I'd like to execute:
- npm test -- --run
- npm run tauri -- build
- git commands
```

**Option B:** Use computer-use (slower but works now)
```
I'll request access to Terminal, which requires your approval in a dialog.
```

### Scenario 2: "I need to build/verify the app"

**Today:**
```bash
bash /Users/tonyseneadza/Codehome/AgenticOS/build-and-verify.sh
```

**Future:** Ask Tony to set up MCP so I can run this automatically.

### Scenario 3: "I want to create/edit a file directly on disk"

**Today:**
I can create files via the Write/Edit tools and show you the path. You can copy/move them.

**Future:** With MCP, I can manage files directly (create, copy, organize, delete).

### Scenario 4: "I want to run a test/script and see results immediately"

**Today:**
You run the script, then copy/paste results or show me the output file.

**Future with MCP:** I run the script and immediately see results.

---

## Asking for Permission (Right Now)

If you're a new session and want more access, here's the conversation:

**You ask me:**
> "What would help you be most productive for the next phase?"

**I'll respond with options:**
> "Three things would help:
> 1. An MCP server to run npm/git/bash commands
> 2. Access to Desktop/Downloads for file staging
> 3. Slack webhook for async notifications
>
> Which one would you like to set up first?"

**You can:**
- Pick one and we can build it together
- Say "just use computer-use for now" (I'll ask for approval each time)
- Say "not right now, let me know when you need it"

---

## What Tony (User) Can Do

Tony has full access to the Mac and can:
- **Install MCP servers** → Settings > Capabilities > MCP Servers
- **Grant computer-use permission** → Approve dialogs when requested
- **Create shell scripts** → Any command he wants Claude to run
- **Connect external tools** → Slack, GitHub, Discord, etc.
- **Modify CLAUDE.md** → Update project rules and constraints
- **Run builds/tests** → Via terminal or scripts

**Recommendation for Tony:** If you want Claude to be most productive, set up an MCP server early. The computer-use dialogs get tedious quickly.

---

## File Location Reference

All paths in `/Users/tonyseneadza/Codehome/AgenticOS/`:

| Path | What's There | Can Read | Can Modify |
|------|-------------|----------|-----------|
| gui/desktop/src/components/ | 13 component files | ✅ | ✅ |
| gui/desktop/src/__tests__/ | 238 test files | ✅ | ✅ |
| gui/desktop/package.json | Dependencies & scripts | ✅ | ⚠️ (ask first) |
| docs/ | All documentation | ✅ | ✅ |
| CLAUDE.md | Project rules | ✅ | ⚠️ (ask first) |
| .git/ | Git history | ✅ | ❌ |
| src-tauri/ | Rust/Tauri code | ✅ | ⚠️ (risky) |

---

## Common Commands You Can Ask Me To Tell You To Run

(I can't run these directly, but I can tell you to run them)

```bash
# Tests
cd /Users/tonyseneadza/Codehome/AgenticOS/gui/desktop && npm test -- --run

# Build verification
bash /Users/tonyseneadza/Codehome/AgenticOS/build-and-verify.sh

# Dev server (you'll see hot reload)
cd /Users/tonyseneadza/Codehome/AgenticOS/gui/desktop && npm run tauri dev

# Git status
cd /Users/tonyseneadza/Codehome/AgenticOS && git status

# Count lines of code
wc -l /Users/tonyseneadza/Codehome/AgenticOS/gui/desktop/src/components/*.jsx
```

---

## Next Phase Recommendations

### If Continuing Component Extraction (Phase 6+)
- Refer to REACT_COMPONENT_TESTING.md for patterns
- Use TESTING_GUIDE.md for CSS property rules
- Target 2.5–3.0:1 test-to-code ratio
- Integrate components into parent explorers

### If Starting Integration Testing (Phase 7)
- Test multi-component flows
- Test cross-component communication
- Verify theme persistence
- Check accessibility across components

### If Starting Polish (Phase 8)
- Add error boundaries
- Refine animations/transitions
- Performance profiling
- Dark mode edge cases

---

## Emergency Contacts

If something breaks:
1. **Tests failing:** Check TESTING_GUIDE.md (4 rules cover 90% of issues)
2. **Git stuck:** Use computer-use to delete `.git/HEAD.lock` (permission issue)
3. **Build failing:** Run build-and-verify.sh on Mac to see actual error
4. **Unclear requirements:** Check CONTINUATION.md for task-by-task context

---

## tl;dr

✅ **You can:** Read code, run tests, create/edit files, analyze and refactor  
⏳ **Ask before:** Using computer-use (one-time approval per request)  
❌ **Can't do:** Build Tauri app, run GUI, access Mac filesystem directly (without MCP)  
🚀 **Next level:** Ask Tony to install MCP server for direct command execution  

**Read these first:** CONTINUATION.md → CLAUDE.md → TESTING_GUIDE.md

Good luck! 🎉
