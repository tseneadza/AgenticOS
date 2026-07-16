import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";
import VaultTree from "../components/VaultTree.jsx";
import NoteReader, { renderMarkdown } from "../components/NoteReader.jsx";
import BrainOrb from "../components/BrainOrb.jsx";
import BrainScannerView from "../components/BrainScannerView.jsx";

// Phase 16b+16c — Brain Scanner frontend. jsdom computes no layout
// (gui-frontend-conventions rule 9): we assert classes / testids / content
// only. The orb's Canvas 2D drawing is UNVERIFIABLE here — getContext("2d")
// is null under jsdom — so the orb tests are tripwires (mounting must
// no-op cleanly, never crash) plus the DOM shell (legend, empty state).

// ── fixtures ────────────────────────────────────────────────────────────────

const TREE = [
  {
    name: "01 - Projects",
    path: "01 - Projects",
    type: "dir",
    children: [
      { name: "Agentic OS.md", path: "01 - Projects/Agentic OS.md", type: "file" },
      {
        name: "PRDs",
        path: "01 - Projects/PRDs",
        type: "dir",
        children: [
          { name: "Deep Dive.md", path: "01 - Projects/PRDs/Deep Dive.md", type: "file" },
        ],
      },
    ],
  },
  { name: "Root note.md", path: "Root note.md", type: "file" },
];

const GRAPH = {
  nodes: [
    { id: "01 - Projects/Agentic OS.md", label: "Agentic OS", type: "note", folder: "01 - Projects" },
    { id: "Root note.md", label: "Root note", type: "note", folder: "" },
    { id: "#ai", label: "#ai", type: "tag", folder: null },
  ],
  edges: [
    { source: "01 - Projects/Agentic OS.md", target: "Root note.md" },
    { source: "01 - Projects/Agentic OS.md", target: "#ai" },
  ],
};

const NOTE = {
  path: "01 - Projects/Agentic OS.md",
  content: "# Agentic\n\nBody text.",
  mtime: 1752561000,
  size: 22,
};

// BrainScannerView hits /api/vault/tree + /graph on mount and /note on
// selection. Stub global.fetch per-path (repo convention: ProjectsView.test).
function stubFetch(overrides = {}) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    calls.push({ url, method: opts.method || "GET" });
    const respond = (body) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    if (url.includes("/api/vault/tree")) return respond(overrides.tree ?? { tree: TREE });
    if (url.includes("/api/vault/graph")) {
      if (overrides.graphDown) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
      }
      return respond(overrides.graph ?? GRAPH);
    }
    if (url.includes("/api/vault/note")) return respond(overrides.note ?? NOTE);
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
  return calls;
}

beforeEach(() => {
  // Real jsdom getContext("2d") returns null but logs a noisy "Not
  // implemented" error per call; return null explicitly (same value the
  // component sees on-device-less jsdom) so the orb's null-guard is still
  // exercised without the stderr spam.
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});

afterEach(() => {
  vi.restoreAllMocks();
  delete global.fetch;
});

// ── VaultTree ───────────────────────────────────────────────────────────────

