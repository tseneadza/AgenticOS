"""Unix socket server for ZSH shell events — FR-10, TR-09.

Listens on ~/.agentic-os/shell.sock (chmod 600) for newline-delimited
JSON events emitted by the ZSH plugin (FR-09).  Each event is dispatched
to registered handlers (typically the shell agent's LangGraph listener).

Protocol:
  Each message is a JSON object terminated by a newline, e.g.:
    {"event": "preexec", "command": "git status", "cwd": "/Users/..."}
    {"event": "precmd",  "exit_code": 0, "cwd": "/Users/..."}
    {"event": "chpwd",   "cwd": "/Users/..."}

TR-09: socket file is user-accessible only (0o600).  Reconnection is
handled on the plugin side; the server loops indefinitely and accepts
new connections after each disconnect.

Usage (from the FastAPI sidecar or a standalone process):
    server = SocketServer()
    server.add_handler(my_async_handler)
    asyncio.run(server.serve())
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

SOCKET_DIR = Path.home() / ".agentic-os"
SOCKET_PATH = SOCKET_DIR / "shell.sock"

# Ring buffer of recent events surfaced to the sidecar terminal endpoint
_event_log: list[dict] = []
MAX_LOG = 200

Handler = Callable[[dict], Awaitable[None]]


class SocketServer:
    """Async Unix socket server that receives and dispatches ZSH shell events."""

    def __init__(self, socket_path: Path = SOCKET_PATH):
        """Initialize the socket server.

        Args:
            socket_path: Filesystem path for the Unix domain socket.
        """
        self.socket_path = socket_path
        self._handlers: list[Handler] = []
        self._server: asyncio.Server | None = None
        self._active_writers: list[asyncio.StreamWriter] = []

    def add_handler(self, handler: Handler) -> None:
        """Register an async handler to be called for each incoming event."""
        self._handlers.append(handler)

    # ------------------------------------------------------------------
    # Core serve loop
    # ------------------------------------------------------------------

    async def serve(self) -> None:
        """Start the Unix socket server.  Runs until cancelled.

        Uses an asyncio.Event wait instead of serve_forever() so that task
        cancellation is handled cleanly: active connections are force-closed
        in the finally block, which avoids the wait_closed() hang that occurs
        when the ZSH plugin is still connected at shutdown time.
        """
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Clean up stale socket file
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.socket_path)
        )

        # TR-09: restrict to current user only
        os.chmod(self.socket_path, stat.S_IRUSR | stat.S_IWUSR)

        logger.info("Shell socket server listening at %s", self.socket_path)
        try:
            # asyncio.start_unix_server begins serving immediately; we just
            # park here waiting for cancellation instead of calling
            # serve_forever() (which delegates to wait_closed() on cancel).
            await asyncio.get_event_loop().create_future()
        except asyncio.CancelledError:
            pass
        finally:
            # Close the listening socket so no new connections are accepted.
            if self._server:
                self._server.close()
            # Force-close every active ZSH connection so wait_closed() returns
            # immediately rather than blocking until the shell session ends.
            for writer in list(self._active_writers):
                try:
                    writer.close()
                except Exception:
                    pass
            self._active_writers.clear()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection, reading newline-delimited JSON events."""
        peer = writer.get_extra_info("peername") or "zsh"
        logger.debug("Shell plugin connected: %s", peer)
        self._active_writers.append(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    event = json.loads(line.decode().strip())
                except json.JSONDecodeError:
                    logger.warning("Malformed shell event (not JSON): %r", line)
                    continue

                # Store in ring buffer for the terminal panel (FR-33)
                _event_log.append(event)
                if len(_event_log) > MAX_LOG:
                    _event_log.pop(0)

                # Dispatch to registered handlers
                for handler in self._handlers:
                    try:
                        await handler(event)
                    except Exception:  # noqa: BLE001
                        logger.exception("Shell event handler error for %s", event)
        finally:
            writer.close()
            if writer in self._active_writers:
                self._active_writers.remove(writer)
            logger.debug("Shell plugin disconnected")


# ------------------------------------------------------------------
# Ring-buffer accessor for the sidecar terminal endpoint (FR-33)
# ------------------------------------------------------------------

def get_recent_lines(n: int = 15) -> list[str]:
    """Return last n log lines formatted as strings for the terminal strip."""
    lines = []
    for ev in _event_log[-n:]:
        evt = ev.get("event", "?")
        cwd = ev.get("cwd", "")
        cmd = ev.get("command", "")
        code = ev.get("exit_code")
        if evt == "preexec":
            lines.append(f"$ {cmd}  [{cwd}]")
        elif evt == "precmd":
            status = "ok" if code == 0 else f"exit {code}"
            lines.append(f"← {status}  [{cwd}]")
        elif evt == "chpwd":
            lines.append(f"cd {cwd}")
        else:
            lines.append(json.dumps(ev))
    return lines


# ------------------------------------------------------------------
# Singleton for import by sidecar and shell_agent
# ------------------------------------------------------------------
_server: SocketServer | None = None


def get_server() -> SocketServer:
    """Return the module-level SocketServer singleton, creating it on first call."""
    global _server
    if _server is None:
        _server = SocketServer()
    return _server
