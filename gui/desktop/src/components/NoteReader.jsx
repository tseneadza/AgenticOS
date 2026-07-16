/**
 * NoteReader — read-mode markdown renderer for one vault note (Phase 16b).
 *
 * Props:
 *   note    — { path, content, mtime, size } from GET /api/vault/note (or null)
 *   loading — request in flight
 *   error   — error string (or null)
 *
 * SECURITY (design §7, Fable 5 review HIGH): the renderer builds React
 * elements from the raw markdown — never dangerouslySetInnerHTML. The Tauri
 * webview origin is CORS-allowlisted at the sidecar, so a <script> smuggled
 * through a note must never reach the DOM as markup. React's text escaping
 * is the defense; keep it that way.
 *
 * Edit mode + Save + New arrive with 16d.
 */

const STYLE_ID = "nr-styles";
const STYLE_CSS = `
.nr-body { font-size: 13px; line-height: 1.65; color: var(--text); }
.nr-body h1, .nr-body h2, .nr-body h3, .nr-body h4 {
  color: var(--text); line-height: 1.3; margin: 14px 0 6px;
}
.nr-body h1 { font-size: 18px; border-bottom: 1px solid var(--border-soft); padding-bottom: 4px; }
.nr-body h2 { font-size: 15.5px; }
.nr-body h3 { font-size: 13.5px; }
.nr-body h4 { font-size: 12.5px; color: var(--text-dim); }
.nr-body p { margin: 6px 0; }
.nr-body ul { margin: 4px 0 4px 18px; padding: 0; }
.nr-body li { margin: 2px 0; }
.nr-code-block {
  font-family: var(--mono);
  font-size: 11.5px;
  background: var(--bg-inset);
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  padding: 8px 10px;
  margin: 8px 0;
  overflow-x: auto;
  white-space: pre;
  color: var(--text-dim);
}
.nr-inline-code {
  font-family: var(--mono);
  font-size: 11.5px;
  background: var(--bg-inset);
  border-radius: 4px;
  padding: 1px 4px;
  color: var(--yellow);
}
.nr-wikilink { color: var(--accent); }
.nr-tag { color: var(--green); }
.nr-hr { border: none; border-top: 1px solid var(--border-soft); margin: 12px 0; }
.nr-frontmatter {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-dim);
  background: var(--bg-inset);
  border-left: 2px solid var(--border-soft);
  padding: 6px 10px;
  margin: 0 0 10px;
  white-space: pre-wrap;
}
.nr-meta { font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }
`;

function useScopedStyles() {
  if (typeof document !== "undefined" && !document.getElementById(STYLE_ID)) {
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = STYLE_CSS;
    document.head.appendChild(el);
  }
}

// ── inline markdown → React elements (escape-first by construction: every
// piece of note text lands in a React text node, never in markup) ──────────
function renderInline(text, keyBase) {
  const parts = [];
  // wikilinks · inline code · bold · italics · tags — one pass, first match wins
  const re = /\[\[([^\]]+)\]\]|`([^`\n]+)`|\*\*([^*]+)\*\*|\*([^*\n]+)\*|(?:^|(?<=\s))#([A-Za-z][\w/-]*)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const key = `${keyBase}-${i++}`;
    if (m[1] !== undefined) {
      const label = m[1].split("|").pop().split("#")[0];
      parts.push(<span key={key} className="nr-wikilink">[[{label}]]</span>);
    } else if (m[2] !== undefined) {
      parts.push(<code key={key} className="nr-inline-code">{m[2]}</code>);
    } else if (m[3] !== undefined) {
      parts.push(<strong key={key}>{m[3]}</strong>);
    } else if (m[4] !== undefined) {
      parts.push(<em key={key}>{m[4]}</em>);
    } else if (m[5] !== undefined) {
      parts.push(<span key={key} className="nr-tag">#{m[5]}</span>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// ── block-level markdown → React elements ──────────────────────────────────
export function renderMarkdown(source) {
  const blocks = [];
  let lines = source.split("\n");
  let key = 0;

  // frontmatter → dim preamble block
  if (lines[0] === "---") {
    const end = lines.indexOf("---", 1);
    if (end > 0) {
      blocks.push(
        <div key={`fm-${key++}`} className="nr-frontmatter">{lines.slice(1, end).join("\n")}</div>
      );
      lines = lines.slice(end + 1);
    }
  }

  let para = [];
  let list = [];
  const flushPara = () => {
    if (para.length) {
      const text = para.join(" ");
      blocks.push(<p key={`p-${key++}`}>{renderInline(text, `p${key}`)}</p>);
      para = [];
    }
  };
  const flushList = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${key++}`}>
          {list.map((item, idx) => (
            <li key={idx}>{renderInline(item, `li${key}-${idx}`)}</li>
          ))}
        </ul>
      );
      list = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("```")) {
      flushPara();
      flushList();
      const fence = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) fence.push(lines[i++]);
      blocks.push(<pre key={`c-${key++}`} className="nr-code-block">{fence.join("\n")}</pre>);
      continue;
    }

    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushPara();
      flushList();
      const Tag = `h${h[1].length}`;
      blocks.push(<Tag key={`h-${key++}`}>{renderInline(h[2], `h${key}`)}</Tag>);
      continue;
    }

    if (/^(-{3,}|\*{3,})\s*$/.test(line)) {
      flushPara();
      flushList();
      blocks.push(<hr key={`hr-${key++}`} className="nr-hr" />);
      continue;
    }

    const li = line.match(/^\s*[-*+]\s+(.*)$/);
    if (li) {
      flushPara();
      list.push(li[1]);
      continue;
    }

    if (line.trim() === "") {
      flushPara();
      flushList();
      continue;
    }

    flushList();
    para.push(line.trim());
  }
  flushPara();
  flushList();
  return blocks;
}

export default function NoteReader({ note, loading, error }) {
  useScopedStyles();

  if (loading) {
    return <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }}>Loading note…</div>;
  }
  if (error) {
    return <div style={{ color: "var(--red)", fontSize: 12, padding: 8 }} data-testid="nr-error">{error}</div>;
  }
  if (!note) {
    return (
      <div style={{ color: "var(--text-dim)", fontSize: 12, padding: 8 }} data-testid="nr-empty">
        Select a note from the tree.
      </div>
    );
  }

  const title = note.path.split("/").pop().replace(/\.md$/i, "");
  return (
    <div data-testid="note-reader">
      <h1 style={{ fontSize: 17, color: "var(--text)", margin: "0 0 2px" }}>{title}</h1>
      <div className="nr-meta">
        {note.path} · {note.size} bytes
      </div>
      <div className="nr-body">{renderMarkdown(note.content || "")}</div>
    </div>
  );
}
