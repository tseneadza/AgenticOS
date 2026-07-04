import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EnvironmentPanel from "../components/EnvironmentPanel";
import { DEFAULT_SIDECAR_URL } from "../settings";

// ─────────────────────────────────────────────────────────────────────────
// Test Suite: EnvironmentPanel (Settings rework)
//
// The panel was rebuilt so every control drives real behavior:
//   - Appearance    → theme.js applyTheme via the __agenticOsSetTheme bridge
//   - Polling speed → settings.polling_speed (consumed via pollMs())
//   - Connection    → settings.sidecar_url (consumed via sidecarUrl())
//   - Diagnostics   → read-only info rows
// The old Phase 9 API-key fields / dead toggles are GONE, and legacy stored
// fields are purged (covered in settings.test.js; asserted here at the UI
// level too).
// ─────────────────────────────────────────────────────────────────────────

const LS_KEY = "agentic-os.settings";
const readStored = () => JSON.parse(localStorage.getItem(LS_KEY) || "null");

describe("EnvironmentPanel (Settings)", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    // Sidecar health probe (mount + Test button).
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    global.AbortSignal.timeout = global.AbortSignal.timeout || (() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete window.__agenticOsSetTheme;
  });

  it("renders all four sections", () => {
    render(<EnvironmentPanel />);
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText("Polling speed")).toBeInTheDocument();
    expect(screen.getByText("Sidecar connection")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics")).toBeInTheDocument();
  });

  it("no longer renders API key inputs", () => {
    render(<EnvironmentPanel />);
    expect(screen.queryByText(/Anthropic API Key/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/GitHub Personal Access Token/i)).not.toBeInTheDocument();
  });

  // ── Appearance ──
  it("applies a theme via the App bridge when present", async () => {
    const bridge = vi.fn();
    window.__agenticOsSetTheme = bridge;
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("theme-option-cyber-dark"));
    expect(bridge).toHaveBeenCalledWith("cyber-dark");
  });

  it("falls back to applyTheme (data-theme + persist) without the bridge", async () => {
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("theme-option-term-light"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("term-light");
    expect(localStorage.getItem("agentic-os.theme")).toBe("term-light");
  });

  it("marks the active theme button", async () => {
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("theme-option-future-dark"));
    expect(screen.getByTestId("theme-option-future-dark").className).toContain("sv-active");
  });

  // ── Polling ──
  it("persists polling speed and shows the saved indicator", async () => {
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("polling-fast"));
    expect(readStored().polling_speed).toBe("fast");
    expect(screen.getByTestId("save-indicator")).toBeInTheDocument();
  });

  // ── Connection ──
  it("commits a valid sidecar URL on Enter (trailing slash stripped)", async () => {
    render(<EnvironmentPanel />);
    const input = screen.getByTestId("sidecar-url-input");
    await userEvent.clear(input);
    await userEvent.type(input, "http://myhost:6001/{enter}");
    expect(readStored().sidecar_url).toBe("http://myhost:6001");
  });

  it("rejects an invalid URL with an error and does not persist it", async () => {
    render(<EnvironmentPanel />);
    const input = screen.getByTestId("sidecar-url-input");
    await userEvent.clear(input);
    await userEvent.type(input, "not-a-url{enter}");
    expect(screen.getByTestId("sidecar-url-error")).toBeInTheDocument();
    expect(readStored()?.sidecar_url ?? DEFAULT_SIDECAR_URL).toBe(DEFAULT_SIDECAR_URL);
  });

  it("Test button reports online when /api/health responds ok", async () => {
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("test-connection"));
    await waitFor(() => expect(screen.getByTestId("test-result")).toHaveTextContent("online"));
    expect(global.fetch).toHaveBeenCalledWith(
      `${DEFAULT_SIDECAR_URL}/api/health`,
      expect.anything(),
    );
  });

  it("Test button reports unreachable on network failure", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("boom"));
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("test-connection"));
    await waitFor(() => expect(screen.getByTestId("test-result")).toHaveTextContent("unreachable"));
  });

  it("Default button restores the default sidecar URL", async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ sidecar_url: "http://other:9000" }));
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("reset-sidecar-url"));
    expect(readStored().sidecar_url).toBe(DEFAULT_SIDECAR_URL);
  });

  // ── Diagnostics ──
  it("shows sidecar online state, version, and storage rows", async () => {
    render(<EnvironmentPanel />);
    await waitFor(() => expect(screen.getByTestId("diag-sidecar")).toHaveTextContent("online"));
    expect(screen.getByTestId("diag-url")).toHaveTextContent(DEFAULT_SIDECAR_URL);
    expect(screen.getByTestId("diag-version").textContent).toMatch(/\d+\.\d+\.\d+/);
    expect(screen.getByTestId("diag-storage")).toHaveTextContent(/keys/);
  });

  it("shows sidecar offline when the health probe fails", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("down"));
    render(<EnvironmentPanel />);
    await waitFor(() => expect(screen.getByTestId("diag-sidecar")).toHaveTextContent("offline"));
  });

  // ── Reset ──
  it("Reset to Defaults restores default settings after confirm", async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ polling_speed: "slow", sidecar_url: "http://x:1" }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("reset-settings"));
    expect(readStored()).toEqual({ polling_speed: "normal", sidecar_url: DEFAULT_SIDECAR_URL });
  });

  it("Reset does nothing when confirm is declined", async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({ polling_speed: "slow" }));
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<EnvironmentPanel />);
    await userEvent.click(screen.getByTestId("reset-settings"));
    expect(readStored().polling_speed).toBe("slow");
  });

  // ── Migration (UI level) ──
  it("purges legacy Phase 9 fields (API keys) from storage on open", () => {
    localStorage.setItem(LS_KEY, JSON.stringify({
      anthropic_api_key: "sk-secret", dark_mode: true, polling_speed: "slow",
    }));
    render(<EnvironmentPanel />);
    const raw = readStored();
    expect(raw.anthropic_api_key).toBeUndefined();
    expect(raw.dark_mode).toBeUndefined();
    expect(raw.polling_speed).toBe("slow");
  });
});
