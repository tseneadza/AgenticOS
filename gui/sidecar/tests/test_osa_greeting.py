"""Presence greeting (2026-07-09) — time-of-day buckets + pending clause."""
import random
from datetime import datetime

from gui.sidecar import osa_greeting as g


def _at(hour: int) -> datetime:
    return datetime(2026, 7, 9, hour, 0, 0)


def test_time_of_day_buckets():
    assert g.time_of_day(_at(7)) == "morning"
    assert g.time_of_day(_at(14)) == "afternoon"
    assert g.time_of_day(_at(19)) == "evening"
    assert g.time_of_day(_at(23)) == "late night"
    assert g.time_of_day(_at(3)) == "late night"  # wraps midnight


def test_greeting_is_from_the_right_pool():
    line = g.greeting(now=_at(7), rng=random.Random(0))
    assert line in g._POOLS["morning"]


def test_pending_clause_grammar():
    rng = random.Random(0)
    assert g.greeting(now=_at(14), pending=0, rng=rng).endswith(".")  # no clause
    assert "1 thing for you." in g.greeting(now=_at(14), pending=1, rng=random.Random(0))
    assert "3 things for you." in g.greeting(now=_at(14), pending=3, rng=random.Random(0))
    # Negative/garbage pending never appends a clause.
    assert "for you" not in g.greeting(now=_at(14), pending=-2, rng=random.Random(0))
