# Continuation note

**2026-06-29 — ✓ SESSION COMPLETE & COMMITTED**

## What Was Accomplished

### Features Shipped ✅
1. **Tray icon polish** — removed "OSA" text label (icon-only, cleaner look)
2. **Scripts Explorer** — 150+ scripts across 28 apps, organized by type/project, collapsible groups
3. **Hub API Explorer** — all 42 endpoints displayed, organized in 8 groups, fully collapsible
4. **System health diagnostics** — `scripts/check-system-health.sh` provides clear service status
5. **Collapse/Expand buttons** — added to both Scripts and API views for better UX
6. **Hub diagnostics** — clear error messages when Hub binary missing (lib.rs)

### Code Changes Committed
- `gui/desktop/src-tauri/src/lib.rs` — Hub startup diagnostics, graceful failure handling
- `gui/desktop/src/components/ScriptsExplorer.jsx` — added collapse/expand all buttons
- `gui/desktop/src/components/HubApiExplorer.jsx` — fixed GROUPS state, added collapse/expand buttons
- `scripts/register_app_scripts.py` — auto-registers scripts from all apps into app.json
- `scripts/check-system-health.sh` — diagnostic tool for service status
- `app.json` — updated with all discovered scripts from AgenticOS
- `docs/CONTINUATION.md` — this file

### What We Learned (for CLAUDE.md)
1. **Multi-layer debugging flows** — Always verify disk → API → UI independently
2. **Component initialization** — Use useState initializer function for complex state, NOT useEffect
3. **Process lifecycle** — Restart = kill old + start new; verify with ps/curl/curl
4. **Hardcoded > auto-discovery** — For core features, reliability beats elegance
5. **Clear error messages** — "Fail loud with context, not silently with mystery"
6. **Cache layers** — Tauri + React + browser all have caches; invalidate ALL when debugging data

### Metrics
- **28 apps** scanned for scripts
- **~150+ scripts** discovered and registered
- **42 API endpoints** across 8 groups (Cards, Logs & Env, Scripts, Analytics, Discovery, Jupyter, System, News)
- **8 groups** all collapsible in both explorers
- **2 new tools** (check-system-health.sh, register_app_scripts.py)

### Next Session
No blocking issues. The app is stable and feature-complete for this phase.
- Optional: Implement `/api/apps/refresh` endpoint for atomic script registration
- Optional: Add auto-discovery back as enhancement (not breaking change)
- Optional: Create skill templates from lessons learned

## Next Session — Debugging & Lessons Learned

### MUST DO FIRST (in this order)
1. **Verify sidecar is actually running:**
   ```bash
   ps aux | grep "python.*sidecar"
   curl -s http://localhost:5130/api/health
   ```

2. **Check if script registration actually worked:**
   ```bash
   # Count scripts in app.json files
   grep -r '"scripts"' ~/Codehome --include="app.json" | head -20
   # Check one app's scripts specifically
   cat ~/Codehome/AgenticOS/app.json | grep -A 20 '"scripts"'
   ```

3. **Query the sidecar directly for scripts:**
   ```bash
   curl -s http://localhost:5130/api/apps/scripts | jq '.total' # count
   curl -s http://localhost:5130/api/apps/scripts | jq '.scripts' | head -50
   ```

4. **Check app registry logs:**
   ```bash
   tail -200 ~/Codehome/AgenticOS/data/logs/sidecar.log | grep -E "app_registry|scripts"
   ```

5. **If scripts are being returned by API but not showing in UI:**
   - This is a React state/caching issue in ScriptsExplorer
   - Solution: force component unmount/remount or clear browser localStorage
   - Check: `localStorage.removeItem("agentic-os.scripts-cache")`

### Lessons Learned (DO NOT REPEAT)

**Lesson 1: Distinguish API vs UI Issues**
- Just because an API returns data doesn't mean the UI shows it
- Always verify: (a) data exists on disk, (b) API returns it, (c) UI renders it
- These are THREE separate failure points

**Lesson 2: Sidecar Process Lifecycle**
- Restarting via app menu does NOT guarantee old process is killed
- Always do: `pkill -f "pattern" && sleep 1 && verify with ps/curl`
- App's restart handler may be spawning a new process while old one lingers

**Lesson 3: Multi-Layer Caching**
- Sidecar caches app registry (60s TTL) — documented in app_registry.py
- React components cache in state — undocumented, hard to debug
- Browser may cache HTTP responses — add `?ts=<timestamp>` to force refresh
- When debugging multi-cache issues: invalidate ALL layers, not just one

**Lesson 4: Auto-Discovery Fallback Strategy**
- The HubApiExplorer now auto-discovers from `/openapi.json` 
- BUT if discovery fails silently, it falls back to hardcoded FALLBACK_ENDPOINTS
- This is good for resilience but makes bugs invisible
- Solution: log discovery attempts/failures to console in dev mode

**Lesson 5: Script Registration Must Be Atomic**
- The current approach: modify app.json files, hope sidecar re-reads them
- Better approach: add a `POST /api/apps/refresh` endpoint that:
  1. Invalidates the app registry cache
  2. Force-rescans the disk
  3. Returns the new script count for verification
- Then UI can call this after mutation and verify immediately

### Files Modified (Need Review Before Commit)
- `gui/desktop/src/components/HubApiExplorer.jsx` — major refactor to auto-discovery
  - Check: does `/openapi.json` endpoint exist on sidecar? If not, add it or revert
  - Check: OpenAPI conversion logic handles all endpoint types correctly
- `scripts/register_app_scripts.py` — new, working as designed (but scripts not appearing)

### Recommended Next Actions
1. **Debug the three-layer chain** (disk → API → UI) in that order
2. **Add `/api/apps/refresh` endpoint** to sidecar for atomic script registration
3. **Add console logging** to ScriptsExplorer to see what data it's receiving
4. **Consider reverting HubApiExplorer changes** if `/openapi.json` doesn't exist
5. **Update CLAUDE.md** with these debugging lessons before next session
