// ProjectCreationDrawer — Phase 11d (FR-5, project scaffolding GUI).
//
// A right-side drawer that drives the sidecar's project-creation flow:
//   1. On open, loads the template + subfolder catalogues from the sidecar.
//   2. Collects a project name, template, subfolder, description, optional
//      custom port, and repo visibility.
//   3. On submit, opens WS /api/projects/ws/create and streams live progress
//      (the stable step set: validate, folder, port, files, venv, github, git,
//      register), then shows the result (path, port, GitHub URL, warnings).
//
// Conventions (docs/gui-frontend-conventions.md):
//   * Theme tokens only (--bg, --bg-panel, --text, --text-dim, --accent, …).
//   * Hover/transition/keyframe CSS lives in a scoped injected stylesheet with
//     component-prefixed `pcd-*` class names (rule 3) — inline styles can't do
//     :hover / @keyframes.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { get } from "../api";

const WS_URL = "ws://localhost:5130/api/projects/ws/create";

// Slug rule mirrors project_manager.validate_project_name on the sidecar:
// lowercase start, letters/digits/single hyphens, no leading/trailing/double
// hyphen, 1–64 chars. Keep in sync with the backend regex.
const NAME_RE = /^[a-z](?:[a-z0-9]|-(?=[a-z0-9])){0,63}$/;

// Ordered, human-friendly labels for the streamed step names.
const STEP_LABELS = {
  validate: "Validate",
  folder: "Create folder",
  port: "Allocate port",
  files: "Generate files",
  venv: "Create venv",
  github: "GitHub repo",
  git: "Git init + commit",
  register: "Register project",
};

// ── scoped stylesheet (injected once) ────────────────────────────────────────
const STYLE_ID = "pcd-styles";
const CSS = `
.pcd-overlay {
  position: fixed; inset: 0; z-index: 900;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0; pointer-events: none;
  transition: opacity 180ms ease;
}
.pcd-overlay.pcd-open { opacity: 1; pointer-events: auto; }

.pcd-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 901;
  width: min(440px, 92vw);
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  box-shadow: -8px 0 24px rgba(0, 0, 0, 0.35);
  display: flex; flex-direction: column;
  transform: translateX(100%);
  transition: transform 200ms ease;
}
.pcd-drawer.pcd-open { transform: translateX(0); }

.pcd-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid var(--border-soft);
}
.pcd-head h2 { margin: 0; font-size: 0.95rem; color: var(--text); }
.pcd-x {
  background: none; border: none; color: var(--text-dim);
  font-size: 1.25rem; line-height: 1; cursor: pointer; padding: 2px 6px;
}
.pcd-x:hover { color: var(--text); }

.pcd-body { padding: 14px 16px; overflow-y: auto; flex: 1; }

.pcd-field { margin-bottom: 12px; }
.pcd-field label {
  display: block; font-size: 0.72rem; text-transform: uppercase;
  letter-spacing: 0.04em; color: var(--text-dim); margin-bottom: 4px;
}
.pcd-field input, .pcd-field select, .pcd-field textarea {
  width: 100%; box-sizing: border-box;
  background: var(--bg-inset); color: var(--text);
  border: 1px solid var(--border-soft); border-radius: 4px;
  padding: 7px 9px; font-size: 0.82rem; font-family: inherit;
}
.pcd-field input:focus, .pcd-field select:focus, .pcd-field textarea:focus {
  outline: none; border-color: var(--accent);
}
.pcd-field textarea { resize: vertical; min-height: 52px; }
.pcd-hint { font-size: 0.68rem; color: var(--text-dim); margin-top: 3px; }
.pcd-hint.pcd-bad { color: var(--red); }

.pcd-row { display: flex; gap: 10px; }
.pcd-row > * { flex: 1; }

.pcd-check { display: flex; align-items: center; gap: 8px; }
.pcd-check input { width: auto; }
.pcd-check label {
  margin: 0; text-transform: none; letter-spacing: 0; font-size: 0.8rem;
  color: var(--text);
}

.pcd-foot {
  display: flex; gap: 10px; justify-content: flex-end;
  padding: 12px 16px; border-top: 1px solid var(--border-soft);
}
.pcd-btn {
  border: 1px solid var(--border-soft); border-radius: 4px;
  padding: 7px 14px; font-size: 0.8rem; font-weight: 600; cursor: pointer;
  background: var(--bg-inset); color: var(--text);
  transition: filter 120ms ease, background 120ms ease;
}
.pcd-btn:hover:not(:disabled) { filter: brightness(1.15); }
.pcd-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pcd-btn-primary { background: var(--accent); color: #1b1b19; border-color: var(--accent); }

/* progress + result */
.pcd-steps { list-style: none; margin: 0; padding: 0; }
.pcd-step {
  display: flex; align-items: center; gap: 9px;
  padding: 6px 0; font-size: 0.82rem; color: var(--text);
  border-bottom: 1px solid var(--border-soft);
}
.pcd-dot {
  width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto;
  background: var(--text-dim);
}
.pcd-dot.pcd-start { background: var(--yellow); animation: pcd-pulse 1s ease-in-out infinite; }
.pcd-dot.pcd-complete { background: var(--green); }
.pcd-dot.pcd-warning { background: var(--yellow); }
.pcd-dot.pcd-error { background: var(--red); }
.pcd-step-msg { color: var(--text-dim); font-size: 0.72rem; margin-left: auto; text-align: right; }
@keyframes pcd-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

.pcd-result {
  margin-top: 14px; padding: 12px; border-radius: 6px;
  background: var(--bg-inset); border: 1px solid var(--border-soft);
}
.pcd-result h3 { margin: 0 0 8px; font-size: 0.85rem; color: var(--green); }
.pcd-result.pcd-fail h3 { color: var(--red); }
.pcd-kv { margin: 0; font-size: 0.78rem; }
.pcd-kv dt { color: var(--text-dim); }
.pcd-kv dd { margin: 0 0 6px; color: var(--text); word-break: break-all; }
.pcd-warns { margin: 8px 0 0; padding-left: 16px; color: var(--yellow); font-size: 0.74rem; }
.pcd-warns li { margin-bottom: 3px; }
.pcd-link { color: var(--accent); }
`;

