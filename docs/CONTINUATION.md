# Continuation note

**2026-06-14: Phase 8 (NF-2) Dashboard Workspace ✅ COMPLETE. Next up:
NF-4 / Phase 9 (Hub absorption) — but it still needs a detailed drill-down
before build.**

## Current state

Roadmap phases 1–8 complete (see `docs/roadmap.md`):

- Phases 1–7 ✅ (signed off 2026-06-14)
- Phase 8 — Dashboard Workspace (NF-2) ✅ (FR-46–51, this session)
- Root `README.md` refreshed to current state (Phases 1–8, dashboard
  workspace, corrected layout) — pushed as `ae3e496`. All work on
  `origin/main`; tree clean.

## Phase 8 (NF-2) — what landed

Front-end-only, as specced. Files touched:
- `gui/desktop/src/App.jsx` — `VIEWS` registry generalized (FR-46); `usePanelGrid`
  hook + module-level `mkPanel` extracted from the old `DashboardView`;
  `DashboardView`→`SysOpsView` (FR-47); new `WorkflowsDashboard` +
  `WorkflowsPanel` + `LinkedEventsPanel` replacing `WorkflowsView`/`EventsView`
  (FR-48/49); `ComingSoon` stub + four placeholder entries (FR-50); activeView
  migration shim (`dashboard`→`sysops`, `events`→`workflows`); nav badge now
  keyed on `v.badge === "approvals"`; placeholder render branch in the shell.
- `gui/desktop/src/App.css` — Phase 8 block at end of file (`.wf-grid`,
  `.sel-bar`, `.run-btn`, `.linked-row`/`.run-subrow`, `.linked-feed`
  `.hi`/`.dim`, `.coming-soon`/`.cs-*`).
- `gui/desktop/src-tauri/src/lib.rs` — View submenu now lists the six dashboards
  (⌘1–6) + Reload (⌘R); menu handler generic (`view-<id>` → `__agenticOsSetView`).

Verified `App.jsx` with an esbuild JSX transform (clean). **Ran on the Mac
2026-06-14:** `npm run tauri dev` compiled cleanly (Rust ~5s incremental) and the
app launched; the native View menu now reads SysOps, Workflows, Web News,
Scripts, Zsh Config Editor, Obsidian Viewer (⌘1–6) + Reload — FR-51 confirmed
live with the sidecar serving real data on :5130. Committed + pushed as
`ce6fc83` on `origin/main`. Remaining manual UI smoke test below (optional).

### Smoke test on the Mac
`cd gui/desktop && npm run tauri dev`, then confirm:
- Nav lists: SysOps, Workflows, Web News, Scripts, Zsh Config Editor, Obsidian
  Viewer; ⌘1–6 + the View menu switch between them.
- SysOps shows the original six-panel grid; an existing `dashboard`/`events`
  value in localStorage opens SysOps/Workflows (no dead screen).
- Workflows dashboard: expand a workflow → its runs load from `/api/runs`; click
  workflow/run/event → highlighting links both panels; "clear" resets the feed.
- Each placeholder shows its "Coming Soon" card.

### ▶ NEXT SESSION: NF-4 / Phase 9 (Hub Absorption) — drill-down first
Still **provisional** (FR-60–64). Firm up the spec before building. Full notes:
`docs/feature-backlog.md` (NF-4) and `docs/PRD-addendum-phases-8-10.md` (Phase 9).

### Deferred
- NF-3 (Phase 10) fully specced (FR-52–59); depends on NF-2 (done) + NF-4.
- Optionally capture further features as new NF-n items in the backlog.

### Repo note
This workspace can edit files but **cannot push** (sandbox has no GitHub creds;
the mount blocks the file-deletes git needs). After edits, commit + push from
the Mac: `git add -A && git commit -m "…" && git push`. Uncommitted doc changes
from this session are waiting to be pushed.

## Key files

- `docs/roadmap.md` — phase status (all ✅ as of 2026-06-14)
- `docs/CHANGELOG.md` — 2026-06-14 sign-off entry
- `Brain2/01 - Projects/PRDs/Agentic OS - Full PRD.md` — Full PRD (not mounted)
