---
name: osa-sidecar-lifecycle
description: |
  Correctly restart, verify, and reason about the AgenticOS FastAPI sidecar (gui.sidecar on :5130). Use this skill whenever you change Python/sidecar code and need it to take effect, whenever a restart "didn't work" or old behavior persists, whenever the app shows stale behavior after an edit, or whenever you suspect duplicate/zombie sidecars. Covers the port-singleton behavior, the "kill ALL PIDs first" rule, the audio-session caveat for background-launched sidecars, and how to confirm the running process is serving the new code.
compatibility: macOS, AgenticOS repo at ~/Codehome/AgenticOS, .venv present
---

# OSA Sidecar Lifecycle (restart the right way, verify it took)

## Overview

The AgenticOS sidecar is a FastAPI app (`python -m gui.sidecar`) that listens on
`:5130`. Almost every "I changed the code but nothing happened" or "I restarted
but it's still broken" problem traces to one of the pitfalls below. This skill
is the canonical restart + verify procedure.

**When to use:**
- You edited any Python under `gui/sidecar/`, `agents/`, `core/`, `osa_voice/`,
  or `config/*.yaml` and need it live (the sidecar loads code + config at
  startup — it does NOT hot-reload).
- A restart "didn't work" / old behavior persists.
- You suspect two sidecars, a zombie, or a port conflict.
- Audio/voice works from your shell tests but not from the sidecar (or vice
  versa).

## The #1 rule: kill ALL sidecar PIDs before starting a new one

The sidecar self-singletons via the port bind: **a second instance detects
:5130 is taken and exits with "already running (PID …) — exiting."** So if an
old sidecar is still alive, your "fresh" start silently no-ops and the OLD code
keeps serving. This is the most common cause of "my change didn't take."

```bash
# WRONG — leaves a survivor if there are multiple/zombie PIDs:
#   kill $(pgrep -f gui.sidecar | head -1)

# RIGHT — kill every matching process, then start one:
cd ~/Codehome/AgenticOS
for p in $(pgrep -f "python -m gui.sidecar"); do kill $p; done
sleep 3
(nohup .venv/bin/python -m gui.sidecar > /tmp/agenticos_sidecar.log 2>&1 &)
sleep 8
pgrep -f gui.sidecar            # expect exactly ONE pid
```

Verify it's actually up and serving the new code:

```bash
curl -s -m 5 localhost:5130/api/osa/state | python3 -m json.tool
tail -5 /tmp/agenticos_sidecar.log
```

If `pgrep` shows two pids, you have a leftover — kill both and retry. If the log
says "already running … exiting", the new one bailed because an old one held the
port: kill everything (`pkill -9 -f "python -m gui.sidecar"`), then start once.

## Audio-session caveat (voice-OUT / afplay)

A sidecar spawns `afplay` (voice-OUT) as a child. Whether that audio reaches the
speakers depends on the **session the sidecar was launched from**:
- Launched from the user's GUI login session (the Tauri app, or a Terminal the
  user is looking at) → audio routes to the speakers. Works.
- Launched from a detached/background automation context → `afplay` may run with
  exit 0 but produce **no sound** (different audio session), and errors are
  swallowed because playback is best-effort.

Implication: if voice tests are silent but return success, relaunch the sidecar
from the user's GUI session (e.g., via the desktop app) rather than a headless
`nohup`. A `POST /api/osa/voice/say` returning `{"ok":true}` only means the text
was handed to a worker thread — **it is NOT proof audio played.** Always confirm
with the user's ears.

## The app vs. your curl: same sidecar?

The Tauri desktop app talks to whatever owns `:5130`. Confirm what that is:

```bash
lsof -nP -iTCP:5130 -sTCP:LISTEN     # the pid serving the app
ps -eo pid,lstart,command | grep -E "gui.sidecar|tauri dev" | grep -v grep
```

In `npm run tauri dev`, the app uses an externally-running sidecar on :5130 (it
does not always spawn its own). If you restart the sidecar while the app is
open, the app reconnects on its next request (each chat turn opens a fresh
HTTP/WS connection) — no app relaunch needed for backend changes. Frontend
(React) changes hot-reload via Vite separately.

## Quick checklist

- [ ] Killed **every** `pgrep -f "python -m gui.sidecar"` pid, not just one
- [ ] `sleep 3` before starting (let the port free up)
- [ ] Started exactly one, confirmed a single pid
- [ ] `curl /api/osa/state` returns 200 with expected fields
- [ ] Log has no "already running … exiting"
- [ ] For voice: sidecar launched from a session with audio; verified by ear

## Key learnings (from the 2026-07-08 voice debug session)

1. The sidecar is already a singleton via the port bind — you don't need extra
   locking. The failure mode is the opposite: a stale instance that won't die,
   masking your new code.
2. "Restarted but unchanged" ≈ old PID still holding :5130. Kill ALL, verify one.
3. Best-effort/non-blocking side effects (voice) return success before they
   happen — never treat HTTP 200 as proof the effect occurred.
4. Background-launched processes can have no audio route. Launch context matters
   for anything touching the speakers/mic.
5. (2026-07-12) A stale sidecar makes OSA truthfully DENY having tools you
   just built — "I don't have a send_message tool" was accurate for six
   hours because the process predated the commit. After adding/wiring ANY
   tool, restart before judging model behavior; check `ps -o lstart` vs the
   commit time when OSA's claims and the code disagree.
6. (2026-07-12) Launch context also sets AppleScript reach and TCC: a
   background-launched sidecar can't LAUNCH apps via `tell application`
   (error -600 — hence the `open -ga` pre-launch rule in osa-system-mcp) and
   inherits Automation grants from its launching host — a sidecar launched
   from a different host will re-prompt on first Messages/Contacts use.
