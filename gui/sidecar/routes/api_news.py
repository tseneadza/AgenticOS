"""
Web News feed + category management routes for AgenticOS.

    GET    /api/news/categories          — list categories (id, name, color, sort_order)
    POST   /api/news/categories          — create a category
    PATCH  /api/news/categories/{id}     — update name/color/sort_order
    DELETE /api/news/categories/{id}     — delete a category (and its feeds)

    GET    /api/news/feeds               — list feeds (joined to category; ?enabled_only, ?category_id)
    POST   /api/news/feeds               — create a feed
    PATCH  /api/news/feeds/{id}          — update a feed
    DELETE /api/news/feeds/{id}          — delete a feed

Backed by MySQL (schema `AgenticOS`, tables news_categories / news_feeds).
Returns 503 if MySQL is unavailable. The schema self-initialises + seeds on
first use.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gui.sidecar.routes import news_db

router = APIRouter()


def _require_db() -> None:
    """Raise HTTP 503 if the MySQL news database is unavailable."""
    if not news_db.is_available():
        raise HTTPException(503, "MySQL unavailable — check ~/.agentic-os/.env")
    news_db.ensure_schema()  # idempotent; cheap after first call


# ── request models ────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    """Request body for creating a news category."""

    name: str
    color: str = "#888780"
    sort_order: int | None = None


class CategoryUpdate(BaseModel):
    """Request body for updating a news category (all fields optional)."""

    name: str | None = None
    color: str | None = None
    sort_order: int | None = None


class FeedCreate(BaseModel):
    """Request body for creating a new RSS feed entry."""

    label: str
    url: str
    category_id: str
    enabled: bool = True


class FeedUpdate(BaseModel):
    """Request body for updating an RSS feed entry (all fields optional)."""

    label: str | None = None
    url: str | None = None
    category_id: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


# ── categories ────────────────────────────────────────────────────────────────

@router.get("/api/news/categories")
def list_categories() -> dict:
    """Return all news categories with count."""
    _require_db()
    cats = news_db.list_categories()
    return {"categories": cats, "count": len(cats)}


@router.post("/api/news/categories", status_code=201)
def create_category(body: CategoryCreate) -> dict:
    """Create a new news category."""
    _require_db()
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    try:
        cat = news_db.create_category(body.name.strip(), body.color, body.sort_order)
    except Exception as exc:  # noqa: BLE001 — likely a duplicate name
        raise HTTPException(409, f"Could not create category: {exc}") from exc
    return {"category": cat}


@router.patch("/api/news/categories/{cat_id}")
def update_category(cat_id: str, body: CategoryUpdate) -> dict:
    """Update a news category's name, color, or sort order."""
    _require_db()
    cat = news_db.update_category(cat_id, body.model_dump(exclude_none=True))
    if not cat:
        raise HTTPException(404, f"Category '{cat_id}' not found")
    return {"category": cat}


@router.delete("/api/news/categories/{cat_id}", status_code=204)
def delete_category(cat_id: str) -> None:
    """Delete a news category and all its associated feeds."""
    _require_db()
    if not news_db.delete_category(cat_id):
        raise HTTPException(404, f"Category '{cat_id}' not found")


# ── feeds ─────────────────────────────────────────────────────────────────────

@router.get("/api/news/feeds")
def list_feeds(enabled_only: bool = False, category_id: str | None = None) -> dict:
    """Return RSS feeds, optionally filtered by enabled status or category."""
    _require_db()
    feeds = news_db.list_feeds(enabled_only=enabled_only, category_id=category_id)
    return {"feeds": feeds, "count": len(feeds)}


@router.post("/api/news/feeds", status_code=201)
def create_feed(body: FeedCreate) -> dict:
    """Create a new RSS feed entry."""
    _require_db()
    if not body.label.strip() or not body.url.strip():
        raise HTTPException(400, "label and url are required")
    feed = news_db.create_feed(body.label.strip(), body.url.strip(), body.category_id, body.enabled)
    return {"feed": feed}


@router.patch("/api/news/feeds/{feed_id}")
def update_feed(feed_id: str, body: FeedUpdate) -> dict:
    """Update an RSS feed's label, URL, category, or enabled status."""
    _require_db()
    if not news_db.get_feed(feed_id):
        raise HTTPException(404, f"Feed '{feed_id}' not found")
    feed = news_db.update_feed(feed_id, body.model_dump(exclude_none=True))
    return {"feed": feed}


@router.delete("/api/news/feeds/{feed_id}", status_code=204)
def delete_feed(feed_id: str) -> None:
    """Delete an RSS feed entry."""
    _require_db()
    if not news_db.delete_feed(feed_id):
        raise HTTPException(404, f"Feed '{feed_id}' not found")

# ── ranking ───────────────────────────────────────────────────────────────────

class ArticleForRanking(BaseModel):
    """Schema for a single article submitted for AI ranking."""

    title: str
    url: str | None = None
    content: str | None = None
    source: str | None = None


class RankRequest(BaseModel):
    """Request body for AI-powered article ranking."""

    articles: list[ArticleForRanking]
    domains: list[str] | None = None
    keywords: list[str] | None = None


@router.post("/api/news/rank")
def rank_articles(body: RankRequest) -> dict:
    """AI-rank articles via the app's active model."""
    _require_db()
    
    if not body.articles:
        raise HTTPException(400, "articles list cannot be empty")
    
    try:
        # Import here to avoid circular imports
        from core.llm import get_default_model
        
        # Build a prompt for ranking
        articles_text = "\n".join([
            f"- Title: {a.title}\n  URL: {a.url or 'N/A'}\n  Source: {a.source or 'N/A'}"
            for a in body.articles
        ])
        
        keywords_text = ", ".join(body.keywords) if body.keywords else "science, technology"
        
        prompt = f"""Rank the following articles by relevance and quality. Return a JSON array with titles and scores (0-1).

Keywords of interest: {keywords_text}

Articles:
{articles_text}

Return ONLY valid JSON in this format:
{{"ranked_articles": [{{"title": "...", "score": 0.95}}, ...]}}"""
        
        model = get_default_model()
        response = model.invoke(prompt)
        
        # Parse the response
        import json
        try:
            result = json.loads(response.content if hasattr(response, 'content') else str(response))
        except json.JSONDecodeError:
            # Fallback: return articles with equal scores
            result = {
                "ranked_articles": [
                    {"title": a.title, "score": 0.5} for a in body.articles
                ]
            }
        
        return result
        
    except Exception as exc:
        raise HTTPException(500, f"Ranking failed: {exc}") from exc