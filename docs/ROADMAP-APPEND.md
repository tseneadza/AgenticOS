# Roadmap append — paste into docs/roadmap.md

> **✅ ACCOMPLISHED, RENUMBERED (audited 2026-07-21):** shipped as the theme
> system (`theme.css` skins + View ▸ Theme), menu-bar tray, and Minimize-to-HUD —
> but NOT as "Phase 12/13" (those numbers went to Diagnostics / Launch System).
> Historical record. See `docs/IDEA_LEDGER.md`.

These continue the existing phase numbering (latest shipped ≈ Phase 9–11). Adjust numbers
to match your current head. FR numbers continue from FR-51 (last seen in `lib.rs`).

---

## Phase 12 — Aesthetic System (full-skin theming)   ⬜ planned

Goal: the app can wear multiple looks; one or more are selected at runtime. Pure restyle —
**no functional change**.

- **FR-60** — Token contract + `[data-theme]` blocks. Promote `App.css :root` into
  `theme.css`; add full-skin tokens (`--accent2`, `--sans`, `--radius`, `--border-w`,
  `--glow`) on top of the existing colors. Default theme = terracotta.
- **FR-60a** — Theme persistence (`localStorage agentic-os.theme`) + apply on boot.
- **FR-60b** — Native **View ▸ Theme** submenu drives `window.__agenticOsSetTheme(key)`
  (mirrors the FR-51 `__agenticOsSetView` bridge).
- **FR-60c** — Tokenize remaining hardcoded hex in `ScriptsExplorer.jsx` /
  `WebNewsView.jsx` so every surface follows the theme.
- **Branches:** `aesthetic-base` (infra) → `aesthetic-01-terracotta`, `-02-cyber`,
  `-03-futuristic`, `-04-terminal`. Each look = one additive `[data-theme]` block (no conflicts).
- **Done when:** all selected themes switch live from the menu, persist across relaunch,
  and no view loses behavior.

## Phase 13 — Menu-bar presence & launch-at-login (Bling #1)   ⬜ planned

- **FR-61** — macOS **status-item (menu-bar) OSA icon** via Tauri `tray-icon`. Dropdown:
  governor status · Open full app · Toggle HUD · Run Morning Briefing · Restart sidecar ·
  Launch-at-login toggle · Quit. Reuses the existing menu-event id router.
- **FR-62** — **Launch at login** via `tauri-plugin-autostart` (default on, first-run only;
  toggle in Settings + tray). Window close hides to the menu bar instead of quitting; the
  existing `RunEvent::Exit` sidecar/hub cleanup runs only on real Quit.
- **Done when:** OSA lives in the menu bar, app auto-starts, closing hides-to-tray, Quit cleans up.

## Phase 14 — Minimize-to-HUD (Bling #2)   ⬜ planned

- **FR-63** — Always-on-top **HUD window** (second `WebviewWindow`, `#/hud`, 320×380,
  decorations off, alwaysOnTop, skipTaskbar). Main "Minimize to HUD" ↔ HUD "⤢ expand"
  swap via Tauri events; tray can toggle it independently.
- **FR-63a** — HUD content over the live sidecar: governor "now", runs/approvals/cost
  counters, **inline Allow/Deny** for the top approval, an "ask agent" line, CPU/RAM footer.
  Themed via the same tokens.
- **Done when:** minimize hides main + floats the HUD; HUD shows live status and can action
  an approval; expand restores the full app.

---

### Dependency order
Phase 12 `aesthetic-base` first (carries the token refactor risk) → aesthetic-0X looks in
parallel → Phase 14 HUD → Phase 13 tray/autostart last (most OS-specific).
