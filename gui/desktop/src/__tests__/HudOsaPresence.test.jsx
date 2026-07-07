import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { HudOsaPresence } from "../Hud";

// Phase 14e — the HUD's compact OSA presence (slim orb + one-line caption).
// It does its own GET /api/osa/events polling (the HUD is a separate Tauri
// window): first poll primes the caption; an announced message afterwards
// flips data-state to "speaking" (~3s) and updates the caption; silent
// messages update the caption only. Fetch is stubbed with a scripted sequence.

function stubFetchSequence(payloads) {
  let i = 0;
  global.fetch = vi.fn(() => {
    const body = payloads[Math.min(i, payloads.length - 1)];
    i += 1;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  });
}

const EMPTY = { messages: [], latest_id: 0 };

describe("HudOsaPresence (HUD orb + caption)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders the orb idle with the 'Standing by.' caption", () => {
    stubFetchSequence([EMPTY]);
    render(<HudOsaPresence intervalMs={10_000} />);
    const orb = screen.getByTestId("hud-osa");
    expect(orb).toHaveAttribute("data-state", "idle");
    expect(screen.getByText("Standing by.")).toBeInTheDocument();
  });

  it("primes the caption from buffered history without speaking", async () => {
    stubFetchSequence([
      {
        messages: [
          { id: 1, app_id: "worldwise", kind: "down", announced: true, text: "Tony — worldwise just went down (port 5150)." },
        ],
        latest_id: 1,
      },
      { messages: [], latest_id: 1 },
    ]);
    render(<HudOsaPresence intervalMs={10_000} />);
    await waitFor(() =>
      expect(
        screen.getByText("Tony — worldwise just went down (port 5150).")
      ).toBeInTheDocument()
    );
    // History never animates — the orb stays idle.
    expect(screen.getByTestId("hud-osa")).toHaveAttribute("data-state", "idle");
  });

  it("speaks (pulses) + updates the caption for a new announced message", async () => {
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
    render(<HudOsaPresence intervalMs={30} />);
    await waitFor(() =>
      expect(screen.getByTestId("hud-osa")).toHaveAttribute("data-state", "speaking")
    );
    expect(
      screen.getByText("Tony — keno just went down (port 5000).")
    ).toBeInTheDocument();
  });

  it("updates the caption only for a new silent message", async () => {
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
    render(<HudOsaPresence intervalMs={30} />);
    await waitFor(() =>
      expect(screen.getByText("keno is back up.")).toBeInTheDocument()
    );
    expect(screen.getByTestId("hud-osa")).toHaveAttribute("data-state", "idle");
  });

  it("degrades silently when the sidecar is down", async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error("connection refused")));
    render(<HudOsaPresence intervalMs={20} />);
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.getByText("Standing by.")).toBeInTheDocument();
    expect(screen.getByTestId("hud-osa")).toHaveAttribute("data-state", "idle");
  });
});
