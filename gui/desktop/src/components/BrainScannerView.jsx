/**
 * BrainScannerView — Phase 16 "Brain Scanner": in-app viewer for the Brain2
 * Obsidian vault. Three panes (design §4):
 *
 *   TREE (left)  ·  ORB (center, rotating node cloud)  ·  READER (right)
 *
 * Selection state (selectedPath) lives here and is shared tree ↔ orb ↔
 * reader so all three agree on the active note and the freeze/highlight.
 * 16b: tree + reader read-mode. 16c: orb. 16d adds edit/create.
 */
import { useState, useEffect, useCallback } from "react";
import VaultTree from "./VaultTree.jsx";
import NoteReader from "./NoteReader.jsx";
import BrainOrb from "./BrainOrb.jsx";

const SIDECAR = "http://localhost:5130";

const STYLE_ID = "bsv-styles";
const STYLE_CSS = `
.bsv-root {
  display: grid;
  grid-template-columns: minmax(180px, 230px) minmax(240px, 1.2fr) minmax(260px, 1fr);
  gap: 12px;
  height: 100%;
  min-height: 0;
}
.bsv-pane {
  background: var(--bg-panel);
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 10px;
  overflow-y: auto;
  min-height: 0;
}
.bsv-pane-center { display: flex; flex-direction: column; overflow: hidden; }
.bsv-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.bsv-title { font-size: 12px; font-weight: 600; color: var(--text-dim); letter-spacing: 0.4px; text-transform: uppercase; }
.bsv-refresh {
  background: var(--bg-inset);
  border: 1px solid var(--border-soft);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 11px;
  padding: 2px 8px;
  cursor: pointer;
}
.bsv-refresh:hover { color: var(--accent); border-color: var(--accent); }
.bsv-offline { color: var(--red); font-size: 12px; padding: 8px; }
`;

function useScopedStyles() {
  if (typeof document !== "undefined" && !document.getElementById(STYLE_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = STYLE_CSS;
    document.head.appendChild(el);
  }
}

export default function BrainScannerView() {
  useScopedStyles();
  const [tree, setTree] = useState(null);
  const [treeError, setTreeError] = useState(null);
  const [graph, setGraph] = useState(null);
  const [selectedPath, setSelectedPath] = useState(null);
  const [note, setNote] = useState(null);
  const [noteLoading, setNoteLoading] = useState(false);
  const [noteError, setNoteError] = useState(null);

  const loadVault = useCallback(async (refresh = false) => {
    setTreeError(null);
    try {
      const [tr, gr] = await Promise.all([
        fetch(`${SIDECAR}/api/vault/tree`),
        fetch(`${SIDECAR}/api/vault/graph${refresh ? "?refresh=1" : ""}`),
      ]);
      if (!tr.ok) throw new Error(`vault tree: HTTP ${tr.status}`);
      setTree((await tr.json()).tree);
      setGraph(gr.ok ? await gr.json() : null);
    } catch (e) {
      setTreeError(String(e.message || e));
      setTree(null);
      setGraph(null);
    }
  }, []);

  useEffect(() => {
    loadVault();
  }, [loadVault]);

  // open a note whenever the shared selection changes (tree click OR orb pick)
  useEffect(() => {
    if (!selectedPath) {
      setNote(null);
      return;
    }
    let cancelled = false;
    setNoteLoading(true);
    setNoteError(null);
    (async () => {
      try {
        const r = await fetch(`${SIDECAR}/api/vault/note?path=${encodeURIComponent(selectedPath)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (!cancelled) setNote(data);
      } catch (e) {
        if (!cancelled) setNoteError(`Could not open note: ${e.message || e}`);
      } finally {
        if (!cancelled) setNoteLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedPath]);

  // orb picks only note nodes; tag nodes just freeze/highlight (no reader)
  const onOrbSelect = useCallback((id) => {
    setSelectedPath(id && !id.startsWith("#") ? id : null);
  }, []);

  return (
    <div className="bsv-root" data-testid="brain-scanner">
      <div className="bsv-pane">
        <div className="bsv-head">
          <span className="bsv-title">Vault</span>
          <button className="bsv-refresh" data-testid="bsv-refresh" onClick={() => loadVault(true)}>
            ↻ refresh
          </button>
        </div>
        {treeError ? (
          <div className="bsv-offline" data-testid="bsv-offline">
            Vault unavailable — {treeError}
          </div>
        ) : (
          <VaultTree tree={tree || []} selectedPath={selectedPath} onSelect={setSelectedPath} />
        )}
      </div>

      <div className="bsv-pane bsv-pane-center">
        <div className="bsv-head">
          <span className="bsv-title">Brain Scanner</span>
        </div>
        <BrainOrb graph={graph} selectedPath={selectedPath} onSelect={onOrbSelect} />
      </div>

      <div className="bsv-pane">
        <div className="bsv-head">
          <span className="bsv-title">Note</span>
        </div>
        <NoteReader note={note} loading={noteLoading} error={noteError} />
      </div>
    </div>
  );
}
