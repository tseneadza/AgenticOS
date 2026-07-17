# Phase 16 — Brain Scanner (Obsidian Vault Viewer)

**Status:** DESIGNED (locked with Tony 2026-07-15) · **Fable 5 design review:
APPROVE-WITH-CHANGES — fixes folded in (2026-07-15)** · NO code yet · awaiting
Tony's go to build
**Supersedes:** the FR-50 "Obsidian Viewer" placeholder dashboard (App.jsx `VIEWS`)
**Renames:** "Obsidian Viewer" → **Brain Scanner** (nav label + view id `obsidian` → `brain-scanner`)

---

## 1. Purpose

Turn the dead "Obsidian Viewer" placeholder into a working in-app viewer/editor for
the **Brain2 Obsidian vault** (`~/Brain2`, already an fs `allowed_root` since Phase
15b). Three things at once:

1. **A living graph.** A rotating 3D "orb" of dots — one dot per note — that
   spins continuously as a soothing ambient affectation ("idiot lights"), with
   the **wikilink edges between connected docs visible** like Obsidian's global
   graph. Selecting a file swaps in a **local-graph orb**: the selected doc at
   center with only its linked docs orbiting it (revised from freeze-in-place,
   Tony 2026-07-16 — see §3).
2. **A navigator.** A folder/file **tree** down the left side (like the real
   Obsidian file explorer) to browse and open notes.
3. **A reader/editor.** Open a note to **read** (rendered markdown) or **edit**
   it, and **create brand-new notes**, saving straight back into the vault.

Design north star: **stay close to how the real Obsidian app actually works** —
file tree on the left, graph view, click-to-open, read/preview vs. edit, new-note
creation.

---

## 2. Locked decisions (Tony interview, 2026-07-15)

