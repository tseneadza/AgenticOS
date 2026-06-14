"""WebSocket PTY terminal handler (Phase 7 — FR-33 expanded view).

Each WebSocket connection spawns an independent zsh login session inside
a pseudo-terminal and bridges it bidirectionally to xterm.js in the React
frontend.  When the WebSocket closes the PTY and child process are cleaned up.

Protocol
--------
browser → server:
  • binary frames   — raw keystrokes / paste data forwarded straight to PTY
  • text JSON frame — {"type": "resize", "cols": N, "rows": N}

server → browser:
  • binary frames   — raw PTY output (ANSI sequences, text, colour codes …)
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import pty
import struct
import termios

from fastapi import WebSocket, WebSocketDisconnect


async def handle(ws: WebSocket) -> None:
    """Accept *ws* and bridge it to a fresh zsh PTY session."""
    await ws.accept()

    # Open a PTY pair; slave end is given to the child process
    master_fd, slave_fd = pty.openpty()

    shell = os.environ.get("SHELL", "/bin/zsh")
    env = {
        **os.environ,
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
    }

    proc = await asyncio.create_subprocess_exec(
        shell, "-l",
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        preexec_fn=os.setsid,   # new session so Ctrl-C etc. work correctly
        close_fds=True,
    )
    os.close(slave_fd)          # parent only needs the master end

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()

    def _pty_readable() -> None:
        """Called by the event loop when master_fd has data to read."""
        try:
            data = os.read(master_fd, 4096)
            reader.feed_data(data)
        except OSError:
            reader.feed_eof()
            loop.remove_reader(master_fd)

    loop.add_reader(master_fd, _pty_readable)

    async def _send_output() -> None:
        """Stream PTY output → WebSocket as binary frames."""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                await ws.send_bytes(chunk)
        except Exception:
            pass

    async def _recv_input() -> None:
        """Forward WebSocket messages → PTY stdin."""
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                raw = msg.get("bytes")
                if raw:
                    # Binary frame = raw keystroke / paste
                    os.write(master_fd, raw)
                else:
                    text = msg.get("text", "")
                    if not text:
                        continue
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "resize":
                        cols = max(1, int(data.get("cols", 80)))
                        rows = max(1, int(data.get("rows", 24)))
                        _resize(master_fd, cols, rows)
        except (WebSocketDisconnect, Exception):
            pass

    try:
        await asyncio.gather(_send_output(), _recv_input())
    finally:
        loop.remove_reader(master_fd)
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


def _resize(fd: int, cols: int, rows: int) -> None:
    """Update the PTY window size so the shell knows its dimensions."""
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass
