# Phase 2 GUI Layout Interview — Decisions

**Date:** 2026-06-19  
**Status:** ✅ Completed  
**Reference:** Based on `gui-layout-alternatives.html` (Alternative A: Sidebar-Focused)

---

## 1. Sidebar Agent Cards — Quick Stats & Controls

**Decision:** Agent cards show **live status + cost** with action dropdowns.

**Design:**
```
┌─ Agent: Osa ─────────────────────┐
│ Status: 🟢 Idle                   │
│ Running: 2 workflows              │
│ Cost today: $0.82                 │
│ [⋮ More] [★ Favorite] [↻ Refresh] │
└───────────────────────────────────┘
```

**Rationale:**
- **Status at a glance:** 🟢 Idle/Running/Error signals health without opening panels
- **Cost visibility:** Spending is top-of-mind in agent systems; daily budget awareness prevents runaway costs
- **Action dropdown:** [⋮ More] for future actions (pause, restart, config) without cluttering the card
- **Favorite toggle:** Quick visual indicator of pinned agents (persisted to `localStorage`)
- **Recent apps below cards:** Hub apps (Weather, Keno Dashboard, etc.) listed below agent cards in sidebar with status dots

**Reference Components:**
- `gui/desktop/src/components/Sidebar/AgentCard.jsx` (new)
- `gui/desktop/src/components/Sidebar/HubAppsSection.jsx` (new)

---

## 2. Main Panel Tabs — Unified Dashboard Layout

**Decision:** Keep **Queue | Logs | Memory | Approvals** tabs + add **Environment** tab.

**Tab Structure:**
```
┌─ Dashboard [↻ Refresh] ──────────┐
│ Queue | Logs | Memory | Env | ⋯  │
├─────────────────────────────────┤
│ [Panel content for active tab]  │
└─────────────────────────────────┘
```

**Tab Definitions:**

1. **Queue** — Workflow runs in progress + history
   - Active runs with status, elapsed time, next action
   - Completed runs with duration + cost
   - [Run] button to launch a new workflow
   
2. **Logs** — Combined agent + system logs (real-time)
   - Agent events (tool calls, approvals, loops)
   - System events (startup, shutdown, port changes)
   - Filter by level (debug/info/warn/error)
   
3. **Memory** — Persistent agent context
   - Soul (agent identity) → read-only
   - Memory (facts, preferences) → editable inline
   - [Edit] button to add memories
   
4. **Environment** — Runtime configuration (NEW)
   - LLM model selection (Ollama local / Anthropic cloud)
   - API keys / Base URLs (obfuscated in display)
   - Feature flags (enable/disable specific capabilities)
   
5. **⋯ More** — Hub, Diagnostics, Scripts (collapsed menu)

