import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SelfDiagnosticsView from "../components/SelfDiagnosticsView";

// The view fetches /api/diagnostics/cached + /api/diagnostics/system on mount
// via api.get (which uses global fetch). We stub fetch per-path.
function stubFetch({ cached, system }) {
  global.fetch = vi.fn((url) => {
    if (url.includes("/api/diagnostics/cached")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(cached) });
    }
    if (url.includes("/api/diagnostics/system")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(system) });
    }
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
}

describe("SelfDiagnosticsView", () => {
  beforeEach(() => {
    stubFetch({
      cached: { available: false, ts: null, system: null, suites: {} },
      system: {
        ts: 1700000000,
        checks: [
          { id: "sidecar", label: "Sidecar API", status: "ok", detail: "Serving on :5130" },
          { id: "mysql", label: "MySQL (data layer)", status: "warn", detail: "Unreachable" },
          { id: "constitution", label: "Constitution guards", status: "ok", detail: "Enforcing" },
        ],
        summary: { ok: 2, warn: 1, fail: 0, overall: "warn" },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders the dialog title and a Run button", () => {
    render(<SelfDiagnosticsView onClose={() => {}} />);
    expect(screen.getByText("Self-Diagnostics")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run diagnostics/i })).toBeInTheDocument();
  });

  it("loads and renders live system checks with status pills", async () => {
    render(<SelfDiagnosticsView onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText("Sidecar API")).toBeInTheDocument());
    expect(screen.getByText("MySQL (data layer)")).toBeInTheDocument();
    expect(screen.getByText("Constitution guards")).toBeInTheDocument();
    // overall badge derived from summary
    await waitFor(() => expect(screen.getAllByText("warn").length).toBeGreaterThan(0));
  });

  it("shows the two test-suite rows before any run", () => {
    render(<SelfDiagnosticsView onClose={() => {}} />);
    expect(screen.getByText("Backend (pytest)")).toBeInTheDocument();
    expect(screen.getByText("Frontend (vitest)")).toBeInTheDocument();
  });

  it("calls onClose from the close button", () => {
    const onClose = vi.fn();
    render(<SelfDiagnosticsView onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    render(<SelfDiagnosticsView onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
