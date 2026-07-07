import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import OSARail, { fmtRel, RAIL_FEED_MAX } from "../components/OSARail";

// OSA right rail (14e follow-on): reactor orb + caption on top, proactive feed
// below. The rail never polls /api/osa/events itself — messages arrive via the
// `events` prop from the single OSAEventsBridge poll. The embedded OSAOrb does
// its cheap GET /api/osa/state status poll when no status prop is given, so we
// stub fetch for that.

const STATE = { ready: true, active_label: "OSA · Qwen", ollama_up: true };

function stubFetch(state = STATE) {
  global.fetch = vi.fn((url) => {
    if (url.includes("/api/osa/state"))
      return Promise.resolve({ ok: true, json: () => Promise.resolve(state) });
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
}

// Build a proactive message with a ts N minutes in the past (sidecar shape:
// ISO-8601 UTC string).
const minsAgo = (n) => new Date(Date.now() - n * 60_000).toISOString();
const msg = (id, over = {}) => ({
  id,
  ts: minsAgo(2),
  app_id: "keno",
  kind: "down",
  text: `message ${id}`,
  announced: false,
  ...over,
});

describe("OSARail", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders the reactor orb with the caption (lastLine)", () => {
    stubFetch();
    render(<OSARail lastLine="RAM's at 73%. You're fine." events={[]} />);
    expect(screen.getByTestId("osa-rail")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /OSA reactor/i })).toBeInTheDocument();
    expect(screen.getByText("RAM's at 73%. You're fine.")).toBeInTheDocument();
  });

  it("passes the presence state through to the orb", () => {
    stubFetch();
    render(<OSARail state="thinking" events={[]} />);
    expect(screen.getByTestId("osa-orb")).toHaveAttribute("data-state", "thinking");
  });

  it("shows the empty state in OSA's voice when there are no events", () => {
    stubFetch();
    render(<OSARail events={[]} />);
    expect(screen.getByTestId("rail-empty")).toHaveTextContent("Nothing to report.");
  });

  it("renders feed messages newest first with relative timestamps", () => {
    stubFetch();
    const events = [
      msg(1, { text: "older message", ts: minsAgo(30) }),
      msg(2, { text: "newer message", ts: minsAgo(2) }),
    ];
    render(<OSARail events={events} />);
    const items = screen.getAllByTestId("rail-feed-item");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("newer message");
    expect(items[0]).toHaveTextContent("2m ago");
    expect(items[1]).toHaveTextContent("older message");
    expect(items[1]).toHaveTextContent("30m ago");
  });

  it("marks announced messages visually distinct from silent ones", () => {
    stubFetch();
    const events = [
      msg(1, { text: "silent recovery", kind: "up", announced: false }),
      msg(2, { text: "announced down", kind: "down", announced: true }),
    ];
    render(<OSARail events={events} />);
    const items = screen.getAllByTestId("rail-feed-item");
    // Newest first: the announced down leads.
    expect(items[0]).toHaveAttribute("data-announced", "true");
    expect(items[0]).toHaveClass("announced");
    expect(items[0]).toHaveAttribute("data-kind", "down");
    expect(items[1]).toHaveAttribute("data-announced", "false");
    expect(items[1]).not.toHaveClass("announced");
  });

  it(`bounds the feed to the freshest ${RAIL_FEED_MAX} messages`, () => {
    stubFetch();
    const events = Array.from({ length: RAIL_FEED_MAX + 5 }, (_, i) => msg(i + 1));
    render(<OSARail events={events} />);
    const items = screen.getAllByTestId("rail-feed-item");
    expect(items).toHaveLength(RAIL_FEED_MAX);
    // Freshest (highest id) first; the 5 oldest are dropped.
    expect(items[0]).toHaveTextContent(`message ${RAIL_FEED_MAX + 5}`);
    expect(screen.queryByText("message 1")).not.toBeInTheDocument();
  });

  it("clicking the orb calls onOpen (jump to the Agent view)", () => {
    stubFetch();
    const onOpen = vi.fn();
    render(<OSARail events={[]} onOpen={onOpen} />);
    fireEvent.click(screen.getByTestId("osa-orb"));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });
});

describe("fmtRel (relative timestamps)", () => {
  const NOW = Date.parse("2026-07-07T12:00:00Z");
  it.each([
    ["2026-07-07T11:59:50Z", "just now"],
    ["2026-07-07T11:58:00Z", "2m ago"],
    ["2026-07-07T09:00:00Z", "3h ago"],
    ["2026-07-05T12:00:00Z", "2d ago"],
  ])("%s → %s", (iso, expected) => {
    expect(fmtRel(iso, NOW)).toBe(expected);
  });

  it("returns an empty string for an unparseable ts", () => {
    expect(fmtRel("not-a-date", NOW)).toBe("");
  });
});

// ── Brief-me-now button (14e follow-on) ─────────────────────────────────────
import { act, waitFor } from "@testing-library/react";

describe("OSARail brief-me-now", () => {
  it("renders the button only when onBrief is provided", () => {
    stubFetch();
    const { rerender } = render(<OSARail events={[]} />);
    expect(screen.queryByTestId("rail-brief")).toBeNull();
    rerender(<OSARail events={[]} onBrief={() => {}} />);
    expect(screen.getByTestId("rail-brief")).toBeTruthy();
    expect(screen.getByTestId("rail-brief").textContent).toBe("Brief me");
  });

  it("click calls onBrief and disables the button while in flight", async () => {
    stubFetch();
    let release;
    const onBrief = vi.fn(() => new Promise((res) => { release = res; }));
    render(<OSARail events={[]} onBrief={onBrief} />);
    const btn = screen.getByTestId("rail-brief");
    await act(async () => { fireEvent.click(btn); });
    expect(onBrief).toHaveBeenCalledTimes(1);
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toBe("One moment…");
    // Second click while pending is a no-op.
    await act(async () => { fireEvent.click(btn); });
    expect(onBrief).toHaveBeenCalledTimes(1);
    await act(async () => { release(); });
    await waitFor(() => expect(btn.disabled).toBe(false));
    expect(btn.textContent).toBe("Brief me");
  });

  it("a rejecting onBrief releases the button (silent degrade)", async () => {
    stubFetch();
    const onBrief = vi.fn(() => Promise.reject(new Error("sidecar down")));
    render(<OSARail events={[]} onBrief={onBrief} />);
    const btn = screen.getByTestId("rail-brief");
    await act(async () => { fireEvent.click(btn); });
    await waitFor(() => expect(btn.disabled).toBe(false));
  });
});
