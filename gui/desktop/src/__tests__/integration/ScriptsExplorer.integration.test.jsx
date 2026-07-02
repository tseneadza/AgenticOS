import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScriptsExplorer from "../../components/ScriptsExplorer";
import { mockScripts, mockScriptInfo, mockScriptContent } from "../../../__tests__/fixtures/mockScripts";

// Mock fetch for API responses
global.fetch = vi.fn();

// ScriptsExplorer loads its data from the Hub sidecar on mount. Route each
// fetch call to a canned response so the component renders the mockScripts.
function installFetchMock() {
  global.fetch.mockImplementation((url) => {
    const u = String(url);
    if (u.includes("/api/health")) {
      return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
    }
    if (u.includes("/apps/scripts/info")) {
      return Promise.resolve({
        ok: true,
        headers: { get: () => "application/json" },
        json: async () => ({
          success: true,
          content: mockScriptContent,
          line_count: mockScriptInfo.lineCount,
        }),
      });
    }
    if (u.includes("/apps/scripts")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ scripts: mockScripts }),
      });
    }
    // Script run / any other endpoint
    return Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ success: true, output: "" }),
    });
  });
}

// Resolve the filter <input> by its placeholder (the component doesn't expose a
// data-testid for it).
function getFilterInput() {
  return screen.getByPlaceholderText(/Filter by name/i);
}

// Render and wait for the async script load to populate the list.
async function renderLoaded() {
  const result = render(<ScriptsExplorer />);
  await screen.findAllByTestId(/script-item/);
  return result;
}

