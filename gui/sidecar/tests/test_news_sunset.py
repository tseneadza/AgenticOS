"""Tests for the Web News article sunset filter (FR-WN aging).

Covers:
  * _parse_pub_date — RFC 2822, ISO 8601, naive, empty, garbage inputs
  * POST /api/news/fetch — default 7-day cutoff, custom max_age_days,
    strict drop of undated/unparseable items, and disable via <= 0.

No network: _fetch_rss is monkeypatched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from gui.sidecar import app as sidecar_app
from gui.sidecar.app import _parse_pub_date, app


# ── _parse_pub_date ───────────────────────────────────────────────────────────

def test_parse_rfc2822():
    d = _parse_pub_date("Tue, 30 Jun 2026 14:05:00 GMT")
    assert d == datetime(2026, 6, 30, 14, 5, tzinfo=timezone.utc)


def test_parse_iso8601_z():
    d = _parse_pub_date("2026-06-30T14:05:00Z")
    assert d == datetime(2026, 6, 30, 14, 5, tzinfo=timezone.utc)


def test_parse_iso8601_offset():
    d = _parse_pub_date("2026-06-30T14:05:00+02:00")
    assert d is not None
    assert d.utcoffset() == timedelta(hours=2)


def test_parse_naive_assumed_utc():
    d = _parse_pub_date("2026-06-30T14:05:00")
    assert d is not None and d.tzinfo == timezone.utc


@pytest.mark.parametrize("raw", ["", None, "not a date", "yesterday-ish", 42])
def test_parse_invalid_returns_none(raw):
    assert _parse_pub_date(raw) is None


# ── /api/news/fetch filtering ─────────────────────────────────────────────────

def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _fake_items():
    """One fresh, one borderline-old, one ancient, one undated, one garbage-dated."""
    mk = lambda i, pub: {  # noqa: E731
        "id": f"item{i}", "title": f"Article {i}", "link": f"https://x.test/{i}",
        "summary": "", "image": "", "published": pub, "domain": "x.test",
    }
    return [
        mk(1, _iso(1)),        # fresh — always kept
        mk(2, _iso(10)),       # 10 days old — dropped at 7d, kept at 14d
        mk(3, _iso(40)),       # ancient — dropped at 7d and 14d
        mk(4, ""),             # undated — strict policy: dropped
        mk(5, "not a date"),   # unparseable — strict policy: dropped
    ]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(sidecar_app, "_fetch_rss", lambda url: _fake_items())
    return TestClient(app)


def _fetch(client, **extra):
    body = {"urls": ["https://x.test/feed"], "keywords": [], **extra}
    res = client.post("/api/news/fetch", json=body)
    assert res.status_code == 200
    return res.json()


def test_default_seven_day_cutoff(client):
    data = _fetch(client)
    ids = {i["id"] for i in data["items"]}
    assert ids == {"item1"}
    assert data["dropped_old"] == 4
    assert data["max_age_days"] == 7


def test_custom_max_age(client):
    data = _fetch(client, max_age_days=14)
    ids = {i["id"] for i in data["items"]}
    assert ids == {"item1", "item2"}  # undated/garbage still dropped (strict)


def test_zero_disables_filter(client):
    data = _fetch(client, max_age_days=0)
    assert len(data["items"]) == 5
    assert data["dropped_old"] == 0


def test_invalid_max_age_falls_back_to_default(client):
    data = _fetch(client, max_age_days="banana")
    assert data["max_age_days"] == 7
    assert {i["id"] for i in data["items"]} == {"item1"}
