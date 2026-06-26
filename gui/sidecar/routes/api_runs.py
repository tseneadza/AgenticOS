"""Run history API — exposes workflow run records from MySQL run_history table.

GET  /api/runs          — paginated list of recent runs
GET  /api/runs/{run_id} — single run detail
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/api/runs")
async def list_runs(limit: int = Query(default=20, le=100)):
    """Return the most recent *limit* workflow runs, newest first.

    Each record includes:
      run_id, workflow, status, started_at, finished_at,
      tokens_used, cost_usd, detail (parsed JSON object).

    The ``detail`` field carries context-specific metadata:
    - completed:   {steps: [...]}
    - skipped:     {reason: "..."}
    - failed:      {error: "..."}
    - interrupted: {reason: "..."}
    """
    from core import memory
    rows = memory.recent_runs(limit=limit)
    for row in rows:
        if isinstance(row.get("detail"), str):
            try:
                row["detail"] = json.loads(row["detail"])
            except Exception:
                row["detail"] = {}
    return {"runs": rows}


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Return a single run by ID."""
    from core import memory
    rows = memory.recent_runs(limit=200)
    for row in rows:
        if row.get("run_id") == run_id:
            if isinstance(row.get("detail"), str):
                try:
                    row["detail"] = json.loads(row["detail"])
                except Exception:
                    row["detail"] = {}
            return row
    raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
