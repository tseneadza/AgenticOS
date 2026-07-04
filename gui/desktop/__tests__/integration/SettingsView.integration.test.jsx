import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsView from "../../src/views/SettingsView";
import { DEFAULT_SIDECAR_URL } from "../../src/settings";
import { pollMs, sidecarUrl } from "../../src/settings";

// ─────────────────────────────────────────────────────────────────────────
// SettingsView Integration Tests — Settings rework
//
// The Phase 9 panel (API keys / feature toggles / dead number settings)
// was replaced: every control now drives real behavior through settings.js
// (pollMs / sidecarUrl) or theme.js (Appearance). These tests exercise the
// full SettingsView → EnvironmentPanel → settings.js → consumer chain.
// ─────────────────────────────────────────────────────────────────────────

const LS_KEY = "agentic-os.settings";
const readStored = () => JSON.parse(localStorage.getItem(LS_KEY) || "null");

describe("SettingsView Integration", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    delete window.__agenticOsSetTheme;
  });

  it("should render SettingsView with the Settings header", () => {
    render(<SettingsView />);
    expect(screen.getByText("Settings")).toBeInTheDocument();
    expect(screen.getByTestId("environment-panel")).toBeInTheDocument();
  });

  it("should display the reworked section headings (old Phase 9 sections gone)", () => {
    render(<SettingsView />);
    expect(screen.getByText("Appearance")).toBeInTheDocument();
    expect(screen.getByText("Polling speed")).toBeInTheDocument();
    expect(screen.getByText("Sidecar connection")).toBeInTheDocument();
    expect(screen.getByText("Diagnostics")).toBeInTheDocument();
    // Dead Phase 9 sections must NOT come back:
    expect(screen.queryByText("API Keys")).not.toBeInTheDocument();
    expect(screen.queryByText("Features")).not.toBeInTheDocument();
    expect(screen.queryByText("System Settings")).not.toBeInTheDocument();
  });

  // ── Theme chain: click → data-theme + theme.js persistence ──
  it("should apply and persist a theme end-to-end", async () => {
    render(<SettingsView />);
    await userEvent.click(screen.getByTestId("theme-option-cyber-light"));
    expect(document.documentElement.getAttribute("data-theme")).toBe("cyber-light");
    expect(localStorage.getItem("agentic-os.theme")).toBe("cyber-light");
  });

  it("should route theme changes through the App bridge when registered", async () => {
    const bridge = vi.fn();
    window.__agenticOsSetTheme = bridge;
    render(<SettingsView />);
    await userEvent.click(screen.getByTestId("theme-option-term-dark"));
    expect(bridge).toHaveBeenCalledWith("term-dark");
  });

  // ── Polling chain: click → settings.js → pollMs consumers ──
  it("should change what pollMs() returns for consuming views", async () => {
    render(<SettingsView />);
    expect(pollMs(5000)).toBe(5000);
    await userEvent.click(screen.getByTestId("polling-slow"));
    expect(readStored().polling_speed).toBe("slow");
    expect(pollMs(5000)).toBe(10000); // what ProjectsView etc. will now use
    await userEvent.click(screen.getByTestId("polling-fast"));
    expect(pollMs(5000)).toBe(2500);
  });

  // ── Sidecar URL chain: input → settings.js → sidecarUrl consumers ──
  it("should change what sidecarUrl() returns for api.js and explorers", async () => {
    render(<SettingsView />);
    const input = screen.getByTestId("sidecar-url-input");
    await userEvent.clear(input);
    await userEvent.type(input, "http://devbox:6001{enter}");
    expect(readStored().sidecar_url).toBe("http://devbox:6001");
    expect(sidecarUrl()).toBe("http://devbox:6001");
  });

  it("should not poison sidecarUrl() with an invalid entry", async () => {
    render(<SettingsView />);
    const input = screen.getByTestId("sidecar-url-input");
    await userEvent.clear(input);
    await userEvent.type(input, "garbage{enter}");
    expect(screen.getByTestId("sidecar-url-error")).toBeInTheDocument();
    expect(sidecarUrl()).toBe(DEFAULT_SIDECAR_URL);
  });

  it("should test the connection against the entered URL", async () => {
    render(<SettingsView />);
    const input = screen.getByTestId("sidecar-url-input");
    await userEvent.clear(input);
    await userEvent.type(input, "http://devbox:6001");
    await userEvent.click(screen.getByTestId("test-connection"));
    await waitFor(() =>
      expect(screen.getByTestId("test-result")).toHaveTextContent("online"));
    expect(global.fetch).toHaveBeenCalledWith(
      "http://devbox:6001/api/health",
      expect.anything(),
    );
  });

  // ── Diagnostics ──
  it("should show live sidecar status in Diagnostics", async () => {
    render(<SettingsView />);
    await waitFor(() =>
      expect(screen.getByTestId("diag-sidecar")).toHaveTextContent("online"));
    expect(screen.getByTestId("diag-url")).toHaveTextContent(DEFAULT_SIDECAR_URL);
  });

  // ── Persistence round-trip ──
  it("should load previously saved settings on mount", () => {
    localStorage.setItem(LS_KEY, JSON.stringify({
      polling_speed: "fast", sidecar_url: "http://devbox:6001",
    }));
    render(<SettingsView />);
    expect(screen.getByTestId("polling-fast").className).toContain("sv-active");
    expect(screen.getByTestId("sidecar-url-input")).toHaveValue("http://devbox:6001");
  });

  it("should purge legacy Phase 9 fields (stored API keys) on mount", () => {
    localStorage.setItem(LS_KEY, JSON.stringify({
      anthropic_api_key: "sk-old-secret", github_token: "ghp",
      dark_mode: true, api_timeout: 30, polling_speed: "slow",
    }));
    render(<SettingsView />);
    const raw = readStored();
    expect(raw.anthropic_api_key).toBeUndefined();
    expect(raw.github_token).toBeUndefined();
    expect(raw.api_timeout).toBeUndefined();
    expect(raw.polling_speed).toBe("slow");
  });

  it("should reset to defaults via the footer button", async () => {
    localStorage.setItem(LS_KEY, JSON.stringify({
      polling_speed: "fast", sidecar_url: "http://devbox:6001",
    }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<SettingsView />);
    await userEvent.click(screen.getByTestId("reset-settings"));
    expect(readStored()).toEqual({
      polling_speed: "normal", sidecar_url: DEFAULT_SIDECAR_URL,
    });
    expect(pollMs(5000)).toBe(5000);
  });

  it("should show the ✓ Saved indicator after a change", async () => {
    render(<SettingsView />);
    await userEvent.click(screen.getByTestId("polling-slow"));
    expect(screen.getByTestId("save-indicator")).toBeInTheDocument();
  });
});
