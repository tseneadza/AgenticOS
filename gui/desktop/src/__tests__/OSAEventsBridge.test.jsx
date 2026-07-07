import { describe, it, expect, vi, afterEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { OSAEventsBridge } from "../App";

// Phase 14e — the proactive events bridge polls GET /api/osa/events with an
// `after` cursor and drives the shared OSA presence: announced → speak(text),
// silent → onLine(text) only. The FIRST poll just primes (caption, no speech).
// We stub global fetch to serve a scripted sequence of payloads and run the
// bridge on a fast interval so the second/third polls land inside waitFor.

function stubFetchSequence(payloads) {
  const calls = [];
  let i = 0;
  global.fetch = vi.fn((url) => {
    calls.push(url);
    const body = payloads[Math.min(i, payloads.length - 1)];
    i += 1;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
  return calls;
}

const EMPTY = { messages: [], latest_id: 0 };

describe("OSAEventsBridge (proactive events polling)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("primes on the first poll: caption only, never speaks buffered history", async () => {
    const speak = vi.fn();
    const onLine = vi.fn();
    stubFetchSequence([
      {
        messages: [
          { id: 1, app_id: "worldwise", kind: "down", announced: true, text: "Tony — worldwise just went down (port 5150)." },
          { id: 2, app_id: "worldwise", kind: "up", announced: false, text: "worldwise is back up." },
        ],
        latest_id: 2,
      },
      { messages: [], latest_id: 2 },
    ]);
    render(<OSAEventsBridge speak={speak} onLine={onLine} intervalMs={10_000} />);
    await waitFor(() => expect(onLine).toHaveBeenCalledWith("worldwise is back up."));
    expect(speak).not.toHaveBeenCalled();
  });

  it("sends the after cursor once primed", async () => {
    const calls = stubFetchSequence([
      { messages: [], latest_id: 7 },
      { messages: [], latest_id: 7 },
    ]);
    render(<OSAEventsBridge speak={vi.fn()} onLine={vi.fn()} intervalMs={30} />);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(calls[0]).toContain("/api/osa/events");
    expect(calls[0]).not.toContain("after=");
    expect(calls[1]).toContain("/api/osa/events?after=7");
  });

  it("speaks the latest announced message after priming", async () => {
    const speak = vi.fn();
    const onLine = vi.fn();
    stubFetchSequence([
      EMPTY,
      {
        messages: [
          { id: 1, app_id: "keno", kind: "down", announced: true, text: "Tony — keno just went down (port 5000)." },
        ],
        latest_id: 1,
      },
      { messages: [], latest_id: 1 },
    ]);
    render(<OSAEventsBridge speak={speak} onLine={onLine} intervalMs={30} />);
    await waitFor(() =>
      expect(speak).toHaveBeenCalledWith("Tony — keno just went down (port 5000).")
    );
  });

  it("updates the caption only for silent messages (no speaking)", async () => {
    const speak = vi.fn();
    const onLine = vi.fn();
    stubFetchSequence([
      EMPTY,
      {
        messages: [
          { id: 1, app_id: "keno", kind: "up", announced: false, text: "keno is back up." },
        ],
        latest_id: 1,
      },
      { messages: [], latest_id: 1 },
    ]);
    render(<OSAEventsBridge speak={speak} onLine={onLine} intervalMs={30} />);
    await waitFor(() => expect(onLine).toHaveBeenCalledWith("keno is back up."));
    expect(speak).not.toHaveBeenCalled();
  });

  it("skips polling while a chat turn is in flight (busyRef)", async () => {
    const calls = stubFetchSequence([EMPTY]);
    render(
      <OSAEventsBridge
        speak={vi.fn()}
        onLine={vi.fn()}
        busyRef={{ current: true }}
        intervalMs={20}
      />
    );
    await new Promise((r) => setTimeout(r, 120));
    expect(calls.length).toBe(0);
  });

  it("degrades silently when the sidecar is down", async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error("connection refused")));
    const speak = vi.fn();
    render(<OSAEventsBridge speak={speak} onLine={vi.fn()} intervalMs={20} />);
    await new Promise((r) => setTimeout(r, 100));
    expect(speak).not.toHaveBeenCalled(); // no crash, no speech
  });

  // ---- 14e follow-on: the rail's feed shares this single poll (onMessages) ----

  it("delivers every batch to onMessages, including buffered history on the priming poll", async () => {
    const speak = vi.fn();
    const onMessages = vi.fn();
    const history = [
      { id: 1, app_id: "keno", kind: "down", announced: true, text: "Tony — keno just went down (port 5000)." },
      { id: 2, app_id: "keno", kind: "up", announced: false, text: "keno is back up." },
    ];
    const fresh = [
      { id: 3, app_id: "worldwise", kind: "down", announced: true, text: "Tony — worldwise just went down (port 5150)." },
    ];
    stubFetchSequence([
      { messages: history, latest_id: 2 },
      { messages: fresh, latest_id: 3 },
      { messages: [], latest_id: 3 },
    ]);
    render(
      <OSAEventsBridge speak={speak} onLine={vi.fn()} onMessages={onMessages} intervalMs={30} />
    );
    // Priming batch reaches the feed even though it is never spoken…
    await waitFor(() => expect(onMessages).toHaveBeenCalledWith(history));
    // …and the post-priming batch reaches BOTH consumers of the one poll:
    await waitFor(() => expect(onMessages).toHaveBeenCalledWith(fresh));
    await waitFor(() =>
      expect(speak).toHaveBeenCalledWith("Tony — worldwise just went down (port 5150).")
    );
    expect(speak).toHaveBeenCalledTimes(1); // history still never spoken
  });

  it("does not call onMessages for empty polls and works without it (optional prop)", async () => {
    const onMessages = vi.fn();
    const calls = stubFetchSequence([EMPTY, EMPTY]);
    render(
      <OSAEventsBridge speak={vi.fn()} onLine={vi.fn()} onMessages={onMessages} intervalMs={30} />
    );
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(2));
    expect(onMessages).not.toHaveBeenCalled();
  });
});