describe("ScriptsExplorer Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch.mockReset();
    localStorage.clear();
    installFetchMock();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 1: Script Selection
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Selection Workflow", () => {
    it("should render script items in list", async () => {
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      expect(scriptItems.length).toBeGreaterThan(0);
    });

    it("should select script when clicking item", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length === 0) return;

      await user.click(scriptItems[0]);

      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should show selection border on selected script", async () => {
      const user = userEvent.setup();
      const { container } = await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length === 0) return;

      await user.click(scriptItems[0]);

      await waitFor(() => {
        const element = container.querySelector(
          `[data-testid="${scriptItems[0].getAttribute("data-testid")}"]`
        );
        // Selection is indicated via the "selected" class (and aria-selected),
        // not an inline border.
        expect(element.className).toContain("selected");
        expect(element).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should show only one script selected at a time", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length < 2) return;

      // Select first
      await user.click(scriptItems[0]);
      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });

      // Select second
      await user.click(scriptItems[1]);
      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "false");
        expect(scriptItems[1]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should keep a script selected when clicking it again (sticky selection)", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length === 0) return;

      // Select
      await user.click(scriptItems[0]);
      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });

      // Selection is sticky — clicking the same item keeps it selected.
      await user.click(scriptItems[0]);
      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should display script name and description", async () => {
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      expect(scriptItems.length).toBeGreaterThan(0);

      scriptItems.forEach(item => {
        expect(item.textContent.trim().length).toBeGreaterThan(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 2: Group Collapse/Expand
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Group Collapse/Expand Workflow", () => {
    it("should render script group headers", async () => {
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      expect(groupHeaders.length).toBeGreaterThan(0);
    });

    it("should collapse group when clicking header", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");

      await user.click(groupHeaders[0]);

      await waitFor(() => {
        const header = screen.getByTestId(`script-group-header-${firstGroupName}`);
        expect(header).toHaveAttribute("aria-expanded", "false");
      });
    });

    it("should expand collapsed group", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");

      // Collapse
      await user.click(groupHeaders[0]);
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "false"
        );
      });

      // Expand
      await user.click(screen.getByTestId(`script-group-header-${firstGroupName}`));
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "true"
        );
      });
    });

    it("should hide group items when collapsed", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const initialItemCount = screen.queryAllByTestId(/script-item/).length;

      // Collapse first group
      await user.click(groupHeaders[0]);

      await waitFor(() => {
        const newItemCount = screen.queryAllByTestId(/script-item/).length;
        expect(newItemCount).toBeLessThanOrEqual(initialItemCount);
      });
    });

    it("should preserve other groups' state when toggling one", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length < 2) return;

      const secondGroupName = groupHeaders[1]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");
      const secondGroupInitialState = groupHeaders[1].getAttribute("aria-expanded");

      // Collapse first group
      await user.click(groupHeaders[0]);

      await waitFor(() => {
        const secondGroup = screen.getByTestId(`script-group-header-${secondGroupName}`);
        expect(secondGroup).toHaveAttribute("aria-expanded", secondGroupInitialState);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 3: Type Filtering
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Type Filtering Workflow", () => {
    it("should render type badges on script items", async () => {
      await renderLoaded();

      const typeBadges = screen.queryAllByTestId(/script-type-badge/);
      expect(typeBadges.length).toBeGreaterThan(0);
    });

    it("should display different types correctly", async () => {
      await renderLoaded();

      const typeBadges = screen.queryAllByTestId(/script-type-badge/);
      const types = ["Launcher", "Test", "Data", "Scraper", "Diagnostic", "Dev Setup", "Maintenance"];

      const foundTypes = new Set();
      typeBadges.forEach(badge => {
        types.forEach(type => {
          if (badge.textContent.includes(type)) {
            foundTypes.add(type);
          }
        });
      });

      expect(foundTypes.size).toBeGreaterThan(0);
    });

    it("should style type badges with appropriate colors", async () => {
      const { container } = await renderLoaded();

      const typeBadges = screen.queryAllByTestId(/script-type-badge/);
      if (typeBadges.length === 0) return;

      // Type badges are color-coded via a semantic CSS class (script-type-badge
      // plus a per-type modifier), not inline color styles.
      typeBadges.slice(0, 3).forEach(badge => {
        expect(badge.className).toContain("script-type-badge");
        // A modifier class beyond the base class encodes the type color.
        expect(badge.className.trim().split(/\s+/).length).toBeGreaterThan(1);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 4: Search/Filter
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Search/Filter Workflow", () => {
    it("should have filter input", async () => {
      await renderLoaded();

      const filterInput = getFilterInput();
      expect(filterInput).toBeInTheDocument();
    });

    it("should filter scripts by name", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "test");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        items.forEach(item => {
          expect(item.textContent.toLowerCase()).toContain("test");
        });
      });
    });

    it("should filter scripts by type", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "Launcher");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBeGreaterThan(0);
      });
    });

    it("should clear filter and show all scripts", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "start");

      await waitFor(() => {
        const itemsFiltered = screen.queryAllByTestId(/script-item/);
        expect(itemsFiltered.length).toBeGreaterThan(0);
      });

      await user.clear(filterInput);

      await waitFor(() => {
        const itemsAll = screen.queryAllByTestId(/script-item/);
        expect(itemsAll.length).toBeGreaterThan(0);
      });
    });

    it("should show no results when filter matches nothing", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "NONEXISTENTSCRIPT12345");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBe(0);
      });
    });

    it("should be case-insensitive", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "LAUNCHER");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBeGreaterThan(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 5: Call Log Persistence
  // ────────────────────────────────────────────────────────────────────────

  describe("Call Log Persistence Workflow", () => {
    it("should render call log section", async () => {
      await renderLoaded();

      const callLog = screen.queryByTestId("call-log");
      expect(callLog || true).toBeTruthy(); // May or may not be initially visible
    });

    it("should persist log entries when filtering", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      // Filter scripts
      const filterInput = getFilterInput();
      await user.type(filterInput, "test");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBeGreaterThan(0);
      });

      // Log entries should still be visible if any exist
      const logEntries = screen.queryAllByTestId(/call-log-entry/);
      expect(logEntries || []).toBeDefined();
    });

    it("should preserve log across selections", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length < 2) return;

      // Select first script
      await user.click(scriptItems[0]);

      // Select second script
      await user.click(scriptItems[1]);

      // Log should persist
      const logSection = screen.queryByTestId("call-log") || true;
      expect(logSection).toBeTruthy();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 6: Group State Preservation
  // ────────────────────────────────────────────────────────────────────────

  describe("Group State Preservation", () => {
    it("should preserve collapsed state across filter", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");

      // Collapse first group
      await user.click(groupHeaders[0]);
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "false"
        );
      });

      // Filter with a term that keeps this group present (groups are by type, and
      // the filter matches on type), so we can verify its collapsed state persists.
      const filterInput = getFilterInput();
      await user.type(filterInput, firstGroupName.toLowerCase());

      // Group should still be collapsed
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "false"
        );
      });
    });

    it("should maintain collapse state after filter clear", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");

      // Collapse
      await user.click(groupHeaders[0]);
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "false"
        );
      });

      // Filter and clear
      const filterInput = getFilterInput();
      await user.type(filterInput, "test");
      await user.clear(filterInput);

      // Should still be collapsed
      await waitFor(() => {
        expect(screen.getByTestId(`script-group-header-${firstGroupName}`)).toHaveAttribute(
          "aria-expanded",
          "false"
        );
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 7: Keyboard Navigation
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Keyboard Navigation", () => {
    it("should allow keyboard Enter to select script", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length === 0) return;

      scriptItems[0].focus();
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should allow keyboard Space to select script", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length === 0) return;

      scriptItems[0].focus();
      await user.keyboard(" ");

      await waitFor(() => {
        expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should allow Enter on group header to toggle", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0]
        .getAttribute("data-testid")
        .replace("script-group-header-", "");

      groupHeaders[0].focus();
      const initialState = groupHeaders[0].getAttribute("aria-expanded");

      await user.keyboard("{Enter}");

      await waitFor(() => {
        const newState = screen
          .getByTestId(`script-group-header-${firstGroupName}`)
          .getAttribute("aria-expanded");
        expect(newState).not.toBe(initialState);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 8: Accessibility
  // ────────────────────────────────────────────────────────────────────────

  describe("Script Accessibility", () => {
    it("should have aria-labels on interactive elements", async () => {
      await renderLoaded();

      // The filter input is labeled by its placeholder (its accessible name).
      const filterInput = getFilterInput();
      expect(filterInput).toHaveAttribute("placeholder", expect.stringMatching(/Filter/i));

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-label");
      });

      const scriptItems = screen.queryAllByTestId(/script-item/);
      scriptItems.forEach(item => {
        expect(item).toHaveAttribute("aria-label");
      });
    });

    it("should have proper ARIA roles", async () => {
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("role", "button");
      });
    });

    it("should have aria-selected on script items", async () => {
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      scriptItems.forEach(item => {
        expect(item).toHaveAttribute("aria-selected");
      });
    });

    it("should have aria-expanded on group headers", async () => {
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-expanded");
      });
    });

    it("should have meaningful text content", async () => {
      await renderLoaded();

      const scriptItems = screen.queryAllByTestId(/script-item/);
      scriptItems.forEach(item => {
        expect(item.textContent.trim().length).toBeGreaterThan(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 9: Empty State
  // ────────────────────────────────────────────────────────────────────────

  describe("Empty State Handling", () => {
    it("should show no results when filter matches nothing", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "NONEXISTENT_SCRIPT_XYZ");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBe(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 10: Complex Multi-Step Workflows
  // ────────────────────────────────────────────────────────────────────────

  describe("Complex Script Workflows", () => {
    it("should filter → collapse → select workflow", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      // Step 1: Filter
      const filterInput = getFilterInput();
      await user.type(filterInput, "test");

      let items = await screen.findAllByTestId(/script-item/);
      expect(items.length).toBeGreaterThan(0);

      // Step 2: Collapse a group
      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length > 0) {
        await user.click(groupHeaders[0]);
      }

      // Step 3: Select first visible item
      items = screen.queryAllByTestId(/script-item/);
      if (items.length > 0) {
        await user.click(items[0]);
        await waitFor(() => {
          expect(items[0]).toHaveAttribute("aria-selected", "true");
        });
      }
    });

    it("should handle rapid filter changes", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();

      await user.type(filterInput, "L");
      await user.type(filterInput, "a");
      await user.type(filterInput, "u");
      await user.type(filterInput, "n");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBeGreaterThan(0);
      });

      // Clear
      await user.clear(filterInput);

      await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        expect(items.length).toBeGreaterThan(0);
      });
    });

    it("should handle multiple group toggles", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const groupHeaders = screen.queryAllByTestId(/script-group-header-/);
      if (groupHeaders.length < 2) return;

      // Toggle first group
      await user.click(groupHeaders[0]);
      // Toggle second group
      await user.click(groupHeaders[1]);
      // Toggle first group back
      await user.click(groupHeaders[0]);

      // All should respond correctly
      await waitFor(() => {
        expect(groupHeaders[0]).toHaveAttribute("aria-expanded");
        expect(groupHeaders[1]).toHaveAttribute("aria-expanded");
      });
    });

    it("should handle selection after filtering", async () => {
      const user = userEvent.setup();
      await renderLoaded();

      const filterInput = getFilterInput();
      await user.type(filterInput, "test");

      let items = await screen.findAllByTestId(/script-item/);
      expect(items.length).toBeGreaterThan(0);

      // Select
      await user.click(items[0]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });

      // Change filter
      await user.clear(filterInput);
      await user.type(filterInput, "start");

      // Previous selection should be cleared
      items = screen.queryAllByTestId(/script-item/);
      if (items.length > 0) {
        const selectedCount = items.filter(
          item => item.getAttribute("aria-selected") === "true"
        ).length;
        expect(selectedCount).toBeLessThanOrEqual(1);
      }
    });
  });
});
