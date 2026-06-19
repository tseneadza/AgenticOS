"""Brain2 agent — reads vault state and writes outputs back to the vault."""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import re
from pathlib import Path

import yaml

from tools import filesystem_tool as fs

CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "settings.yaml").read_text()
)["settings"]
VAULT = Path(CONFIG["vault_path"])


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return {}


def _doc_hash(text: str) -> str:
    """Stable content identity for a note, ignoring any frontmatter block.

    The raw-note processor prepends `--- ... ---` frontmatter when it files a
    note, so hashing the body only lets a raw note and its filed copy resolve
    to the same identity.
    """
    m = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
    body = text[m.end():] if m else text
    body = re.sub(r"\s+", " ", body).strip()
    return hashlib.sha1(body.encode("utf-8")).hexdigest()


def _recent_docs(since_ts: float, seen: set[str] | None = None) -> list[dict]:
    """Vault `.md` files created at or after *since_ts*, newest first.

    "Created" uses the filesystem birth time (st_birthtime on macOS/APFS),
    falling back to mtime where birth time is unavailable. Auto-generated
    briefing/session outputs and the vault index are skipped so the brief
    never lists itself. Docs whose content hash is in *seen* (already surfaced
    in a prior brief) or duplicated within this batch (e.g. a raw note and its
    filed copy) are dropped, keeping the newest instance.
    """
    seen = seen or set()
    cfg = CONFIG.get("briefing", {})
    exclude = set(
        cfg.get(
            "recent_exclude_folders",
            ["06 - Archive", "Templates", ".obsidian", ".git", ".trash"],
        )
    )
    max_items = int(cfg.get("recent_max_items", 30))

    candidates: list[dict] = []
    for root, dirs, files in os.walk(VAULT):
        # Prune excluded + hidden directories in-place so we don't descend them.
        dirs[:] = [d for d in dirs if d not in exclude and not d.startswith(".")]
        rel_root = Path(root).relative_to(VAULT)
        top = rel_root.parts[0] if rel_root.parts else ""
        if top in exclude:
            continue
        for fn in files:
            if not fn.endswith(".md") or fn == "index.md":
                continue
            if fn.endswith("Morning Briefing.md") or fn.endswith("Session Report.md"):
                continue
            path = Path(root) / fn
            try:
                st = path.stat()
                created = getattr(st, "st_birthtime", st.st_mtime)
                if created < since_ts:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            candidates.append(
                {
                    "title": fn[:-3],
                    "path": str(path.relative_to(VAULT)),
                    "folder": "" if str(rel_root) == "." else str(rel_root),
                    "created": dt.datetime.fromtimestamp(created).isoformat(
                        timespec="seconds"
                    ),
                    "hash": _doc_hash(text),
                    "_ts": created,
                }
            )

    candidates.sort(key=lambda d: d["_ts"], reverse=True)
    out: list[dict] = []
    batch: set[str] = set()
    for d in candidates:
        h = d["hash"]
        if h in seen or h in batch:
            continue
        batch.add(h)
        d.pop("_ts", None)
        out.append(d)
        if len(out) >= max_items:
            break
    return out