describe("VaultTree", () => {
  it("renders dirs and files from the fixture tree (top levels open)", () => {
    render(<VaultTree tree={TREE} selectedPath={null} onSelect={() => {}} />);
    expect(screen.getByTestId("vault-tree")).toBeInTheDocument();
    expect(screen.getByTestId("vt-dir-01 - Projects")).toBeInTheDocument();
    // file rows show the name without the .md extension
    expect(screen.getByTestId("vt-file-Root note.md")).toHaveTextContent("Root note");
    expect(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md")).toHaveTextContent("Agentic OS");
  });

  it("folder click toggles its children open/closed", () => {
    render(<VaultTree tree={TREE} selectedPath={null} onSelect={() => {}} />);
    // depth-1 dir (PRDs) starts closed — its file is not rendered
    expect(screen.queryByTestId("vt-file-01 - Projects/PRDs/Deep Dive.md")).toBeNull();
    fireEvent.click(screen.getByTestId("vt-dir-01 - Projects/PRDs"));
    expect(screen.getByTestId("vt-file-01 - Projects/PRDs/Deep Dive.md")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("vt-dir-01 - Projects/PRDs"));
    expect(screen.queryByTestId("vt-file-01 - Projects/PRDs/Deep Dive.md")).toBeNull();
  });

  it("collapsing a top-level folder hides its files", () => {
    render(<VaultTree tree={TREE} selectedPath={null} onSelect={() => {}} />);
    expect(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("vt-dir-01 - Projects"));
    expect(screen.queryByTestId("vt-file-01 - Projects/Agentic OS.md")).toBeNull();
  });

  it("file click calls onSelect with the relative path", () => {
    const onSelect = vi.fn();
    render(<VaultTree tree={TREE} selectedPath={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md"));
    expect(onSelect).toHaveBeenCalledWith("01 - Projects/Agentic OS.md");
  });

  it("the selectedPath row carries the vt-selected class (and only it)", () => {
    render(
      <VaultTree tree={TREE} selectedPath="01 - Projects/Agentic OS.md" onSelect={() => {}} />
    );
    expect(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md")).toHaveClass("vt-selected");
    expect(screen.getByTestId("vt-file-Root note.md")).not.toHaveClass("vt-selected");
  });

  it("shows the empty message for a missing or empty tree", () => {
    const { rerender } = render(<VaultTree tree={[]} selectedPath={null} onSelect={() => {}} />);
    expect(screen.getByText("Vault is empty.")).toBeInTheDocument();
    rerender(<VaultTree tree={null} selectedPath={null} onSelect={() => {}} />);
    expect(screen.getByText("Vault is empty.")).toBeInTheDocument();
  });
});

// ── NoteReader — renderMarkdown (SECURITY-CRITICAL) ─────────────────────────

describe("renderMarkdown security (design §7 HIGH — no markup from note text)", () => {
  it("a <script> smuggled in a note never becomes a DOM script element", () => {
    const evil = "<script>alert(1)</script>";
    const { container } = render(<div className="nr-body">{renderMarkdown(evil)}</div>);
    expect(container.querySelectorAll("script").length).toBe(0);
    // React text-escaping: the payload survives only as literal text
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("an <img onerror=...> never becomes a DOM img element", () => {
    const evil = '<img src=x onerror="alert(2)">';
    const { container } = render(<div className="nr-body">{renderMarkdown(evil)}</div>);
    expect(container.querySelectorAll("img").length).toBe(0);
    expect(container.textContent).toContain('<img src=x onerror="alert(2)">');
  });

  it("payloads inside headings, lists and fences also stay text", () => {
    const evil = [
      "# <script>a()</script>",
      "- <img src=x onerror=b()>",
      "```",
      "<script>c()</script>",
      "```",
    ].join("\n");
    const { container } = render(<div className="nr-body">{renderMarkdown(evil)}</div>);
    expect(container.querySelectorAll("script").length).toBe(0);
    expect(container.querySelectorAll("img").length).toBe(0);
    expect(container.querySelector("h1").textContent).toContain("<script>a()</script>");
    expect(container.querySelector("li").textContent).toContain("<img src=x onerror=b()>");
    expect(container.querySelector("pre").textContent).toContain("<script>c()</script>");
  });
});

describe("renderMarkdown structure", () => {
  const SOURCE = [
    "---",
    "title: Test Note",
    "tags: [demo]",
    "---",
    "# Heading One",
    "## Heading Two",
    "Some **bold** and *ital* with `inline()` code, a [[Other Note|alias]] link and a #mytag here.",
    "",
    "- item one",
    "- item two",
    "",
    "---",
    "",
    "```js",
    "const x = 1;",
    "```",
  ].join("\n");

  function renderNote(src = SOURCE) {
    return render(<div className="nr-body">{renderMarkdown(src)}</div>).container;
  }

  it("renders frontmatter as an nr-frontmatter block, not headings/hr", () => {
    const c = renderNote();
    const fm = c.querySelector(".nr-frontmatter");
    expect(fm).not.toBeNull();
    expect(fm.textContent).toContain("title: Test Note");
    expect(fm.textContent).toContain("tags: [demo]");
  });

  it("renders headings at the right levels", () => {
    const c = renderNote();
    expect(c.querySelector("h1").textContent).toBe("Heading One");
    expect(c.querySelector("h2").textContent).toBe("Heading Two");
  });

  it("renders list items", () => {
    const c = renderNote();
    const items = [...c.querySelectorAll("ul li")].map((li) => li.textContent);
    expect(items).toEqual(["item one", "item two"]);
  });

  it("renders a fenced code block with its content and an inline code span", () => {
    const c = renderNote();
    const pre = c.querySelector("pre.nr-code-block");
    expect(pre.textContent).toContain("const x = 1;");
    expect(c.querySelector("code.nr-inline-code").textContent).toBe("inline()");
  });

  it("renders wikilink and tag spans with their classes", () => {
    const c = renderNote();
    // [[Other Note|alias]] → display label after the pipe
    expect(c.querySelector("span.nr-wikilink").textContent).toBe("[[alias]]");
    expect(c.querySelector("span.nr-tag").textContent).toBe("#mytag");
  });

  it("renders bold, italics and a horizontal rule", () => {
    const c = renderNote();
    expect(c.querySelector("strong").textContent).toBe("bold");
    expect(c.querySelector("em").textContent).toBe("ital");
    expect(c.querySelector("hr.nr-hr")).not.toBeNull();
  });
});

// ── NoteReader — component states ───────────────────────────────────────────

describe("NoteReader states", () => {
  it("shows the loading state", () => {
    render(<NoteReader note={null} loading={true} error={null} />);
    expect(screen.getByText(/Loading note/)).toBeInTheDocument();
  });

  it("shows the error state (nr-error)", () => {
    render(<NoteReader note={null} loading={false} error="Could not open note: HTTP 404" />);
    expect(screen.getByTestId("nr-error")).toHaveTextContent("Could not open note: HTTP 404");
  });

  it("shows the empty prompt when no note is selected (nr-empty)", () => {
    render(<NoteReader note={null} loading={false} error={null} />);
    expect(screen.getByTestId("nr-empty")).toHaveTextContent("Select a note from the tree.");
  });

  it("renders the note title from the filename stem plus path/size meta", () => {
    render(<NoteReader note={NOTE} loading={false} error={null} />);
    const reader = screen.getByTestId("note-reader");
    expect(reader.querySelector("h1").textContent).toBe("Agentic OS");
    expect(reader.textContent).toContain("01 - Projects/Agentic OS.md");
    expect(reader.textContent).toContain("22 bytes");
    expect(reader.textContent).toContain("Body text.");
  });
});

// ── BrainScannerView — wiring (fetch on mount, selection, refresh) ──────────

describe("BrainScannerView", () => {
  it("fetches tree + graph on mount and renders all three panes", async () => {
    const calls = stubFetch();
    render(<BrainScannerView />);
    await waitFor(() => expect(screen.getByTestId("vault-tree")).toBeInTheDocument());
    expect(calls.some((c) => c.url.includes("/api/vault/tree"))).toBe(true);
    expect(calls.some((c) => c.url.includes("/api/vault/graph"))).toBe(true);
    expect(screen.getByTestId("brain-scanner")).toBeInTheDocument();
    expect(screen.getByTestId("brain-orb")).toBeInTheDocument();
    expect(screen.getByTestId("nr-empty")).toBeInTheDocument();
    // initial load is NOT a refresh
    expect(calls.some((c) => c.url.includes("refresh=1"))).toBe(false);
  });

  it("shows bsv-offline when the sidecar is down", async () => {
    global.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    render(<BrainScannerView />);
    await waitFor(() => expect(screen.getByTestId("bsv-offline")).toBeInTheDocument());
    expect(screen.getByTestId("bsv-offline").textContent).toContain("Vault unavailable");
    expect(screen.queryByTestId("vault-tree")).toBeNull();
  });

  it("clicking a file fetches the note with an encodeURIComponent'd path and opens the reader", async () => {
    const calls = stubFetch();
    render(<BrainScannerView />);
    await waitFor(() => expect(screen.getByTestId("vault-tree")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md"));

    const encoded = encodeURIComponent("01 - Projects/Agentic OS.md");
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes(`/api/vault/note?path=${encoded}`))).toBe(true)
    );
    await waitFor(() => expect(screen.getByTestId("note-reader")).toBeInTheDocument());
    // shared selection highlights the tree row too
    expect(screen.getByTestId("vt-file-01 - Projects/Agentic OS.md")).toHaveClass("vt-selected");
  });

  it("refresh button re-fetches the graph with ?refresh=1", async () => {
    const calls = stubFetch();
    render(<BrainScannerView />);
    await waitFor(() => expect(screen.getByTestId("vault-tree")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("bsv-refresh"));

    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/api/vault/graph?refresh=1"))).toBe(true)
    );
  });

  it("keeps the tree usable when only the graph endpoint fails (orb-empty)", async () => {
    stubFetch({ graphDown: true });
    render(<BrainScannerView />);
    await waitFor(() => expect(screen.getByTestId("vault-tree")).toBeInTheDocument());
    expect(screen.getByTestId("orb-empty")).toBeInTheDocument();
  });
});

// ── BrainOrb — jsdom tripwires (canvas drawing is on-device-only, rule 9) ───

describe("BrainOrb", () => {
  it("renders orb-empty when graph is null", () => {
    render(<BrainOrb graph={null} selectedPath={null} onSelect={() => {}} />);
    expect(screen.getByTestId("orb-empty")).toHaveTextContent("Graph unavailable.");
  });

  it("mounts with a graph without crashing (getContext('2d') is null in jsdom)", () => {
    // TRIPWIRE: jsdom has no 2D context; the component must no-op cleanly.
    expect(() =>
      render(<BrainOrb graph={GRAPH} selectedPath={null} onSelect={() => {}} />)
    ).not.toThrow();
    expect(screen.getByTestId("brain-orb")).toBeInTheDocument();
    expect(screen.getByTestId("brain-orb").querySelector("canvas")).not.toBeNull();
  });

  it("renders the legend from note folders only (tags excluded, root labeled)", () => {
    render(<BrainOrb graph={GRAPH} selectedPath={null} onSelect={() => {}} />);
    const legend = screen.getByTestId("orb-legend");
    expect(legend.textContent).toContain("01 - Projects");
    expect(legend.textContent).toContain("(root)");
    expect(legend.textContent).not.toContain("#ai");
  });

  it("selection prop + unmount do not throw under jsdom", () => {
    const { rerender, unmount } = render(
      <BrainOrb graph={GRAPH} selectedPath={null} onSelect={() => {}} />
    );
    rerender(
      <BrainOrb graph={GRAPH} selectedPath="01 - Projects/Agentic OS.md" onSelect={() => {}} />
    );
    expect(screen.getByTestId("brain-orb")).toBeInTheDocument();
    expect(() => unmount()).not.toThrow();
  });

  it("source tripwire: the effect null-guards getContext (design §7)", () => {
    // vitest runs with cwd = gui/desktop (import.meta.url is not file:// here)
    const src = fs.readFileSync(
      path.resolve(process.cwd(), "src/components/BrainOrb.jsx"),
      "utf8"
    );
    // canvas.getContext && ...("2d") followed by an early return when falsy
    expect(src).toMatch(/getContext\s*&&\s*canvas\.getContext\("2d"\)/);
    expect(src).toMatch(/if\s*\(!ctx\)\s*return/);
  });
});

// ── VIEWS registry tripwire (App.jsx) ───────────────────────────────────────

describe("VIEWS registry (App.jsx tripwire)", () => {
  const appSrc = fs.readFileSync(path.resolve(process.cwd(), "src/App.jsx"), "utf8");

  it("registers the brain-scanner view", () => {
    expect(appSrc).toContain('id: "brain-scanner"');
    expect(appSrc).toContain('label: "Brain Scanner"');
    expect(appSrc).toContain("component: BrainScannerView");
  });

  it("keeps the VIEW_KEY migration from the obsidian placeholder", () => {
    expect(appSrc).toMatch(/if\s*\(saved === "obsidian"\)\s*saved = "brain-scanner"/);
  });
});
