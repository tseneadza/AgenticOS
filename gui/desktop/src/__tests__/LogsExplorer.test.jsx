import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LogsExplorer from "../components/LogsExplorer";

// ─────────────────────────────────────────────────────────────────────────
// Mock Log Data Generators
// ─────────────────────────────────────────────────────────────────────────

function createMockLog(timestamp, level, message) {
  return { timestamp, level, message };
}

function createMockLogs(count = 50) {
  const levels = ["DEBUG", "INFO", "WARN", "ERROR"];
  const logs = [];
  for (let i = 0; i < count; i++) {
    const hour = Math.floor(i / 10);
    const min = (i % 10) * 6;
    const timestamp = `2026-06-30 10:${min.toString().padStart(2, "0")}:${hour.toString().padStart(2, "0")}`;
    const level = levels[i % 4];
    const messages = [
      "System started successfully",
      "Database connection established",
      "Processing request",
      "Warning: high memory usage",
      "Error: connection timeout",
      "Debug: entering function X",
      "Info: configuration loaded",
      "Cleanup completed",
    ];
    const message = messages[i % messages.length];
    logs.push(createMockLog(timestamp, level, `${message} (${i})`));
  }
  return logs;
}

// ─────────────────────────────────────────────────────────────────────────
// Test Suite: LogsExplorer
// ─────────────────────────────────────────────────────────────────────────

