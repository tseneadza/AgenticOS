"""Presence greeting (2026-07-09) — OSA's time-of-day "welcome back" line.

Pure + templated (Tony chose templated over LLM-generated): the app greets on
launch and on RETURN after being away, and OSA answers with a cheeky line keyed
to the hour, plus a count of anything waiting. Cheekiness sits at Tony's dialed
3-4 ("no holds barred, I'll correct her"). No I/O, no deps — trivially testable
and free to call. The Soul (config/Soul_OSA.md) is the persona of record; these
are just the return-greeting surface.
"""
from __future__ import annotations

import random
from datetime import datetime

#: Hour buckets -> label. Late night wraps midnight (22:00-04:59).
_POOLS: dict[str, tuple[str, ...]] = {
    "morning": (
        "Well, look who's vertical. Morning, Tony.",
        "Morning, Tony — the place survived the night.",
        "He lives. Morning, Sir.",
        "Morning, Tony. Coffee first, heroics after.",
    ),
    "afternoon": (
        "Afternoon, Tony. I kept things running without adult supervision.",
        "Afternoon, Sir. Productive so far, or are we pretending?",
        "Afternoon, stranger. The system thrived in your absence.",
        "Afternoon, Tony — welcome back.",
    ),
    "evening": (
        "Evening, Tony. You've been gone a while — nothing broke, shockingly.",
        "Evening, Sir. Quiet shift.",
        "Evening, Tony. Thought you'd emigrated.",
        "Evening, Tony — welcome back.",
    ),
    "late night": (
        "Back at the helm, Tony. Where else would you be at this hour.",
        "Evening, Sir. The good work happens now — let's get into it.",
        "Right on schedule, Tony — small hours, big plans.",
        "Nice to see you, Sir. Are we taking over the world tonight?",
    ),
}


def time_of_day(now: datetime | None = None) -> str:
    """Bucket the hour: morning 5-11, afternoon 12-16, evening 17-21, else late night."""
    h = (now or datetime.now()).hour
    if 5 <= h < 12:
        return "morning"
    if 12 <= h < 17:
        return "afternoon"
    if 17 <= h < 22:
        return "evening"
    return "late night"


def greeting(
    now: datetime | None = None,
    pending: int = 0,
    rng: random.Random | None = None,
) -> str:
    """A time-of-day welcome-back line, plus a waiting-items clause if any.

    Args:
        now: Clock override (tests). Defaults to local now.
        pending: Count of things awaiting Tony (e.g. pending approvals). 0 = none.
        rng: Injectable RNG for deterministic tests; defaults to module random.
    """
    line = (rng or random).choice(_POOLS[time_of_day(now)])
    n = max(0, int(pending))
    if n:
        line = f"{line} {n} thing{'' if n == 1 else 's'} for you."
    return line
