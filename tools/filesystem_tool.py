"""Filesystem tool — all vault reads/writes flow through here.

Phase 2 (TR-03 closed): operations are delegated to a real MCP stdio
client speaking to @modelcontextprotocol/server-filesystem, spawned via
npx with the allowed roots derived from settings.vault_path plus the
constitution's write_allowlist. Function signatures are unchanged from
Phase 1, so agents and workflows are untouched.

Constitution enforcement stays HERE, client-side, before any call is
delegated — the MCP server is a transport, not the safety boundary.

`settings.yaml: filesystem_backend` selects the backend:
  - "mcp" (default): persistent MCP stdio session in a background thread
  - "direct": Phase 1 direct file ops (fallback for environments where
    spawning node/npx is unreliable, e.g. some launchd contexts)

Known residual direct op: delete_file. The MCP filesystem server exposes
no delete tool, so deletion remains a guarded direct operation in both
backends (still requires file_delete approval + write-path check).
"""
from __future__ import annotations

import asyncio
import atexit
import shutil
import threading
from contextlib import AsyncExitStack
from pathlib import Path

import yaml

from core.constitution import Constitution

_constitution = Constitution.load()
_files_written = 0

_SETTINGS = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "settings.yaml").read_text()
)["settings"]

_BACKEND = _SETTINGS.get("filesystem_backend", "mcp")


def _allowed_roots() -> list[str]:
    """Roots handed to the MCP server: vault + write allowlist, deduped."""
    roots: list[str] = []
    for candidate in [_SETTINGS.get("vault_path", ""), *_constitution.write_allowlist]:
        candidate = candidate.rstrip("/")
        if not candidate:
            continue
        if any(candidate == r or candidate.startswith(r + "/") for r in roots):
            continue
        roots = [r for r in roots if not r.startswith(candidate + "/")]
        roots.append(candidate)
    return roots


class _McpFilesystemClient:
    """Persistent stdio session to @modelcontextprotocol/server-filesystem.

    Runs an asyncio loop in a daemon thread so the synchronous tool
    functions below can block on MCP calls without event-loop plumbing
    in agents.
    """

    _START_TIMEOUT = 30
    _CALL_TIMEOUT = 30

    def __init__(self, roots: list[str]):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-fs-client", daemon=True
        )
        self._thread.start()
        self._stack: AsyncExitStack | None = None
        self._session = None
        self._tools: set[str] = set()
        fut = asyncio.run_coroutine_threadsafe(self._start(roots), self._loop)
        fut.result(timeout=self._START_TIMEOUT)
        atexit.register(self.close)

    async def _start(self, roots: list[str]) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
        params = StdioServerParameters(
            command=npx,
            args=["-y", "@modelcontextprotocol/server-filesystem", *roots],
        )
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        listed = await self._session.list_tools()
        self._tools = {t.name for t in listed.tools}

    async def _call(self, tool: str, args: dict) -> str:
        result = await self._session.call_tool(tool, args)
        text = "\n".join(
            c.text for c in result.content if getattr(c, "text", None) is not None
        )
        if result.isError:
            raise RuntimeError(f"MCP filesystem tool '{tool}' failed: {text}")
        return text

    def call(self, tool: str, args: dict) -> str:
        fut = asyncio.run_coroutine_threadsafe(self._call(tool, args), self._loop)
        return fut.result(timeout=self._CALL_TIMEOUT)

    @property
    def tools(self) -> set[str]:
        return self._tools

    def close(self) -> None:
        if self._stack is not None:
            stack, self._stack = self._stack, None
            try:
                fut = asyncio.run_coroutine_threadsafe(stack.aclose(), self._loop)
                fut.result(timeout=5)
            except Exception:
                pass  # best-effort shutdown of the npx child
        self._loop.call_soon_threadsafe(self._loop.stop)


_client: _McpFilesystemClient | None = None
_client_lock = threading.Lock()


def _mcp() -> _McpFilesystemClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = _McpFilesystemClient(_allowed_roots())
        return _client


def reset_write_counter() -> None:
    global _files_written
    _files_written = 0


def read_text_file(path: str) -> str:
    if _BACKEND != "mcp":
        return Path(path).read_text(encoding="utf-8")
    client = _mcp()
    tool = "read_text_file" if "read_text_file" in client.tools else "read_file"
    return client.call(tool, {"path": path})


def list_directory(path: str) -> list[str]:
    if _BACKEND != "mcp":
        return sorted(p.name for p in Path(path).iterdir())
    raw = _mcp().call("list_directory", {"path": path})
    # Server returns lines like "[FILE] name" / "[DIR] name" — strip the
    # prefix to preserve the Phase 1 return shape (sorted bare names).
    names = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith(("[FILE]", "[DIR]")):
            names.append(line.split("] ", 1)[1])
        elif line:
            names.append(line)
    return sorted(names)


def write_file(path: str, content: str, *, approved: bool = False) -> str:
    global _files_written
    _constitution.guard("file_write", payload=content, approved=True)
    _constitution.guard_write_path(path)
    _files_written += 1
    _constitution.check_files_written(_files_written)
    if _BACKEND != "mcp":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)
    client = _mcp()
    parent = str(Path(path).parent)
    if "create_directory" in client.tools:
        client.call("create_directory", {"path": parent})
    client.call("write_file", {"path": path, "content": content})
    return path


def delete_file(path: str, *, approved: bool = False) -> None:
    # file_delete is on the approval_required list — guard() raises
    # ApprovalRequired unless approved=True is passed post-approval.
    # Direct op in both backends: the MCP filesystem server exposes no
    # delete tool (documented deviation, see module docstring).
    _constitution.guard("file_delete", payload=str(path), approved=approved)
    _constitution.guard_write_path(path)
    Path(path).unlink()