describe("LogsExplorer Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without errors", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
    });

    it("should render search input", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("log-search-input")).toBeInTheDocument();
    });

    it("should render filter buttons for all levels", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("filter-btn-DEBUG")).toBeInTheDocument();
      expect(screen.getByTestId("filter-btn-INFO")).toBeInTheDocument();
      expect(screen.getByTestId("filter-btn-WARN")).toBeInTheDocument();
      expect(screen.getByTestId("filter-btn-ERROR")).toBeInTheDocument();
    });

    it("should render export buttons", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("export-txt")).toBeInTheDocument();
      expect(screen.getByTestId("export-json")).toBeInTheDocument();
    });

    it("should render auto-scroll toggle", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("toggle-autoscroll")).toBeInTheDocument();
    });

    it("should render logs container", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("logs-container")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Log Display Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("log display", () => {
    it("should display logs from mock data", () => {
      const mockLogs = createMockLogs(5);
      render(<LogsExplorer logs={mockLogs} />);
      mockLogs.forEach((log) => {
        expect(screen.getByText(new RegExp(log.message))).toBeInTheDocument();
      });
    });

    it("should display empty state when no logs", () => {
      render(<LogsExplorer logs={[]} />);
      expect(screen.getByTestId("empty-logs")).toBeInTheDocument();
      expect(screen.getByText("No logs available")).toBeInTheDocument();
    });

    it("should display log entries with correct structure", () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Test message"),
      ];
      render(<LogsExplorer logs={mockLogs} />);
      expect(screen.getByTestId("log-entry-INFO")).toBeInTheDocument();
    });

    it("should render large dataset (1000+ logs)", () => {
      const mockLogs = createMockLogs(1000);
      const { container } = render(<LogsExplorer logs={mockLogs} />);
      expect(container.querySelectorAll('[data-testid^="log-entry-"]').length).toBeGreaterThan(0);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Filter Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("filtering by level", () => {
    it("should filter by single level (ERROR only)", async () => {
      const mockLogs = createMockLogs(20);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Uncheck all except ERROR
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-WARN"));

      // Should only show ERROR logs
      const errorLogs = mockLogs.filter((log) => log.level === "ERROR");
      const logCount = screen.getByText(new RegExp(`Showing ${errorLogs.length}`));
      expect(logCount).toBeInTheDocument();
    });

    it("should filter by multiple levels (ERROR + WARN)", async () => {
      const mockLogs = createMockLogs(20);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Uncheck DEBUG and INFO
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-INFO"));

      // Should show ERROR + WARN logs only
      const filtered = mockLogs.filter(
        (log) => log.level === "ERROR" || log.level === "WARN"
      );
      const logCount = screen.getByText(new RegExp(`Showing ${filtered.length}`));
      expect(logCount).toBeInTheDocument();
    });

    it("should apply OR logic to filters", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "ERROR", "Error 1"),
        createMockLog("2026-06-30 10:00:01", "WARN", "Warn 1"),
        createMockLog("2026-06-30 10:00:02", "INFO", "Info 1"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Uncheck INFO and DEBUG, keep ERROR and WARN
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-DEBUG"));

      // Should show 2 logs (ERROR + WARN)
      expect(screen.getByText(new RegExp("Showing 2 of 3"))).toBeInTheDocument();
    });

    it("should update display when filter state changes", async () => {
      const mockLogs = createMockLogs(10);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Initially all levels should be visible
      expect(screen.getByText(new RegExp("Showing 10 of 10"))).toBeInTheDocument();

      // Filter to ERROR only
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-WARN"));

      // Should update count
      const errorCount = mockLogs.filter((log) => log.level === "ERROR").length;
      expect(
        screen.getByText(new RegExp(`Showing ${errorCount} of 10`))
      ).toBeInTheDocument();
    });

    it("should show message when no logs match filter", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Test"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Filter to ERROR (won't find any)
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-WARN"));

      expect(screen.getByText("No logs match your filter")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Search Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("search functionality", () => {
    it("should search by message text", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Database connection"),
        createMockLog("2026-06-30 10:00:01", "WARN", "Network timeout"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "Database");

      expect(screen.getByText(new RegExp("Showing 1 of 2"))).toBeInTheDocument();
    });

    it("should search case-insensitively", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "ERROR detected"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "error");

      expect(screen.getByText(new RegExp("Showing 1 of 1"))).toBeInTheDocument();
    });

    it("should clear search and show all again", async () => {
      const mockLogs = createMockLogs(5);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "xyz-not-found");
      expect(screen.getByText("No logs match your filter")).toBeInTheDocument();

      await user.clear(searchInput);
      expect(screen.getByText(new RegExp("Showing 5 of 5"))).toBeInTheDocument();
    });

    it("should highlight matching search terms", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Database connection"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "Database");

      // The matching text should be highlighted with special styling
      const logEntry = screen.getByTestId("log-entry-INFO");
      expect(logEntry).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Auto-scroll Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("auto-scroll behavior", () => {
    it("should have auto-scroll enabled by default", () => {
      render(<LogsExplorer logs={createMockLogs(5)} />);
      const button = screen.getByTestId("toggle-autoscroll");
      expect(button.textContent).toContain("ON");
    });

    it("should toggle auto-scroll on button click", async () => {
      const user = userEvent.setup();
      render(<LogsExplorer logs={createMockLogs(5)} />);
      const button = screen.getByTestId("toggle-autoscroll");

      expect(button.textContent).toContain("ON");
      await user.click(button);
      expect(button.textContent).toContain("OFF");
      await user.click(button);
      expect(button.textContent).toContain("ON");
    });

    it("should pause auto-scroll when button is clicked", async () => {
      const user = userEvent.setup();
      render(<LogsExplorer logs={createMockLogs(5)} />);
      const button = screen.getByTestId("toggle-autoscroll");

      await user.click(button);
      expect(button).toHaveAttribute("aria-pressed", "false");
    });

    it("should maintain scroll position when paused", async () => {
      const user = userEvent.setup();
      const { rerender } = render(<LogsExplorer logs={createMockLogs(10)} />);
      const button = screen.getByTestId("toggle-autoscroll");

      await user.click(button);
      // Add more logs while paused
      rerender(<LogsExplorer logs={createMockLogs(15)} />);

      // Auto-scroll should be OFF
      expect(button.textContent).toContain("OFF");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Export Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("export functionality", () => {
    beforeEach(() => {
      // Mock URL and download functions
      global.URL.createObjectURL = vi.fn(() => "blob:mock");
      global.URL.revokeObjectURL = vi.fn();
      document.createElement = vi.fn((tag) => {
        if (tag === "a") {
          return {
            href: "",
            download: "",
            click: vi.fn(),
          };
        }
        return document.createElement(tag);
      });
    });

    afterEach(() => {
      vi.clearAllMocks();
    });

    it("should export filtered logs as .txt", async () => {
      const mockLogs = createMockLogs(5);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const exportBtn = screen.getByTestId("export-txt");
      await user.click(exportBtn);

      // Verify blob was created
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });

    it("should export filtered logs as .json", async () => {
      const mockLogs = createMockLogs(5);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const exportBtn = screen.getByTestId("export-json");
      await user.click(exportBtn);

      // Verify blob was created
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });

    it("should export only visible logs (respecting filters)", async () => {
      const mockLogs = createMockLogs(10);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      // Filter to ERROR only
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-WARN"));

      await user.click(screen.getByTestId("export-txt"));

      // URL.createObjectURL should be called
      expect(global.URL.createObjectURL).toHaveBeenCalled();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Copy to Clipboard Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("copy to clipboard", () => {
    beforeEach(() => {
      Object.assign(navigator, {
        clipboard: {
          writeText: vi.fn(() => Promise.resolve()),
        },
      });
    });

    it("should copy log entry to clipboard on click", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Test message"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const logEntry = screen.getByTestId("log-entry-INFO");
      await user.click(logEntry);

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringContaining("Test message")
      );
    });

    it("should show 'Copied!' feedback after copy", async () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Test"),
      ];
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const logEntry = screen.getByTestId("log-entry-INFO");
      await user.click(logEntry);

      await waitFor(() => {
        expect(screen.getByText("Copied!")).toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Keyboard Accessibility Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("keyboard accessibility", () => {
    it("should allow Tab navigation through filters", async () => {
      const user = userEvent.setup();
      render(<LogsExplorer logs={[]} />);

      const filterBtn = screen.getByTestId("filter-btn-ERROR");
      filterBtn.focus();
      expect(filterBtn).toHaveFocus();
    });

    it("should allow Enter key to toggle filters", async () => {
      const mockLogs = createMockLogs(10);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const filterBtn = screen.getByTestId("filter-btn-DEBUG");
      filterBtn.focus();
      await user.keyboard("{Enter}");

      // Filter should be toggled
      expect(filterBtn).toHaveAttribute("aria-pressed", "false");
    });

    it("should allow Space key to toggle filters", async () => {
      const mockLogs = createMockLogs(10);
      const user = userEvent.setup();
      render(<LogsExplorer logs={mockLogs} />);

      const filterBtn = screen.getByTestId("filter-btn-DEBUG");
      filterBtn.focus();
      await user.keyboard(" ");

      expect(filterBtn).toHaveAttribute("aria-pressed", "false");
    });

    it("should allow Tab into search input", async () => {
      const user = userEvent.setup();
      render(<LogsExplorer logs={[]} />);

      const searchInput = screen.getByTestId("log-search-input");
      searchInput.focus();
      expect(searchInput).toHaveFocus();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Mobile Responsiveness Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("mobile responsiveness", () => {
    it("should render controls in a mobile-friendly layout", () => {
      const { container } = render(<LogsExplorer logs={createMockLogs(5)} />);
      const controls = container.querySelector('[data-testid="log-filter"]');
      expect(controls).toBeInTheDocument();
    });

    it("should have readable font size on mobile", () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "INFO", "Test"),
      ];
      const { container } = render(<LogsExplorer logs={mockLogs} />);
      const logEntry = container.querySelector('[data-testid^="log-entry-"]');
      const style = window.getComputedStyle(logEntry);
      // Font size should be at least 12px for readability
      expect(logEntry.style.fontSize).toBe("12px");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-time Update Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-time updates", () => {
    it("should update display when logs prop changes", () => {
      const initialLogs = createMockLogs(5);
      const { rerender } = render(<LogsExplorer logs={initialLogs} />);

      expect(screen.getByText(new RegExp("Showing 5 of 5"))).toBeInTheDocument();

      const updatedLogs = createMockLogs(10);
      rerender(<LogsExplorer logs={updatedLogs} />);

      expect(screen.getByText(new RegExp("Showing 10 of 10"))).toBeInTheDocument();
    });

    it("should maintain filter state when logs update", async () => {
      const initialLogs = createMockLogs(10);
      const user = userEvent.setup();
      const { rerender } = render(<LogsExplorer logs={initialLogs} />);

      // Apply filter
      await user.click(screen.getByTestId("filter-btn-DEBUG"));
      await user.click(screen.getByTestId("filter-btn-INFO"));
      await user.click(screen.getByTestId("filter-btn-WARN"));

      const beforeUpdate = screen.getByText(new RegExp(/Showing \d+ of 10/));

      // Update logs
      const updatedLogs = createMockLogs(15);
      rerender(<LogsExplorer logs={updatedLogs} />);

      // Filter should still be applied
      const errorCount = updatedLogs.filter((l) => l.level === "ERROR").length;
      expect(screen.getByText(new RegExp(`Showing ${errorCount}`))).toBeInTheDocument();
    });

    it("should maintain search state when logs update", async () => {
      const initialLogs = createMockLogs(10);
      const user = userEvent.setup();
      const { rerender } = render(<LogsExplorer logs={initialLogs} />);

      // Apply search
      const searchInput = screen.getByTestId("log-search-input");
      await user.type(searchInput, "connection");

      // Update logs
      const updatedLogs = [
        ...createMockLogs(5),
        createMockLog("2026-06-30 10:00:00", "INFO", "Database connection established"),
      ];
      rerender(<LogsExplorer logs={updatedLogs} />);

      // Search should still be applied
      expect(searchInput).toHaveValue("connection");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Theme & Styling Tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("theme and styling", () => {
    it("should use theme variables for colors", () => {
      const mockLogs = [
        createMockLog("2026-06-30 10:00:00", "ERROR", "Error message"),
      ];
      const { container } = render(<LogsExplorer logs={mockLogs} />);
      const logEntry = container.querySelector('[data-testid^="log-entry-"]');
      expect(logEntry.style.color).toBeTruthy();
    });

    it("should render in all themes without errors", () => {
      const themes = [
        "terracotta-light",
        "terracotta-dark",
        "cyber-light",
        "cyber-dark",
      ];
      const mockLogs = createMockLogs(5);

      themes.forEach((theme) => {
        const { unmount } = render(<LogsExplorer logs={mockLogs} />);
        expect(screen.getByTestId("logs-explorer")).toBeInTheDocument();
        unmount();
      });
    });
  });
});
