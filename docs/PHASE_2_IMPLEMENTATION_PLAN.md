# Phase 2+ Implementation Plan — Tauri GUI Enhancement

**Scope:** Enhanced GUI with Environment config, Diagnostics sidebar, Scripts view, and Hub MCP integration (35 tools)  
**Timeline:** 3 sprints (2 weeks per sprint)  
**Start:** 2026-06-19  
**Status:** Planning phase

---

## 1. Phase Overview

### Goals
1. **Configuration management:** Environment tab for LLM switching + API key management
2. **Operational visibility:** Diagnostics sidebar for system health
3. **Workflow launcher:** Favorites + Scripts view for quick access to workflows
4. **Hub MCP wiring:** Integrate all 35 Hub MCP tools into GUI panels

### Scope (In)
- Environment tab (LLM config, API keys, feature flags)
- Diagnostics sidebar panel (collapsible)
- Scripts view (workflow launcher)
- Hub panel enhancement (show all 35 tools)
- Sidebar agent card favorites dropdown

### Scope (Out)
- Hub absorption (Phase 9 — separate)
- Authoring workflows in GUI (Phase 10+ — future)
- Cloud backup / account sync (Future)

---

## 2. Architecture

### High-Level Diagram

```
┌─ Tauri App (React) ──────────────────────────────┐
│                                                   │
│  ┌─ Sidebar ────────────────────────────────────┐│
│  │ • Agent Cards + Favorites                    ││
│  │ • Hub Apps (from Hub MCP)                    ││
│  │ • [⊟ Diagnostics] (collapsible)             ││
│  │ • Nav Links (Dashboard, Workflows, Scripts) ││
│  └────────────────────────────────────────────── ││
│                                                   │
│  ┌─ Main Panel ─────────────────────────────────┐│
│  │ Tabs: Queue | Logs | Memory | Env | More    ││
│  │                                               ││
│  │ Environment Tab:                             ││
│  │ ├─ LLM Config (Ollama/Anthropic)            ││
│  │ ├─ API Keys (obfuscated)                    ││
│  │ └─ Feature Flags                            ││
│  │                                               ││
│  │ Scripts View:                                ││
│  │ ├─ Workflow list (from workflows.yaml)      ││
│  │ ├─ Schedule + cost metrics                  ││
│  │ └─ [Run] / [Edit] buttons                   ││
│  └────────────────────────────────────────────── ││
│                                                   │
│  ┌─ WebSocket Polling ───────────────────────────┐│
│  │ /ws/agui: Dashboard events (adaptive poll)    ││
│  │ /ws/agent: Agent chat (Phase 10)              ││
│  │ /ws/config: Config changes (new)              ││
│  └────────────────────────────────────────────── ││
└───────────────────────────────────────────────────┘
           ↓
┌─ Sidecar (FastAPI) :5130 ────────────────────────┐
│ • /api/runs — workflow runs + history            │
│ • /api/agents — agent status + soul/memory       │
│ • /api/config — LLM config, API keys, flags (NEW)│
│ • /api/panels/* — system, agent, hub, etc.       │
│ • /ws/agui — event stream                        │
└───────────────────────────────────────────────────┘
           ↓
┌─ Core Services ──────────────────────────────────┐
│ • LLM layer (Ollama + Anthropic)                 │
│ • Hub MCP (35 tools)                             │
│ • Constitution + HITL                            │
│ • Workflows (LangGraph)                          │
└───────────────────────────────────────────────────┘
```

### Data Flow

**Environment Tab:**
```
User selects Ollama Local
         ↓
React reads radio selection
         ↓
PUT /api/config { model: "ollama", host: "..." }
         ↓
Sidecar validates connection (curl to Ollama)
         ↓
Sidecar writes ~/.agentic-os/config.yaml
         ↓
Sidecar emits /ws/config event
         ↓
React updates UI (🟢 connected / 🔴 error)
```