def read_focus_and_queue(state: dict) -> dict:
    """Scan the vault: active projects, raw-note queue, open tasks."""
    projects = []
    projects_dir = VAULT / "01 - Projects"
    if projects_dir.exists():
        for name in fs.list_directory(str(projects_dir)):
            if not name.endswith(".md"):
                continue
            meta = _frontmatter(fs.read_text_file(str(projects_dir / name)))
            projects.append(
                {
                    "name": name[:-3],
                    "status": str(meta.get("status", "unknown")),
                    "priority": str(meta.get("priority", "")),
                }
            )

    raw_dir = VAULT / "00 - Raw"
    raw_notes = (
        [n for n in fs.list_directory(str(raw_dir)) if n.endswith(".md")]
        if raw_dir.exists()
        else []
    )

    open_tasks: list[str] = []
    tasks_dir = VAULT / "Tasks"
    if tasks_dir.exists():
        for name in fs.list_directory(str(tasks_dir)):
            if not name.endswith(".md"):
                continue
            for line in fs.read_text_file(str(tasks_dir / name)).splitlines():
                if line.strip().startswith("- [ ]"):
                    open_tasks.append(line.strip()[5:].strip())

    # "Recently created" = docs created since the last completed briefing run
    # (cold start: fall back to a fixed look-back window). See settings.briefing.
    from core import memory as _mem

    brief_cfg = CONFIG.get("briefing", {})
    watermark_wf = brief_cfg.get("recent_watermark_workflow", "morning-briefing")
    fallback_hours = float(brief_cfg.get("recent_fallback_hours", 24))
    since_ts = _mem.last_run_at(watermark_wf)
    cold_start = since_ts is None
    if since_ts is None:
        since_ts = dt.datetime.now().timestamp() - fallback_hours * 3600
    recent = _recent_docs(since_ts, _mem.seen_doc_hashes())

    return {
        "projects": projects,
        "raw_note_count": len(raw_notes),
        "raw_notes": raw_notes,
        "open_tasks": open_tasks[:20],
        "recent_docs": recent,
        "recent_doc_count": len(recent),
        "recent_since": dt.datetime.fromtimestamp(since_ts).isoformat(timespec="seconds"),
        "recent_cold_start": cold_start,
        "scanned_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def write_to_reflections(state: dict) -> dict:
    """Write the generated brief to 04 - Reflections/."""
    brief = state["outputs"]["generate_brief"]["brief"]
    today = dt.date.today().isoformat()
    target = VAULT / "04 - Reflections" / f"{today} - Morning Briefing.md"
    written = fs.write_file(str(target), brief)
    # Remember which docs we just surfaced so they don't reappear as "new" if
    # they later move folders (e.g. raw-note processing rewrites the file with
    # a fresh creation timestamp). Done here, post-write, so a failed brief
    # never burns a doc's one-and-only appearance.
    from core import memory as _mem

    surfaced = state["outputs"].get("read_vault", {}).get("recent_docs", [])
    marked = _mem.mark_docs_briefed(surfaced)
    return {"written_to": written, "docs_marked_briefed": marked}


def write_test_note(state: dict) -> dict:
    """Approval-demo workflow: write a throwaway note (gated by HITL)."""
    today = dt.datetime.now().isoformat(timespec="seconds")
    target = VAULT / "06 - Archive" / "agentic-os-approval-test.md"
    written = fs.write_file(
        str(target),
        f"# Approval Demo\n\nWritten by Agentic OS after human approval at {today}.\n",
    )
    return {"written_to": written}


# ================================================================ Phase 5

# ---------------------------------------------------------------- FR-13: process-raw-notes

_RAW_NOTE_TYPES = {
    "project": "01 - Projects",
    "task": "Tasks",
    "learning": "02 - Learning",
    "reflection": "04 - Reflections",
    "resource": "05 - Resources",
    "reference": "03 - Reference",
}

_RAW_KEYWORDS: dict[str, list[str]] = {
    "project": ["project", "build", "ship", "launch", "prd", "roadmap"],
    "task": ["todo", "task", "action", "follow up", "follow-up", "do:"],
    "learning": ["learn", "how to", "question", "explore", "research", "understand"],
    "reflection": ["journal", "reflection", "retro", "retrospective", "feeling", "today"],
    "resource": ["resource", "link", "article", "book", "video", "podcast", "read"],
}


def _classify_note(content: str, filename: str) -> str:
    text = (filename + " " + content).lower()
    scores: dict[str, int] = {t: 0 for t in _RAW_NOTE_TYPES}
    for note_type, keywords in _RAW_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[note_type] += 1
    best = max(scores, key=lambda k: scores[k])
    return _RAW_NOTE_TYPES.get(best, "03 - Reference")


def scan_raw_notes(state: dict) -> dict:
    raw_dir = VAULT / "00 - Raw"
    if not raw_dir.exists():
        return {"raw_notes": [], "raw_count": 0}
    notes = [n for n in fs.list_directory(str(raw_dir)) if n.endswith(".md")]
    return {"raw_notes": notes, "raw_count": len(notes)}


def process_each_raw_note(state: dict) -> dict:
    raw_dir = VAULT / "00 - Raw"
    archive_dir = VAULT / "06 - Archive" / "processed-raw"
    notes = state.get("outputs", {}).get("scan_raw", {}).get("raw_notes", [])
    results = []
    for filename in notes:
        src = raw_dir / filename
        try:
            content = fs.read_text_file(str(src))
        except Exception:
            results.append({"file": filename, "status": "read_error"})
            continue

        dest_folder = _classify_note(content, filename)

        if not content.startswith("---"):
            today = dt.date.today().isoformat()
            content = f"---\ndate: {today}\nsource: raw\nstatus: active\n---\n\n{content}"

        try:
            fs.write_file(str(VAULT / dest_folder / filename), content)
            fs.write_file(
                str(archive_dir / filename),
                f"# Archived\n\nMoved to `{dest_folder}/{filename}` on {dt.date.today().isoformat()}.\n",
            )
            results.append({"file": filename, "status": "moved", "destination": dest_folder})
        except Exception as exc:
            results.append({"file": filename, "status": "error", "error": str(exc)})

    processed = sum(1 for r in results if r["status"] == "moved")
    return {"processed": processed, "results": results}


# ---------------------------------------------------------------- FR-14: research-learning-notes

def scan_learning_notes(state: dict) -> dict:
    learning_dir = VAULT / "02 - Learning"
    if not learning_dir.exists():
        return {"learning_notes": [], "learning_count": 0}
    to_process = []
    for name in fs.list_directory(str(learning_dir)):
        if not name.endswith(".md"):
            continue
        content = fs.read_text_file(str(learning_dir / name))
        fm = _frontmatter(content)
        if str(fm.get("status", "")).lower() == "processing":
            to_process.append({"filename": name, "title": fm.get("title", name[:-3])})
    return {"learning_notes": to_process, "learning_count": len(to_process)}


def research_each_learning_note(state: dict) -> dict:
    """Mark notes as researched and add Claude's Analysis stub.

    Full LLM research runs via briefing_agent in a follow-on step;
    this action updates frontmatter so notes won't be re-queued.
    """
    learning_dir = VAULT / "02 - Learning"
    notes = state.get("outputs", {}).get("scan_learning", {}).get("learning_notes", [])
    results = []
    for note_meta in notes:
        filename = note_meta["filename"]
        path = learning_dir / filename
        try:
            content = fs.read_text_file(str(path))
        except Exception:
            results.append({"file": filename, "status": "read_error"})
            continue

        updated = re.sub(
            r"^(status:\s*)processing",
            "status: researched",
            content,
            flags=re.MULTILINE,
        )

        if "## Claude's Analysis" not in updated:
            updated += (
                f"\n\n## Claude's Analysis\n\n"
                f"*Research queued {dt.date.today().isoformat()}.*\n"
            )

        try:
            fs.write_file(str(path), updated)
            results.append({"file": filename, "status": "queued"})
        except Exception as exc:
            results.append({"file": filename, "status": "error", "error": str(exc)})

    return {"researched": len([r for r in results if r["status"] == "queued"]), "results": results}


# ---------------------------------------------------------------- FR-15: save-session

def collect_session_summary(state: dict) -> dict:
    from core.memory import Memory
    mem = Memory()
    runs = mem.recent_runs(limit=10)
    projects = []
    projects_dir = VAULT / "01 - Projects"
    if projects_dir.exists():
        for name in fs.list_directory(str(projects_dir)):
            if not name.endswith(".md"):
                continue
            fm = _frontmatter(fs.read_text_file(str(projects_dir / name)))
            if str(fm.get("status", "")).lower() == "active":
                projects.append(fm.get("title", name[:-3]))
    return {
        "recent_runs": [
            {"workflow": r.get("workflow", ""), "status": r.get("status", ""), "cost_usd": r.get("cost_usd", 0)}
            for r in runs
        ],
        "active_projects": projects,
        "session_date": dt.date.today().isoformat(),
    }


def write_session_report(state: dict) -> dict:
    data = state.get("outputs", {}).get("collect_session", {})
    today = dt.date.today().isoformat()
    runs = data.get("recent_runs", [])
    projects = data.get("active_projects", [])
    total_cost = sum(r.get("cost_usd", 0) for r in runs)
    completed = sum(1 for r in runs if r.get("status") == "completed")
    failed = sum(1 for r in runs if r.get("status") not in ("completed", "running"))

    run_lines = [f"- {r['workflow']} — {r['status']} (${r['cost_usd']:.4f})" for r in runs]
    project_lines = [f"- {p}" for p in projects] if projects else ["- (none)"]

    lines = [
        "---", f"date: {today}", "type: session-report", "---", "",
        f"# Session Report — {today}", "",
        "## Workflows Run",
        *run_lines,
        "",
        f"**Total cost this session:** ${total_cost:.4f}",
        f"**Completed:** {completed}  **Failed:** {failed}", "",
        "## Active Projects",
        *project_lines,
        "",
        "## Next Day Focus", "",
        "> *Fill in before closing for tomorrow's morning-briefing context.*", "",
    ]

    target = VAULT / "04 - Reflections" / f"{today} - Session Report.md"
    written = fs.write_file(str(target), "\n".join(lines))
    return {"written_to": written, "total_cost_usd": total_cost}


ACTIONS = {
    "read_focus_and_queue": read_focus_and_queue,
    "write_to_reflections": write_to_reflections,
    "write_test_note": write_test_note,
    # Phase 5 (FR-13–15)
    "scan_raw_notes": scan_raw_notes,
    "process_each_raw_note": process_each_raw_note,
    "scan_learning_notes": scan_learning_notes,
    "research_each_learning_note": research_each_learning_note,
    "collect_session_summary": collect_session_summary,
    "write_session_report": write_session_report,
}
