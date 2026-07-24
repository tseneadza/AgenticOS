---
name: theme-integrity
description: >
  Required procedure for ANY change to AgenticOS themes, design tokens, or the
  native View menu: adding/editing a theme or theme variant, touching
  gui/desktop/src/theme.css / theme.js / App.css tokens, editing the View ▸
  Theme menu in lib.rs, restyling components, or debugging "theme doesn't
  show / looks unchanged / theme missing from menu" reports. Trigger on:
  theme, dark mode, light mode, skin, design token, --radius, --glow,
  color-mix, View menu, "themes look wrong", "styles not showing".
---

# Theme integrity — the three-way sync and its tripwires

## Why this skill exists (the 2026-07-24 mishap)

Light variants of all 4 themes sat fully implemented in `theme.css` +
`theme.js` for weeks while the native **View ▸ Theme menu in `lib.rs` still
listed only the 4 legacy dark ids** — so users saw "only dark themes."
Simultaneously, the FR-60 token contract (`--radius`, `--glow`, …) was
defined but almost unconsumed (`var(--radius)` used ONCE app-wide), so theme
switching changed colors but never shape/elevation. Both failures were
invisible: no error, no failing test. Undefined or unexposed theme plumbing
**fails silently**.

## The three sync points — a theme exists only if it's in ALL THREE

| # | Surface | File | What it owns |
|---|---------|------|--------------|
| 1 | Token blocks | `gui/desktop/src/theme.css` | `[data-theme="<key>"] { … }` — the full token contract per variant |
| 2 | Registry | `gui/desktop/src/theme.js` | `THEMES` (key + label), persistence, `applyTheme` |
| 3 | Native menu | `gui/desktop/src-tauri/src/lib.rs` | `MenuItem::with_id(app, "theme-<key>", "<label>", …)` — the ONLY user-facing switcher |

**Adding or renaming a variant touches all three in the same change.** A key
in 1+2 but not 3 is unreachable (the exact mishap). Labels in 3 must match
labels in 2 (tested).

## Non-negotiable steps for any theme/token change

1. **Run the tripwires first and last:**
   `cd gui/desktop && npx vitest run src/__tests__/themeIntegrity.test.js`
   They enforce: THEMES↔theme.css parity (both directions), THEMES↔lib.rs
   menu parity (both directions), label match, per-theme token-contract
   completeness (every block defines all 16 contract tokens — a missing one
   silently inherits terra), no undefined `var(--x)` in App.css/theme.css,
   and a token-adoption floor (`--radius`/`--radius-sm` usage counts).
2. **New token?** Define it in `theme.css` in the `:root` base block AND in
   every `[data-theme]` block (or derive it with `calc(var(--base)…)` once in
   `:root`, like `--radius-sm`). Then add it to `REQUIRED` in
   `themeIntegrity.test.js` and the table in
   `docs/gui-frontend-conventions.md`.
3. **Token mapping rules** (from the adoption pass, commit b53249d):
   panels/cards → `var(--radius)`; chips/inputs/badges → `var(--radius-sm)`;
   elevation shadows → `box-shadow: var(--glow)`; semantic hues stay fixed
   but their backgrounds derive via
   `color-mix(in srgb, <hue> 14%, var(--bg-inset))`; pills (`50%`/`999px`)
   and hairline radii (≤2px) stay literal. Never invent a `var(--x)` that
   isn't defined — it fails silently.
4. **lib.rs changed? cargo check on-device, then a REBUILD is required.**
   Menu items are Rust: they will NOT appear under an already-running app or
   stale bundle. `cd gui/desktop/src-tauri && cargo check`, then
   `npm run tauri -- build --debug --bundles app`.

## "It looks unchanged" debugging order (before touching any code)

1. Which binary is running? `open` silently focuses an installed
   `/Applications/Agentic OS.app` over a fresh debug build —
   `pkill -f '/Applications/Agentic OS.app'` first.
2. Frontend edits hot-reload ONLY under `npm run tauri dev`; installed
   bundles serve compiled assets until rebuilt.
3. Rust/menu/config changes need a recompile even under dev.
4. Only then suspect the CSS — and check for undefined `var(--x)` (silent!)
   before anything else: `npx vitest run src/__tests__/themeIntegrity.test.js`.

## Definition of done for theme work

- [ ] themeIntegrity suite green + full `npx vitest run` green.
- [ ] All three sync points updated in the same commit.
- [ ] `docs/gui-frontend-conventions.md` + `docs/CHANGELOG.md` updated if the
      contract changed.
- [ ] On-device visual pass: flip every variant from View ▸ Theme (all views
      + HUD) in a freshly rebuilt bundle.
