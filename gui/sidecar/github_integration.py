"""GitHub Integration — Phase 11b (GitHub API + token resolution).

Thin, synchronous helpers for creating remote GitHub repositories as part of
the project-scaffolding flow. Kept synchronous on purpose so the calls are easy
to unit-test and drop into the (synchronous) git init/commit/push flow in
``project_manager.py``.

Public API (Phase 11b):
    get_github_token()                          -> str | None
    class GitHubError(Exception)
    class GitHubClient
        get_auth_user()                         -> dict
        check_token_valid()                     -> bool
        create_repo(repo_name, description, private) -> dict
    setup_repo(repo_name, description, private)  -> dict | None

Token source (locked design):
    1. ``github.token`` in ``~/.agentic-os/config.yaml`` (same file the config
       API writes, yaml.safe_load, chmod 0600).
    2. Fallback to ``gh auth token`` (subprocess).
    3. Otherwise ``None``.

Security: the token is never persisted by this module and never logged.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import httpx
import yaml

log = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

#: Same config file the config API (routes/api_config.py) reads/writes.
_CONFIG_FILE = Path.home() / ".agentic-os" / "config.yaml"

#: GitHub REST API base + pinned API version.
_API_BASE_URL = "https://api.github.com"
_API_VERSION = "2022-11-28"

#: HTTP timeout (seconds) for all GitHub API calls.
_TIMEOUT = 10.0


# ── token resolution ──────────────────────────────────────────────────────────

def _load_config() -> dict:
    """Load ``~/.agentic-os/config.yaml`` -> dict (best-effort).

    Factored out so tests can monkeypatch config loading without touching the
    real filesystem. A missing file or any parse error yields ``{}``.
    """
    try:
        if not _CONFIG_FILE.exists():
            return {}
        with open(_CONFIG_FILE, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        log.debug("_load_config: could not read %s: %s", _CONFIG_FILE, exc)
        return {}


def get_github_token() -> str | None:
    """Resolve a GitHub token, or ``None`` if none is available.

    Resolution order:
        1. ``github.token`` from ``~/.agentic-os/config.yaml`` (if non-empty).
        2. Output of ``gh auth token`` (if the CLI is present and authed).
        3. ``None``.

    Never raises; never logs the token value.
    """
    # 1. Config file.
    config = _load_config()
    token = config.get("github", {}).get("token")
    if isinstance(token, str) and token.strip():
        log.debug("get_github_token: using token from config.yaml")
        return token.strip()

    # 2. gh CLI fallback.
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        if result.returncode == 0 and result.stdout.strip():
            log.debug("get_github_token: using token from `gh auth token`")
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:  # incl. FileNotFoundError, Timeout
        log.debug("get_github_token: `gh auth token` unavailable: %s", exc)

    # 3. Nothing.
    log.warning("get_github_token: no GitHub token found (config.yaml or gh CLI)")
    return None


# ── errors ────────────────────────────────────────────────────────────────────

class GitHubError(Exception):
    """Raised when a GitHub API call fails with an unrecoverable error."""


# ── client ────────────────────────────────────────────────────────────────────

class GitHubClient:
    """Minimal synchronous GitHub REST client (only what Phase 11b needs)."""

    def __init__(self, token: str) -> None:
        self._token = token
        self.base_url = _API_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _API_VERSION,
        }

    # -- user ------------------------------------------------------------------

    def get_auth_user(self) -> dict:
        """GET /user — return the authenticated user's profile dict.

        Raises:
            GitHubError: on any non-2xx response (status + message included).
        """
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(f"{self.base_url}/user", headers=self.headers)

        if not (200 <= resp.status_code < 300):
            raise GitHubError(
                f"GitHub /user failed (status {resp.status_code}): {resp.text}"
            )
        return resp.json()

    def check_token_valid(self) -> bool:
        """Return True if the token authenticates against /user. Never raises."""
        try:
            self.get_auth_user()
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("check_token_valid: token invalid or API error: %s", exc)
            return False

    # -- repos -----------------------------------------------------------------

    def create_repo(
        self,
        repo_name: str,
        description: str | None = None,
        private: bool = True,
    ) -> dict:
        """POST /user/repos — create a repo for the authenticated user.

        Args:
            repo_name: the repository name.
            description: optional repo description.
            private: create a private repo (default True, per locked design).

        Returns:
            The created-repo JSON (has ``html_url``, ``clone_url``, ``ssh_url``,
            ``full_name`` …).

        Raises:
            GitHubError: on 422 (name already exists) with a clear message, or
                any other non-2xx response.
        """
        payload = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": False,
        }
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                f"{self.base_url}/user/repos",
                headers=self.headers,
                json=payload,
            )

        if 200 <= resp.status_code < 300:
            return resp.json()

        if resp.status_code == 422:
            raise GitHubError(
                f"GitHub repo '{repo_name}' already exists (or name is invalid): "
                f"{resp.text}"
            )

        raise GitHubError(
            f"GitHub create_repo failed (status {resp.status_code}): {resp.text}"
        )


# ── orchestration-friendly entry point ────────────────────────────────────────

def setup_repo(
    repo_name: str,
    description: str | None = None,
    private: bool = True,
) -> dict | None:
    """Best-effort: resolve a token and create *repo_name* on GitHub.

    Returns the created-repo dict, or ``None`` if no token is available or the
    API call fails. Lenient by design (mirrors the scaffolding flow): a GitHub
    failure warns but never raises, so it can never abort project creation.
    """
    token = get_github_token()
    if not token:
        log.warning("setup_repo: no GitHub token available; skipping remote creation")
        return None

    try:
        return GitHubClient(token).create_repo(
            repo_name, description=description, private=private
        )
    except GitHubError as exc:
        log.warning("setup_repo: GitHub repo creation failed: %s", exc)
        return None
