/**
 * Scripts View — Browse, manage, and run workflows with usage instructions
 *
 * Features:
 * - Tabbed interface: Scripts | Queue | Logs | Memory | Environment
 * - Workflow list with search/filter
 * - Click workflow to see usage instructions
 * - [Run Now] button to launch workflow
 * - Shows cost metrics, schedule, last run time
 * - Usage info panel with how to use each script
 *
 * Persists:
 * - Active tab to localStorage
 * - Selected workflow to localStorage
 * - Expanded workflows state to localStorage
 */

import { useEffect, useRef, useState } from "react";
import { get, post } from "../api";
import TabBar from "../components/Dashboard/TabBar";
import Queue from "../components/Dashboard/Tabs/Queue";
import Logs from "../components/Dashboard/Tabs/Logs";
import Memory from "../components/Dashboard/Tabs/Memory";
import Environment from "../components/Dashboard/Tabs/Environment";
import "./ScriptsView.css";

const SCRIPTS_TAB_KEY = "agentic-os.scriptsTab";
const SCRIPTS_SELECTED_KEY = "agentic-os.scriptsSelected";
const SCRIPTS_EXPANDED_KEY = "agentic-os.scriptsExpanded";

const TABS = [
  { id: "scripts", label: "Workflows" },
  { id: "all-scripts", label: "All Scripts" },
  { id: "queue", label: "Queue", component: Queue },
  { id: "logs", label: "Logs", component: Logs },
  { id: "memory", label: "Memory", component: Memory },
  { id: "environment", label: "Environment", component: Environment },
];

// Sample usage instructions for workflows
const USAGE_INSTRUCTIONS = {
  "morning-briefing": {
    description: "Daily briefing compiled from Brain2 notes",
    howToUse: [
      "1. This workflow runs automatically at 7 AM daily",
      "2. It gathers all notes from your Brain2 vault",
      "3. Summarizes them using Claude AI",
      "4. Writes a reflection to your vault",
      "To run manually, click [Run Now]",
    ],
    inputs: ["None — automatically uses Brain2 vault"],
    outputs: ["Daily reflection entry in Brain2"],
  },
  "process-raw-notes": {
    description: "Process and organize unprocessed notes",
    howToUse: [
      "1. Add notes to the 00 - Raw folder in Brain2",
      "2. Run this workflow to process them",
      "3. Notes are classified and filed appropriately",
      "4. Original notes are archived",
      "Use this when your inbox gets full",
    ],
    inputs: ["Notes in 00 - Raw folder"],
    outputs: ["Organized and filed notes"],
  },
  "research-learning-notes": {
    description: "Deep research on learning topics",
    howToUse: [
      "1. Create a note in 02 - Learning with status: processing",
      "2. Run this workflow to research it",
      "3. Claude performs web + knowledge research",
      "4. Generates analysis and summary documents",
      "Best for learning new concepts",
    ],
    inputs: ["Learning notes with status: processing"],
    outputs: ["Research report + quick summary"],
  },
};

function formatTime(timestamp) {
  if (!timestamp) return "—";
  const d = new Date(timestamp * 1000);
  return d.toLocaleDateString() + " " + d.toLocaleTimeString();
}

