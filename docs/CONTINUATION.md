# Continuation note

**2026-06-29 — Phase 13 complete, ready for commit**

## Completed this session
- **Tray icon fix (FR-61):** macOS Tahoe "Allow in Menu Bar" permission was
  defaulting to OFF. Tray now works with signed `.app` bundle.
- **First-launch onboarding (FR-61b):** native macOS dialog (osascript) on
  first launch guides user to enable tray in System Settings. Marker file:
  `~/Codehome/AgenticOS/data/.tray_onboarding_shown`.
- **Close-to-hide (FR-62 enhancement):** closing the window hides it instead
  of quitting. App stays resident behind tray icon. Added
  `RunEvent::ExitRequested → api.prevent_exit()` to the run handler.
- **Installed to /Applications:** debug build copied and signed.
- **CLAUDE.md updated** with lessons 8–11 (Tahoe permission, close-to-hide,
  `open` reuse, install flow).

## Files changed (uncommitted — NEED COMMIT)
- `CLAUDE.md` — new lessons 8–11
- `gui/desktop/src-tauri/src/lib.rs` — tray builder, onboarding dialog, ExitRequested handler
- `gui/desktop/src-tauri/capabilities/default.json` — core:tray:default, core:menu:default
- `gui/desktop/src-tauri/Cargo.toml` — tray-icon feature
- `gui/desktop/src-tauri/Cargo.lock` — lockfile update
- `gui/desktop/src-tauri/tauri.conf.json` — window config changes
- `gui/desktop/src/App.css` — style updates
- `gui/desktop/src/App.jsx` — component updates
- `gui/desktop/src/main.jsx` — entry point updates
- `gui/desktop/src/theme.css` — new (FR-60 design tokens)
- `gui/desktop/src/theme.js` — new (theme switching)
- `gui/desktop/src/Hud.jsx` — new (HUD window)
- `gui/desktop/src/components/DiagnosticsPanel.jsx` — updates
- `gui/desktop/src/components/ScriptsExplorer.jsx` — updates
- `gui/desktop/src/components/WebNewsView.jsx` — updates
- `docs/CONTINUATION.md` — this file

## Untracked files (decide whether to commit)
- `gui/desktop/src-tauri/icons/tray.png` — OSA monogram 32x32 (not yet wired up)
- `gui/desktop/src-tauri/icons/32x32.png.bak` — backup of original icon
- `docs/IMPLEMENTATION-PLAN.md`, `docs/ROADMAP-APPEND.md` — planning docs
- `data/` — runtime data directory (should be in .gitignore)
- `AgenticOS Enhanced copy.pdf`, `menubar_right.png`, `menubar_test.png` — temp files (don't commit)

## Next steps (next session)
1. **Commit all Phase 12/13/14 changes** — stage the modified + new files above,
   skip the temp files. Suggested message:
   `"feat: Phase 12-14 — themes, HUD, tray icon, close-to-hide, onboarding (FR-60/61/62)"`
2. **Replace icons/32x32.png** with proper OSA monogram (currently still Gemini logo)
3. **Wire up tray.png** as the tray-specific icon (white on transparent, template-style)
4. **Update docs/roadmap.md** — mark Phase 13 complete
5. **Update docs/CHANGELOG.md** — log all FR-60/61/62 changes
6. **Add `data/` to .gitignore** — runtime data shouldn't be tracked