function useScopedStyles() {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) return;
    const el = document.createElement("style");
    el.id = STYLE_ID;
    el.textContent = CSS;
    document.head.appendChild(el);
    // Leave the stylesheet mounted for the app's lifetime — it's tiny and other
    // drawer instances reuse it.
  }, []);
}

const EMPTY_FORM = {
  name: "",
  template: "",
  subfolder: "",
  customSubfolder: "",
  description: "",
  customPort: "",
  private: true,
};

// Sentinel select value that reveals the free-text "new folder" input.
const CUSTOM = "__custom__";

// A subfolder name must be a single safe path segment. Spaces are allowed
// (e.g. "The Sciences", "Mobile Apps"); path separators and leading dots aren't.
const SUBFOLDER_RE = /^[^/\\.][^/\\]*$/;

export default function ProjectCreationDrawer({ open, onClose, onCreated }) {
  useScopedStyles();

  const [templates, setTemplates] = useState([]);
  const [subfolders, setSubfolders] = useState([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [events, setEvents] = useState([]); // [{step, status, message}]
  const [phase, setPhase] = useState("idle"); // idle | creating | done | error
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const wsRef = useRef(null);

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  // Load catalogues whenever the drawer opens (from a clean slate).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPhase("idle");
    setEvents([]);
    setResult(null);
    setErrorMsg("");
    setForm(EMPTY_FORM);

    Promise.all([
      get("/api/projects/templates").catch(() => ({ templates: [] })),
      get("/api/projects/subfolders").catch(() => ({ suggested: [], all: [] })),
    ]).then(([t, s]) => {
      if (cancelled) return;
      const tpls = t.templates || [];
      const subs = (s.suggested && s.suggested.length ? s.suggested : s.all) || [];
      setTemplates(tpls);
      setSubfolders(subs);
      set({
        template: tpls[0]?.id || "",
        subfolder: subs[0] || "apps",
      });
    });

    return () => { cancelled = true; };
  }, [open]);

  // Tear down any live socket when the drawer closes / unmounts.
  useEffect(() => {
    if (open) return;
    wsRef.current?.close();
    wsRef.current = null;
  }, [open]);

  // The effective subfolder is either the picked one or the typed custom name.
  const isCustomSub = form.subfolder === CUSTOM;
  const effectiveSubfolder = isCustomSub
    ? form.customSubfolder.trim()
    : form.subfolder;
  const subfolderValid = SUBFOLDER_RE.test(effectiveSubfolder);

  const nameValid = form.name === "" || NAME_RE.test(form.name);
  const canSubmit =
    phase !== "creating" &&
    NAME_RE.test(form.name) &&
    !!form.template &&
    subfolderValid;

  const portValid =
    form.customPort === "" ||
    (/^\d+$/.test(form.customPort) &&
      +form.customPort >= 1024 &&
      +form.customPort <= 65535);

  function submit(e) {
    e.preventDefault();
    if (!canSubmit || !portValid) return;

    setPhase("creating");
    setEvents([]);
    setResult(null);
    setErrorMsg("");

    let ws;
    try {
      ws = new WebSocket(WS_URL);
    } catch (err) {
      setPhase("error");
      setErrorMsg(`Could not open connection: ${err}`);
      return;
    }
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          name: form.name,
          template: form.template,
          subfolder: effectiveSubfolder,
          description: form.description || null,
          custom_port: form.customPort ? +form.customPort : null,
          private: form.private,
        })
      );
    };

    ws.onmessage = (m) => {
      let msg;
      try {
        msg = JSON.parse(m.data);
      } catch {
        return;
      }
      if (msg.step === "complete" && msg.status === "success") {
        setResult(msg.result || null);
        setPhase("done");
        onCreated?.(msg.result);
        ws.close();
        return;
      }
      if (msg.step === "error" || msg.status === "failed") {
        setErrorMsg(msg.error || msg.message || "Project creation failed");
        setPhase("error");
        ws.close();
        return;
      }
      // Progress frame — collapse repeats of the same step to its latest status.
      setEvents((prev) => {
        const next = prev.filter((e2) => e2.step !== msg.step);
        next.push({ step: msg.step, status: msg.status, message: msg.message });
        return next;
      });
    };

    ws.onerror = () => {
      // onclose follows; only surface if we weren't already finished.
      setPhase((p) => (p === "creating" ? "error" : p));
      setErrorMsg((e2) => e2 || "Connection error — is the sidecar running on :5130?");
    };

    ws.onclose = () => {
      setPhase((p) => (p === "creating" ? "error" : p));
      setErrorMsg((e2) =>
        e2 || (result ? "" : "Connection closed before completion.")
      );
    };
  }

  const busy = phase === "creating";

  const orderedEvents = useMemo(() => {
    const order = Object.keys(STEP_LABELS);
    return [...events].sort(
      (a, b) => order.indexOf(a.step) - order.indexOf(b.step)
    );
  }, [events]);

  return (
    <>
      <div
        className={`pcd-overlay${open ? " pcd-open" : ""}`}
        onClick={busy ? undefined : onClose}
      />
      <aside className={`pcd-drawer${open ? " pcd-open" : ""}`} aria-hidden={!open}>
        <div className="pcd-head">
          <h2>Create New Project</h2>
          <button className="pcd-x" onClick={busy ? undefined : onClose} title="Close">
            ×
          </button>
        </div>

        <form className="pcd-body" onSubmit={submit}>
          <div className="pcd-field">
            <label>Project name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set({ name: e.target.value })}
              placeholder="my-project"
              disabled={busy}
              autoFocus
            />
            {!nameValid && (
              <div className="pcd-hint pcd-bad">
                Lowercase letters, digits and single hyphens; must start with a
                letter.
              </div>
            )}
          </div>

          <div className="pcd-field">
            <label>Template *</label>
            <select
              value={form.template}
              onChange={(e) => set({ template: e.target.value })}
              disabled={busy}
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.icon ? `${t.icon} ` : ""}
                  {t.name}
                </option>
              ))}
            </select>
            {templates.find((t) => t.id === form.template)?.description && (
              <div className="pcd-hint">
                {templates.find((t) => t.id === form.template).description}
              </div>
            )}
          </div>

          <div className="pcd-row">
            <div className="pcd-field">
              <label>Subfolder</label>
              <select
                value={form.subfolder}
                onChange={(e) => set({ subfolder: e.target.value })}
                disabled={busy}
              >
                {subfolders.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
                {subfolders.length === 0 && <option value="apps">apps</option>}
                <option value={CUSTOM}>＋ New folder…</option>
              </select>
              {isCustomSub && (
                <input
                  type="text"
                  value={form.customSubfolder}
                  onChange={(e) => set({ customSubfolder: e.target.value })}
                  placeholder="e.g. The Sciences"
                  disabled={busy}
                  style={{ marginTop: 6 }}
                  autoFocus
                />
              )}
              {isCustomSub && form.customSubfolder && !subfolderValid && (
                <div className="pcd-hint pcd-bad">No slashes or leading dot.</div>
              )}
            </div>
            <div className="pcd-field">
              <label>Custom port</label>
              <input
                type="number"
                value={form.customPort}
                onChange={(e) => set({ customPort: e.target.value })}
                placeholder="auto"
                min="1024"
                max="65535"
                disabled={busy}
              />
              {!portValid && (
                <div className="pcd-hint pcd-bad">1024–65535</div>
              )}
            </div>
          </div>

          <div className="pcd-field">
            <label>Description</label>
            <textarea
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
              placeholder="What does this project do?"
              disabled={busy}
            />
          </div>

          <div className="pcd-field pcd-check">
            <input
              id="pcd-private"
              type="checkbox"
              checked={form.private}
              onChange={(e) => set({ private: e.target.checked })}
              disabled={busy}
            />
            <label htmlFor="pcd-private">Create GitHub repo as private</label>
          </div>

          {(orderedEvents.length > 0 || phase !== "idle") && (
            <ul className="pcd-steps">
              {orderedEvents.map((ev) => (
                <li className="pcd-step" key={ev.step}>
                  <span className={`pcd-dot pcd-${ev.status}`} />
                  <span>{STEP_LABELS[ev.step] || ev.step}</span>
                  {ev.message && <span className="pcd-step-msg">{ev.message}</span>}
                </li>
              ))}
            </ul>
          )}

          {phase === "done" && result && (
            <div className="pcd-result">
              <h3>✓ Project created</h3>
              <dl className="pcd-kv">
                <dt>Path</dt>
                <dd>{result.path}</dd>
                <dt>Port</dt>
                <dd>{result.port}</dd>
                {result.github_url && (
                  <>
                    <dt>GitHub</dt>
                    <dd>
                      <a
                        className="pcd-link"
                        href={result.github_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {result.github_url}
                      </a>
                      {result.pushed ? " · pushed" : " · not pushed"}
                    </dd>
                  </>
                )}
              </dl>
              {result.warnings && result.warnings.length > 0 && (
                <ul className="pcd-warns">
                  {result.warnings.map((w, i) => (
                    <li key={i}>⚠ {w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {phase === "error" && (
            <div className="pcd-result pcd-fail">
              <h3>✗ Creation failed</h3>
              <div className="pcd-hint pcd-bad">{errorMsg}</div>
            </div>
          )}
        </form>

        <div className="pcd-foot">
          {phase === "done" ? (
            <button type="button" className="pcd-btn pcd-btn-primary" onClick={onClose}>
              Done
            </button>
          ) : (
            <>
              <button
                type="button"
                className="pcd-btn"
                onClick={onClose}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="pcd-btn pcd-btn-primary"
                onClick={submit}
                disabled={!canSubmit || !portValid}
              >
                {busy ? "Creating…" : "Create Project"}
              </button>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
