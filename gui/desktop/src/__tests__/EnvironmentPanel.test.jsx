import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EnvironmentPanel from "../components/EnvironmentPanel";

// ─────────────────────────────────────────────────────────────────────────
// Test Suite: EnvironmentPanel
// ─────────────────────────────────────────────────────────────────────────

describe("EnvironmentPanel Component", () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();

    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn(() => Promise.resolve()),
      },
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

    it("should render close button", () => {
      render(<EnvironmentPanel />);
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

    it("should render save and reset buttons", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("save-settings")).toBeInTheDocument();
      expect(screen.getByTestId("reset-settings")).toBeInTheDocument();
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
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(input, "sk-test-key");

      const copyButton = screen.getByTestId("copy-btn-anthropic_api_key");
      await user.click(copyButton);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("sk-test-key");
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

    it("should accept valid number input", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "10");

      expect(input).toHaveValue(10);
    });

    it("should have default values", () => {
      render(<EnvironmentPanel />);
      expect(screen.getByTestId("number-input-log_refresh_interval")).toHaveValue(5);
      expect(screen.getByTestId("number-input-api_timeout")).toHaveValue(30);
    });

    it("should show error for value below minimum", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "0");

      await waitFor(() => {
        expect(screen.getByTestId("error-log_refresh_interval")).toBeInTheDocument();
      });
    });

    it("should show error for value above maximum", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-api_timeout");
      await user.clear(input);
      await user.type(input, "1000");

      await waitFor(() => {
        expect(screen.getByTestId("error-api_timeout")).toBeInTheDocument();
      });
    });

    it("should show error for non-numeric input", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "abc");

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

    it("should accept values within valid range", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const input = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(input);
      await user.type(input, "30");

      expect(input).toHaveValue(30);
      expect(screen.queryByTestId("error-log_refresh_interval")).not.toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Save & Persistence Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("save to localStorage", () => {
    it("should save settings to localStorage on save button click", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.anthropic_api_key).toBe("sk-test-key");
    });

    it("should show success message after save", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      await waitFor(() => {
        expect(screen.getByText("Settings saved!")).toBeInTheDocument();
      });
    });

    it("should disable save button when no changes", () => {
      render(<EnvironmentPanel />);
      const saveButton = screen.getByTestId("save-settings");
      expect(saveButton).toBeDisabled();
    });

    it("should enable save button when changes made", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const toggle = screen.getByTestId("toggle-dark_mode");
      await user.click(toggle);

      const saveButton = screen.getByTestId("save-settings");
      expect(saveButton).not.toBeDisabled();
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

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      unmount();

      // Remount
      render(<EnvironmentPanel />);

      expect(screen.getByTestId("api-key-input-anthropic_api_key")).toHaveValue(
        "sk-test-key"
      );
    });

    it("should save feature toggles", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "test-key");

      const darkModeToggle = screen.getByTestId("toggle-dark_mode");
      await user.click(darkModeToggle);

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.dark_mode).toBe(false);
    });

    it("should save system settings", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "test-key");

      const numberInput = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(numberInput);
      await user.type(numberInput, "20");

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.log_refresh_interval).toBe(20);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Validation Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("validation", () => {
    it("should warn when required API key is missing", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      expect(screen.getByTestId("required-warning")).toBeInTheDocument();
      expect(
        screen.getByText(expect.stringContaining("Anthropic API Key is required"))
      ).toBeInTheDocument();
    });

    it("should clear warning when required key is filled", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      expect(screen.queryByTestId("required-warning")).not.toBeInTheDocument();
    });

    it("should not save if required field is empty", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      // localStorage should not have been updated
      expect(localStorage.getItem("agentic-os.settings")).toBeNull();
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
      await user.clear(numberInput);
      await user.type(numberInput, "20");

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
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      apiKeyInput.focus();
      expect(apiKeyInput).toHaveFocus();
    });

    it("should allow Enter to toggle feature flags", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      const toggle = screen.getByTestId("toggle-dark_mode");
      toggle.focus();
      expect(toggle).toBeChecked();

      await user.keyboard("{Enter}");
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
      expect(screen.getByText(/Anthropic API Key/)).toBeInTheDocument();
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
      expect(header.style.color).toBe("var(--text)");
    });

    it("should render in all themes without errors", () => {
      const themes = ["terracotta-light", "terracotta-dark"];
      themes.forEach((theme) => {
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
    it("should handle multiple changes and save together", async () => {
      const user = userEvent.setup();
      render(<EnvironmentPanel />);

      // Change multiple settings
      const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
      await user.type(apiKeyInput, "sk-test-key");

      const darkModeToggle = screen.getByTestId("toggle-dark_mode");
      await user.click(darkModeToggle);

      const numberInput = screen.getByTestId("number-input-log_refresh_interval");
      await user.clear(numberInput);
      await user.type(numberInput, "10");

      // Save all changes
      const saveButton = screen.getByTestId("save-settings");
      await user.click(saveButton);

      // Verify all saved
      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.anthropic_api_key).toBe("sk-test-key");
      expect(stored.dark_mode).toBe(false);
      expect(stored.log_refresh_interval).toBe(10);
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
