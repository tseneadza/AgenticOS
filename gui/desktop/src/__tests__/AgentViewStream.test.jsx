// AgentView streaming upgrade (2026-07-07 late) — WS tokens + live tool chips,
// interrupt-based Allow/Deny confirms, thread persistence + transcript restore,
// New chat, timestamps + copy. A controllable MockWebSocket stands in for the
// sidecar's /api/osa/ws/chat; fetch is stubbed for state/history/POST-fallback.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { AgentView } from "../App";

const THREAD_KEY = "agentic-os.osa-thread";

const STATE = {
  ready: true,
  active_model: "qwen2.5:7b-instruct",
  active_label: "Qwen2.5 7B Instruct (local)",
  ollama_up: true,
  soul: "Soul_OSA.md",
};

class MockWebSocket {
  static instances = [];
  static OPEN = 1;
  static CLOSED = 3;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    MockWebSocket.instances.push(this);
  }
  send(data) { this.sent.push(JSON.parse(data)); }
  close() { this.readyState = MockWebSocket.CLOSED; this.onclose?.(); }
  // test drivers
  _open() { this.readyState = MockWebSocket.OPEN; this.onopen?.(); }
  _frame(obj) { this.onmessage?.({ data: JSON.stringify(obj) }); }
  _die() { this.readyState = MockWebSocket.CLOSED; this.onclose?.(); }
}

function stubFetch(overrides = {}) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || "GET";
    let body = null;
    try { body = opts.body ? JSON.parse(opts.body) : null; } catch { /* ignore */ }
    calls.push({ url, method, body });
    const respond = (b) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
    if (url.includes("/api/osa/state")) return respond(overrides.state ?? STATE);
    if (url.includes("/api/osa/history")) return respond(
      overrides.history ?? { exists: false, available: true, turns: [] });
    if (url.includes("/api/osa/chat")) return respond(
      overrides.chat ?? { reply: "fallback reply", thread_id: "osa-post1", route: "default", model: "m", tool_trace: [] });
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
  return calls;
}

async function sendMessage(text = "how's my memory") {
  const box = await screen.findByPlaceholderText(/Message OSA/);
  fireEvent.change(box, { target: { value: text } });
  fireEvent.click(screen.getByText("Send"));
  await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(0));
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  act(() => ws._open());
  return ws;
}

