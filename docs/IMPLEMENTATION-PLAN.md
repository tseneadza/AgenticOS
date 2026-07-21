# Agentic OS — Aesthetic System + Bling Implementation Plan

> **✅ ACCOMPLISHED (audited 2026-07-21):** theming, menu-bar OSA tray, and
> Minimize-to-HUD all shipped (phase numbers diverged — see `ROADMAP-APPEND.md`
> note). Historical record. See `docs/IDEA_LEDGER.md`.

Companion to the `AgenticOS Enhanced.dc.html` mockup. This is the build plan for
landing that mockup's three changes in the real Tauri + React app
(`gui/desktop/`) **without losing any functionality**:

1. **Full-skin theming** — 4 selectable looks, switched from the native **View ▸ Theme** menu.
2. **Bling #1** — a macOS **menu-bar (status-item) OSA icon** + **launch at login**.
3. **Bling #2** — a **minimize-to-HUD** floating, always-on-top mini view.

Plus enhanced **Web News / Scripts / Hub API** views (agentic actions, better states).

---

## 0. Guiding principles

- **Tokens already exist.** Every component styles off CSS variables defined once in
  `gui/desktop/src/App.css` `:root` (`--bg`, `--bg-panel`, `--accent`, `--text`, `--mono`, …).
  Theming is therefore **additive token blocks**, not a rewrite. This is why multiple
  aesthetics can coexist and ship together.
- **No behavior changes in a restyle.** A theme only swaps tokens. Logic, data flow,
  the sidecar contract (`localhost:5130`), AG-UI events, HITL gates, and the dashboard
  registry stay byte-for-byte the same.
- **Switcher lives in the native menu** (your stated choice). The React app exposes a
  hook; `lib.rs` drives it — identical to the existing `window.__agenticOsSetView` bridge.

---

## 1. Branching strategy (`aesthetic-##`)

The app must be able to wear several looks and let one or more win. Structure it so themes
never conflict:

```
main
└── aesthetic-base ............ theme INFRASTRUCTURE only (no new look)
    │   • token contract + [data-theme] plumbing
    │   • View ▸ Theme menu + persistence
    │   • tokenize the last hardcoded hex (see §2.3)
    ├── aesthetic-01-terracotta . refined current look (default)  → ONE [data-theme] block
    ├── aesthetic-02-cyber ....... Cyber Neon                      → ONE [data-theme] block
    ├── aesthetic-03-futuristic .. Bold Futuristic (glass/glow)    → ONE [data-theme] block
    └── aesthetic-04-terminal .... Terminal Green (CRT)            → ONE [data-theme] block
```

**Why this shape**
- `aesthetic-base` merges to `main` first and carries all the risk (token refactor + menu).
- Each `aesthetic-0X` branch adds **only its own `[data-theme="x"] { … }` block** plus an
  entry in the theme registry. Different files / different keys ⇒ **no merge conflicts**.
- Review each look in isolation on its branch; merge the winners. Because each is just one
  additive block, shipping 1 or all 4 is the same effort — the runtime switch already exists.

**Per-branch checklist** (commit to the branch, open PR titled `aesthetic-0X: <name>`):
- [ ] Add `[data-theme="<key>"]` block to `theme.css` (colors + `--mono`/`--sans` + `--radius` + `--border-w` + density).
- [ ] Register `{ key, label, branch }` in `THEMES` (see §2.2).
- [ ] Screenshot all 7 views + HUD in the theme; attach to PR.
- [ ] Verify contrast (WCAG AA on text/bg) and that status colors (green/red/yellow) stay legible.

---

## 2. Phase 12 — Full-skin theme system  (branch: `aesthetic-base`)

### 2.1 Token contract (full skin)
Promote the single `:root` in `App.css` into a documented contract and add the
non-color tokens the mockup proved out:

| Token | Role | terra | cyber | future | term |
|---|---|---|---|---|---|
| `--bg / --bg-panel / --bg-inset` | surfaces | warm dark | near-black | indigo | CRT black |
| `--border / --border-soft` | section borders | `#888780` | teal-grey | violet | green-grey |
| `--text / --text-dim` | type | bone | mint-white | lilac-white | phosphor |
| `--accent / --accent2` | brand + secondary | `#d97b4f` | mint/magenta | violet/cyan | green |
| `--green/--red/--yellow` | status (keep semantic) | … | … | … | … |
| `--sans / --mono` | type system | system/SF Mono | Space Grotesk/JBMono | same | JBMono/JBMono |
| `--radius` | corner shape | 8px | 6px | 14px | 2px |
| `--border-w` | panel weight | 2px | 1px | 1px | 1px |
| `--glow` | elevation | soft | neon ring | indigo glow | hairline |
| `--density-pad / --gap` | spacing | comfy | comfy | comfy | comfy |

