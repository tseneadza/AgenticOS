#!/usr/bin/env python3
"""sync_version.py — one version number, everywhere.

Source of truth: gui/desktop/package.json  "version"

Synced targets:
  gui/desktop/src-tauri/tauri.conf.json   "version"
  gui/desktop/src-tauri/Cargo.toml        [package] version
  gui/desktop/src-tauri/Cargo.lock        [[package]] name = "desktop" version
  gui/sidecar/app.py                      FastAPI(..., version="X.Y.Z")

(The GUI brand badges in App.jsx / Hud.jsx and the Settings Diagnostics row
import package.json directly — no sync needed there.)

Usage:
  python scripts/sync_version.py               # sync targets to package.json
  python scripts/sync_version.py --set 0.3.0   # write package.json, then sync
  python scripts/sync_version.py --bump minor  # bump package.json, then sync
  python scripts/sync_version.py --check       # exit 1 if anything is out of sync

Bump policy (locked with Tony 2026-07-03): minor per completed roadmap phase,
patch for fixes in between.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "gui/desktop/package.json"
TAURI_CONF = ROOT / "gui/desktop/src-tauri/tauri.conf.json"
CARGO_TOML = ROOT / "gui/desktop/src-tauri/Cargo.toml"
CARGO_LOCK = ROOT / "gui/desktop/src-tauri/Cargo.lock"
SIDECAR_APP = ROOT / "gui/sidecar/app.py"

SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[\w.]+)?$")


def read_version() -> str:
    return json.loads(PKG.read_text())["version"]


def write_package_json(version: str) -> None:
    data = json.loads(PKG.read_text())
    data["version"] = version
    PKG.write_text(json.dumps(data, indent=2) + "\n")


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("-")[0].split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def sub_or_die(path: Path, pattern: str, repl: str, text: str) -> str:
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"ERROR: version pattern not found in {path} — fix the file or this script.")
    return new


def targets(version: str):
    """Yield (path, current_text, synced_text) for every target file."""
    conf = TAURI_CONF.read_text()
    yield TAURI_CONF, conf, sub_or_die(
        TAURI_CONF, r'^(\s*"version":\s*")[^"]+(")', rf"\g<1>{version}\g<2>", conf)

    toml = CARGO_TOML.read_text()
    yield CARGO_TOML, toml, sub_or_die(
        CARGO_TOML, r'^(version\s*=\s*")[^"]+(")', rf"\g<1>{version}\g<2>", toml)

    if CARGO_LOCK.exists():
        lock = CARGO_LOCK.read_text()
        yield CARGO_LOCK, lock, sub_or_die(
            CARGO_LOCK,
            r'(\[\[package\]\]\nname = "desktop"\nversion = ")[^"]+(")',
            rf"\g<1>{version}\g<2>", lock)

    app = SIDECAR_APP.read_text()
    yield SIDECAR_APP, app, sub_or_die(
        SIDECAR_APP, r'(FastAPI\([^)]*version=")[^"]+(")', rf"\g<1>{version}\g<2>", app)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--set", dest="set_to", metavar="X.Y.Z")
    g.add_argument("--bump", choices=["major", "minor", "patch"])
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.set_to:
        if not SEMVER.match(args.set_to):
            sys.exit(f"ERROR: '{args.set_to}' is not a semver version.")
        write_package_json(args.set_to)
    elif args.bump:
        write_package_json(bump(read_version(), args.bump))

    version = read_version()
    drift = []
    for path, current, synced in targets(version):
        if current != synced:
            drift.append(path)
            if not args.check:
                path.write_text(synced)

    rel = lambda p: p.relative_to(ROOT)
    if args.check:
        if drift:
            print(f"OUT OF SYNC with package.json ({version}):")
            for p in drift:
                print(f"  {rel(p)}")
            sys.exit(1)
        print(f"✓ all versions in sync at {version}")
    else:
        for p in drift:
            print(f"  synced {rel(p)}")
        print(f"✓ version {version} everywhere")


if __name__ == "__main__":
    main()