**Rationale:**
- **Existing tabs validated:** Queue/Logs/Memory/Approvals work well; no redesign needed
- **Environment tab closes a gap:** Users need LLM config + API management without opening system settings
- **Collapsed More menu:** Prevents sidebar from becoming a nav dump; "new paradigm = new nav link" (CLAUDE.md principle #7)

**Reference Components:**
- `gui/desktop/src/components/Dashboard/TabBar.jsx` (new)
- `gui/desktop/src/components/Dashboard/Tabs/{Queue,Logs,Memory,Environment}.jsx` (new Environment)

---

## 3. Logs Display — Keep in Memory + Add Diagnostics Sidebar Panel

**Decision:** Logs stay in the Logs tab. Add a **collapsible Diagnostics sidebar panel** for system health.

**Layout:**
```
┌────────────────────────────────────┐
│ Sidebar                    Main    │
│ ┌──────────┐  ┌─────────────────┐  │
│ │ Agents   │  │ Queue | Logs ↔  │  │
│ │ Hub Apps │  │ Memory | Env    │  │
│ │          │  │                 │  │
│ │ [⊟ Diag] │  │ [Real-time      │  │
│ │ CPU 23%  │  │  agent logs]    │  │
│ │ RAM 70%  │  │                 │  │
│ │ Net 1.2M │  │                 │  │
│ └──────────┘  └─────────────────┘  │
└────────────────────────────────────┘
```

**Diagnostics Sidebar Panel (Collapsed → Expanded):**
- **Collapsed:** Shows 3 key metrics (CPU, RAM, Net)
- **Expanded:** Full system health (CPU per-core, memory breakdown, disk, network, load avg, top process)
- **Toggle:** [⊟] to collapse / [⊞] to expand; state persisted to `localStorage["agentic-os.diagExpanded"]`

**Rationale:**
- **Logs tab for workflows:** Agent activity logs belong with queue runs (context is run → events → logs)
- **Diagnostics for ops:** System health is an ops concern (separate from workflow logs)
- **Sidebar real estate:** Collapsible diagnostics doesn't steal space from main content
- **Accessible at a glance:** Quick health check without switching panels

**Reference Components:**
- `gui/desktop/src/components/Dashboard/Tabs/Logs.jsx` (enhanced with filter)
- `gui/desktop/src/components/Sidebar/DiagnosticsPanel.jsx` (new)

---

## 4. Environment Variables — Config Tab + Integrated Settings UI

**Decision:** Create **Environment tab** in main dashboard for runtime config + API keys.

**Layout (Environment Tab):**
```
LLM Configuration
┌─────────────────────────────────────┐
│ Active Model: [Ollama (local) ▼]   │
│ • Ollama Host: http://localhost:11434
│ • Base URL: http://localhost:11434/v1
│ • Fallback: Anthropic Claude       │
│                                     │
│ API Credentials                     │
│ • Anthropic API Key: [•••••••••]   │
│ • Edit [key icon]                   │
│                                     │
│ Feature Flags                       │
│ ☑ Shell commands (run_shell)       │
│ ☑ Brain2 integration                │
│ ☑ Hub absorption (Phase 9)          │
└─────────────────────────────────────┘
```

**Behavior:**
- **Model selector:** Radio buttons (Ollama local / Anthropic cloud)
- **Settings for each model:** Revealed on selection (Ollama host URL, Anthropic base URL/key)
- **Obfuscated keys:** Display `••••••••` with [Edit] button (requires HITL approval for changes)
- **Feature flags:** Checkboxes to enable/disable experimental features (logged to `config/flags.yaml`)
- **Validation:** Test connection before saving (icon → 🟢 working / 🔴 error)

**Rationale:**
- **Self-contained UI:** No need to edit YAML files or env vars directly
- **Safe by design:** Obfuscated keys + approval for changes prevent accidental exposure
- **Experimentation:** Feature flags let users opt into Phase 9/10 features early
- **LLM flexibility:** Users can swap local/cloud on the fly without CLI overhead

**Reference Components:**
- `gui/desktop/src/components/Dashboard/Tabs/Environment.jsx` (new)
- `gui/sidecar/routes/api_config.py` (new endpoints: GET/PUT `/api/config`)

---

## 5. Scripts & Favorites — Hub Panel + Sidebar Favorites Dropdown

**Decision:** Scripts in **Hub panel** (existing); **Favorites dropdown** on agent card + dedicated scripts view.

**Layout:**

*Sidebar (Agent Card):*
```
Agent: Osa
Status: 🟢 Idle
Cost: $0.82
[★ Favorites ▼]  [⋮ More]
├ morning-briefing
├ process-raw-notes
└ research-learning-notes
```

*Main Panel (Separate Scripts View):*
```
View Menu: Dashboard | Workflows | Scripts | Hub | ...
┌──────────────────────────────────────┐
│ Available Scripts                    │
├──────────────────────────────────────┤
│ [morning-briefing]                   │
│ Scheduled: Daily 7am                 │
│ Cost avg: $0.45 · Runs: 23          │
│ [Run] [Edit] [▼ Details]            │
├──────────────────────────────────────┤
│ [process-raw-notes]                  │
│ Scheduled: Every 4h                  │
│ Cost avg: $0.12 · Runs: 67          │
│ [Run] [Edit] [▼ Details]            │
└──────────────────────────────────────┘
```

**Behavior:**
- **Favorites dropdown:** On agent card, click [★ Favorites ▼] to launch a pinned workflow (stored in `localStorage["agentic-os.favorites"]`)
- **Scripts view:** Dedicated view in sidebar (added to `VIEWS` registry); shows all workflows + scheduling + cost metrics
- **Hub panel stays:** App management (start/stop/manifest) remains in Hub (Phase 6); not a script concern
- **Filter bar:** Favorites dropdown + scripts view both support quick search by name or tag

**Rationale:**
- **Favorites at hand:** Quick-launch workflows from agent card without opening main dashboard
- **Scripts as a view:** Follows "new paradigm = new nav link" (CLAUDE.md #7); scripting is its own workflow
- **Hub stays focused:** Hub is for **apps** (microservices), not **workflows** (scheduled tasks)
- **Scalability:** As script count grows, dedicated Scripts view prevents sidebar clutter

**Reference Components:**
- `gui/desktop/src/components/Sidebar/AgentCard.jsx` → Favorites dropdown
- `gui/desktop/src/views/ScriptsView.jsx` (new)
- `gui/desktop/src/hooks/useFavorites.js` (new)

---

## Implementation Priority

1. **Immediate (Phase 2a):** Environment tab + Favorites dropdown
2. **Near-term (Phase 2b):** Diagnostics sidebar panel + Scripts view
3. **Nice-to-have (Phase 2c):** Filter bars, feature flags UI

---

## Acceptance Criteria (Phase 2)

| Criterion | Status |
|-----------|--------|
| Environment tab configured + saved to `/api/config` | 🔲 Pending |
| Favorites dropdown launches workflows from sidebar | 🔲 Pending |
| Diagnostics panel collapses/expands with `localStorage` persistence | 🔲 Pending |
| Scripts view lists all workflows with scheduling + cost data | 🔲 Pending |
| Tab bar renders Queue \| Logs \| Memory \| Environment \| More | 🔲 Pending |
| All new components integrate with Hub MCP (35 tools) | 🔲 Pending |

---

## Files to Create/Modify

**New Components:**
- `gui/desktop/src/components/Dashboard/Tabs/Environment.jsx`
- `gui/desktop/src/components/Sidebar/DiagnosticsPanel.jsx`
- `gui/desktop/src/views/ScriptsView.jsx`
- `gui/desktop/src/hooks/useFavorites.js`

**Modified Components:**
- `gui/desktop/src/components/Sidebar/AgentCard.jsx` → Add favorites dropdown
- `gui/desktop/src/components/Dashboard/TabBar.jsx` → Add Environment tab
- `gui/desktop/src/App.jsx` → Register Scripts view in `VIEWS` registry

**Backend (Sidecar):**
- `gui/sidecar/routes/api_config.py` (new, GET/PUT `/api/config`)
- `gui/sidecar/config/` → Config schema + validation

**Documentation:**
- This file (PHASE_2_LAYOUT_DECISIONS.md) → Approved 2026-06-19
- `docs/CHANGELOG.md` → Phase 2 decisions entry
- Brain2 → Phase 2 decisions + acceptance criteria

---

**Approved by:** Tony Seneadza  
**Approved on:** 2026-06-19  
**Next:** Proceed to PHASE_2_IMPLEMENTATION_PLAN.md
