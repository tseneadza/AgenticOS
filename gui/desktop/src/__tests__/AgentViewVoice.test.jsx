// Voice <-> on-screen chat unification (14x, 2026-07-14). SPOKEN turns arrive
// on the shared AG-UI bus (/ws/agui) tagged source:"voice" and fold into the
// SAME transcript as typed chat: OSA_VOICE_TURN_STARTED opens a turn, streamed
// TEXT_MESSAGE_CONTENT deltas fill it, OSA_VOICE_TURN_FINISHED finalizes it —
// rendered with a mic indicator so spoken turns are distinguishable.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { AgentView, OSAContext } from "../App";

const STATE = { ready: true, ollama_up: true, soul: "Soul_OSA.md" };
const VOICE_ON = { enabled: true, deps_ok: true, state: "idle", wake_active: false };

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
  _open() { this.readyState = MockWebSocket.OPEN; this.onopen?.(); }
  _frame(obj) { this.onmessage?.({ data: JSON.stringify(obj) }); }
}

function stubFetch(overrides = {}) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || "GET";
    let body = null;
    try { body = opts.body ? JSON.parse(opts.body) : null; } catch { /* ignore */ }
    calls.push({ url, method, body });
    const respond = (b) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
    if (url.includes("/api/osa/voice/state")) return respond(overrides.voiceState ?? VOICE_ON);
    if (url.includes("/api/osa/voice/ptt")) return respond(overrides.ptt ?? { ok: true, transcript: "", reply: "" });
    if (url.includes("/api/osa/active-thread")) return respond({ thread_id: body?.thread_id ?? null });
    if (url.includes("/api/osa/history")) return respond(overrides.history ?? { exists: false, turns: [] });
    if (url.includes("/api/osa/state")) return respond(overrides.state ?? STATE);
    if (url.includes("/api/osa/chat")) return respond(overrides.chat ?? { reply: "typed reply", thread_id: "osa-t", tool_trace: [] });
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
  return calls;
}

async function aguiSocket() {
  // The voice subscription opens once voice/state resolves (voiceIn=true).
  await waitFor(() => {
    const ws = MockWebSocket.instances.find((w) => String(w.url).includes("/ws/agui"));
    expect(ws).toBeTruthy();
  });
  return MockWebSocket.instances.find((w) => String(w.url).includes("/ws/agui"));
}

function renderWithPresence() {
  const presence = { state: "idle", lastLine: "", setOsaState: vi.fn(), speak: vi.fn() };
  render(
    <OSAContext.Provider value={presence}>
      <AgentView />
    </OSAContext.Provider>
  );
  return presence;
}

describe("AgentView voice unification (14x)", () => {
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

  it("folds a streamed voice turn (start -> deltas -> finish) into the transcript with a mic indicator", async () => {
    stubFetch();
    const presence = renderWithPresence();
    const ws = await aguiSocket();
    act(() => ws._open());

    act(() => ws._frame({
      type: "OSA_VOICE_TURN_STARTED", source: "voice", turn_id: "vt-1",
      thread_id: "osa-shared", user: "what time is it",
    }));
    // The spoken question appears as a user turn immediately.
    await screen.findByText(/what time is it/);

    act(() => {
      ws._frame({ type: "TEXT_MESSAGE_CONTENT", source: "voice", run_id: "vt-1", delta: "It is " });
      ws._frame({ type: "TEXT_MESSAGE_CONTENT", source: "voice", run_id: "vt-1", delta: "noon, Sir." });
    });
    await screen.findByText(/It is noon, Sir\./);

    act(() => ws._frame({
      type: "OSA_VOICE_TURN_FINISHED", source: "voice", turn_id: "vt-1",
      thread_id: "osa-shared", reply: "It is noon, Sir.",
    }));

    // Mic indicator marks it as a spoken turn; orb speaks the final reply.
    expect(screen.getByTestId("voice-mic")).toBeInTheDocument();
    expect(presence.speak).toHaveBeenCalledWith("It is noon, Sir.");
  });

  it("ignores non-voice events on the same bus", async () => {
    stubFetch();
    renderWithPresence();
    const ws = await aguiSocket();
    act(() => ws._open());
    act(() => ws._frame({ type: "OSA_VOICE_TURN_STARTED", source: "workflow", turn_id: "wf-1", user: "not a voice turn" }));
    // A workflow event must not create an OSA chat turn.
    expect(screen.queryByText(/not a voice turn/)).not.toBeInTheDocument();
  });

  it("does not double-render a PTT turn already published on the bus", async () => {
    stubFetch({ ptt: { ok: true, transcript: "hello there", reply: "Hi, Sir.", turn_id: "vt-ptt" } });
    renderWithPresence();
    const ws = await aguiSocket();
    act(() => ws._open());

    const mic = await screen.findByTestId("mic-btn");
    fireEvent.click(mic);
    // PTT caption rendered synchronously from the POST response.
    await screen.findByText(/hello there/);

    // The sidecar also publishes the same turn on the bus; the shared turn_id
    // must suppress a duplicate.
    act(() => ws._frame({
      type: "OSA_VOICE_TURN_STARTED", source: "voice", turn_id: "vt-ptt",
      thread_id: "osa-shared", user: "hello there",
    }));
    expect(screen.getAllByText(/hello there/)).toHaveLength(1);
  });

  it("POSTs the active thread so voice unifies with the on-screen conversation", async () => {
    localStorage.setItem("agentic-os.osa-thread", "osa-restored");
    const calls = stubFetch({ history: { exists: false, turns: [] } });
    renderWithPresence();
    await waitFor(() =>
      expect(calls.some((c) => c.url.includes("/api/osa/active-thread") && c.method === "POST" && c.body?.thread_id === "osa-restored")).toBe(true)
    );
  });
});
