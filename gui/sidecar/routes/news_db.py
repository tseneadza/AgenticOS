"""
SQLAlchemy-backed feed + category store for the AgenticOS Web News view.

Everything lives in the `agenticos` schema (shared with the task system — note
macOS MySQL is case-insensitive, so `AgenticOS` == `agenticos`). As of Phase
13f this store runs entirely on the shared SQLAlchemy ORM layer
(``gui.sidecar.db`` + ``gui.sidecar.models``); no raw ``mysql.connector`` code
remains.

Self-bootstrapping: ensure_schema() creates the database + all tables (via
``db.init_db()``) and seeds the default catalogue on first run. Connection
config is read from ~/.agentic-os/.env (never committed) by ``gui.sidecar.db``.

Public API (signatures + return shapes are stable — routes/api_news.py depends
on them): is_available, ensure_schema, list_categories, create_category,
update_category, delete_category, list_feeds, get_feed, create_feed,
update_feed, delete_feed.
"""
from __future__ import annotations

import logging
import re
import uuid
from sqlalchemy import func

from gui.sidecar import db as _db
from gui.sidecar.db import get_session
from gui.sidecar.models import NewsCategory, NewsFeed

_log = logging.getLogger("agentcos.news_db")

_SCHEMA_READY = False


def is_available() -> bool:
    """True if the MySQL server is reachable (delegates to gui.sidecar.db)."""
    return _db.is_available()


def _gen_id(prefix: str = "") -> str:
    """Generate a short random ID with an optional prefix."""
    return (prefix + uuid.uuid4().hex)[:16]


