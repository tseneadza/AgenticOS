import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsView from "../../src/views/SettingsView";
import EnvironmentPanel from "../../src/components/EnvironmentPanel";

// ─────────────────────────────────────────────────────────────────────────
// SettingsView Integration Tests — Phase 9
// Test that EnvironmentPanel renders correctly as a dedicated Settings page
// within the main dashboard navigation.
// ─────────────────────────────────────────────────────────────────────────

describe("SettingsView Integration", () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 1: SettingsView renders correctly
  // ─────────────────────────────────────────────────────────────────────────
  it("should render SettingsView component", () => {
    render(<SettingsView />);
    // EnvironmentPanel should render with "Settings" header
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 2: EnvironmentPanel renders within SettingsView
  // ─────────────────────────────────────────────────────────────────────────
  it("should render EnvironmentPanel as the main content", () => {
    render(<SettingsView />);
    const panel = screen.getByTestId("environment-panel");
    expect(panel).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 3: Settings section headings are visible
  // ─────────────────────────────────────────────────────────────────────────
  it("should display all settings section headings", () => {
    render(<SettingsView />);
    expect(screen.getByText("API Keys")).toBeInTheDocument();
    expect(screen.getByText("Features")).toBeInTheDocument();
    expect(screen.getByText("System Settings")).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 4: API key input fields render
  // ─────────────────────────────────────────────────────────────────────────
  it("should render API key input fields", () => {
    render(<SettingsView />);
    expect(screen.getByText("Anthropic API Key")).toBeInTheDocument();
    expect(screen.getByText("GitHub Personal Access Token")).toBeInTheDocument();
    expect(screen.getByTestId("api-key-input-anthropic_api_key")).toBeInTheDocument();
    expect(screen.getByTestId("api-key-input-github_token")).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 5: Feature toggle checkboxes render
  // ─────────────────────────────────────────────────────────────────────────
  it("should render feature toggle checkboxes", () => {
    render(<SettingsView />);
    expect(screen.getByTestId("toggle-dark_mode")).toBeInTheDocument();
    expect(screen.getByTestId("toggle-animations")).toBeInTheDocument();
    expect(screen.getByTestId("toggle-auto_refresh")).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 6: Number input fields render with min/max validation
  // ─────────────────────────────────────────────────────────────────────────
  it("should render number input fields for system settings", () => {
    render(<SettingsView />);
    expect(screen.getByTestId("number-input-log_refresh_interval")).toBeInTheDocument();
    expect(screen.getByTestId("number-input-api_timeout")).toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 7: API key visibility toggle works
  // ─────────────────────────────────────────────────────────────────────────
  it("should toggle API key visibility when button is clicked", async () => {
    render(<SettingsView />);
    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");

    // Set a value
    await userEvent.type(apiKeyInput, "sk-test-key-123");

    // Initially should be masked (type="password")
    expect(apiKeyInput).toHaveAttribute("type", "password");

    // Click show button
    const showButton = screen.getByTestId("toggle-show-anthropic_api_key");
    fireEvent.click(showButton);

    // Should be revealed (type="text")
    await waitFor(() => {
      expect(apiKeyInput).toHaveAttribute("type", "text");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 8: Copy API key button works
  // ─────────────────────────────────────────────────────────────────────────
  it("should copy API key to clipboard", async () => {
    const mockClipboard = {
      writeText: vi.fn().mockResolvedValue(undefined),
    };
    global.navigator.clipboard = mockClipboard;

    render(<SettingsView />);
    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");

    // Set a value
    await userEvent.type(apiKeyInput, "sk-test-key-123");

    // Click copy button
    const copyButton = screen.getByTestId("copy-btn-anthropic_api_key");
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(mockClipboard.writeText).toHaveBeenCalledWith("sk-test-key-123");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 9: Feature toggle changes are tracked
  // ─────────────────────────────────────────────────────────────────────────
  it("should update settings when a feature toggle is changed", async () => {
    render(<SettingsView />);
    const darkModeToggle = screen.getByTestId("toggle-dark_mode");

    // Initially checked (default: true)
    expect(darkModeToggle).toBeChecked();

    // Click to uncheck
    fireEvent.click(darkModeToggle);

    // Should be unchecked
    await waitFor(() => {
      expect(darkModeToggle).not.toBeChecked();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 10: Number input validation rejects invalid values
  // ─────────────────────────────────────────────────────────────────────────
  it("should validate number inputs and show error messages", async () => {
    render(<SettingsView />);
    const refreshInput = screen.getByTestId("number-input-log_refresh_interval");

    // The controlled number input only commits valid values, so emit the
    // out-of-range value in a single change event.
    fireEvent.change(refreshInput, { target: { value: "0" } });

    // Error message should appear
    await waitFor(() => {
      const error = screen.getByTestId("error-log_refresh_interval");
      expect(error).toBeInTheDocument();
      expect(error.textContent).toMatch(/Minimum value is 1/i);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 11: Changes auto-save to localStorage (debounced)
  // ─────────────────────────────────────────────────────────────────────────
  it("should auto-save settings to localStorage when a field changes", async () => {
    render(<SettingsView />);

    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    await userEvent.type(apiKeyInput, "sk-test-key-456");

    // Auto-save (debounced) persists to localStorage without a manual button.
    await waitFor(() => {
      const stored = localStorage.getItem("agentic-os.settings");
      expect(stored).toBeTruthy();
      const parsed = JSON.parse(stored);
      expect(parsed.anthropic_api_key).toBe("sk-test-key-456");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 12: Settings persist across page refresh
  // ─────────────────────────────────────────────────────────────────────────
  it("should load previously saved settings from localStorage on mount", async () => {
    // First render: set and save a value
    const savedSettings = {
      anthropic_api_key: "sk-saved-key",
      github_token: "",
      dark_mode: false,
      animations: true,
      auto_refresh: false,
      log_refresh_interval: 10,
      api_timeout: 60,
    };
    localStorage.setItem("agentic-os.settings", JSON.stringify(savedSettings));

    // Second render: should load the saved values
    render(<SettingsView />);

    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    expect(apiKeyInput).toHaveValue("sk-saved-key");

    const darkModeToggle = screen.getByTestId("toggle-dark_mode");
    expect(darkModeToggle).not.toBeChecked(); // Should be false

    const animationsToggle = screen.getByTestId("toggle-animations");
    expect(animationsToggle).toBeChecked(); // Should be true
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 13: Reset button resets all settings to defaults
  // ─────────────────────────────────────────────────────────────────────────
  it("should reset settings to defaults when Reset button is clicked", async () => {
    window.confirm = vi.fn().mockReturnValue(true);

    render(<SettingsView />);

    // Modify some settings
    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    await userEvent.type(apiKeyInput, "sk-custom-key");

    const darkModeToggle = screen.getByTestId("toggle-dark_mode");
    fireEvent.click(darkModeToggle); // Toggle off

    // Click reset button
    const resetButton = screen.getByTestId("reset-settings");
    fireEvent.click(resetButton);

    await waitFor(() => {
      // Should be reset to defaults
      expect(apiKeyInput).toHaveValue("");
      expect(darkModeToggle).toBeChecked(); // Default is true
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 14: Auto-save shows the ✓ Saved indicator
  // ─────────────────────────────────────────────────────────────────────────
  it("should show the ✓ Saved indicator after an auto-save", async () => {
    render(<SettingsView />);

    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    await userEvent.type(apiKeyInput, "sk-test-success");

    // The ✓ Saved indicator should appear after the debounced save.
    await waitFor(() => {
      expect(screen.getByText("✓ Saved")).toBeInTheDocument();
    });

    // Indicator should disappear again after its timeout.
    await waitFor(
      () => {
        expect(screen.queryByText("✓ Saved")).not.toBeInTheDocument();
      },
      { timeout: 2500 }
    );
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 15: Required API key warning appears when empty
  // ─────────────────────────────────────────────────────────────────────────
  it("should show required API key warning when key is empty", async () => {
    render(<SettingsView />);

    // The panel should show a warning when anthropic_api_key is not set
    await waitFor(() => {
      const warning = screen.getByTestId("required-warning");
      expect(warning).toBeInTheDocument();
      expect(warning.textContent).toMatch(/Anthropic API Key is required/i);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 16: Clear API key button removes value
  // ─────────────────────────────────────────────────────────────────────────
  it("should clear API key when Clear button is clicked", async () => {
    render(<SettingsView />);

    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    await userEvent.type(apiKeyInput, "sk-test-to-clear");

    // Clear button should appear
    await waitFor(() => {
      const clearButton = screen.getByTestId("clear-anthropic_api_key");
      expect(clearButton).toBeInTheDocument();
      fireEvent.click(clearButton);
    });

    // Value should be cleared
    await waitFor(() => {
      expect(apiKeyInput).toHaveValue("");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 17: Number input accepts valid values within range
  // ─────────────────────────────────────────────────────────────────────────
  it("should accept valid number values within min/max range", async () => {
    render(<SettingsView />);
    const refreshInput = screen.getByTestId("number-input-log_refresh_interval");

    // Commit a valid value via a single change event.
    fireEvent.change(refreshInput, { target: { value: "15" } });

    await waitFor(() => {
      expect(refreshInput).toHaveValue(15);
    });

    // Error should not appear
    const error = screen.queryByTestId("error-log_refresh_interval");
    expect(error).not.toBeInTheDocument();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 18: Auto-save persists changes without a manual save button
  // ─────────────────────────────────────────────────────────────────────────
  it("should auto-save changes without a manual Save button", async () => {
    render(<SettingsView />);

    // The auto-save UI has no manual save button.
    expect(screen.queryByTestId("save-settings")).not.toBeInTheDocument();

    // Make a change; it should be persisted automatically.
    const apiKeyInput = screen.getByTestId("api-key-input-anthropic_api_key");
    await userEvent.type(apiKeyInput, "sk-test");

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.anthropic_api_key).toBe("sk-test");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 19: EnvironmentPanel integrates with app theme variables
  // ─────────────────────────────────────────────────────────────────────────
  it("should apply theme CSS variables from app", () => {
    render(<SettingsView />);

    const panel = screen.getByTestId("environment-panel");
    const computedStyle = window.getComputedStyle(panel);

    // Should have theme-aware colors (using CSS variables)
    expect(panel).toHaveStyle("background: var(--bg)");
    expect(panel).toHaveStyle("color: var(--text)");
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 20: Missing required key surfaces a warning while auto-save continues
  // ─────────────────────────────────────────────────────────────────────────
  it("should warn about the missing required key while still auto-saving other fields", async () => {
    localStorage.clear();
    render(<SettingsView />);

    // The required-key warning is shown because no Anthropic key is set.
    expect(screen.getByTestId("required-warning")).toBeInTheDocument();

    // Changing another field still auto-saves, but the API key stays empty.
    const refreshInput = screen.getByTestId("number-input-log_refresh_interval");
    fireEvent.change(refreshInput, { target: { value: "10" } });

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("agentic-os.settings"));
      expect(stored.log_refresh_interval).toBe(10);
      expect(stored.anthropic_api_key || "").toBe("");
    });

    // Warning remains until a key is entered.
    expect(screen.getByTestId("required-warning")).toBeInTheDocument();
  });
});
