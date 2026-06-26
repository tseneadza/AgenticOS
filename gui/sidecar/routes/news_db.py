"""
MySQL-backed feed + category store for the AgenticOS Web News view.

Everything lives in the `AgenticOS` schema (shared with the task system —
note macOS MySQL is case-insensitive, so `AgenticOS` == `agenticos`).

Self-bootstrapping: ensure_schema() creates the database, the
`news_categories` / `news_feeds` tables, and seeds the default catalogue on
first run. Reads connection config from ~/.agentic-os/.env (never committed).

Connection env vars (same as tasks_db):
    MYSQL_HOST  (default: localhost)
    MYSQL_USER  (default: root)
    MYSQL_PASS  (default: "")
    MYSQL_DB    (default: AgenticOS)
    MYSQL_PORT  (default: 3306)
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env from ~/.agentic-os/.env — never raises if file is absent
load_dotenv(Path.home() / ".agentic-os" / ".env", override=False)

_log = logging.getLogger("agentcos.news_db")

_DB_NAME = os.getenv("MYSQL_DB", "AgenticOS")

# ── connection config ─────────────────────────────────────────────────────────
_CFG = {
    "host":     os.getenv("MYSQL_HOST", "localhost"),
    "user":     os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASS", ""),
    "database": _DB_NAME,
    "port":     int(os.getenv("MYSQL_PORT", "3306")),
}

_AVAILABLE: bool | None = None   # None = not yet checked
_SCHEMA_READY = False


def _connect(use_db: bool = True):
    """Return a new mysql.connector connection. Raises on failure.

    use_db=False connects to the server without selecting a database — needed
    to CREATE DATABASE before it exists.
    """
    import mysql.connector  # type: ignore
    cfg = dict(_CFG)
    if not use_db:
        cfg.pop("database", None)
    return mysql.connector.connect(**cfg)


def is_available() -> bool:
    """True if the MySQL server is reachable. Cached after first check."""
    global _AVAILABLE
    if _AVAILABLE is not None:
        return _AVAILABLE
    try:
        conn = _connect(use_db=False)
        conn.close()
        _AVAILABLE = True
    except Exception as exc:  # noqa: BLE001
        _log.warning("MySQL unavailable — news feed store disabled: %s", exc)
        _AVAILABLE = False
    return _AVAILABLE


def _gen_id(prefix: str = "") -> str:
    """Generate a short random ID with an optional prefix."""
    return (prefix + uuid.uuid4().hex)[:16]


def _slug(name: str) -> str:
    """Convert a name into a URL-safe slug, falling back to a random ID."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or _gen_id()


def _row_to_dict(cursor, row) -> dict:
    """Convert a database row to a dict, normalizing datetimes and booleans."""
    cols = [d[0] for d in cursor.description]
    d = dict(zip(cols, row))
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    # normalise the enabled tinyint to a real bool
    if "enabled" in d and d["enabled"] is not None:
        d["enabled"] = bool(d["enabled"])
    return d


# ── schema + seed ─────────────────────────────────────────────────────────────

