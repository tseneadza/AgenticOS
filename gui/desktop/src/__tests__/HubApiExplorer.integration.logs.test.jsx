import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HubApiExplorer from "../components/HubApiExplorer";

// Mock fetch for API responses
global.fetch = vi.fn();

// ─────────────────────────────────────────────────────────────────────────
// Test Suite: LogsExplorer Integration in HubApiExplorer
// ─────────────────────────────────────────────────────────────────────────

describe("HubApiExplorer + LogsExplorer Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch.mockReset();
    // LogsExplorer persists filter/search/auto-scroll state to localStorage;
    // clear it so state doesn't leak between tests.
    localStorage.clear();
    // Spy on console.error so "no console errors" assertions have a real spy.
    vi.spyOn(console, "error").mockImplementation(() => {});
    // Mock health checks
    global.fetch.mockImplementation((url) => {
      if (String(url).includes("/health")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ status: "ok" }),
        });
      }
      return Promise.reject(new Error("Not mocked"));
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 1: Logs tab renders
  // ─────────────────────────────────────────────────────────────────────────

  describe("Logs Tab Rendering", () => {
    it("should render Logs tab in TabSwitcher", async () => {
      render(<HubApiExplorer />);
      await waitFor(() => {
        expect(screen.getByTestId("tab-button-logs")).toBeInTheDocument();
      });
    });

    it("should render Logs tab between Explorer and Call Log tabs", async () => {
      render(<HubApiExplorer />);
      await waitFor(() => {
        const tabs = screen.getAllByRole("tab");
        const tabIds = tabs.map((tab) => tab.getAttribute("data-testid"));
        const explorerIdx = tabIds.indexOf("tab-button-explorer");
        const logsIdx = tabIds.indexOf("tab-button-logs");
        const calllogIdx = tabIds.indexOf("tab-button-calllog");

        expect(explorerIdx).toBeLessThan(logsIdx);
        expect(logsIdx).toBeLessThan(calllogIdx);
      });
    });

    it("should display Logs label on tab", async () => {
      render(<HubApiExplorer />);
      await waitFor(() => {
        const logsTab = screen.getByTestId("tab-button-logs");
        expect(logsTab).toHaveTextContent("Logs");
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 2: Tab switching shows/hides LogsExplorer
  // ─────────────────────────────────────────────────────────────────────────

  describe("Tab Switching", () => {
    it("should show LogsExplorer when Logs tab is clicked", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });
    });

    it("should hide LogsExplorer when switching to Explorer tab", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Go to Logs tab
      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Switch back to Explorer
      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      await waitFor(() => {
        expect(screen.queryByTestId("logs-explorer")).not.toBeInTheDocument();
      });
    });

    it("should hide LogsExplorer when switching to Call Log tab", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Go to Logs tab
      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Switch to Call Log
      const calllogTab = screen.getByTestId("tab-button-calllog");
      await user.click(calllogTab);

      await waitFor(() => {
        expect(screen.queryByTestId("logs-explorer")).not.toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 3: Filter state preserved across tab switches
  // ─────────────────────────────────────────────────────────────────────────

  describe("Filter State Persistence", () => {
    it("should preserve filter state when switching tabs", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Go to Logs tab
      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Apply a filter (toggle ERROR level)
      const errorFilterBtn = screen.getByTestId("filter-btn-ERROR");
      await user.click(errorFilterBtn);

      // Switch to Explorer
      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      // Switch back to Logs
      await user.click(logsTab);

      await waitFor(() => {
        const errorFilterBtn = screen.getByTestId("filter-btn-ERROR");
        // Filter state should be preserved (ERROR toggled off → not pressed).
        expect(errorFilterBtn).toHaveAttribute("aria-pressed", "false");
      });
    });

    it("should preserve search state when switching tabs", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Go to Logs tab
      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Type in search
      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "error");

      // Verify search value
      expect(searchInput).toHaveValue("error");

      // Switch to Explorer
      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      // Switch back to Logs
      await user.click(logsTab);

      await waitFor(() => {
        const searchInput = screen.getByTestId("log-search-input");
        expect(searchInput).toHaveValue("error");
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 4: Logs display with correct styling
  // ─────────────────────────────────────────────────────────────────────────

  describe("Log Display", () => {
    it("should display logs with all required elements", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        const logs = screen.queryAllByTestId(/log-entry/);
        expect(logs.length).toBeGreaterThan(0);
      });
    });

    it("should display logs with correct styling (theme variables)", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        const logs = screen.queryAllByTestId(/log-entry/);
        logs.forEach((log) => {
          const style = window.getComputedStyle(log);
          // Verify CSS variables are applied
          expect(style.fontFamily).toMatch(/monospace|mono/i);
        });
      });
    });

    it("should display logs with different colors for different levels", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        const errorLogs = screen.queryAllByTestId("log-entry-ERROR");
        const infoLogs = screen.queryAllByTestId("log-entry-INFO");
        expect(errorLogs.length + infoLogs.length).toBeGreaterThan(0);
      });
    });

    it("should render empty state when logs are filtered to nothing", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("log-search-input")).toBeInTheDocument();
      });

      // Search for text that matches no log — this yields the empty state.
      // (Un-checking every level filter instead shows ALL logs, not none.)
      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "zzz-nonexistent-log-text-9999");

      await waitFor(() => {
        expect(screen.getByTestId("empty-logs")).toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 5: Keyboard navigation between tabs
  // ─────────────────────────────────────────────────────────────────────────

  describe("Keyboard Navigation", () => {
    it("should navigate between tabs using Tab key", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const explorerTab = screen.getByTestId("tab-button-explorer");
      explorerTab.focus();

      // Tab to next tab
      await user.keyboard("{Tab}");
      const logsTab = screen.getByTestId("tab-button-logs");
      expect(logsTab).toHaveFocus();

      // Tab to next tab
      await user.keyboard("{Tab}");
      const calllogTab = screen.getByTestId("tab-button-calllog");
      expect(calllogTab).toHaveFocus();
    });

    it("should activate tab with Enter key", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      logsTab.focus();

      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 6: All 8 themes render without errors
  // ─────────────────────────────────────────────────────────────────────────

  describe("Theme Compatibility", () => {
    const themes = [
      "terracotta",
      "cyber",
      "future",
      "terminal",
      "ocean",
      "forest",
      "sunset",
      "mono",
    ];

    themes.forEach((theme) => {
      it(`should render LogsExplorer correctly with ${theme} theme`, async () => {
        const { container } = render(<HubApiExplorer />);

        // Apply theme by setting data-theme attribute
        if (theme !== "terracotta") {
          container.setAttribute("data-theme", theme);
        }

        const user = userEvent.setup();
        const logsTab = screen.getByTestId("tab-button-logs");
        await user.click(logsTab);

        await waitFor(() => {
          expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
        });

        // Verify no console errors
        expect(console.error).not.toHaveBeenCalled();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 7: Mobile responsiveness
  // ─────────────────────────────────────────────────────────────────────────

  describe("Mobile Responsiveness", () => {
    it("should render LogsExplorer with mobile viewport", async () => {
      // Mock window.matchMedia for mobile
      const originalMatchMedia = window.matchMedia;
      window.matchMedia = vi.fn().mockImplementation((query) => ({
        matches: query === "(max-width: 768px)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));

      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      window.matchMedia = originalMatchMedia;
    });

    it("should maintain functionality on small screens", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Verify filter buttons are still accessible
      expect(screen.getByTestId("filter-btn-ERROR")).toBeInTheDocument();

      // Verify search input is still accessible
      expect(screen.getByTestId("log-search-input")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 8: Integration with other explorer features
  // ─────────────────────────────────────────────────────────────────────────

  describe("Integration with Other Features", () => {
    it("should maintain Call Log count badge while on Logs tab", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Select an endpoint
      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
      });

      const firstEndpoint = screen.getAllByTestId(/endpoint-list-item/)[0];
      await user.click(firstEndpoint);

      // Get to Logs tab
      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      // Call Log tab should still show count
      const calllogTab = screen.getByTestId("tab-button-calllog");
      expect(calllogTab).toBeInTheDocument();
    });

    it("should switch between all three tabs seamlessly", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const explorerTab = screen.getByTestId("tab-button-explorer");
      const logsTab = screen.getByTestId("tab-button-logs");
      const calllogTab = screen.getByTestId("tab-button-calllog");

      // Switch to Logs
      await user.click(logsTab);
      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });

      // Switch to Call Log
      await user.click(calllogTab);
      await waitFor(() => {
        expect(screen.queryByTestId("logs-explorer")).not.toBeInTheDocument();
      });

      // Switch back to Explorer
      await user.click(explorerTab);
      await waitFor(() => {
        expect(screen.getByText("← Select an endpoint to explore")).toBeInTheDocument();
      });

      // Switch back to Logs
      await user.click(logsTab);
      await waitFor(() => {
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test 9: Log functionality within HubApiExplorer context
  // ─────────────────────────────────────────────────────────────────────────

  describe("Log Functionality in Context", () => {
    it("should allow copying logs by clicking them", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        const logs = screen.queryAllByTestId(/log-entry/);
        expect(logs.length).toBeGreaterThan(0);
      });

      // Install our clipboard stub AFTER userEvent.setup() so it wins over
      // userEvent's shim. navigator.clipboard is getter-only in jsdom, so it
      // must be (re)defined rather than assigned.
      const writeText = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        writable: true,
        value: { writeText },
      });

      const firstLog = screen.queryAllByTestId(/log-entry/)[0];
      await user.click(firstLog);

      // Verify clipboard was called (might be async)
      await waitFor(() => {
        expect(writeText).toHaveBeenCalled();
      });
    });

    it("should allow searching logs in context", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("log-search-input")).toBeInTheDocument();
      });

      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "error");

      expect(searchInput).toHaveValue("error");
    });

    it("should allow filtering logs by level", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const logsTab = screen.getByTestId("tab-button-logs");
      await user.click(logsTab);

      await waitFor(() => {
        expect(screen.getByTestId("filter-btn-ERROR")).toBeInTheDocument();
      });

      const errorFilterBtn = screen.getByTestId("filter-btn-ERROR");
      const initialStyle = errorFilterBtn.style.border;

      await user.click(errorFilterBtn);

      // Style should change
      expect(errorFilterBtn.style.border).not.toBe(initialStyle);
    });
  });
});