| # | Decision | Choice |
|---|----------|--------|
| 1 | **Orb rendering** | **Native 3D orb in the React frontend.** Skip Graphify — it's a code→graph pipeline whose only vault output is a *static* HTML graph + a regenerated markdown vault; it can't give the live spin / freeze-on-select / highlight interactions. We render the orb ourselves from vault data. |
| 2 | **Graph edges** | **Real `[[wikilinks]]` + `#tags`**, matching the actual Obsidian graph. Backend parses note bodies for wikilinks (and tags) and emits edges. Folder is still used for **dot color/cluster**, but the connective tissue is links. |
| 3 | **Save posture** | **Direct save, like the real Obsidian app.** A dedicated vault write path scoped to `~/Brain2` — NOT routed through the Phase 15 HITL Constitution approval queue. Saving/creating a note writes the file immediately. (Rationale + guardrails in §6.) |
| 4 | **Build mode** | **Subagents where they help** (Tony's standing preference): `test-author` writes the test files; parallelizable build chunks (backend API vs. frontend view) can be split to subagents; supervisor integrates, re-runs the full suites, and commits. |
| 5 | **Orb substrate** | **Canvas 2D, no new dependency** (locked 2026-07-15). Hand-rolled pseudo-3D sphere — matches the app's minimal-deps / ponytail ethos (even OSAOrb is pure CSS). three.js is NOT added. Open item A below is resolved. |

### Graphify — why it's out
`graphify` (PyPI `graphifyy`) ingests a *codebase*, runs an AST + LLM-subagent
pipeline into a NetworkX graph, and can *export* an Obsidian vault + a static
interactive HTML graph. That is the **inverse** of this feature (we already have
the vault; we want to visualize it live) and its HTML output is not the
interactive, tree-driven, freeze-on-select orb Tony described. Decision: do not
take the dependency. If we ever want link-analysis/community-detection on the
vault, revisit `networkx` server-side as a *separate* enhancement.

---

## 3. Rendering approach — the orb

The current `OSAOrb` is a **CSS** affectation (breathing core + ripples), not a
data-driven graph, so it is NOT reused for the node cloud. The Brain Scanner orb
is a **data-driven** render of N note-dots on a rotating sphere.

**Two candidate substrates (build-time pick, §9 open item A):**

- **A — three.js (recommended for picking).** Add `three` as a frontend dep
  (not currently present — the app deliberately keeps deps minimal, so this is a
  real, called-out addition). Points cloud on a sphere, `raycaster` for
  click-to-pick a dot, easy per-dot highlight, smooth rotation. ~150KB gz.
- **B — dependency-free Canvas 2D.** Project 3D dot positions → 2D with a manual
  rotation matrix, z-sort for depth, hit-test clicks by nearest projected dot.
  No new dependency (fits the project's ponytail/minimal-deps ethos), but we hand-
  roll picking and depth. Heavier vaults (1000+ notes) are the stress case.

**DECISION (locked 2026-07-15): B — Canvas 2D, no new dependency.** Keeps deps at
zero, matches house style (ponytail / CSS-only OSAOrb). three.js is not added. If
a very large vault (1000+ notes) ever makes hand-rolled picking/depth painful,
revisit three.js as a *separate* enhancement — not in this phase.

**Behavior (REVISED with Tony 2026-07-16 — supersedes the freeze-in-place spec):**
- **FULL mode (nothing selected):** slow continuous Y-axis rotation (the "idiot
  lights" ambience). Every note is a **solid** dot — tag nodes are NOT rendered
  (hollow dots read as placeholders); edges are real `[[wikilink]]` connections
  only, drawn **always-visible** as faint depth-faded lines (Obsidian's global
  graph). Sphere positions are assigned in **deterministic hash order**, not
  vault order — alphabetical order groups folders into colored latitude bands
  and makes the orb look non-uniform.
- **LOCAL mode (a doc selected, from tree OR by clicking its dot):** the
  collection is replaced by a **new orb built from the selection** — the
  selected doc at center (accent + halo + title), its linked docs orbiting it
  with visible edges and titles (labels fade in on the front hemisphere so
  heavily-linked docs stay readable; gentle rotation). Clicking a linked doc
  **re-centers** the local orb on it; clicking empty space **deselects** and
  the full collection resumes. This is Obsidian's local graph.
- **STEERABLE (Tony 2026-07-16):** drag the orb to rotate it freely on both
  axes (yaw + pitch); releasing a drag flings the spin onward in that
  direction at the ambient pace. Press-release under ~4px is a click
  (select); anything larger is a steer, never a selection.
- **Group colors are UNIQUE (Tony 2026-07-16):** each group (top-level
  folder) gets its own hue, evenly spaced around the HSL wheel so no two
  groups share a color (data-viz colors, same precedent as WebNewsView
  categories — UI chrome still uses theme tokens only). Docs not in any
  group share one neutral color — "(ungrouped)" in the legend — until they
  find a group.
- A small legend maps color→group.
- Tags-as-nodes remain in the `/api/vault/graph` payload (§5) — the orb simply
  does not render them; a future tags toggle stays possible without API change.

---

## 4. Layout (3-pane, Obsidian-like)

```
┌───────────────┬────────────────────────────┬────────────────────┐
│  TREE (left)  │        ORB (center)        │  READER/EDITOR      │
│               │                            │  (right, on open)   │
│ ▸ 00 - Raw    │      · · ·  ·   ·          │  # Note title       │
│ ▾ 01 - Proj   │    ·   ●(selected)  ·      │  rendered markdown  │
│   • note A    │      ·   · ·  ·            │  ────────────       │
│   • note B    │   (spins; local graph on   │  [Edit] [Save] [New]│
│ ▸ 02 - Learn  │    selection)              │                     │
└───────────────┴────────────────────────────┴────────────────────┘
```

- **Left — tree:** folders expand/collapse; files open on click. Reflects the
  real vault folder structure. New-note button (＋) creates a note in the
  selected folder.
- **Center — orb:** always visible; the ambient spinner. Selection state is
  shared with the tree and the reader (single `selectedPath`).
- **Right — reader/editor:** hidden until a note is open. **Read mode** renders
  markdown; **Edit mode** is a textarea (source) with **Save**; **New** creates.

Follows GUI principle #7 (new paradigm = its own nav view, already registered) and
the theme-token rules in `docs/gui-frontend-conventions.md`.

---

## 5. Backend — vault API (new sidecar routes)

New router `gui/sidecar/routes/api_vault.py` (FastAPI @ :5130), registered in
`app.py` and in `HubApiExplorer.jsx` `ENDPOINTS` (API registration rule). Reads
the **local filesystem** directly (sidecar runs on Tony's Mac); **path-scoped to
the vault root** — every path is `resolve()`d and must stay under it (reuse the
Phase 15b `resolve_path` / `under_any_root` pattern; reject symlink escapes and
`..`).

> **Vault root is CONFIG, not hardcoded (Fable 5 review, HIGH).** The root comes
> from config (a `vault_root` setting, defaulting to the `~/Brain2` entry in
> `system_mcp.fs.allowed_roots`) and MUST be **injectable in tests** via a
> `tmp_path` fixture vault — 16a's pytest never touches the real Brain2. The graph
> cache is **in-memory** (no DB — the MySQL/SQLAlchemy rule is moot here; don't
> invent a table).

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/vault/tree` | Folder/file tree of the vault (dirs + `.md` files, names + relative paths). |
| GET | `/api/vault/note?path=` | Raw markdown of one note (+ metadata: mtime, size). |
| GET | `/api/vault/graph` | Nodes (one per note: id/path/folder) + edges parsed from `[[wikilinks]]` and shared `#tags`. Cached; invalidated on write. |
| PUT | `/api/vault/note` | Save edited note (body scoped-write to `~/Brain2`). |
| POST | `/api/vault/note` | Create a new note (path + optional template/frontmatter). Refuse overwrite. |

**Wikilink parsing:** regex `\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]` → resolve
target by basename to a note; unresolved links are dropped from the graph (or shown
as ghost nodes — §9 open item B). Duplicate basename (two `note.md` in different
folders): pick the **shortest path** (Obsidian's rule) deterministically.

**Parse hygiene (Fable 5 review, MEDIUM) — do these BEFORE regexing the body:**
- **Strip fenced code blocks** (```` ``` ````) and inline code so `[[links]]` and
  `#refs` in code samples don't become edges.
- **Strip + separately parse YAML frontmatter.** Tags live canonically in
  frontmatter `tags:` — parse those explicitly; a body-only tag regex misses them.
- Body tag regex `(?:^|\s)#([A-Za-z][\w/-]*)` — the leading-letter requirement
  rejects hex colors (`#fff`, `#d97b4f`) and pure-numeric issue refs.

**Tags as NODES, not pairwise edges (Fable 5 review, MEDIUM).** A `#tag` shared by
N notes must NOT emit N·(N−1)/2 note-to-note edges (one tag on 200 notes ≈ 20k
edges — swamps the payload and the Canvas draw loop). Model each tag as its own
**visually-distinct node** with note→tag edges (this is what real Obsidian does).

**Cache invalidation across ALL writers (Fable 5 review, MEDIUM).** Brain2 is also
written by the real Obsidian app, `process-raw-notes`, `filesystem_tool.py`, and
OSA `fs_mcp` — "invalidate on our own write" goes stale. Key the in-memory cache on
a **fast vault scan (max mtime + file count)** or a short TTL, and honor a
`?refresh=1` param wired to the manual refresh button (§9 item E).

**Tree hygiene:** exclude `.obsidian/`, hidden dotfiles, and non-`.md` assets from
`/api/vault/tree`. Sanitize the POST `name` field (reject path separators in the
name itself, even though `resolve()` catches traversal). Note title = **filename
stem** for v1 (not frontmatter `title`/first-H1 — say so, revisit later).

**Write scoping (critical):** the save/create endpoints re-validate the resolved
destination is under the vault root **in the handler body** (approval-can't-smuggle
pattern from 15b fs move). No writes outside the vault, ever. `.md` only.
**Empty-vault / vault-missing** → clean 503 in 16a (not deferred to polish).

---

## 6. Save posture & guardrails (direct save)

Tony chose direct save so it *feels like Obsidian*. This deliberately does **not**
go through the Constitution HITL queue. Guardrails that make that safe:

1. **Hard path scope** — writes are validated (resolved, under-root, `.md`) in the
   route body; a caller cannot write outside `~/Brain2`.
2. **No delete in v1** — Brain Scanner can read/edit/create. Deleting notes is out
   of scope (deletion stays a governed fs op). Removes the biggest footgun.
3. **No overwrite on create** — POST refuses if the target exists.
4. **Mandatory `.bak` before every overwrite (PUT)** — REQUIRED, not optional. A
   PUT that replaces existing content is equivalent to destroying it; write a
   timestamped backup first. (Promotes old §9 item C to a hard requirement.)
5. **Optimistic concurrency on PUT** — GET returns `mtime`; PUT must carry the
   expected `mtime` and return **409** on mismatch. This covers Tony editing the
   same note in the real Obsidian app at the same time (a case the first draft
   omitted), not just double-clicks.
6. **This is the app's OWN vault write path**, distinct from OSA's `fs_mcp`
   governed writes and from `filesystem_tool.py` (the workflow-agent vault path).
   Documented deviation, mirrors how 15b noted fs_mcp ≠ filesystem_tool.

> ⚠️ **Constitution-bypass channel (Fable 5 review, HIGH).** This route is NOT
> only reachable by Tony's clicks. Because `osascript`/`run_command` auto-runs
> un-gated (accepted risk, `constitution.yaml` ~L114), a live OSA flow could
> `curl -X PUT localhost:5130/api/vault/note …` and clobber a note with zero
> HITL. Guardrails 3–5 (`.md`-only + no-overwrite-create + mandatory `.bak` +
> mtime-409) are what make that acceptable for a personal app. Add a one-line
> comment near `fs.allowed_roots` in `constitution.yaml` pointing here so a
> future security pass doesn't rediscover this path cold. **`security-verifier`
> is REQUIRED on the 16d write diff** even though it doesn't touch the listed
> spine files (15a kwargs-bypass precedent).

---

## 7. Frontend — components

- `gui/desktop/src/components/BrainScannerView.jsx` — the 3-pane view.
- `gui/desktop/src/components/VaultTree.jsx` — recursive folder/file tree.
- `gui/desktop/src/components/BrainOrb.jsx` — the rotating node-orb (substrate per
  §3), props: `nodes`, `edges`, `selectedPath`, `onSelect`.
- `gui/desktop/src/components/NoteReader.jsx` — read (markdown render) / edit
  (textarea + Save) / new. Markdown render: a tiny in-house renderer (house style
  prefers no new dep). **MUST escape-first / render to React elements — never
  `dangerouslySetInnerHTML` from raw note content** (Fable 5 review, HIGH): the
  Tauri webview origin `tauri://localhost` is CORS-allowlisted at the sidecar, so
  injected `<script>` in a note could call the §5 write endpoints. Escape HTML, or
  build React nodes, before mounting.
- **Registry change:** in `App.jsx` `VIEWS`, replace the `obsidian` placeholder
  entry with `{ id: "brain-scanner", label: "Brain Scanner", component:
  BrainScannerView }`. **Add the `VIEW_KEY` migration** `if (saved === "obsidian")
  saved = "brain-scanner"` (App.jsx ~L1694 pattern — else a saved `obsidian` view
  lands broken). Update `Hud.jsx` nav list + the native menu (FR-51 / `lib.rs`
  View submenu id `view-obsidian`, label, `cmd+6` ~L156 + the array ~L178) so
  tree/menu/shortcuts stay in sync. Per the Tauri rule, the menu change needs a
  **real Rust rebuild** (not `tauri dev` hot-reload) to appear.

**Canvas theming (Fable 5 review, LOW).** A 2D context can't read CSS vars. Read
`--accent`/`--green`/etc. via `getComputedStyle(document.documentElement)` at mount
and re-read on the existing `theme-changed` event / `data-theme` change — do NOT
hardcode hex (breaks skins, violates §3). **Null-guard `getContext('2d')`** — it
returns `null` under jsdom/vitest, so `BrainOrb` must no-op cleanly or the suite
crashes rather than merely under-verifying. The orb is **unverified until seen
on-device** (`gui-frontend-conventions.md` §9).

Selection state (`selectedPath`) lives in `BrainScannerView` and is shared by tree
↔ orb ↔ reader so all three agree on the active note and the full↔local orb mode.
**Pause the rAF spin loop** when the view is inactive or the window is hidden
(battery).

---

## 8. Sub-phase plan

| Sub | Scope |
|-----|-------|
| **16a** | Backend vault API: `api_vault.py` (tree, note read, graph parse) + scoping + register in app.py & HubApiExplorer + pytest. Read-only slice. |
| **16b** | Frontend: `BrainScannerView` + `VaultTree` + `NoteReader` **read mode**; rename placeholder → Brain Scanner in VIEWS/Hud/menu; vitest. |
| **16c** | `BrainOrb` rotating node-orb: full collection w/ visible wikilink edges + local-graph orb on selection (§3 revised behavior), wired to `/api/vault/graph`; vitest tripwire (jsdom can't see canvas). **Definition of done includes the on-device visual pass** — the orb cannot be verified by its own vitest slice, so don't defer that to 16e. |
| **16d** | Edit + create: PUT/POST save endpoints (scoped write, mandatory `.bak`, mtime-409) + reader edit mode + new-note flow; pytest + vitest. **`security-verifier` REQUIRED on the write diff** (§6). |
| **16e** | Polish: theme pass on-device (`npm run tauri dev`), wikilink click-to-open navigation, legend, empty/error states. |

---

## 9. Open items (decide at build)

- ~~**A. Orb substrate**~~ — **RESOLVED: Canvas 2D, no new dependency** (§2 #5, §3).
- **B. Ghost nodes** — show unresolved `[[links]]` as faint nodes (real Obsidian
  does) or drop them. **Lean:** drop in v1, add later.
- **C. Overwrite backup** — write a `.bak` before overwriting on save? **Lean:**
  yes, cheap safety.
- **D. Markdown renderer** — hand-rolled minimal vs. a small library. **Lean:**
  minimal in-house (headings/bold/lists/links/code) to hold the no-new-dep line;
  revisit if fidelity matters.
- **E. Live vault watch** — auto-refresh tree/graph when files change on disk
  (fs watch) vs. manual refresh. **Lean:** manual refresh button in v1.

### Small wins to fold in (Fable 5 review)
- Orb hover → note-title tooltip (nearly free with the hit-test 16c already builds).
- Legend doubles as a folder filter (click a color to dim other clusters).
- POST create response returns the new relative path so tree/orb select it at once.
- Wikilink click-to-open in the reader (already in 16e).

---

## 10. Docs / conventions to honor (same-change)

- `docs/roadmap.md` — Phase 16 section + sub-phase table (added this session).
- `docs/CHANGELOG.md` — entry per sub-phase.
- `docs/GLOSSARY.md` (+ Brain2 mirror) — new terms (Brain Scanner, orb node cloud,
  wikilink edge, vault write path) as they're introduced.
- `HubApiExplorer.jsx` `ENDPOINTS` — every `/api/vault/*` route.
- `docs/gui-frontend-conventions.md` — theme tokens only; verify persisted edits.
- FR-51 — keep the native menu/⌘-shortcuts in sync with the renamed view.