**Favorites Dropdown:**
```
User clicks [★ Favorites ▼] on Agent Card
         ↓
React shows favorite workflows from localStorage
         ↓
User clicks "morning-briefing"
         ↓
POST /api/runs { workflow: "morning-briefing" }
         ↓
Sidecar launches LangGraph run
         ↓
/ws/agui event stream updates Queue tab
```

**Diagnostics Panel:**
```
App mounts → localStorage["agentic-os.diagExpanded"] = false
         ↓
Collapsed: Show CPU/RAM/Net
         ↓
User clicks [⊞] to expand
         ↓
localStorage["agentic-os.diagExpanded"] = true
         ↓
Expanded: Show full system health (per-core CPU, etc.)
         ↓
usePoll(2s) updates metrics in real-time
```

---

## 3. Component Breakdown

### Sprint 1: Foundation (Week 1-2)

#### 3.1 Environment Tab

**File:** `gui/desktop/src/components/Dashboard/Tabs/Environment.jsx`

**Features:**
- LLM model selector (Ollama local / Anthropic cloud)
- Per-model settings (host URL, base URL, API key)
- Feature flags toggle list
- Connection test button + status indicator
- Save/Cancel buttons

**State Management:**
```javascript
const [config, setConfig] = useState({
  llm: {
    activeModel: "ollama", // or "anthropic"
    ollama: { host: "http://localhost:11434" },
    anthropic: { baseUrl: "...", apiKey: "•••••" }
  },
  flags: {
    shellCommands: true,
    brain2Integration: true,
    hubAbsorption: false
  }
});
```

**API Calls:**
```
GET /api/config → Load current config
PUT /api/config → Save changes (HITL approval for key changes)
POST /api/config/test → Test LLM connection
```

**Validation:**
- URL format check (must be valid HTTP/HTTPS)
- Connection test (curl to model endpoint)
- API key format (non-empty, reasonable length)

**UI States:**
- Loading: "Testing connection..."
- Success: 🟢 Connected to Ollama 11434
- Error: 🔴 Connection failed (show error details)
- Saving: Disabled buttons during PUT

#### 3.2 Diagnostics Sidebar Panel

**File:** `gui/desktop/src/components/Sidebar/DiagnosticsPanel.jsx`

**Features:**
- Collapsible header with toggle icon [⊟] / [⊞]
- Collapsed view: 3-line summary (CPU, RAM, Net)
- Expanded view: Full system health breakdown
- Real-time updates via `usePoll(2s)`
- Persistent state: `localStorage["agentic-os.diagExpanded"]`

**Collapsed Layout:**
```
[⊞ Diagnostics]
CPU 23% | RAM 70% | Net 1.2M
```

**Expanded Layout:**
```
[⊟ Diagnostics]
CPU (all cores)    23% ████░░░░░░
  • core 0         18% ███░░░░░░░
  • core 1         28% █████░░░░░
  • core 2         15% ██░░░░░░░░
  • core 3         32% ██████░░░░
Memory             70% █████████░ (11.2 / 16 GB)
Disk               62% ██████░░░░ (312 / 500 GB)
Network            in: 1.2 MB/s | out: 340 KB/s
Load Average       1.42 · 1.18 · 0.97
Top Process        python3 (8.4%)
```

**API Call:**
```
GET /api/panels/system → Returns full system health
```

**Component State:**
```javascript
const [expanded, setExpanded] = useState(
  JSON.parse(localStorage.getItem("agentic-os.diagExpanded") || "false")
);
useEffect(() => {
  localStorage.setItem("agentic-os.diagExpanded", JSON.stringify(expanded));
}, [expanded]);
```

#### 3.3 Agent Card Favorites Dropdown

**File:** `gui/desktop/src/components/Sidebar/AgentCard.jsx` (modify)

**Features:**
- Favorite workflows dropdown (click [★ Favorites ▼])
- List favorite workflows from localStorage
- [+] button to add favorites (opens workflow picker)
- [×] next to each favorite to remove
- Click favorite to launch workflow

