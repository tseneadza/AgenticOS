import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import OSAOrb from "../components/OSAOrb";

// OSAOrb fetches GET /api/osa/state on mount (only when no `status` prop is
// given) via the api.js get() helper, which calls global fetch. Stub it.
const STATE = { ready: true, active_label: "OSA · Qwen", ollama_up: true };

function stubFetch(state = STATE) {
  global.fetch = vi.fn((url) => {
    if (url.includes("/api/osa/state"))
      return Promise.resolve({ ok: true, json: () => Promise.resolve(state) });
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
}

describe("OSAOrb", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders the OSA label and reactor", () => {
    stubFetch();
    render(<OSAOrb />);
    expect(screen.getByText("OSA")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /OSA reactor/i })).toBeInTheDocument();
  });

  it("defaults to the idle state and the 'Standing by.' caption", () => {
    stubFetch();
    render(<OSAOrb />);
    expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "idle");
    expect(screen.getByText("Standing by.")).toBeInTheDocument();
  });

  it("applies the correct data-state for each state prop", () => {
    for (const state of ["idle", "thinking", "speaking", "listening"]) {
      stubFetch();
      const { unmount } = render(<OSAOrb state={state} status="x" />);
      expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", state);
      unmount();
    }
  });

  it("falls back to idle for an unknown state", () => {
    stubFetch();
    render(<OSAOrb state="bogus" status="x" />);
    expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "idle");
  });

  it("shows the lastLine caption when provided", () => {
    stubFetch();
    render(<OSAOrb lastLine="RAM's at 73%. You're fine." status="x" />);
    expect(screen.getByText("RAM's at 73%. You're fine.")).toBeInTheDocument();
  });

  it("shows a caller-provided status and does not poll /api/osa/state", () => {
    stubFetch();
    render(<OSAOrb status="Local · Ollama up" />);
    expect(screen.getByText("Local · Ollama up")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("populates the status sub-caption from /api/osa/state when no status prop", async () => {
    stubFetch();
    render(<OSAOrb />);
    await waitFor(() =>
      expect(screen.getByText(/OSA · Qwen · Ollama up/)).toBeInTheDocument()
    );
  });

  it("calls onOpen when clicked", () => {
    stubFetch();
    const onOpen = vi.fn();
    render(<OSAOrb status="x" onOpen={onOpen} />);
    fireEvent.click(screen.getByTestId("osa-orb"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("exposes an accessible name for the clickable wrapper", () => {
    stubFetch();
    render(<OSAOrb status="x" />);
    expect(screen.getByRole("button", { name: /Open OSA chat/i })).toBeInTheDocument();
  });

  it("degrades silently when /api/osa/state fails", async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    );
    render(<OSAOrb />);
    // Still renders the orb + default caption; no throw.
    expect(screen.getByText("OSA")).toBeInTheDocument();
    expect(screen.getByText("Standing by.")).toBeInTheDocument();
  });
});

// ── Brain display (2026-07-07): pin + runtime truth in the status line ──────
describe("OSAOrb brain display", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals?.();
  });

  it("shows Auto and the active label when nothing is pinned", async () => {
    stubFetch({ ready: true, active_label: "Qwen2.5 7B Instruct (local)", ollama_up: true });
    render(<OSAOrb />);
    await waitFor(() =>
      expect(screen.getByText(/Auto · Qwen2\.5 7B Instruct \(local\) · Ollama up/)).toBeInTheDocument()
    );
  });

  it("shows the pin when pinned and no escalation", async () => {
    stubFetch({
      ready: true, active_label: "irrelevant", ollama_up: true,
      pinned_model: "qwen2.5:7b-instruct",
      pinned_label: "Qwen2.5 7B Instruct (local)",
      last_turn_escalated: false,
    });
    render(<OSAOrb />);
    await waitFor(() =>
      expect(screen.getByText(/Pinned: Qwen2\.5 7B Instruct \(local\) · Ollama up/)).toBeInTheDocument()
    );
  });

  it("shows the actual runtime model when the last turn escalated", async () => {
    stubFetch({
      ready: true, active_label: "irrelevant", ollama_up: true,
      pinned_model: "qwen2.5:7b-instruct",
      pinned_label: "Qwen2.5 7B Instruct (local)",
      last_turn_escalated: true,
      last_turn_label: "Claude Sonnet 4.6 (cloud)",
    });
    render(<OSAOrb />);
    await waitFor(() =>
      expect(screen.getByText(/Pinned: Qwen2\.5 7B Instruct \(local\) \(ran Claude Sonnet 4\.6 \(cloud\)\) · Ollama up/)).toBeInTheDocument()
    );
  });
});
