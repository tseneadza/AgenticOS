import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AgentView, OSAContext } from "../App";

// AgentView is now an OSA chat: it loads GET /api/osa/state once and posts each
// message to POST /api/osa/chat (synchronous request/response). We stub global
// fetch per-path; the api.js get/post helpers call fetch under the hood.
const STATE = {
  ready: true,
  active_model: "qwen2.5:7b-instruct",
  active_label: "Qwen2.5 7B Instruct (local)",
  ollama_up: true,
  ollama_warmed: true,
  soul: "Soul_OSA.md",
};

const CHAT_REPLY = {
  reply: "Your memory looks healthy — 62% free.",
  thread_id: "osa-abc123",
  model: "qwen2.5:7b-instruct",
  route: "local",
  ollama_ready: true,
  tool_trace: [{ tool: "read_memory", args: { scope: "summary" } }],
};

function stubFetch(overrides = {}) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || "GET";
    let body = null;
    try { body = opts.body ? JSON.parse(opts.body) : null; } catch { /* ignore */ }
    calls.push({ url, method, body });
    const respond = (b) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) });
    if (url.includes("/api/osa/state")) return respond(overrides.state ?? STATE);
    if (url.includes("/api/osa/chat")) return respond(overrides.chat ?? CHAT_REPLY);
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
  return calls;
}

describe("AgentView (OSA chat)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders the OSA status strip from /api/osa/state", async () => {
    stubFetch();
    render(<AgentView />);
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );
    expect(screen.getByText(/Ollama up/)).toBeInTheDocument();
    expect(screen.getByText(/soul: Soul_OSA.md/)).toBeInTheDocument();
  });

  it("enables the input when OSA is ready", async () => {
    stubFetch();
    render(<AgentView />);
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );
    const box = screen.getByPlaceholderText(/Message OSA/);
    expect(box).not.toBeDisabled();
  });

  it("sends a message and renders the user turn, OSA reply, route badge and a tool chip", async () => {
    const calls = stubFetch();
    render(<AgentView />);
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );

    const box = screen.getByPlaceholderText(/Message OSA/);
    fireEvent.change(box, { target: { value: "how's my memory?" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    // User turn appears immediately.
    expect(screen.getByText("how's my memory?")).toBeInTheDocument();

    // OSA reply + tool chip + route badge appear after the response resolves.
    await waitFor(() =>
      expect(screen.getByText(/Your memory looks healthy/)).toBeInTheDocument()
    );
    expect(screen.getByText("read_memory")).toBeInTheDocument();
    // Route badge for this turn: "● local" + the model id in agent-meta.
    expect(screen.getByText(/● local/)).toBeInTheDocument();
    expect(screen.getByText(/qwen2.5:7b-instruct/)).toBeInTheDocument();

    const chat = calls.find((c) => c.url.includes("/api/osa/chat"));
    expect(chat).toBeTruthy();
    expect(chat.body.message).toBe("how's my memory?");
    expect(chat.body.thread_id).toBeNull(); // first send has no thread yet
  });

  it("reuses the thread_id from the first reply on the next send", async () => {
    const calls = stubFetch();
    render(<AgentView />);
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );
    const box = screen.getByPlaceholderText(/Message OSA/);

    fireEvent.change(box, { target: { value: "first" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));
    await waitFor(() =>
      expect(screen.getByText(/Your memory looks healthy/)).toBeInTheDocument()
    );

    fireEvent.change(box, { target: { value: "second" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    await waitFor(() => {
      const chats = calls.filter((c) => c.url.includes("/api/osa/chat"));
      expect(chats.length).toBe(2);
      expect(chats[1].body.thread_id).toBe("osa-abc123");
    });
  });

  it("shows an error turn when the chat request fails", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("/api/osa/state"))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(STATE) });
      // /api/osa/chat fails
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    });
    render(<AgentView />);
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );
    const box = screen.getByPlaceholderText(/Message OSA/);
    fireEvent.change(box, { target: { value: "boom" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    await waitFor(() => expect(screen.getByText(/error:/)).toBeInTheDocument());
  });
});

// Phase 14c: AgentView drives the shared OSA reactor orb via OSAContext.
// Inject spy setters through a provider and assert the state transitions.
describe("AgentView drives OSA presence (Phase 14c)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  function renderWithPresence(overrides) {
    const presence = {
      state: "idle",
      lastLine: "",
      setOsaState: vi.fn(),
      speak: vi.fn(),
    };
    render(
      <OSAContext.Provider value={presence}>
        <AgentView />
      </OSAContext.Provider>
    );
    return presence;
  }

  it("sets 'thinking' on send and 'speaking' with the reply on success", async () => {
    stubFetch();
    const presence = renderWithPresence();
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );

    const box = screen.getByPlaceholderText(/Message OSA/);
    fireEvent.change(box, { target: { value: "how's my memory?" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    // "thinking" fires synchronously on send.
    expect(presence.setOsaState).toHaveBeenCalledWith("thinking");

    // On the resolved reply, speak() is called with OSA's line.
    await waitFor(() =>
      expect(presence.speak).toHaveBeenCalledWith(
        "Your memory looks healthy — 62% free."
      )
    );
  });

  it("returns to 'idle' when the chat request fails", async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes("/api/osa/state"))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(STATE) });
      return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    });
    const presence = renderWithPresence();
    await waitFor(() =>
      expect(screen.getByText(/Qwen2.5 7B Instruct \(local\)/)).toBeInTheDocument()
    );
    const box = screen.getByPlaceholderText(/Message OSA/);
    fireEvent.change(box, { target: { value: "boom" } });
    fireEvent.click(screen.getByRole("button", { name: /Send/ }));

    expect(presence.setOsaState).toHaveBeenCalledWith("thinking");
    await waitFor(() =>
      expect(presence.setOsaState).toHaveBeenCalledWith("idle")
    );
    expect(presence.speak).not.toHaveBeenCalled();
  });
});