> Exact values are in the mockup's `<style>` block — copy them verbatim; they're tuned.

### 2.2 Switching plumbing
- New file `gui/desktop/src/theme.css` — `:root` (default = terra) + four `[data-theme="…"]` blocks. Import once in `main.jsx`.
- New `gui/desktop/src/theme.js`:
  ```js
  export const THEMES = [
    { key:'terra',  label:'Terracotta Dark', branch:'aesthetic-01' },
    { key:'cyber',  label:'Cyber Neon',      branch:'aesthetic-02' },
    { key:'future', label:'Bold Futuristic', branch:'aesthetic-03' },
    { key:'term',   label:'Terminal Green',  branch:'aesthetic-04' },
  ];
  const LS = 'agentic-os.theme';
  export const loadTheme = () => localStorage.getItem(LS) || 'terra';
  export function applyTheme(key){
    document.documentElement.setAttribute('data-theme', key);
    localStorage.setItem(LS, key);
  }
  ```
- In `App.jsx`: on mount `applyTheme(loadTheme())`; expose the bridge for the native menu
  (mirror of the existing `__agenticOsSetView`, see `lib.rs:on_menu_event`):
  ```js
  window.__agenticOsSetTheme = (key) => applyTheme(key);
  ```

### 2.3 Native **View ▸ Theme** menu  (FR-60)
In `src-tauri/src/lib.rs` `build_menu()`, add a Theme submenu under View:
```rust
let t_terra  = MenuItem::with_id(app, "theme-terra",  "Terracotta Dark", true, None::<&str>)?;
let t_cyber  = MenuItem::with_id(app, "theme-cyber",  "Cyber Neon",      true, None::<&str>)?;
let t_future = MenuItem::with_id(app, "theme-future", "Bold Futuristic", true, None::<&str>)?;
let t_term   = MenuItem::with_id(app, "theme-term",   "Terminal Green",  true, None::<&str>)?;
let theme_menu = Submenu::with_items(app, "Theme", true, &[&t_terra,&t_cyber,&t_future,&t_term])?;
// add &theme_menu to the View submenu items
```
Handle generically in `on_menu_event` (same style as `view-`):
```rust
id if id.starts_with("theme-") => {
    let key = &id["theme-".len()..];
    let _ = window.eval(&format!("window.__agenticOsSetTheme && window.__agenticOsSetTheme('{key}')"));
}
```
(Optional: a checkmark on the active theme by rebuilding the menu on change.)

### 2.4 Tokenize the stragglers (the only real refactor)
A handful of components hardcode hex and **won't follow a theme** until tokenized:
- `components/ScriptsExplorer.jsx` → `TYPE_STYLE` bg/colors, output-panel border colors.
- `components/WebNewsView.jsx` → `DEFAULT_CATEGORIES` colors, `ScoreBadge` thresholds.
- Any `#1c3a2a`-style literals → map to `color-mix(in srgb, var(--accent) …%, transparent)` or a new token.
> Category/type **hues** can stay fixed (they encode meaning), but their *backgrounds* should
> derive from tokens so they read on every surface. Mockup shows the `color-mix` pattern.

### 2.5 Acceptance
- [ ] Switch all 4 themes from View ▸ Theme; every view + HUD repaint; choice persists across relaunch.
- [ ] No layout shift beyond intended radius/border/density.
- [ ] Zero functional diffs (runs, approvals, events, registry all behave as before).

---

## 3. Phase 13 — Bling #1: menu-bar OSA icon + launch at login

### 3.1 Menu-bar status item  (FR-61)
macOS "top bar where Ollama/Docker live" = **status items**. Use Tauri 2's tray:
- `Cargo.toml`: `tauri = { version = "2", features = ["tray-icon"] }`.
- Add a template (monochrome) tray icon asset, e.g. `icons/tray.png` (the OSA diamond).
- In `lib.rs` `setup()`:
  ```rust
  use tauri::tray::{TrayIconBuilder};
  let tray_menu = Menu::with_items(app, &[ /* items below */ ])?;
  TrayIconBuilder::new()
      .icon(app.default_window_icon().unwrap().clone())
      .menu(&tray_menu)
      .menu_on_left_click(true)
      .on_menu_event(/* reuse the same id router */)
      .build(app)?;
  ```
- Dropdown items (from your picks):
  - **Governor — now** (status line; non-clickable header, refreshed — see note)
  - **Open full app** → `window.show()` + `set_focus()`
  - **Toggle sidecar HUD** → emits `toggle-hud` (Phase 14)
  - **Run Morning Briefing** → existing `POST /api/workflows/morning-briefing/run`
  - **Restart sidecar** → existing `agent-restart-sidecar` path
  - separator → **Launch at login** (checkbox, §3.2) · **Quit**
  > Live governor status in a native menu needs the menu rebuilt on change. Simplest: a tiny
  > poller in `lib.rs` (or push from the sidecar) that rebuilds the tray menu's header item
  > every ~5s from `GET /api/governor/status`. If that's heavy, ship a static "Open HUD for
  > live status" line first and iterate.

