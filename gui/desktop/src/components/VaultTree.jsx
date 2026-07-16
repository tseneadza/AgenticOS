/**
 * VaultTree — recursive folder/file tree of the Brain2 vault (Phase 16b).
 *
 * Props:
 *   tree         — nested entries from GET /api/vault/tree ({name,path,type,children})
 *   selectedPath — relative path of the open note (highlight)
 *   onSelect     — (path) => void, called when a file row is clicked
 *
 * Read-only in 16b; the new-note (＋) affordance arrives with 16d.
 */
import { useState } from "react";

const STYLE_ID = "vt-styles";
const STYLE_CSS = `
.vt-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.5;
  user-select: none;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.vt-row:hover { background: var(--bg-inset); color: var(--text); }
.vt-row.vt-selected { background: var(--bg-inset); color: var(--accent); }
.vt-caret { width: 12px; flex: none; font-size: 9px; color: var(--text-dim); }
.vt-name { overflow: hidden; text-overflow: ellipsis; }
.vt-dir > .vt-name { color: var(--text); font-weight: 600; }
.vt-children { margin-left: 13px; border-left: 1px solid var(--border-soft); padding-left: 5px; }
`;

function useScopedStyles() {
  if (typeof document !== "undefined" && !document.getElementById(STYLE_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = STYLE_CSS;
    document.head.appendChild(el);
  }
}

function TreeNode({ entry, selectedPath, onSelect, depth }) {
  // Top two levels start open so the vault is scannable at first paint.
  const [open, setOpen] = useState(depth < 1);

  if (entry.type === "dir") {
    return (
      <div>
        <div
          className="vt-row vt-dir"
          data-testid={`vt-dir-${entry.path}`}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="vt-caret">{open ? "▼" : "▶"}</span>
          <span className="vt-name">{entry.name}</span>
        </div>
        {open && (
          <div className="vt-children">
            {(entry.children || []).map((child) => (
              <TreeNode
                key={child.path}
                entry={child}
                selectedPath={selectedPath}
                onSelect={onSelect}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  const selected = entry.path === selectedPath;
  return (
    <div
      className={`vt-row${selected ? " vt-selected" : ""}`}
      data-testid={`vt-file-${entry.path}`}
      onClick={() => onSelect(entry.path)}
    >
      <span className="vt-caret">•</span>
      <span className="vt-name">{entry.name.replace(/\.md$/i, "")}</span>
    </div>
  );
}

export default function VaultTree({ tree, selectedPath, onSelect }) {
  useScopedStyles();
  if (!tree || tree.length === 0) {
    return <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }}>Vault is empty.</div>;
  }
  return (
    <div data-testid="vault-tree">
      {tree.map((entry) => (
        <TreeNode
          key={entry.path}
          entry={entry}
          selectedPath={selectedPath}
          onSelect={onSelect}
          depth={0}
        />
      ))}
    </div>
  );
}