function ScriptsTab({ workflows, selectedWf, onSelectWorkflow, onRunWorkflow, busy, expanded, onToggleExpanded, onSearch, searchQuery }) {
  return (
    <div className="scripts-view-container">
      {/* Left: Workflow list */}
      <div className="scripts-list-panel">
        <div className="scripts-search">
          <input
            type="text"
            placeholder="Search workflows…"
            value={searchQuery}
            onChange={(e) => onSearch(e.target.value)}
            className="search-input"
          />
        </div>

        <div className="scripts-list">
          {workflows.length === 0 ? (
            <div className="empty">No workflows defined</div>
          ) : (
            workflows.map((wf) => (
              <div
                key={wf.name}
                className={`script-item${selectedWf === wf.name ? " selected" : ""}`}
                onClick={() => onSelectWorkflow(wf.name)}
              >
                <div className="script-item-header">
                  <span className="script-item-name">{wf.name}</span>
                  <span className="script-item-cost">${(wf.costAvg || 0).toFixed(2)}</span>
                </div>
                <div className="script-item-meta">
                  <span className="meta-runs">Runs: {wf.runCount || 0}</span>
                  <span className="meta-schedule">{wf.schedule || "—"}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Script details + usage instructions */}
      <div className="scripts-detail-panel">
        {selectedWf ? (
          (() => {
            const wf = workflows.find((w) => w.name === selectedWf);
            const usage = USAGE_INSTRUCTIONS[selectedWf] || {};

            // Guard: a persisted/stale selection (or one filtered out by search)
            // may not exist in the current list. Don't deref undefined.
            if (!wf) {
              return (
                <div className="scripts-detail-panel-empty">
                  <div className="empty-state">
                    <span className="empty-icon">📋</span>
                    <p>Select a script to see usage instructions</p>
                  </div>
                </div>
              );
            }

            return (
              <div className="script-details-view">
                <div className="details-header">
                  <h2>{wf.name}</h2>
                  <button
                    className="btn approve"
                    disabled={busy === wf.name}
                    onClick={() => onRunWorkflow(wf.name)}
                  >
                    {busy === wf.name ? "Running…" : "Run Now"}
                  </button>
                </div>

                <div className="details-description">
                  {wf.description || usage.description || "No description available"}
                </div>

                {/* Metrics */}
                <div className="details-section">
                  <h3>Metrics</h3>
                  <div className="metrics-grid">
                    <div className="metric">
                      <span className="metric-label">Average Cost</span>
                      <span className="metric-value">${(wf.costAvg || 0).toFixed(4)}</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Total Runs</span>
                      <span className="metric-value">{wf.runCount || 0}</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Last Run</span>
                      <span className="metric-value">{formatTime(wf.lastRun)}</span>
                    </div>
                    <div className="metric">
                      <span className="metric-label">Schedule</span>
                      <span className="metric-value" style={{ fontFamily: "var(--mono)" }}>
                        {wf.schedule || "Manual"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* How to Use */}
                {usage.howToUse && (
                  <div className="details-section">
                    <h3>📖 How to Use</h3>
                    <div className="how-to-use">
                      {usage.howToUse.map((step, i) => (
                        <div key={i} className="how-to-step">
                          {step}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Inputs/Outputs */}
                {(usage.inputs || usage.outputs) && (
                  <div className="details-section">
                    <div className="io-grid">
                      {usage.inputs && (
                        <div className="io-block">
                          <h4>Input</h4>
                          <ul>
                            {(Array.isArray(usage.inputs) ? usage.inputs : [usage.inputs]).map((inp, i) => (
                              <li key={i}>{inp}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {usage.outputs && (
                        <div className="io-block">
                          <h4>Output</h4>
                          <ul>
                            {(Array.isArray(usage.outputs) ? usage.outputs : [usage.outputs]).map((out, i) => (
                              <li key={i}>{out}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Steps */}
                {wf.steps && wf.steps.length > 0 && (
                  <div className="details-section">
                    <h3>Steps</h3>
                    <div className="steps-list">
                      {wf.steps.map((step, i) => (
                        <div key={i} className="step-item">
                          <span className="step-num">{i + 1}</span>
                          <span className="step-name">{step}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()
        ) : (
          <div className="scripts-detail-panel-empty">
            <div className="empty-state">
              <span className="empty-icon">📋</span>
              <p>Select a script to see usage instructions</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AllScriptsTab({ scriptsByApp, selectedScript, onSelectScript }) {
  const [expandedApps, setExpandedApps] = useState({});
  const [searchQuery, setSearchQuery] = useState("");

  const toggleApp = (appName) => {
    setExpandedApps((prev) => ({ ...prev, [appName]: !prev[appName] }));
  };

  // Filter scripts by search
  const filteredApps = {};
  Object.entries(scriptsByApp).forEach(([app, scripts]) => {
    const filtered = scripts.filter(
      (s) =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.description?.toLowerCase().includes(searchQuery.toLowerCase())
    );
    if (filtered.length > 0) {
      filteredApps[app] = filtered;
    }
  });

  return (
    <div className="scripts-view-container">
      {/* Left: App list */}
      <div className="scripts-list-panel">
        <div className="scripts-search">
          <input
            type="text"
            placeholder="Search scripts…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
        </div>

        <div className="scripts-list">
          {Object.keys(filteredApps).length === 0 ? (
            <div className="empty">No scripts found</div>
          ) : (
            Object.entries(filteredApps).map(([app, scripts]) => (
              <div key={app}>
                <div
                  className="app-header"
                  onClick={() => toggleApp(app)}
                  style={{ cursor: "pointer" }}
                >
                  <span className="disclosure">
                    {expandedApps[app] ? "▾" : "▸"}
                  </span>
                  <span className="app-name">{app}</span>
                  <span className="app-count">{scripts.length}</span>
                </div>

                {expandedApps[app] && (
                  <div className="app-scripts">
                    {scripts.map((script) => (
                      <div
                        key={`${app}/${script.name}`}
                        className={`script-item${
                          selectedScript?.path === script.path ? " selected" : ""
                        }`}
                        onClick={() => onSelectScript({ ...script, app })}
                      >
                        <div className="script-item-name">{script.name}</div>
                        <div className="script-item-type">{script.type}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Script details */}
      <div className="scripts-detail-panel">
        {selectedScript ? (
          <div className="script-details-view">
            <div className="details-header">
              <div>
                <h2>{selectedScript.name}</h2>
                <p className="details-app">{selectedScript.app}</p>
              </div>
            </div>

            <div className="details-description">
              {selectedScript.description}
            </div>

            <div className="details-section">
              <h3>Information</h3>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Type</span>
                  <span className="info-value">{selectedScript.type}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Executable</span>
                  <span className="info-value">
                    {selectedScript.executable ? "Yes" : "No"}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Modified</span>
                  <span className="info-value">
                    {selectedScript.modified ? new Date(selectedScript.modified * 1000).toLocaleDateString() : "—"}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Size</span>
                  <span className="info-value">
                    {(selectedScript.size / 1024).toFixed(1)} KB
                  </span>
                </div>
              </div>
            </div>

            <div className="details-section">
              <h3>Path</h3>
              <div className="path-display">{selectedScript.path}</div>
            </div>

            {selectedScript.usage && selectedScript.usage.length > 0 && (
              <div className="details-section">
                <h3>📖 Usage</h3>
                <ul className="usage-list">
                  {selectedScript.usage.map((u, i) => (
                    <li key={i}>{u}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div className="scripts-detail-panel-empty">
            <div className="empty-state">
              <span className="empty-icon">📂</span>
              <p>Select a script to see details</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ScriptsView({ ctx }) {
  const [workflows, setWorkflows] = useState([]);
  const [scriptsByApp, setScriptsByApp] = useState({});
  const [scriptsError, setScriptsError] = useState(null);
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(SCRIPTS_TAB_KEY) || "scripts");
  const [selectedWf, setSelectedWf] = useState(() => localStorage.getItem(SCRIPTS_SELECTED_KEY) || null);
  const [selectedScript, setSelectedScript] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [busy, setBusy] = useState(null);
  const [expanded, setExpanded] = useState(
    JSON.parse(localStorage.getItem(SCRIPTS_EXPANDED_KEY) || "{}")
  );

  // Load workflows and scripts
  useEffect(() => {
    get("/api/workflows")
      .then((data) => {
        setWorkflows(data.workflows || []);
      })
      .catch((e) => console.error("Failed to load workflows:", e));

    get("/api/scripts")
      .then((data) => {
        setScriptsByApp(data.apps || {});
        setScriptsError(null);
      })
      .catch((e) => {
        console.error("Failed to load scripts:", e);
        setScriptsError(e.message);
      });
  }, []);

  // Persist tab selection
  useEffect(() => {
    localStorage.setItem(SCRIPTS_TAB_KEY, activeTab);
  }, [activeTab]);

  // Persist selected workflow
  useEffect(() => {
    if (selectedWf) {
      localStorage.setItem(SCRIPTS_SELECTED_KEY, selectedWf);
    }
  }, [selectedWf]);

  const runWorkflow = (name) => {
    setBusy(name);
    post(`/api/workflows/${name}/run`)
      .catch((e) => console.error(`Failed to run workflow ${name}:`, e))
      .finally(() => setBusy(null));
  };

  const filteredWorkflows = workflows.filter(
    (wf) =>
      wf.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      wf.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const tab = TABS.find((t) => t.id === activeTab);
  const TabComponent = tab?.component;

  return (
    <div className="scripts-view">
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="scripts-content">
        {activeTab === "scripts" ? (
          <ScriptsTab
            workflows={filteredWorkflows}
            selectedWf={selectedWf}
            onSelectWorkflow={setSelectedWf}
            onRunWorkflow={runWorkflow}
            busy={busy}
            expanded={expanded}
            onToggleExpanded={(name) => {
              setExpanded((prev) => ({ ...prev, [name]: !prev[name] }));
            }}
            onSearch={setSearchQuery}
            searchQuery={searchQuery}
          />
        ) : activeTab === "all-scripts" ? (
          scriptsError ? (
            <div className="empty" style={{ color: "var(--red)" }}>
              Error loading scripts: {scriptsError}
            </div>
          ) : Object.keys(scriptsByApp).length === 0 ? (
            <div className="empty">Loading scripts or no scripts found...</div>
          ) : (
            <AllScriptsTab
              scriptsByApp={scriptsByApp}
              selectedScript={selectedScript}
              onSelectScript={setSelectedScript}
            />
          )
        ) : TabComponent ? (
          <TabComponent ctx={ctx} />
        ) : (
          <div className="empty">Tab not implemented</div>
        )}
      </div>
    </div>
  );
}
