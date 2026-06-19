# Brain2 Summary — Phase 2 GUI Layout Decisions & Implementation Plan

**For:** Brain2 `01 - Projects/Agentic OS.md` (Progress Log section)  
**Date:** 2026-06-19  
**Action:** Copy this entire section and paste into the Brain2 Agentic OS project note

---

## Phase 2 GUI Enhancement — Layout Interview Complete & Implementation Roadmap Ready

### Session Work (2026-06-19)

**Completed:**
1. ✅ Reviewed layout alternatives (Alternative A: Sidebar-Focused)
2. ✅ Answered 5 layout interview questions:
   - **Sidebar agent cards:** Status 🟢/🔴 + cost + [★ Favorites] dropdown
   - **Main panel tabs:** Queue|Logs|Memory|Approvals + **Environment** (NEW)
   - **Logs display:** Logs tab + collapsible **Diagnostics sidebar panel**
   - **Environment variables:** Integrated **Environment tab** (LLM config, API keys, feature flags)
   - **Scripts & favorites:** Hub for apps; sidebar Favorites + dedicated **Scripts view**
3. ✅ Created comprehensive Phase 2 implementation plan (3 sprints, 6 weeks)
4. ✅ Documented all decisions in `PHASE_2_LAYOUT_DECISIONS.md`
5. ✅ Detailed implementation breakdown in `PHASE_2_IMPLEMENTATION_PLAN.md`
6. ✅ Updated CHANGELOG.md with Phase 2 overview

**Files Created:**
- `docs/PHASE_2_LAYOUT_DECISIONS.md` — 5 layout questions + design mockups + acceptance criteria
- `docs/PHASE_2_IMPLEMENTATION_PLAN.md` — 3-sprint roadmap, 12 new files, 6 modified files, API design, tests
- `docs/BRAIN2_SUMMARY.md` — This file (for Brain2 reference)

### Design Decisions (Approved 2026-06-19)

#### 1. Sidebar Agent Cards
```
Agent: Osa
Status: 🟢 Idle
Cost: $0.82
[★ Favorites ▼]  [⋮ More]
├ morning-briefing
├ process-raw-notes
└ research-learning-notes
```
**Rationale:** Quick status check + cost visibility + one-click workflow launch.

#### 2. Main Panel Tabs
```
Queue | Logs | Memory | Environment | ⋯ More
```
**New Tab: Environment**
- LLM model selector (Ollama local / Anthropic cloud)
- API key management (obfuscated)
- Feature flags toggle
- Connection test button

**Rationale:** Self-contained config UI; no YAML editing needed.

#### 3. Diagnostics Sidebar Panel
Collapsible → Shows CPU/RAM/Net (collapsed) or full system health (expanded)  
**Rationale:** Ops visibility at a glance, persistent collapse state in localStorage.

#### 4. Scripts View
Dedicated view in sidebar → Lists all workflows with scheduling + cost metrics  
**Rationale:** Follows "new paradigm = new nav link" principle; scalable as script count grows.

#### 5. Favorites Dropdown
Click [★ Favorites ▼] on agent card → Launch favorite workflows in 1 second  
**Rationale:** Quick access without navigating to Scripts view.

---

### Implementation Roadmap

| Sprint | Weeks | Goal | Deliverable |
|--------|-------|------|-------------|
| 1 | 1-2 | Foundation | Environment tab + Diagnostics panel (localStorage persistence) |
| 2 | 3-4 | Integration | Scripts view + Hub MCP wiring (all 35 tools) + Favorites dropdown |
| 3 | 5-6 | Polish | Tests (>80% coverage) + Docs + PR review |

**Timeline:** June 19 → Early August 2026 (3 sprints, ~6 weeks elapsed)

---

### New Components (12 files)

**Frontend (React):**
1. `Environment.jsx` — LLM config + flags
2. `DiagnosticsPanel.jsx` — System health (collapse/expand)
3. `ScriptsView.jsx` — Workflow launcher
4. `useFavorites.js` — Favorites hook
5. `useDiagnosticsPanel.js` — Collapse/expand hook
6. Tests: Environment.test.jsx, ScriptsView.test.jsx, Diagnostics.test.jsx

**Backend (FastAPI):**
7. `api_config.py` — Config endpoints (GET/PUT /api/config, POST /api/config/test)
8. `api_workflows.py` — Workflow list (GET /api/workflows)
9. `test_config.py` — Config endpoint tests
10. `config/schema.yaml` — Config file schema

---

### API Additions

**GET /api/config** → Current LLM model + flags  
**PUT /api/config** → Save config (HITL approval for key changes)  
**POST /api/config/test** → Test connection to LLM  
**GET /api/workflows** → List all workflows + metadata (schedule, cost, run count)

---

### Hub MCP Integration

Phase 2 wires all **35 Hub MCP tools** into the GUI:
- **Hub panel** displays apps with start/stop/restart controls
- **Agent blocks** (✦ N badge) show capability manifest
- **Scripts view** can trigger Hub apps via Hub MCP
- **Workflow launch** can depend on Hub app availability

No new Hub MCP tools needed; existing 35 tools are ready.

---

### Success Criteria

✅ 5 layout questions answered + approved  
✅ Environment tab saves LLM config + tests connection  
✅ Diagnostics collapse/expand with localStorage persistence  
✅ Favorites dropdown launches workflows (<1 sec)  
✅ Scripts view lists + filters workflows  
✅ Hub panel shows all apps (from Hub MCP)  
✅ Integration tests pass (frontend + backend, >80% coverage)  
✅ No regressions in existing panels  
✅ Docs complete (CHANGELOG, API reference, Brain2 update)  
✅ PR merged with code review sign-off  

---

### Next Phases

**Phase 9 (Hub Absorption):** Integrate app management into Agentic OS natively (Phase 2 Hub panel is prerequisite ✅)

**Phase 10+ (Agent Authoring):** GUI workflow builder + config management (Phase 2 Scripts view is prerequisite ✅)

---

### Key Files for Reference

In `Codehome/AgenticOS/`:
- `docs/PHASE_2_LAYOUT_DECISIONS.md` — Layout Q&A, mockups, components list
- `docs/PHASE_2_IMPLEMENTATION_PLAN.md` — Full 3-sprint breakdown, file manifest, API design
- `docs/CHANGELOG.md` — Updated with Phase 2 overview
- `docs/roadmap.md` — Phase status (to be updated upon completion)

In this Brain2 note:
- Copy this **Phase 2 GUI Enhancement** section into the project progress log
- Reference `PHASE_2_LAYOUT_DECISIONS.md` for layout interview details
- Update Phase 2 status to 🟩 IN PROGRESS (starting Sprint 1)

---

**Last Updated:** 2026-06-19  
**Status:** ✅ Layout decisions complete, ready for Sprint 1 (Environment tab + Diagnostics)  
**Owner:** Tony Seneadza