describe("AgentView (OSA streaming chat)", () => {
  beforeEach(() => {
    localStorage.clear();
    MockWebSocket.instances = [];
    global.WebSocket = MockWebSocket;
  });
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
    delete global.WebSocket;
    localStorage.clear();
  });

  it("streams tokens live, then the final frame replaces authoritatively", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage();
    expect(ws.sent[0]).toMatchObject({ message: "how's my memory", thread_id: null });

    act(() => {
      ws._frame({ type: "start", thread_id: "osa-t1", model: "claude-x", route: "default" });
      ws._frame({ type: "token", delta: "RAM's at" });
      ws._frame({ type: "token", delta: " 73%." });
    });
    expect(screen.getByText(/RAM's at 73%\./)).toBeInTheDocument();

    act(() => {
      ws._frame({ type: "final", reply: "RAM's at 73%. Nothing alarming.",
        thread_id: "osa-t1", model: "claude-x", route: "default", tool_trace: [] });
    });
    expect(screen.getByText(/Nothing alarming/)).toBeInTheDocument();
    expect(screen.getByText(/☁ cloud/)).toBeInTheDocument();
  });

  it("shows live tool chips running → done", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage("how's the cpu");

    act(() => ws._frame({ type: "tool_start", tool: "system_health", args: {} }));
    let chip = screen.getByText("system_health").closest(".trace-chip");
    expect(chip.className).toContain("running");

    act(() => ws._frame({ type: "tool_end", tool: "system_health", ok: true }));
    chip = screen.getByText("system_health").closest(".trace-chip");
    expect(chip.className).toContain("done");
  });

  it("renders Allow/Deny on awaiting_confirm and resumes with approve", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage("stop worldwise");

    act(() => ws._frame({ type: "awaiting_confirm", action: "app_stop",
      description: "Stopping worldwise" }));
    expect(screen.getByTestId("agent-confirm")).toBeInTheDocument();
    expect(screen.getByText(/Stopping worldwise/)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/Allow/));
    expect(ws.sent[ws.sent.length - 1]).toEqual({ resume: "approve" });
    // Buttons disable once a decision is made.
    expect(screen.getByText(/Allow/).closest("button")).toBeDisabled();

    act(() => ws._frame({ type: "final", reply: "Understood, Sir. worldwise is down.",
      thread_id: "osa-t1", model: "claude-x", route: "default",
      tool_trace: [{ tool: "stop_app", args: { app_id: "worldwise" } }], confirmed: true }));
    expect(screen.getByText(/worldwise is down/)).toBeInTheDocument();
    expect(screen.queryByTestId("agent-confirm")).not.toBeInTheDocument();
  });

  it("Deny sends a deny resume", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage("stop worldwise");
    act(() => ws._frame({ type: "awaiting_confirm", action: "app_stop",
      description: "Stopping worldwise" }));
    fireEvent.click(screen.getByText(/Deny/));
    expect(ws.sent[ws.sent.length - 1]).toEqual({ resume: "deny" });
  });

  it("resumes over a FRESH socket when the original died mid-confirm", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage("stop worldwise");
    act(() => {
      ws._frame({ type: "start", thread_id: "osa-t9", model: "m", route: "default" });
      ws._frame({ type: "awaiting_confirm", action: "app_stop",
        description: "Stopping worldwise" });
      ws._die(); // socket lost — the interrupt stays parked on the checkpointer
    });
    fireEvent.click(screen.getByText(/Allow/));
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(2));
    const ws2 = MockWebSocket.instances[1];
    act(() => ws2._open());
    expect(ws2.sent[0]).toEqual({ resume: "approve", thread_id: "osa-t9" });
  });

  it("persists the thread_id and restores the transcript on remount", async () => {
    stubFetch();
    const { unmount } = render(<AgentView />);
    const ws = await sendMessage();
    act(() => {
      ws._frame({ type: "start", thread_id: "osa-t1", model: "m", route: "local" });
      ws._frame({ type: "final", reply: "Done.", thread_id: "osa-t1",
        model: "m", route: "local", tool_trace: [] });
    });
    expect(localStorage.getItem(THREAD_KEY)).toBe("osa-t1");
    unmount();

    const calls = stubFetch({ history: { exists: true, available: true, turns: [
      { user: "how's my memory", text: "RAM's at 73%.",
        tools: [{ tool: "system_health", args: {} }] },
    ] } });
    render(<AgentView />);
    await waitFor(() => expect(screen.getByText(/RAM's at 73%\./)).toBeInTheDocument());
    expect(screen.getByText("how's my memory")).toBeInTheDocument();
    expect(screen.getByText(/restored/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/api/osa/history?thread_id=osa-t1"))).toBe(true);
  });

  it("New chat clears the transcript and the stored thread", async () => {
    stubFetch();
    render(<AgentView />);
    const ws = await sendMessage();
    act(() => ws._frame({ type: "final", reply: "Done.", thread_id: "osa-t1",
      model: "m", route: "local", tool_trace: [] }));
    expect(localStorage.getItem(THREAD_KEY)).toBe("osa-t1");

    fireEvent.click(screen.getByText(/New chat/));
    expect(localStorage.getItem(THREAD_KEY)).toBeNull();
    expect(screen.queryByText("Done.")).not.toBeInTheDocument();
    expect(screen.getByText(/Ask OSA to run the machine/)).toBeInTheDocument();
  });

  it("completed turns show a timestamp and a working copy button", async () => {
    stubFetch();
    const writeText = vi.fn(() => Promise.resolve());
    Object.assign(navigator, { clipboard: { writeText } });
    render(<AgentView />);
    const ws = await sendMessage();
    act(() => ws._frame({ type: "final", reply: "RAM's at 73%.", thread_id: "osa-t1",
      model: "m", route: "local", tool_trace: [] }));

    const meta = document.querySelector(".agent-meta");
    expect(meta.querySelector(".agent-time")).toBeTruthy();
    fireEvent.click(screen.getByText(/copy/));
    expect(writeText).toHaveBeenCalledWith("RAM's at 73%.");
  });

  it("falls back to the sync POST route when the WS dies without a frame", async () => {
    const calls = stubFetch({ chat: { reply: "posted reply", thread_id: "osa-p1",
      route: "default", model: "m", tool_trace: [] } });
    render(<AgentView />);
    const box = await screen.findByPlaceholderText(/Message OSA/);
    fireEvent.change(box, { target: { value: "hello" } });
    fireEvent.click(screen.getByText("Send"));
    const ws = MockWebSocket.instances[0];
    act(() => ws._die()); // never opened / no frames → POST fallback
    await waitFor(() => expect(screen.getByText("posted reply")).toBeInTheDocument());
    expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/osa/chat"))).toBe(true);
  });
});
