# Agentic OS — agent instructions

## Session-budget rule (cost control)

Tony works on this project across Claude session windows to stay within
plan limits ("do the work when it's free"). All agents working in this
repo must follow this cycle:

1. **Work normally** while session capacity is available.
2. **Checkpoint before stopping.** If you are close to a session/usage
   limit (or asked to wrap up), stop starting new work and write a
   continuation note to `docs/CONTINUATION.md` containing: what was
   completed, what is in progress (file + line specifics), exact next
   steps, and any commands needed to verify.
3. **Never leave the repo broken** at a checkpoint — finish or revert the
   in-flight edit so the GUI builds and workflows run.
4. **On resume** (new session after reset), read `docs/CONTINUATION.md`
   first, do the work, then clear or update the note.
5. Prefer cheap verification (targeted greps, single builds) over broad
   re-exploration to conserve budget.

## Project conventions

- Phase numbering follows the **renumbered PRD** (`Brain2/01 - Projects/
  PRDs/Agentic OS - Full PRD.md`): 1 Core Orchestration, 2 Tauri GUI,
  3 GUI Navigation Shell (FR-36–39), 4 Shell Integration, 5 Brain2
  Workflow Agents, 6 Codehome Deep Integration. `docs/roadmap.md` must
  match this numbering.
- Docs policy: documentation updates land in the same change that alters
  behavior (`docs/CHANGELOG.md`, `docs/roadmap.md`).
- GUI design principle #7: **new paradigm = new nav link** — never add
  another always-on dashboard panel for a new interaction paradigm.
- Sidecar port 5130 is registered in `hub/docs/PORT_ASSIGNMENTS.md`
  (TR-10); register any new port before use.

## Real filesystem rule (NO SANDBOX ILLUSIONS)

**When Tony says "work on your real filesystem" or "I give you permission to work in the real world":**

1. **NEVER** give instructions for Tony to run commands. Instead:
   - Use `computer-use` tools to directly interact with his Mac
   - Use `Read`/`Write`/`Edit` tools for file operations on /Users/tonyseneadza paths
   - Create files, modify configs, generate assets — DO IT, don't describe it

2. **NEVER** assume shell commands will work. Instead:
   - For filesystem tasks: Use Read/Write/Edit directly
   - For running commands: Create a script file and ask Tony to execute it
   - For UI tasks: Use computer-use (screenshot, click, type, etc.)

3. **Pattern to avoid:** Saying "run `npm run tauri -- dev`" without first ensuring all prerequisite files (icons, configs, etc.) actually exist on disk.

4. **Pattern to use:** Write the missing files first using Write tool, then ask for the build command.

## Icon handling rule (NO REGENERATION ISSUES)

**For app icon work:**

1. **Source of truth:** `gui/desktop/src-tauri/icons/icon.png` (512×512 or larger)
   - This is the ONLY file that should be manually edited
   - All other icon files are auto-generated from this source
   - Keep it in version control

2. **Auto-generated files (never edit manually):**
   - `32x32.png`, `64x64.png`, `128x128.png`, `128x128@2x.png`
   - `icon.icns` (macOS, generated during Tauri build)
   - `icon.ico` (Windows, generated during Tauri build)

3. **When changing the icon:**
   - Update `icon.png` in `gui/desktop/src-tauri/icons/`
   - Run: `cd gui/desktop && npm run tauri icon src-tauri/icons/icon.png`
     (regenerates the full set: .icns, .ico, all sized PNGs, Windows/Android/iOS)
   - Run: `rm -rf src-tauri/target && npm run tauri dev` to rebuild
   - All five files in `tauri.conf.json` → `bundle.icon` must exist or the build fails

4. **See:** `gui/desktop/ICON_SETUP.md` for detailed icon instructions

## GUI / frontend rule (NO SILENT STYLE BUGS)

**Before building or editing any React view/component in `gui/desktop/`,
read `docs/gui-frontend-conventions.md`.** Key rules, each learned the hard way:

1. **Use only the theme tokens defined in `gui/desktop/src/App.css` `:root`**
   (`--text`, `--text-dim`, `--bg`, `--bg-panel`, `--bg-inset`, `--border`,
   `--border-soft`, `--accent`, `--green`, `--red`, `--yellow`, `--mono`).
   There is NO `--fg` / `--fg-muted`. Undefined CSS vars fail **silently** and
   wreck the visual hierarchy with no error — grep any pasted component for
   `var(--` and confirm every token exists.
2. **RSS/feed work**: the feed catalogue + categories live in **MySQL** (schema
   `AgenticOS`, tables `news_feeds` / `news_categories`) via
   `routes/news_db.py` + `routes/api_news.py`, managed in the ⚙ Settings drawer.
   They are NOT hardcoded — `news_db._SEED_*` only seeds an empty DB on first
   run. In `_fetch_rss` (`app.py`): extract images BEFORE stripping HTML; don't
   over-truncate summaries (cap `[:2000]`); restart the sidecar to clear the
   15-min feed cache (and to pick up any Python change).
3. **"Show more" toggles**: gate on measured DOM overflow, not `text.length > N`.
4. **Verify edits persisted** — read the region back after editing a large file;
   a tool reporting success is not proof the change is on disk.
5. The Tauri build can't run from the assistant sandbox — hand Tony the exact
   `npm run tauri dev` / sidecar-restart command and verify by reading diffs.

## API registration rule (Codehome → AgenticOS)

**Every HTTP endpoint must appear in the in-app API Explorer**
(`gui/desktop/src/components/HubApiExplorer.jsx`). When you add, rename, or
remove a route — a sidecar route in `gui/sidecar/` (FastAPI @ :5130) or a Hub
endpoint (@ :8085) — you MUST update that file's `ENDPOINTS` array in the SAME
change. A shipped endpoint missing from the Explorer is incomplete.

- Sidecar entries: `server: "sidecar"`, full path including `/api`
  (e.g. `/api/news/rank`).
- Hub entries: omit `server`, path relative to `/api` (e.g. `/cards`);
  use `rootPath: true` for Hub root paths like `/health`.
- Full contract, checklist, and the recommended auto-discovery approach
  (Explorer reads the sidecar's `/openapi.json`) are in
  `docs/api-registry.md`. Read it before adding any API.