_CATEGORIES_DDL = """
CREATE TABLE IF NOT EXISTS news_categories (
    id          VARCHAR(64)  PRIMARY KEY,
    name        VARCHAR(128) NOT NULL UNIQUE,
    color       VARCHAR(16)  NOT NULL DEFAULT '#888780',
    sort_order  INT          NOT NULL DEFAULT 0,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

_FEEDS_DDL = """
CREATE TABLE IF NOT EXISTS news_feeds (
    id           VARCHAR(64)  PRIMARY KEY,
    label        VARCHAR(255) NOT NULL,
    url          VARCHAR(512) NOT NULL,
    category_id  VARCHAR(64)  NOT NULL,
    enabled      TINYINT(1)   NOT NULL DEFAULT 1,
    sort_order   INT          NOT NULL DEFAULT 0,
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_news_feeds_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

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


def ensure_schema() -> None:
    """Create the database, tables, and seed defaults. Idempotent + cheap after first."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    # 1. Create the database if it doesn't exist (connect without selecting one).
    conn = _connect(use_db=False)
    try:
        cur = conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{_DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        conn.commit()
    finally:
        conn.close()

    # 2. Create tables + seed inside the database.
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(_CATEGORIES_DDL)
        cur.execute(_FEEDS_DDL)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM news_categories")
        if cur.fetchone()[0] == 0:
            cur.executemany(
                "INSERT INTO news_categories (id, name, color, sort_order) VALUES (%s,%s,%s,%s)",
                _SEED_CATEGORIES,
            )
            cur.executemany(
                "INSERT INTO news_feeds (id, label, category_id, url, sort_order) "
                "VALUES (%s,%s,%s,%s,0)",
                _SEED_FEEDS,
            )
            conn.commit()
            _log.warning("Seeded %d categories + %d feeds into `%s`.",
                         len(_SEED_CATEGORIES), len(_SEED_FEEDS), _DB_NAME)
    finally:
        conn.close()

    _SCHEMA_READY = True


# ── categories ────────────────────────────────────────────────────────────────

def list_categories() -> list[dict]:
    """Return all news categories ordered by sort_order then name."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name, color, sort_order FROM news_categories ORDER BY sort_order, name")
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
    finally:
        conn.close()


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
    conn = _connect()
    try:
        cur = conn.cursor()
        if sort_order is None:
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM news_categories")
            sort_order = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO news_categories (id, name, color, sort_order) VALUES (%s,%s,%s,%s)",
            (cat_id, name, color, sort_order),
        )
        conn.commit()
        cur.execute("SELECT id, name, color, sort_order FROM news_categories WHERE id=%s", (cat_id,))
        return _row_to_dict(cur, cur.fetchone())
    finally:
        conn.close()


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
    conn = _connect()
    try:
        cur = conn.cursor()
        if fields:
            set_clause = ", ".join(f"{k} = %s" for k in fields)
            cur.execute(
                f"UPDATE news_categories SET {set_clause} WHERE id = %s",
                list(fields.values()) + [cat_id],
            )
            conn.commit()
        cur.execute("SELECT id, name, color, sort_order FROM news_categories WHERE id=%s", (cat_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None
    finally:
        conn.close()


def delete_category(cat_id: str) -> bool:
    """Delete a category and all of its feeds."""
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM news_feeds WHERE category_id = %s", (cat_id,))
        cur.execute("DELETE FROM news_categories WHERE id = %s", (cat_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── feeds ─────────────────────────────────────────────────────────────────────

def list_feeds(enabled_only: bool = False, category_id: str | None = None) -> list[dict]:
    """Return feeds joined to their category. `domain` = category name (kept for
    frontend compatibility); `color` = category color."""
    conn = _connect()
    try:
        cur = conn.cursor()
        where, params = [], []
        if enabled_only:
            where.append("f.enabled = 1")
        if category_id:
            where.append("f.category_id = %s"); params.append(category_id)
        sql = (
            "SELECT f.id, f.label, f.url, f.category_id, f.enabled, f.sort_order, "
            "       c.name AS domain, c.color AS color "
            "FROM news_feeds f LEFT JOIN news_categories c ON f.category_id = c.id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY c.sort_order, f.sort_order, f.label"
        cur.execute(sql, params)
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_feed(feed_id: str) -> dict | None:
    """Fetch a single feed by ID, joined with its category.

    Args:
        feed_id: The unique feed identifier.

    Returns:
        The feed as a dictionary, or None if not found.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT f.id, f.label, f.url, f.category_id, f.enabled, f.sort_order, "
            "       c.name AS domain, c.color AS color "
            "FROM news_feeds f LEFT JOIN news_categories c ON f.category_id = c.id "
            "WHERE f.id = %s",
            (feed_id,),
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None
    finally:
        conn.close()


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
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO news_feeds (id, label, url, category_id, enabled) VALUES (%s,%s,%s,%s,%s)",
            (feed_id, label, url, category_id, 1 if enabled else 0),
        )
        conn.commit()
        return get_feed(feed_id)
    finally:
        conn.close()


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
        fields["enabled"] = 1 if fields["enabled"] else 0
    if not fields:
        return get_feed(feed_id)
    conn = _connect()
    try:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        cur.execute(
            f"UPDATE news_feeds SET {set_clause} WHERE id = %s",
            list(fields.values()) + [feed_id],
        )
        conn.commit()
        return get_feed(feed_id)
    finally:
        conn.close()


def delete_feed(feed_id: str) -> bool:
    """Delete a feed by its ID.

    Args:
        feed_id: The unique feed identifier.

    Returns:
        True if the feed was deleted, False if not found.
    """
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM news_feeds WHERE id = %s", (feed_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
