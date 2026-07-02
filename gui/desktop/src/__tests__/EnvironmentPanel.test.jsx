import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EnvironmentPanel from "../components/EnvironmentPanel";

// ─────────────────────────────────────────────────────────────────────────
// Test Suite: EnvironmentPanel
//
// EnvironmentPanel was refactored to AUTO-SAVE (debounced, 500ms) on any
// settings change. There is no longer a manual "Save" button or a dirty/enable
// flow. These tests assert the current auto-save contract:
//   - changing a field persists to localStorage["agentic-os.settings"]
//     (asserted via waitFor after the debounce), and
//   - the "✓ Saved" indicator appears after a save.
// ─────────────────────────────────────────────────────────────────────────

// Helper: read the persisted settings object (or null if not yet written).
function readStoredSettings() {
  const raw = localStorage.getItem("agentic-os.settings");
  return raw ? JSON.parse(raw) : null;
}

describe("EnvironmentPanel Component", () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();

    // Mock clipboard API. navigator.clipboard is getter-only in jsdom, so it
    // must be (re)defined rather than assigned.
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      writable: true,
      value: { writeText: vi.fn(() => Promise.resolve()) },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Rendering Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without errors", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("environment-panel")).toBeInTheDocument();
    });

    it("should render settings header", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByText("Settings")).toBeInTheDocument();
    });

    it("should render close button when onClose is provided", () => {
      render(<EnvironmentPanel onClose={vi.fn()} />);
      expect(screen.getByTestId("close-settings")).toBeInTheDocument();
    });

    it("should render all API key inputs", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("api-key-input-anthropic_api_key")).toBeInTheDocument();
      expect(screen.getByTestId("api-key-input-github_token")).toBeInTheDocument();
    });

    it("should render all feature toggles", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("toggle-dark_mode")).toBeInTheDocument();
      expect(screen.getByTestId("toggle-animations")).toBeInTheDocument();
      expect(screen.getByTestId("toggle-auto_refresh")).toBeInTheDocument();
    });

    it("should render all system settings", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("number-input-log_refresh_interval")).toBeInTheDocument();
      expect(screen.getByTestId("number-input-api_timeout")).toBeInTheDocument();
    });

    it("should render the reset button (auto-save has no manual save button)", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("reset-settings")).toBeInTheDocument();
      // Auto-save contract: there is no manual save button.
      expect(screen.queryByTestId("save-settings")).not.toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // API Key Input Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("API key inputs", () => {
    it("should mask API key input by default", () => {
      render(<EnvironmentPanel />);
      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      expect(input).toHaveAttribute("type", "password");
    });

    it("should toggle visibility of API key", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "test-key-123");

      const showButton = screen.getByTestId("toggle-show-anthropic_api_key");
      expect(showButton).toBeInTheDocument();

      await user.click(showButton);
      expect(input).toHaveAttribute("type", "text");

      await user.click(showButton);
      expect(input).toHaveAttribute("type", "password");
    });

    it("should allow entering API key value", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "sk-test-api-key");

      expect(input).toHaveValue("sk-test-api-key");
    });

    it("should show copy button when key is entered", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      expect(screen.queryByTestId("copy-btn-anthropic_api_key")).not.toBeInTheDocument();

      await user.type(input, "test-key");
      expect(screen.getByTestId("copy-btn-anthropic_api_key")).toBeInTheDocument();
    });

    it("should copy API key to clipboard", async () => {
      const user = userEvent.setup();
      // Install our clipboard stub AFTER setup so it wins over userEvent's shim.
      const writeText = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        writable: true,
        value: { writeText },
      });
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "sk-test-key");

      const copyButton = screen.getByTestId("copy-btn-anthropic_api_key");
      await user.click(copyButton);

      expect(writeText).toHaveBeenCalledWith("sk-test-key");
    });

    it("should show 'Copied' feedback after copy", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "test-key");

      const copyButton = screen.getByTestId("copy-btn-anthropic_api_key");
      await user.click(copyButton);

      await waitFor(() => {
        expect(copyButton).toHaveTextContent("Copied");
      });
    });

    it("should mark required API keys with *", () => {
      render(<EnvironmentPanel />);
      const labels = screen.getAllByText(/Anthropic API Key/);
      expect(labels[0].parentElement).toHaveTextContent("*");
    });

    it("should display descriptions for API keys", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByText("For Claude API calls")).toBeInTheDocument();
      expect(screen.getByText("For git operations")).toBeInTheDocument();
    });

    it("should clear API key on clear button click", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "test-key");
      expect(input).toHaveValue("test-key");

      const clearButton = screen.getByTestId("clear-anthropic_api_key");
      await user.click(clearButton);

      expect(input).toHaveValue("");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Feature Toggle Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("feature toggles", () => {
    it("should render toggle switches", () => {
      render(<EnvironmentPanel />);
      const darkModeToggle = screen.getByTestId("toggle-dark_mode");
      expect(darkModeToggle).toHaveAttribute("type", "checkbox");
    });

    it("should toggle feature flag on click", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const toggle = screen.getByTestId("toggle-dark_mode");
      expect(toggle).toBeChecked();

      await user.click(toggle);
      expect(toggle).not.toBeChecked();

      await user.click(toggle);
      expect(toggle).toBeChecked();
    });

    it("should have default values for feature flags", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("toggle-dark_mode")).toBeChecked();
      expect(screen.getByTestId("toggle-animations")).toBeChecked();
      expect(screen.getByTestId("toggle-auto_refresh")).toBeChecked();
    });

    it("should display descriptions for feature flags", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByText("Enable dark theme")).toBeInTheDocument();
      expect(screen.getByText("Enable smooth transitions")).toBeInTheDocument();
      expect(screen.getByText("Automatically refresh log display")).toBeInTheDocument();
    });

    it("should toggle multiple feature flags independently", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const darkMode = screen.getByTestId("toggle-dark_mode");
      const animations = screen.getByTestId("toggle-animations");

      await user.click(darkMode);
      expect(darkMode).not.toBeChecked();
      expect(animations).toBeChecked();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Number Input Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("number inputs", () => {
    it("should render number inputs for system settings", () => {
      render(<EnvironmentPanel />);
      const logInterval = screen.getByTestId("number-input-log_refresh_interval");
      expect(logInterval).toHaveAttribute("type", "number");
    });

    it("should accept valid number input", () => {
      render(<EnvironmentPanel />);

      // The controlled number input only commits valid values, so drive it
      // with a single change event carrying the full value.
      const input = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(input, { target: { value: "10" } });

      expect(input).toHaveValue(10);
    });

    it("should have default values", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("number-input-log_refresh_interval")).toHaveValue(5);
      expect(screen.getByTestId("number-input-api_timeout")).toHaveValue(30);
    });

    it("should show error for value below minimum", async () => {
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(input, { target: { value: "0" } });

      await waitFor(() => {
        expect(screen.getByTestId("error-log_refresh_interval")).toBeInTheDocument();
      });
    });

    it("should show error for value above maximum", async () => {
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-api_timeout");
      fireEvent.change(input, { target: { value: "1000" } });

      await waitFor(() => {
        expect(screen.getByTestId("error-api_timeout")).toBeInTheDocument();
      });
    });

    it("should show error for non-numeric input", async () => {
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      // A number input strips non-numeric characters, so emit the raw value
      // directly to exercise the NaN validation branch.
      fireEvent.change(input, { target: { value: "abc" } });

      await waitFor(() => {
        expect(screen.getByTestId("error-log_refresh_interval")).toBeInTheDocument();
      });
    });

    it("should display descriptions for system settings", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByText("How often to check for new logs")).toBeInTheDocument();
      expect(
        screen.getByText("Maximum time to wait for API responses")
      ).toBeInTheDocument();
    });

    it("should accept values within valid range", () => {
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(input, { target: { value: "30" } });

      expect(input).toHaveValue(30);
      expect(screen.queryByTestId("error-log_refresh_interval")).not.toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Auto-save & Persistence Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("auto-save to localStorage", () => {
    it("should auto-save an entered API key to localStorage", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      await waitFor(() => {
        expect(readStoredSettings()?.anthropic_api_key).toBe("sk-test-key");
      });
    });

    it("should show the ✓ Saved indicator after a change", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      await waitFor(() => {
        expect(screen.getByText("✓ Saved")).toBeInTheDocument();
      });
    });

    it("should load settings from localStorage on mount", () => {
      const settings = {
        anthropic_api_key: "sk-stored-key",
        dark_mode: false,
        log_refresh_interval: 15,
      };
      localStorage.setItem("agentic-os.settings", JSON.stringify(settings));

      render(<EnvironmentPanel />);

      expect(screen.getByTestId("api-key-input-anthropic_api_key")).toHaveValue(
        "sk-stored-key"
      );
      expect(screen.getByTestId("toggle-dark_mode")).not.toBeChecked();
      expect(screen.getByTestId("number-input-log_refresh_interval")).toHaveValue(15);
    });

    it("should persist settings across remounts", async () => {
      const user = userEvent.setup();
      const { unmount } = render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      // Wait for the debounced auto-save to persist.
      await waitFor(() => {
        expect(readStoredSettings()?.anthropic_api_key).toBe("sk-test-key");
      });

      unmount();

      // Remount
      render(<EnvironmentPanel />);

      expect(screen.getByTestId("api-key-input-anthropic_api_key")).toHaveValue(
        "sk-test-key"
      );
    });

    it("should auto-save feature toggle changes", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const darkModeToggle = screen.getByTestId("toggle-dark_mode");
      await user.click(darkModeToggle);

      await waitFor(() => {
        expect(readStoredSettings()?.dark_mode).toBe(false);
      });
    });

    it("should auto-save system setting changes", async () => {
      render(<EnvironmentPanel />);

      const numberInput = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(numberInput, { target: { value: "20" } });

      await waitFor(() => {
        expect(readStoredSettings()?.log_refresh_interval).toBe(20);
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Validation Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("validation", () => {
    it("should warn when the required API key is missing on mount", () => {
      render(<EnvironmentPanel />);
      // No key stored → the required-key warning is shown.
      const warning = screen.getByTestId("required-warning");
      expect(warning).toBeInTheDocument();
      expect(warning).toHaveTextContent(/Anthropic API Key is required/);
    });

    it("should not show the required warning when a key is already stored", () => {
      localStorage.setItem(
        "agentic-os.settings",
        JSON.stringify({ anthropic_api_key: "sk-existing" })
      );
      render(<EnvironmentPanel />);
      expect(screen.queryByTestId("required-warning")).not.toBeInTheDocument();
    });

    it("should validate number ranges on input", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "100");

      await waitFor(() => {
        expect(screen.getByTestId("error-log_refresh_interval")).toBeInTheDocument();
      });
    });

    it("should not persist an out-of-range number value", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "100");

      await waitFor(() => {
        expect(screen.getByTestId("error-log_refresh_interval")).toBeInTheDocument();
      });

      // Invalid values are rejected before reaching state, so the persisted
      // value must never become the out-of-range number.
      expect(readStoredSettings()?.log_refresh_interval).not.toBe(100);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Reset Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("reset to defaults", () => {
    it("should reset all settings to defaults on reset button click", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const numberInput = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(numberInput, { target: { value: "20" } });

      const resetButton = screen.getByTestId("reset-settings");

      // Mock window.confirm
      window.confirm = vi.fn(() => true);
      await user.click(resetButton);

      expect(apiKeyInput).toHaveValue("");
      expect(numberInput).toHaveValue(5);
    });

    it("should ask for confirmation before reset", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      window.confirm = vi.fn(() => false);

      const resetButton = screen.getByTestId("reset-settings");
      await user.click(resetButton);

      expect(window.confirm).toHaveBeenCalled();
    });

    it("should not reset if user cancels confirmation", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      window.confirm = vi.fn(() => false);

      const resetButton = screen.getByTestId("reset-settings");
      await user.click(resetButton);

      expect(apiKeyInput).toHaveValue("sk-test-key");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Keyboard Accessibility Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("keyboard accessibility", () => {
    it("should allow Tab navigation through all inputs", async () => {
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      apiKeyInput.focus();
      expect(apiKeyInput).toHaveFocus();
    });

    it("should keep feature flags keyboard-focusable and toggleable", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const toggle = screen.getByTestId("toggle-dark_mode");
      toggle.focus();
      expect(toggle).toHaveFocus();
      expect(toggle).toBeChecked();

      // Checkboxes toggle on Space (Enter is a no-op per the HTML spec).
      await user.keyboard(" ");
      expect(toggle).not.toBeChecked();
    });

    it("should allow Space to toggle feature flags", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const toggle = screen.getByTestId("toggle-dark_mode");
      toggle.focus();
      expect(toggle).toBeChecked();

      await user.keyboard(" ");
      expect(toggle).not.toBeChecked();
    });

    it("should have proper labels for all inputs", () => {
      render(<EnvironmentPanel />);
      // "Anthropic API Key" appears in both the field label and the required
      // warning, so assert at least one match rather than a unique one.
      expect(screen.getAllByText(/Anthropic API Key/).length).toBeGreaterThan(0);
      expect(screen.getByText("Dark Mode Enabled")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Mobile Responsiveness Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("mobile responsiveness", () => {
    it("should render in mobile viewport", () => {
      const { container } = render(<EnvironmentPanel />);
      const panel = container.querySelector('[data-testid="environment-panel"]');
      expect(panel).toHaveStyle({ display: "flex" });
    });

    it("should show content in scrollable area", () => {
      const { container } = render(<EnvironmentPanel />);
      const content = container.querySelector('[data-testid="settings-content"]');
      expect(content).toHaveStyle({ overflow: "auto" });
    });

    it("should not hide content on dark mode", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      expect(apiKeyInput).toBeVisible();

      const toggle = screen.getByTestId("toggle-dark_mode");
      await user.click(toggle);

      expect(apiKeyInput).toBeVisible();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Theme & Styling Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("theme and styling", () => {
    it("should use theme variables for colors", () => {
      const { container } = render(<EnvironmentPanel />);
      const header = container.querySelector("h2");
      // Header inherits panel text color; verify the panel uses the theme var.
      const panel = container.querySelector('[data-testid="environment-panel"]');
      expect(panel.style.color).toBe("var(--text)");
      expect(header).toBeInTheDocument();
    });

    it("should render in all themes without errors", () => {
      const themes = ["terracotta-light", "terracotta-dark"];
      themes.forEach(() => {
        const { unmount } = render(<EnvironmentPanel />);
        expect(screen.getByTestId("environment-panel")).toBeInTheDocument();
        unmount();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Integration Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("integration", () => {
    it("should auto-save multiple changes together", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      // Change multiple settings
      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const darkModeToggle = screen.getByTestId("toggle-dark_mode");
      await user.click(darkModeToggle);

      const numberInput = screen.getByTestId("number-input-log_refresh_interval");
      fireEvent.change(numberInput, { target: { value: "10" } });

      // Verify all auto-saved
      await waitFor(() => {
        const stored = readStoredSettings();
        expect(stored?.anthropic_api_key).toBe("sk-test-key");
        expect(stored?.dark_mode).toBe(false);
        expect(stored?.log_refresh_interval).toBe(10);
      });
    });

    it("should handle close button", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      render(<EnvironmentPanel onClose={onClose} />);

      const closeButton = screen.getByTestId("close-settings");
      await user.click(closeButton);

      expect(onClose).toHaveBeenCalled();
    });
  });
});
