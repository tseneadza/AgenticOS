"""
Phase 11a + Phase 13a — SQLAlchemy ORM models for the AgenticOS FastAPI sidecar.

Phase 11a tables (Project Creation Scaffolding):
    projects  — one row per scaffolded/discovered project
    ports     — allocation ledger for locally-served app ports

Phase 13a tables (Data-Driven App Launch System):
    app_commands        — ordered launch steps per app (command + args + cwd)
    app_processes       — running-process tracking (pid, port, status, health)
    app_health_checks   — optional per-app/port health endpoint config
    port_collision_log  — audit trail for port collisions (backfill/runtime)

Design notes (deviations from the Phase 13 design doc, locked with Tony
2026-07-02):
  * No MySQL ENUMs — portable ``String`` columns validated in the Python
    layer (``launch_config.py``), so the in-memory-SQLite test pattern keeps
    working. Valid value sets live in ``launch_config`` constants.
  * ``ports.port`` stays the primary key (no surrogate ``id``) — equivalent
    to the doc's ``UNIQUE(port)`` and avoids a destructive PK migration on
    the 28 live rows.
  * No DB-level FK ``ports.app_id -> projects.id`` — the ledger legitimately
    holds service ports (agenticos-sidecar, dreamcatcher-backend) that have
    no projects row. Integrity is enforced in the Python layer.

These bind to the shared ``Base`` from ``gui.sidecar.db``. Importing this
module has no side effects and requires no live database, so tests may bind
the same models to an in-memory SQLite engine.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

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
    venv_path = Column(String(512), nullable=True)  # Phase 13a
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
    __table_args__ = (
        UniqueConstraint("app_id", "port_type", name="uk_app_port_type"),
    )

    port = Column(Integer, primary_key=True, autoincrement=False)
    app_id = Column(String(128), nullable=False, index=True)
    # Phase 13a: frontend | backend | api | admin | other (validated in Python)
    port_type = Column(String(32), nullable=False, default="api", index=True)
    status = Column(String(32), default="allocated")
    allocated_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<Port port={self.port!r} app_id={self.app_id!r} "
            f"type={self.port_type!r} status={self.status!r}>"
        )


class AppCommand(Base):
    """One ordered launch step for an app (Phase 13a).

    ``args`` is a JSON array supporting template variables resolved by
    ``launch_config.build_launch_command``: ``{app_path}``, ``{venv_path}``
    and ``{<port_type>_port}`` (e.g. ``{backend_port}``).
    """

    __tablename__ = "app_commands"
    __table_args__ = (
        UniqueConstraint("app_id", "step_order", name="uk_app_step"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(String(128), nullable=False, index=True)
    step_order = Column(Integer, nullable=False)
    command = Column(String(255), nullable=False)
    args = Column(JSON, nullable=True)                 # JSON array of strings
    working_directory = Column(String(512), nullable=True)  # relative to app root
    port_type = Column(String(32), nullable=True)      # which port this step serves
    port_variable_name = Column(String(128), nullable=True)
    environment_json = Column(JSON, nullable=True)     # {"KEY": "value"} (templated)
    wait_for_completion = Column(Boolean, nullable=False, default=False)
    wait_for_port = Column(Boolean, nullable=False, default=False)
    wait_for_port_timeout_seconds = Column(Integer, nullable=False, default=30)
    health_check_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<AppCommand app_id={self.app_id!r} step={self.step_order!r} "
            f"command={self.command!r}>"
        )


class AppProcess(Base):
    """A launched (or previously launched) process for an app (Phase 13a)."""

    __tablename__ = "app_processes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(String(128), nullable=False, index=True)
    pid = Column(Integer, nullable=False, index=True)
    # frontend | backend | api | admin | migration | other
    process_type = Column(String(32), nullable=False, default="other")
    port = Column(Integer, nullable=True)
    started_at = Column(DateTime, default=_utcnow, index=True)
    stopped_at = Column(DateTime, nullable=True)
    # running | stopped | error
    status = Column(String(32), nullable=False, default="running", index=True)
    exit_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    log_path = Column(String(512), nullable=True)
    child_pids = Column(JSON, nullable=True)           # informational only —
    # cleanup uses process-group kill (killpg), not child-PID chasing
    health_check_url = Column(String(255), nullable=True)
    last_health_check = Column(DateTime, nullable=True)
    is_healthy = Column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return (
            f"<AppProcess app_id={self.app_id!r} pid={self.pid!r} "
            f"port={self.port!r} status={self.status!r}>"
        )


class AppHealthCheck(Base):
    """Optional health-endpoint config per (app, port) (Phase 13a)."""

    __tablename__ = "app_health_checks"
    __table_args__ = (
        UniqueConstraint("app_id", "port", name="uk_app_port"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    app_id = Column(String(128), nullable=False, index=True)
    port = Column(Integer, nullable=False, index=True)
    endpoint = Column(String(255), nullable=False, default="/health")
    method = Column(String(8), nullable=False, default="GET")   # GET | POST
    expected_status_code = Column(Integer, nullable=False, default=200)
    timeout_seconds = Column(Integer, nullable=False, default=5)
    interval_seconds = Column(Integer, nullable=False, default=10)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"<AppHealthCheck app_id={self.app_id!r} port={self.port!r} "
            f"endpoint={self.endpoint!r}>"
        )


class PortCollisionLog(Base):
    """Audit trail for port collisions found during backfill/allocation/runtime."""

    __tablename__ = "port_collision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    port = Column(Integer, nullable=False, index=True)
    app_id_1 = Column(String(128), nullable=True)
    app_id_2 = Column(String(128), nullable=True)
    discovered_at = Column(DateTime, default=_utcnow, index=True)
    phase = Column(String(50), nullable=True)          # backfill | allocation | runtime
    notes = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PortCollisionLog port={self.port!r} "
            f"apps=({self.app_id_1!r}, {self.app_id_2!r}) resolved={self.resolved!r}>"
        )