def _slug(name: str) -> str:
    """Convert a name into a URL-safe slug, falling back to a random ID."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or _gen_id()


def _cat_to_dict(c: NewsCategory) -> dict:
    """Category row -> dict with the frontend contract keys."""
    return {
        "id": c.id,
        "name": c.name,
        "color": c.color,
        "sort_order": c.sort_order,
    }


def _feed_to_dict(f: NewsFeed, c: NewsCategory | None) -> dict:
    """Feed row (joined to its category) -> dict with the frontend contract.

    `domain` = category name and `color` = category color are kept for
    frontend compatibility; `enabled` is normalised to a real bool.
    """
    return {
        "id": f.id,
        "label": f.label,
        "url": f.url,
        "category_id": f.category_id,
        "enabled": bool(f.enabled),
        "sort_order": f.sort_order,
        "domain": c.name if c else None,
        "color": c.color if c else None,
    }


# ── seed data ─────────────────────────────────────────────────────────────────

# (id, name, color, sort_order)
_SEED_CATEGORIES = [
    ("physics-space",        "Physics & Space",          "#7b9fd4", 1),
    ("biology-life",         "Biology & Life Sciences",  "#7fb069", 2),
    ("ai-ml",                "AI & Machine Learning",    "#d97b4f", 3),
    ("neuroscience",         "Neuroscience",             "#c47bd9", 4),
    ("mathematics",          "Mathematics",              "#e0b84c", 5),
    ("engineering-tech",     "Engineering & Technology", "#4fd9c4", 6),
    ("chemistry-materials",  "Chemistry & Materials",    "#d94f8a", 7),
    ("climate-earth",        "Climate & Earth Science",  "#4fa8d9", 8),
]

# (id, label, category_id, url)
_SEED_FEEDS = [
    ("sciencenews-physics", "Science News – Physics",      "physics-space",       "https://www.sciencenews.org/topic/physics/feed"),
    ("quanta-physics",      "Quanta Magazine",             "physics-space",       "https://www.quantamagazine.org/feed/"),
    ("sciencedaily-space",  "ScienceDaily – Space",        "physics-space",       "https://www.sciencedaily.com/rss/space_time.xml"),
    ("arxiv-physics",       "arXiv – Physics (new)",       "physics-space",       "https://rss.arxiv.org/rss/physics"),
    ("arxiv-hep",           "arXiv – HEP",                 "physics-space",       "https://rss.arxiv.org/rss/hep-ph"),
    ("aa-highlights",       "Astronomy & Astrophysics – Highlights", "physics-space", "https://feeds.feedburner.com/aa_high"),
    ("physorg-astro",       "Phys.org – Astrophysics",     "physics-space",       "https://phys.org/rss-feed/journals/astrophysics"),
    ("astrophiz",           "Astrophiz Podcast",           "physics-space",       "https://astrophiz.com/feed"),
    ("mit-astro",           "MIT News – Astrophysics",     "physics-space",       "https://news.mit.edu/rss/topic/astrophysics"),
    ("sciencedaily-biology","ScienceDaily – Biology",      "biology-life",        "https://www.sciencedaily.com/rss/plants_animals/biology.xml"),
    ("sciencenews-life",    "Science News – Life",         "biology-life",        "https://www.sciencenews.org/topic/life/feed"),
    ("scitechdaily-bio",    "SciTechDaily – Biology",      "biology-life",        "https://scitechdaily.com/feed/"),
    ("arxiv-ai",            "arXiv – AI",                  "ai-ml",               "https://rss.arxiv.org/rss/cs.AI"),
    ("arxiv-ml",            "arXiv – ML",                  "ai-ml",               "https://rss.arxiv.org/rss/cs.LG"),
    ("sciencedaily-ai",     "ScienceDaily – AI",           "ai-ml",               "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml"),
    ("sciencedaily-neuro",  "ScienceDaily – Neuroscience", "neuroscience",        "https://www.sciencedaily.com/rss/mind_brain/neuroscience.xml"),
    ("arxiv-neuro",         "arXiv – Neurons & Cognition", "neuroscience",        "https://rss.arxiv.org/rss/q-bio.NC"),
    ("sciencenews-brain",   "Science News – Brain",        "neuroscience",        "https://www.sciencenews.org/topic/brain-behavior/feed"),
    ("quanta-math",         "Quanta – Math",               "mathematics",         "https://www.quantamagazine.org/mathematics/feed/"),
    ("arxiv-math",          "arXiv – Mathematics",         "mathematics",         "https://rss.arxiv.org/rss/math"),
    ("sciencedaily-math",   "ScienceDaily – Math",         "mathematics",         "https://www.sciencedaily.com/rss/computers_math/mathematics.xml"),
    ("sciencedaily-eng",    "ScienceDaily – Engineering",  "engineering-tech",    "https://www.sciencedaily.com/rss/matter_energy/engineering.xml"),
    ("arxiv-cs-sys",        "arXiv – Systems",             "engineering-tech",    "https://rss.arxiv.org/rss/cs.SY"),
    ("newscientist",        "New Scientist",               "engineering-tech",    "https://www.newscientist.com/feed/home/"),
    ("chemworld",           "Chemistry World",             "chemistry-materials", "https://www.chemistryworld.com/rss"),
    ("sciencedaily-chem",   "ScienceDaily – Chemistry",    "chemistry-materials", "https://www.sciencedaily.com/rss/matter_energy/chemistry.xml"),
    ("arxiv-condmat",       "arXiv – Condensed Matter",    "chemistry-materials", "https://rss.arxiv.org/rss/cond-mat"),
    ("sciencedaily-earth",  "ScienceDaily – Earth",        "climate-earth",       "https://www.sciencedaily.com/rss/earth_climate/earth_science.xml"),
    ("sciencedaily-climate","ScienceDaily – Climate",      "climate-earth",       "https://www.sciencedaily.com/rss/earth_climate/global_warming.xml"),
    ("quanta-earth",        "Quanta – Earth Science",      "climate-earth",       "https://www.quantamagazine.org/earth-science/feed/"),
]


# ── schema + seed ─────────────────────────────────────────────────────────────

def ensure_schema() -> None:
    """Create the database + all tables (via db.init_db) and seed defaults.

    Idempotent + cheap after the first successful run.
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    # Create the database + all ORM tables via the shared SQLAlchemy layer.
    _db.init_db()

    # Seed categories + feeds if the categories table is empty.
    s = get_session()
    try:
        if s.query(NewsCategory).count() == 0:
            for cid, name, color, sort_order in _SEED_CATEGORIES:
                s.add(NewsCategory(id=cid, name=name, color=color, sort_order=sort_order))
            for fid, label, category_id, url in _SEED_FEEDS:
                s.add(NewsFeed(
                    id=fid, label=label, url=url,
                    category_id=category_id, sort_order=0, enabled=True,
                ))
            s.commit()
            _log.warning("Seeded %d categories + %d feeds.",
                         len(_SEED_CATEGORIES), len(_SEED_FEEDS))
    finally:
        s.close()

    _SCHEMA_READY = True


# ── categories ────────────────────────────────────────────────────────────────

def list_categories() -> list[dict]:
    """Return all news categories ordered by sort_order then name."""
    s = get_session()
    try:
        rows = (
            s.query(NewsCategory)
            .order_by(NewsCategory.sort_order, NewsCategory.name)
            .all()
        )
        return [_cat_to_dict(c) for c in rows]
    finally:
        s.close()


