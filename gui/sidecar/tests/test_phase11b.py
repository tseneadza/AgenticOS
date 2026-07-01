"""Phase 11b — unit tests for GitHub integration + git scaffolding.

These tests are self-contained and MUST NOT hit the network, real GitHub, the
``gh`` CLI, or a real token:

    * ``get_github_token`` is exercised with ``_load_config`` /
      ``subprocess.run`` monkeypatched.
    * ``GitHubClient.create_repo`` / ``check_token_valid`` are exercised with a
      fake ``httpx.Client`` (no sockets opened).
    * ``init_git_repo`` uses REAL git in a ``tmp_path`` (git is available in the
      test env) but never pushes (no network).

Run from the repo root using the repo venv:

    .venv/bin/python -m pytest gui/sidecar/tests/test_phase11b.py -v
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable (so ``gui.sidecar.*`` resolves) regardless
# of the pytest invocation directory. tests/ -> sidecar -> gui -> ROOT
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gui.sidecar import github_integration as gh  # noqa: E402
from gui.sidecar import project_manager as pm  # noqa: E402


# ── fakes ─────────────────────────────────────────────────────────────────────

class _FakeResponse:
    """Minimal stand-in for an httpx.Response."""

    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self) -> dict:
        return self._json


class _FakeClient:
    """Minimal context-manager stand-in for httpx.Client.

    Records the last POST json and returns a canned response so no real network
    call is made. Configured via class attributes set per-test.
    """

    #: response returned by GET requests
    get_response: _FakeResponse = _FakeResponse(200, {"login": "octocat"})
    #: response returned by POST requests
    post_response: _FakeResponse = _FakeResponse(201, {})
    #: captured POST payload for assertions
    last_post_json: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, headers=None):
        return type(self).get_response

    def post(self, url, headers=None, json=None):
        type(self).last_post_json = json
        return type(self).post_response


# ── get_github_token tests ────────────────────────────────────────────────────

def test_get_github_token_from_config(monkeypatch):
    monkeypatch.setattr(
        gh, "_load_config", lambda: {"github": {"token": "config-token"}}
    )
    # subprocess must NOT be consulted when config has a token.
    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(gh.subprocess, "run", _boom)

    assert gh.get_github_token() == "config-token"


def test_get_github_token_from_gh_cli(monkeypatch):
    monkeypatch.setattr(gh, "_load_config", lambda: {})

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="ghtoken\n", stderr="")

    monkeypatch.setattr(gh.subprocess, "run", _fake_run)

    assert gh.get_github_token() == "ghtoken"


def test_get_github_token_none_when_gh_missing(monkeypatch):
    monkeypatch.setattr(gh, "_load_config", lambda: {})

    def _missing(*a, **k):
        raise FileNotFoundError("gh not installed")

    monkeypatch.setattr(gh.subprocess, "run", _missing)

    assert gh.get_github_token() is None


def test_get_github_token_ignores_empty_config_token(monkeypatch):
    monkeypatch.setattr(gh, "_load_config", lambda: {"github": {"token": "   "}})

    def _fake_run(cmd, capture_output=False, text=False, timeout=None):
        return subprocess.CompletedProcess(cmd, 0, stdout="fallback\n", stderr="")

    monkeypatch.setattr(gh.subprocess, "run", _fake_run)

    assert gh.get_github_token() == "fallback"


# ── GitHubClient tests ────────────────────────────────────────────────────────

def _install_fake_client(monkeypatch, *, get_status=200, get_json=None,
                         post_status=201, post_json=None, post_text=""):
    _FakeClient.get_response = _FakeResponse(get_status, get_json or {"login": "octocat"})
    _FakeClient.post_response = _FakeResponse(post_status, post_json or {}, post_text)
    _FakeClient.last_post_json = None
    monkeypatch.setattr(gh.httpx, "Client", _FakeClient)


def test_create_repo_defaults_private(monkeypatch):
    _install_fake_client(
        monkeypatch,
        post_status=201,
        post_json={
            "full_name": "octocat/my-repo",
            "html_url": "https://github.com/octocat/my-repo",
            "clone_url": "https://github.com/octocat/my-repo.git",
            "ssh_url": "git@github.com:octocat/my-repo.git",
        },
    )
    client = gh.GitHubClient("fake-token")
    result = client.create_repo("my-repo", description="desc")

    assert _FakeClient.last_post_json["private"] is True
    assert _FakeClient.last_post_json["name"] == "my-repo"
    assert _FakeClient.last_post_json["auto_init"] is False
    assert result["clone_url"] == "https://github.com/octocat/my-repo.git"


def test_create_repo_can_be_public(monkeypatch):
    _install_fake_client(monkeypatch, post_status=201, post_json={"clone_url": "x"})
    gh.GitHubClient("fake-token").create_repo("r", private=False)
    assert _FakeClient.last_post_json["private"] is False


def test_create_repo_422_already_exists(monkeypatch):
    _install_fake_client(
        monkeypatch, post_status=422, post_text="name already exists on this account"
    )
    client = gh.GitHubClient("fake-token")
    with pytest.raises(gh.GitHubError) as exc:
        client.create_repo("taken")
    assert "already exists" in str(exc.value)


def test_create_repo_other_error(monkeypatch):
    _install_fake_client(monkeypatch, post_status=500, post_text="boom")
    with pytest.raises(gh.GitHubError):
        gh.GitHubClient("fake-token").create_repo("r")


def test_check_token_valid_true(monkeypatch):
    _install_fake_client(monkeypatch, get_status=200, get_json={"login": "octocat"})
    assert gh.GitHubClient("fake-token").check_token_valid() is True


def test_check_token_valid_false_on_401(monkeypatch):
    _install_fake_client(monkeypatch, get_status=401)
    assert gh.GitHubClient("fake-token").check_token_valid() is False


def test_setup_repo_returns_none_without_token(monkeypatch):
    monkeypatch.setattr(gh, "get_github_token", lambda: None)
    assert gh.setup_repo("my-repo") is None


def test_setup_repo_best_effort_on_github_error(monkeypatch):
    monkeypatch.setattr(gh, "get_github_token", lambda: "fake-token")
    _install_fake_client(monkeypatch, post_status=500, post_text="boom")
    assert gh.setup_repo("my-repo") is None


# ── init_git_repo tests (REAL git, no network) ────────────────────────────────

def test_init_git_repo_local(tmp_path):
    # Something to commit.
    (tmp_path / "README.md").write_text("# hello\n")

    status = pm.init_git_repo(
        tmp_path,
        remote_url="https://example.com/x/y.git",
        push=False,
    )

    assert status["initialized"] is True
    assert status["committed"] is True
    assert status["remote_added"] is True
    assert status["pushed"] is False
    assert (tmp_path / ".git").exists()


def test_init_git_repo_no_remote(tmp_path):
    (tmp_path / "file.txt").write_text("data\n")

    status = pm.init_git_repo(tmp_path)

    assert status["initialized"] is True
    assert status["committed"] is True
    assert status["remote_added"] is False
    assert status["pushed"] is False
