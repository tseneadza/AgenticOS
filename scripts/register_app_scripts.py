#!/usr/bin/env python3
"""
Discover and register scripts in all Codehome apps' app.json files.

Scans each app directory for:
  - Shell scripts (.sh files in scripts/ or root)
  - Python scripts (.py files in scripts/ or root)

Then updates each app.json to add discovered scripts to the "scripts" array,
skipping duplicates and preserving existing entries.

Usage:
  python3 register_app_scripts.py [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def find_app_jsons() -> list[Path]:
    """Find all app.json files in ~/Codehome."""
    codehome = Path.home() / "Codehome"
    if not codehome.exists():
        print(f"Error: {codehome} not found")
        sys.exit(1)

    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".DS_Store", "dist", "build"}
    results = []

    def walk(root: Path):
        try:
            for entry in root.iterdir():
                if entry.name in skip_dirs or entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    walk(entry)
                elif entry.name == "app.json":
                    results.append(entry)
        except PermissionError:
            pass

    walk(codehome)
    return results


def discover_scripts(app_path: Path) -> list[dict]:
    """Discover shell and Python scripts in an app directory."""
    scripts = []

    # Look for scripts/ subdirectory or root-level scripts
    script_dirs = []
    if (app_path / "scripts").is_dir():
        script_dirs.append(app_path / "scripts")
    # Also check root-level shell scripts
    script_dirs.append(app_path)

    for script_dir in script_dirs:
        try:
            for item in script_dir.iterdir():
                if item.is_file() and item.name not in {"__init__.py", ".DS_Store"}:
                    if item.suffix in {".sh", ".py", ".ts", ".js"}:
                        rel_path = str(item.relative_to(app_path))
                        scripts.append({
                            "name": item.stem,  # filename without extension
                            "path": rel_path,
                            "description": f"Script: {item.name}",
                        })
        except PermissionError:
            pass

    # Remove duplicates, preserve order
    seen = set()
    unique = []
    for s in scripts:
        if s["path"] not in seen:
            seen.add(s["path"])
            unique.append(s)

    return sorted(unique, key=lambda s: s["name"])


def update_app_json(app_json_path: Path, new_scripts: list[dict], dry_run: bool = False, force: bool = False) -> bool:
    """Update app.json with discovered scripts."""
    try:
        data = json.loads(app_json_path.read_text())
    except Exception as e:
        print(f"  ERROR reading {app_json_path}: {e}")
        return False

    existing_scripts = data.get("scripts") or []
    existing_paths = {s.get("path") for s in existing_scripts}

    # Add new scripts that don't already exist
    added = 0
    for script in new_scripts:
        if script["path"] not in existing_paths:
            existing_scripts.append(script)
            added += 1

    if added == 0 and not force:
        print(f"  (no changes needed)")
        return True

    data["scripts"] = existing_scripts

    if dry_run:
        print(f"  [DRY RUN] Would add {added} scripts")
        print(f"    New total: {len(existing_scripts)} scripts")
        return True

    try:
        app_json_path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"  ✓ Added {added} scripts (total: {len(existing_scripts)})")
        return True
    except Exception as e:
        print(f"  ERROR writing {app_json_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Discover and register scripts in Codehome apps")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without modifying files")
    parser.add_argument("--force", action="store_true", help="Update even if no new scripts found")
    args = parser.parse_args()

    app_jsons = find_app_jsons()
    print(f"Found {len(app_jsons)} app.json files in ~/Codehome\n")

    updated_count = 0
    for app_json_path in sorted(app_jsons):
        app_path = app_json_path.parent
        app_name = app_path.name

        print(f"{app_name}:")
        scripts = discover_scripts(app_path)

        if scripts:
            print(f"  Discovered {len(scripts)} scripts:")
            for s in scripts:
                print(f"    - {s['name']} ({s['path']})")
            if update_app_json(app_json_path, scripts, dry_run=args.dry_run, force=args.force):
                updated_count += 1
        else:
            print(f"  (no scripts found)")

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Updated {updated_count} app.json files")


if __name__ == "__main__":
    main()