**State:**
```javascript
const [favorites, setFavorites] = useState(
  JSON.parse(localStorage.getItem("agentic-os.favorites") || "[]")
);

const launchWorkflow = (wfName) => {
  fetch("/api/runs", {
    method: "POST",
    body: JSON.stringify({ workflow: wfName })
  });
};
```

**localStorage Schema:**
```json
{
  "agentic-os.favorites": ["morning-briefing", "process-raw-notes"]
}
```

---

### Sprint 2: Views & Integration (Week 3-4)

#### 3.4 Scripts View

**File:** `gui/desktop/src/views/ScriptsView.jsx`

**Features:**
- List all workflows from `workflows.yaml`
- Show schedule (cron), cost avg, run count
- [Run Now] button
- [Edit] button (opens authoring — Phase 10)
- [▼ Details] to expand workflow details
- Search/filter by name

**Data Source:**
```
GET /api/workflows → Returns all workflows + metadata:
[
  {
    "name": "morning-briefing",
    "description": "Daily briefing from Brain2",
    "schedule": "0 7 * * *",
    "costAvg": 0.45,
    "runCount": 23,
    "lastRun": "2026-06-19T07:00:00Z",
    "steps": ["gather_brain2_notes", "summarize_with_claude", "write_to_reflection"]
  }
]
```

**Component:**
```javascript
export default function ScriptsView() {
  const [workflows, setWorkflows] = useState([]);
  const [search, setSearch] = useState("");
  
  useEffect(() => {
    fetch("/api/workflows").then(r => r.json()).then(setWorkflows);
  }, []);
  
  const filtered = workflows.filter(w => 
    w.name.includes(search) || w.description.includes(search)
  );
  
  return (
    <div>
      <input 
        placeholder="Search scripts..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {filtered.map(wf => (
        <ScriptCard key={wf.name} workflow={wf} />
      ))}
    </div>
  );
}
```

**Register in VIEWS:**
```javascript
// App.jsx
const VIEWS = {
  dashboard: { label: "Dashboard", component: DashboardView },
  workflows: { label: "Workflows", component: WorkflowsView },
  scripts: { label: "Scripts", component: ScriptsView },
  // ...
};
```

#### 3.5 Enhanced Hub Panel

**File:** `gui/desktop/src/components/Dashboard/Panels/HubPanel.jsx` (modify)

**Integration Points:**
- Call `hub_mcp.get_app_list()` via sidecar
- Display all apps from Codehome (unified registry)
- Show agent blocks (capability manifest) with [✦ N] badge
- [Start] / [Stop] / [Restart] buttons
- Inline status indicator (🟢 running / 🔴 stopped / 🟡 idle)

**API Changes:**
```
GET /api/panels/hub → Returns app list + agent blocks
POST /api/panels/hub/action → Run start/stop/restart
  {
    "appId": "weather",
    "action": "start"
  }
```

**Hub MCP Tools Used:**
- `list_apps()` — Get all apps
- `get_app_status(appId)` — Check status
- `start_app(appId)` — Launch app
- `stop_app(appId)` — Shut down app
- `restart_app(appId)` — Restart app
- `get_app_manifest(appId)` — Show agent blocks

#### 3.6 Config Backend Routes

**File:** `gui/sidecar/routes/api_config.py` (new)

**Endpoints:**
```python
@router.get("/api/config")
async def get_config():
    """Return current LLM config + flags."""
    return {
        "llm": {
            "activeModel": "ollama",  # or "anthropic"
            "ollama": { "host": "http://localhost:11434" },
            "anthropic": { "baseUrl": "...", "apiKey": "•••••" }
        },
        "flags": { "shellCommands": True, ... }
    }

@router.put("/api/config")
async def update_config(payload: ConfigUpdate):
    """Save config changes (HITL approval for keys)."""
    # Validate
    # Test connection
    # Write to ~/.agentic-os/config.yaml
    # Emit /ws/config event
    return { "status": "saved" }

@router.post("/api/config/test")
async def test_connection(payload: LLMConfig):
    """Test connection to LLM endpoint."""
    # curl to endpoint
    # Return status (connected / error)
    return { "status": "connected", "details": "..." }
```