def create_category(name: str, color: str = "#888780", sort_order: int | None = None) -> dict:
    """Create a new news category and return it.

    Args:
        name: Category display name.
        color: Hex color string for UI display.
        sort_order: Optional sort position; auto-incremented if None.

    Returns:
        The newly created category as a dictionary.
    """
    cat_id = _slug(name)
    s = get_session()
    try:
        if sort_order is None:
            current_max = s.query(func.max(NewsCategory.sort_order)).scalar()
            sort_order = (current_max or 0) + 1
        cat = NewsCategory(id=cat_id, name=name, color=color, sort_order=sort_order)
        s.add(cat)
        s.commit()
        s.refresh(cat)
        return _cat_to_dict(cat)
    finally:
        s.close()


def update_category(cat_id: str, updates: dict) -> dict | None:
    """Update allowed fields on a news category.

    Args:
        cat_id: The category ID to update.
        updates: Dict of field names to new values (name, color, sort_order).

    Returns:
        The updated category dict, or None if not found.
    """
    allowed = {"name", "color", "sort_order"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    s = get_session()
    try:
        cat = s.get(NewsCategory, cat_id)
        if cat is None:
            return None
        for k, v in fields.items():
            setattr(cat, k, v)
        if fields:
            s.commit()
            s.refresh(cat)
        return _cat_to_dict(cat)
    finally:
        s.close()


def delete_category(cat_id: str) -> bool:
    """Delete a category and all of its feeds. Returns True if a row was removed."""
    s = get_session()
    try:
        s.query(NewsFeed).filter(NewsFeed.category_id == cat_id).delete()
        deleted = (
            s.query(NewsCategory).filter(NewsCategory.id == cat_id).delete()
        )
        s.commit()
        return deleted > 0
    finally:
        s.close()


# ── feeds ─────────────────────────────────────────────────────────────────────

def list_feeds(enabled_only: bool = False, category_id: str | None = None) -> list[dict]:
    """Return feeds joined to their category. `domain` = category name (kept for
    frontend compatibility); `color` = category color."""
    s = get_session()
    try:
        q = (
            s.query(NewsFeed, NewsCategory)
            .outerjoin(NewsCategory, NewsFeed.category_id == NewsCategory.id)
        )
        if enabled_only:
            q = q.filter(NewsFeed.enabled.is_(True))
        if category_id:
            q = q.filter(NewsFeed.category_id == category_id)
        q = q.order_by(
            NewsCategory.sort_order, NewsFeed.sort_order, NewsFeed.label
        )
        return [_feed_to_dict(f, c) for f, c in q.all()]
    finally:
        s.close()


def get_feed(feed_id: str) -> dict | None:
    """Fetch a single feed by ID, joined with its category.

    Args:
        feed_id: The unique feed identifier.

    Returns:
        The feed as a dictionary, or None if not found.
    """
    s = get_session()
    try:
        row = (
            s.query(NewsFeed, NewsCategory)
            .outerjoin(NewsCategory, NewsFeed.category_id == NewsCategory.id)
            .filter(NewsFeed.id == feed_id)
            .first()
        )
        if row is None:
            return None
        f, c = row
        return _feed_to_dict(f, c)
    finally:
        s.close()


def create_feed(label: str, url: str, category_id: str, enabled: bool = True) -> dict:
    """Create a new RSS feed entry and return it.

    Args:
        label: Display label for the feed.
        url: The RSS/Atom feed URL.
        category_id: ID of the category this feed belongs to.
        enabled: Whether the feed is active for fetching.

    Returns:
        The newly created feed as a dictionary.
    """
    feed_id = _gen_id("f")
    s = get_session()
    try:
        s.add(NewsFeed(
            id=feed_id, label=label, url=url,
            category_id=category_id, enabled=bool(enabled),
        ))
        s.commit()
    finally:
        s.close()
    return get_feed(feed_id)


def update_feed(feed_id: str, updates: dict) -> dict | None:
    """Update allowed fields on a feed.

    Args:
        feed_id: The feed ID to update.
        updates: Dict of field names to new values.

    Returns:
        The updated feed dict, or None if not found.
    """
    allowed = {"label", "url", "category_id", "enabled", "sort_order"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if "enabled" in fields:
        fields["enabled"] = bool(fields["enabled"])
    if not fields:
        return get_feed(feed_id)
    s = get_session()
    try:
        feed = s.get(NewsFeed, feed_id)
        if feed is None:
            return None
        for k, v in fields.items():
            setattr(feed, k, v)
        s.commit()
    finally:
        s.close()
    return get_feed(feed_id)


def delete_feed(feed_id: str) -> bool:
    """Delete a feed by its ID.

    Args:
        feed_id: The unique feed identifier.

    Returns:
        True if the feed was deleted, False if not found.
    """
    s = get_session()
    try:
        deleted = s.query(NewsFeed).filter(NewsFeed.id == feed_id).delete()
        s.commit()
        return deleted > 0
    finally:
        s.close()
