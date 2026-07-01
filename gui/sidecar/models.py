"""
Phase 11a — SQLAlchemy ORM models for the AgenticOS FastAPI sidecar.

Defines the tables backing the Project Creation Scaffolding feature:
    projects  — one row per scaffolded project
    ports     — allocation ledger for locally-served app ports

These bind to the shared ``Base`` from ``gui.sidecar.db``. Importing this
module has no side effects and requires no live database, so tests may bind
the same models to an in-memory SQLite engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from gui.sidecar.db import Base


def _utcnow() -> datetime:
    """Return the current UTC time (used as a column default)."""
    return datetime.now(timezone.utc)


class Project(Base):
    """A scaffolded project created by the Project Creation feature."""

    __tablename__ = "projects"

    id = Column(String(128), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    path = Column(String(512), nullable=False, unique=True)
    subfolder = Column(String(128), nullable=True, index=True)
    template = Column(String(128), nullable=False, index=True)
    port = Column(Integer, nullable=True)
    github_repo_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=_utcnow, index=True)
    created_by = Column(String(255), default="osa")

    def __repr__(self) -> str:
        return (
            f"<Project id={self.id!r} name={self.name!r} "
            f"template={self.template!r} path={self.path!r}>"
        )


class Port(Base):
    """Ledger row recording the allocation of a single local port.

    The primary key ``port`` IS the port number — it is not autoincremented.
    """

    __tablename__ = "ports"

    port = Column(Integer, primary_key=True, autoincrement=False)
    app_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), default="allocated")
    allocated_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<Port port={self.port!r} app_id={self.app_id!r} "
            f"status={self.status!r}>"
        )