**Config File Schema:**
```yaml
# ~/.agentic-os/config.yaml
llm:
  activeModel: ollama  # or anthropic
  ollama:
    host: http://localhost:11434
    baseUrl: http://localhost:11434/v1
  anthropic:
    baseUrl: https://api.anthropic.com/v1
    apiKey: ${ANTHROPIC_API_KEY}  # From env or .env
flags:
  shellCommands: true
  brain2Integration: true
  hubAbsorption: false
```

#### 3.7 Workflows API Endpoint

**File:** `gui/sidecar/routes/api_workflows.py` (new)

**Endpoint:**
```python
@router.get("/api/workflows")
async def list_workflows():
    """Return all workflows from workflows.yaml + metadata."""
    workflows = load_workflows()
    return [
        {
            "name": wf.name,
            "description": wf.description,
            "schedule": wf.schedule or None,
            "costAvg": calculate_avg_cost(wf.name),
            "runCount": count_workflow_runs(wf.name),
            "lastRun": get_last_run(wf.name),
            "steps": [step.name for step in wf.steps]
        }
        for wf in workflows
    ]
```

---

### Sprint 3: Testing & Polish (Week 5-6)

#### 3.8 Integration Testing

**Test Files:**
- `gui/desktop/src/__tests__/Environment.test.jsx` — Config save/load, validation
- `gui/desktop/src/__tests__/Diagnostics.test.jsx` — Collapse/expand, polling
- `gui/desktop/src/__tests__/ScriptsView.test.jsx` — Workflow list, launch
- `gui/sidecar/tests/test_config.py` — Config endpoints, connection test

**Test Coverage:**
- Config validation (URL format, key format, connection)
- localStorage persistence (Diagnostics expanded state, favorites)
- WebSocket events (config changes propagate to UI)
- Hub MCP tool calls (start/stop/status)
- Workflow launch (POST /api/runs with correct payload)

#### 3.9 Documentation & Handoff

**Files:**
- `docs/CHANGELOG.md` — 2026-06-19 Phase 2 completion entry
- `docs/PHASE_2_IMPLEMENTATION_PLAN.md` — This file (updated with completion notes)
- `docs/API.md` — Document new endpoints (/api/config, /api/workflows)
- Brain2 — Copy decisions + plan to `01 - Projects/Agentic OS.md`

---

## 4. Development Workflow

### Local Development Setup

```bash
# Terminal 1: Run sidecar
cd ~/Codehome/AgenticOS
source .venv/bin/activate
python -m gui.sidecar.app

# Terminal 2: Run Tauri dev
cd ~/Codehome/AgenticOS/gui/desktop
npm run tauri dev

# Terminal 3 (optional): Watch tests
npm run test:watch
```

### Git Workflow

1. Create branch: `git checkout -b phase2-gui-env`
2. Work in sprints (weekly commits)
3. Before pushing: `npm run lint && npm run test` (frontend), `pytest` (backend)
4. Update `docs/CHANGELOG.md` in each commit
5. Push to origin: `git push origin phase2-gui-env`
6. Create PR → code review → merge to main

---

## 5. File Manifest

### New Files (12 total)

**Frontend (8):**
1. `gui/desktop/src/components/Dashboard/Tabs/Environment.jsx` — LLM config + flags
2. `gui/desktop/src/components/Sidebar/DiagnosticsPanel.jsx` — System health sidebar
3. `gui/desktop/src/views/ScriptsView.jsx` — Workflow launcher
4. `gui/desktop/src/hooks/useFavorites.js` — Favorites logic
5. `gui/desktop/src/hooks/useDiagnosticsPanel.js` — Collapse/expand logic
6. `gui/desktop/src/__tests__/Environment.test.jsx` — Tests
7. `gui/desktop/src/__tests__/ScriptsView.test.jsx` — Tests
8. `gui/desktop/src/__tests__/Diagnostics.test.jsx` — Tests

