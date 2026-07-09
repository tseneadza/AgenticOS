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
    for (const state of ["idle", "thinking", "speaking", "listening", "alert"]) {
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

  it("names its state — the word readout tracks the state prop (14f)", () => {
    stubFetch();
    const { unmount } = render(<OSAOrb state="thinking" status="x" />);
    expect(screen.getByTestId("osa-orb-word")).toHaveTextContent("thinking");
    unmount();
    stubFetch();
    render(<OSAOrb state="alert" status="x" />);
    expect(screen.getByTestId("osa-orb-word")).toHaveTextContent("alert");
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
    // 2026-07-08: the orb now ALSO polls /api/osa/voice/state (live voice
    // states) — only the /api/osa/state status poll must be suppressed.
    const osaStateCalls = global.fetch.mock.calls.filter(
      (c) => String(c[0]).includes("/api/osa/state")
    );
    expect(osaStateCalls).toHaveLength(0);
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

// ── onState observer (2026-07-07): rail piggybacks the orb's state poll ─────
describe("OSAOrb onState callback", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals?.();
  });

  it("invokes onState with each successful /api/osa/state payload", async () => {
    const payload = { ready: true, active_label: "OSA", ollama_up: true, pinned_model: "claude-fable-5" };
    stubFetch(payload);
    const onState = vi.fn();
    render(<OSAOrb onState={onState} />);
    await waitFor(() => expect(onState).toHaveBeenCalled());
    expect(onState.mock.calls[0][0]).toMatchObject({ pinned_model: "claude-fable-5" });
  });

  it("a throwing onState does not break the orb's status line", async () => {
    stubFetch({ ready: true, active_label: "OSA", ollama_up: true });
    const onState = vi.fn(() => { throw new Error("observer boom"); });
    render(<OSAOrb onState={onState} />);
    await waitFor(() =>
      expect(screen.getByText(/Auto · OSA · Ollama up/)).toBeInTheDocument()
    );
    expect(onState).toHaveBeenCalled();
  });

  it("is not called when a caller-provided status suppresses the poll", async () => {
    stubFetch(STATE);
    const onState = vi.fn();
    render(<OSAOrb status="Local · Ollama up" onState={onState} />);
    await new Promise((r) => setTimeout(r, 30)); // give any (wrong) poll a beat
    // 2026-07-08: voice-state polling is allowed; /api/osa/state is not.
    const osaStateCalls = global.fetch.mock.calls.filter(
      (c) => String(c[0]).includes("/api/osa/state")
    );
    expect(osaStateCalls).toHaveLength(0);
    expect(onState).not.toHaveBeenCalled();
  });
});


// ═════════════════════════════════════════════════════════════════════════════
// Live voice states (2026-07-08) — the orb polls /api/osa/voice/state and maps
// the server-side pipeline states onto its visuals.
// ═════════════════════════════════════════════════════════════════════════════

describe("OSAOrb live voice states", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  function stubVoiceFetch(voice) {
    global.fetch = vi.fn((url) => {
      if (String(url).includes("/api/osa/voice/state"))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(voice) });
      return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
    });
  }

  it("maps server 'listening' onto the orb even when the prop says idle", async () => {
    stubVoiceFetch({ enabled: true, deps_ok: true, state: "listening" });
    render(<OSAOrb state="idle" status="x" />);
    await waitFor(() =>
      expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "listening")
    );
  });

  it("maps server 'transcribing' onto 'thinking'", async () => {
    stubVoiceFetch({ enabled: true, deps_ok: true, state: "transcribing" });
    render(<OSAOrb state="idle" status="x" />);
    await waitFor(() =>
      expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "thinking")
    );
  });

  it("alert prop outranks the live voice state", async () => {
    stubVoiceFetch({ enabled: true, deps_ok: true, state: "listening" });
    render(<OSAOrb state="alert" status="x" />);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "alert");
  });

  it("stays on the prop state when voice is disabled", async () => {
    stubVoiceFetch({ enabled: false, deps_ok: false, state: "disabled" });
    render(<OSAOrb state="idle" status="x" />);
    await new Promise((r) => setTimeout(r, 30));
    expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "idle");
  });
});