### 3.2 Launch at login  (FR-62)
- Add `tauri-plugin-autostart` (`Cargo.toml` + `.plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))`).
- **Default: ON**, first-run only (so you don't fight a user who turned it off): on first
  launch set a `first_run` flag in app config and `enable()` autostart; thereafter respect
  the user's choice.
- Surface the same toggle in **Settings ▸ Startup** and the tray checkbox; both call the plugin.
- Window close → **hide** instead of quit (so the menu-bar icon stays resident):
  intercept `WindowEvent::CloseRequested`, `api.prevent_close()`, `window.hide()`. Real quit
  is the tray/menu **Quit** item (which runs the existing sidecar/hub cleanup on `Exit`).

### 3.3 Acceptance
- [ ] OSA icon appears in the macOS menu bar; dropdown actions work.
- [ ] App auto-starts at login (default on), toggle in Settings + tray flips it.
- [ ] Closing the window hides to the menu bar; sidecar/hub keep running; Quit cleans up.

---

## 4. Phase 14 — Bling #2: minimize-to-HUD (floating, always-on-top)

### 4.1 Shape
A small always-on-top **HUD window** (your choice: floating HUD) that mirrors the most
time-sensitive surface. Recommended: a **second `WebviewWindow`** rather than resizing main —
it can stay on top while the main window is hidden, and renders a dedicated `/hud` route.

`tauri.conf.json` → add a second window (created hidden):
```json
{ "label": "hud", "url": "index.html#/hud", "width": 320, "height": 380,
  "decorations": false, "alwaysOnTop": true, "skipTaskbar": true,
  "resizable": false, "visible": false, "transparent": true }
```

### 4.2 Toggle behavior  (FR-63)
- Main app **"Minimize to HUD"** button (mockup: sidebar footer) → `hide('main')` + `show('hud')`.
- HUD **⤢ expand** → `hide('hud')` + `show('main')` + focus.
- Tray **Toggle sidecar HUD** → show/hide `hud` independently (HUD can float over the app too).
- Wire via Tauri events (`emit('toggle-hud')`, `WebviewWindow::get`).

### 4.3 HUD content (React `/hud` route — reuses sidecar + AG-UI)
Compact, ~320px. From the mockup (flexible — easy to trim if you don't love an item):
- **Governor "now"** — live workflow + step + token count (AG-UI stream, same as SysOps strip).
- **Counters** — runs in flight · approvals waiting · cost today.
- **Top approval** — inline **Allow / Deny** (the urgent HITL moment, no need to open the app).
- **Ask agent** — one-line prompt box → posts to the governing agent.
- **Footer** — CPU / RAM / sidecar dot.
Same `var(--*)` tokens ⇒ the HUD themes for free.

### 4.4 Acceptance
- [ ] Minimize hides main + shows always-on-top HUD; expand reverses it.
- [ ] HUD shows live governor status and can Allow/Deny an approval against `:5130`.
- [ ] HUD honors the active theme.

---

## 5. Enhanced views (folds into the aesthetic branches)

Keep **all** current functionality; add the agentic actions from the mockup:
- **Web News** (`WebNewsView.jsx`) — keep domains/keywords/AI-rank/density/grid; add **"Summarize top 5"** (one Claude call over ranked items) + a digest card; real skeleton/empty/error states.
- **Scripts** (`ScriptsExplorer.jsx`) — keep filter/sort/group/run/run-log; add **"Wrap as agent tool"** (registers the script as a governed tool with an allowlist entry) in the detail header.
- **Hub API** (`HubApiExplorer.jsx`) — keep the endpoint catalogue; add **Try-it** (method + body + Send → live response), an auth preset (sidecar-local bearer), and **request history**.

---

## 6. Risks & non-goals
- **Risk:** hardcoded hex in two components (§2.4) — contain to `aesthetic-base`, test those views in all 4 themes.
- **Risk:** live governor status in a native tray menu (§3.1) — ship static-first, iterate to polling.
- **Non-goal:** light mode (none of the 4 chosen looks is light) — token contract supports it later if wanted.
- **Non-goal:** changing the sidecar API, registry, or AG-UI schema.

## 7. Suggested order
`aesthetic-base` (Phase 12) → merge → `aesthetic-01..04` in parallel → Phase 14 (HUD) →
Phase 13 (tray + autostart) last (it's the most OS-specific and benefits from the HUD existing).