**Backend (2):**
9. `gui/sidecar/routes/api_config.py` — Config endpoints
10. `gui/sidecar/routes/api_workflows.py` — Workflow list endpoint
11. `gui/sidecar/tests/test_config.py` — Config tests
12. `gui/sidecar/config/schema.yaml` — Config schema

### Modified Files (6 total)

1. `gui/desktop/src/components/Sidebar/AgentCard.jsx` — Add favorites dropdown
2. `gui/desktop/src/components/Dashboard/TabBar.jsx` — Add Environment tab
3. `gui/desktop/src/App.jsx` — Register ScriptsView in VIEWS
4. `gui/desktop/src/components/Sidebar/Sidebar.jsx` — Add DiagnosticsPanel
5. `gui/sidecar/app.py` — Mount new routes (api_config, api_workflows)
6. `docs/CHANGELOG.md` — Phase 2 entries

---

## 6. API Reference

### New Endpoints

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| GET | `/api/config` | Fetch LLM config + flags | None |
| PUT | `/api/config` | Save config (validated) | HITL approval |
| POST | `/api/config/test` | Test LLM connection | None |
| GET | `/api/workflows` | List all workflows + metadata | None |
| POST | `/api/runs` | Launch a workflow | None |

### WebSocket Events

| Event | Emitted by | Payload |
|-------|-----------|---------|
| `config.updated` | Sidecar (api_config) | `{ llm, flags }` |
| `run.started` | Sidecar (LangGraph) | `{ runId, workflow }` |
| `run.completed` | Sidecar (LangGraph) | `{ runId, cost, duration }` |

---

## 7. Timeline & Milestones

| Sprint | Week | Goal | Deliverable |
|--------|------|------|-------------|
| 1 | 1-2 | Environment tab + Diagnostics | Config UI working, localStorage persistence |
| 2 | 3-4 | Scripts view + Hub integration | Scripts launch workflows, Hub MCP wired |
| 3 | 5-6 | Testing + docs + handoff | Test coverage >80%, docs complete, PR merged |

---

## 8. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Ollama not installed (local mode) | Users can't select local model | Fallback to Anthropic; show install link |
| API key exposure in logs | Security concern | Obfuscate in display, never log plaintext |
| Workflow list too long (100+ scripts) | UI performance | Pagination + search filter |
| WebSocket event flood | Sidecar overload | Debounce config updates, cap event rate |
| Config file corruption | Data loss | Backup + validation on load, atomic writes |

---

## 9. Success Criteria

- ✅ All 5 layout questions answered + accepted
- ✅ Environment tab saves LLM config + tests connection
- ✅ Diagnostics panel collapses/expands with persistence
- ✅ Favorites dropdown launches workflows in <1 second
- ✅ Scripts view loads and filters workflows
- ✅ Hub panel shows all apps from Hub MCP
- ✅ Integration tests pass (frontend + backend)
- ✅ No regressions in existing panels (Queue, Logs, Memory)
- ✅ Docs complete (CHANGELOG, API reference, Brain2 update)
- ✅ PR merged to main with code review sign-off

---

## 10. Next Phases

### Phase 9 — Hub Absorption
Move app management from external Hub (:8085) into Agentic OS natively.
**Depends on:** Phase 2 Hub panel enhancement ✅

### Phase 10+ — Agent Authoring
GUI workflow builder + config management in the app.
**Depends on:** Phase 2 Scripts view ✅

---

**Document Status:** 🟩 Planning  
**Last Updated:** 2026-06-19  
**Next Action:** Execute Sprint 1 (Environment tab + Diagnostics)  
**Owner:** Tony Seneadza
