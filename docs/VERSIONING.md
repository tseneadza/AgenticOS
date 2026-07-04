# Versioning

One version number, everywhere. Locked with Tony 2026-07-03 after the five
declared versions had drifted to four different values (v0.4 brand badge,
0.2.0 tauri.conf + sidecar, 0.1.0 package.json + Cargo.toml).

## Source of truth

`gui/desktop/package.json` — everything else follows it.

- **GUI displays** (App.jsx sidebar brand, Hud.jsx brand, Settings ▸
  Diagnostics row) import `package.json` directly — always in sync by
  construction, never edit a version string in JSX.
- **Synced files** (rewritten by the script): `src-tauri/tauri.conf.json`,
  `src-tauri/Cargo.toml`, `src-tauri/Cargo.lock` (desktop package entry),
  `gui/sidecar/app.py` (FastAPI `version=`).

## Procedure

```bash
python3 scripts/sync_version.py --bump minor   # completed roadmap phase
python3 scripts/sync_version.py --bump patch   # fix between phases
python3 scripts/sync_version.py --set X.Y.Z    # explicit value
python3 scripts/sync_version.py --check        # CI/pre-commit: exit 1 on drift
```

Then commit the touched files in the same commit as the CHANGELOG entry for
whatever earned the bump.

## Bump policy

- **Minor** per completed roadmap phase (e.g. Phase 13f lands → 0.3.0).
- **Patch** for fixes shipped between phases.
- **Major** reserved for a deliberate 1.0 (feature-complete launch system +
  GUI) — Tony's call.

Never hand-edit a version in a synced file; run the script. If a synced
file's format changes and the script can't find its pattern, it exits with
an error naming the file rather than silently skipping it.
