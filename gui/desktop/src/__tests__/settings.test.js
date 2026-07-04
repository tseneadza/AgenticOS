import { describe, it, expect, beforeEach } from "vitest";
import {
  loadSettings, saveSettings, resetSettings, subscribeSettings,
  pollMs, sidecarUrl, sidecarWsUrl, sidecarHost,
  DEFAULTS, DEFAULT_SIDECAR_URL,
} from "../settings";

const LS_KEY = "agentic-os.settings";

describe("settings registry", () => {
  beforeEach(() => localStorage.clear());

  it("returns defaults when nothing is stored", () => {
    expect(loadSettings()).toEqual(DEFAULTS);
  });

  it("returns defaults when storage is corrupt", () => {
    localStorage.setItem(LS_KEY, "{not json");
    expect(loadSettings()).toEqual(DEFAULTS);
  });

  it("persists via saveSettings and merges over defaults", () => {
    saveSettings({ polling_speed: "fast" });
    expect(loadSettings()).toEqual({ ...DEFAULTS, polling_speed: "fast" });
    expect(JSON.parse(localStorage.getItem(LS_KEY)).polling_speed).toBe("fast");
  });

  it("purges legacy Phase 9 fields (incl. stored API keys) on load", () => {
    localStorage.setItem(LS_KEY, JSON.stringify({
      anthropic_api_key: "sk-secret",
      github_token: "ghp_x",
      dark_mode: true,
      log_refresh_interval: 5,
      polling_speed: "slow",
    }));
    expect(loadSettings()).toEqual({ ...DEFAULTS, polling_speed: "slow" });
    // The rewrite must actually drop the secret from disk.
    const raw = JSON.parse(localStorage.getItem(LS_KEY));
    expect(raw.anthropic_api_key).toBeUndefined();
    expect(raw.github_token).toBeUndefined();
    expect(raw.polling_speed).toBe("slow");
  });

  it("resetSettings restores defaults", () => {
    saveSettings({ polling_speed: "fast", sidecar_url: "http://other:9999" });
    resetSettings();
    expect(loadSettings()).toEqual(DEFAULTS);
  });

  it("notifies subscribers on save and unsubscribes cleanly", () => {
    const seen = [];
    const un = subscribeSettings((s) => seen.push(s));
    saveSettings({ polling_speed: "slow" });
    expect(seen).toHaveLength(1);
    expect(seen[0].polling_speed).toBe("slow");
    un();
    saveSettings({ polling_speed: "fast" });
    expect(seen).toHaveLength(1);
  });
});

describe("pollMs", () => {
  beforeEach(() => localStorage.clear());

  it("is identity at normal speed", () => {
    expect(pollMs(5000)).toBe(5000);
  });

  it("doubles at slow and halves at fast", () => {
    saveSettings({ polling_speed: "slow" });
    expect(pollMs(5000)).toBe(10000);
    saveSettings({ polling_speed: "fast" });
    expect(pollMs(5000)).toBe(2500);
  });

  it("falls back to 1× on an unknown speed value", () => {
    saveSettings({ polling_speed: "warp" });
    expect(pollMs(4000)).toBe(4000);
  });
});

describe("sidecarUrl / sidecarWsUrl / sidecarHost", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to localhost:5130", () => {
    expect(sidecarUrl()).toBe(DEFAULT_SIDECAR_URL);
    expect(sidecarHost()).toBe("localhost:5130");
  });

  it("strips trailing slashes", () => {
    saveSettings({ sidecar_url: "http://myhost:6000///" });
    expect(sidecarUrl()).toBe("http://myhost:6000");
  });

  it("falls back to the default on a non-http value", () => {
    saveSettings({ sidecar_url: "ftp://nope" });
    expect(sidecarUrl()).toBe(DEFAULT_SIDECAR_URL);
    saveSettings({ sidecar_url: "" });
    expect(sidecarUrl()).toBe(DEFAULT_SIDECAR_URL);
  });

  it("derives ws:// URLs with the path appended", () => {
    expect(sidecarWsUrl("/ws/agui")).toBe("ws://localhost:5130/ws/agui");
    saveSettings({ sidecar_url: "https://remote:8443" });
    expect(sidecarWsUrl("/x")).toBe("wss://remote:8443/x");
  });
});
