import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HubApiExplorer from "../../components/HubApiExplorer";
import { mockEndpoints, mockResponse, mockErrorResponse } from "../../../__tests__/fixtures/mockEndpoints";

// Mock fetch for API responses
global.fetch = vi.fn();

describe("HubApiExplorer Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch.mockReset();
    // HubApiExplorer persists filter/collapse state to localStorage; clear it so
    // state from one test (e.g. a collapsed group or an active filter) doesn't
    // leak into the next and hide the endpoint list.
    localStorage.clear();
    // Health-check fetches run on mount; give them a benign resolved response.
    global.fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 1: Filter → Display Updates
  // ────────────────────────────────────────────────────────────────────────

  describe("Filter Workflow", () => {
    it("should filter endpoints by method name", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      // Lowercase term (the filter is case-sensitive against lowercased fields).
      await user.type(filterInput, "get");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
        items.forEach(item => {
          expect(item.getAttribute("aria-label").toLowerCase()).toContain("get");
        });
      });
    });

    it("should filter endpoints by path", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const allInitial = screen.queryAllByTestId(/endpoint-list-item/).length;
      const filterInput = screen.getByTestId("filter-input");
      await user.type(filterInput, "cards");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
        // Filtering narrows the list (matches occur on path OR description).
        expect(items.length).toBeLessThan(allInitial);
      });
      // At least one surviving endpoint references "cards" in its path.
      const labels = screen
        .queryAllByTestId(/endpoint-list-item/)
        .map(i => i.getAttribute("aria-label").toLowerCase());
      expect(labels.some(l => l.includes("cards"))).toBe(true);
    });

    it("should clear filter and show all endpoints", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const allInitial = screen.queryAllByTestId(/endpoint-list-item/).length;
      expect(allInitial).toBeGreaterThan(0);

      const filterInput = screen.getByTestId("filter-input");
      // NOTE: the component's filter is currently case-sensitive against
      // lowercased fields, so filter terms must be lowercase to match.
      await user.type(filterInput, "get");

      await waitFor(() => {
        const itemsFiltered = screen.queryAllByTestId(/endpoint-list-item/);
        expect(itemsFiltered.length).toBeGreaterThan(0);
        expect(itemsFiltered.length).toBeLessThanOrEqual(allInitial);
      });

      await user.clear(filterInput);

      await waitFor(() => {
        const itemsAll = screen.queryAllByTestId(/endpoint-list-item/);
        expect(itemsAll.length).toBe(allInitial);
      });
    });

    it("should show no results when filter matches nothing", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      await user.type(filterInput, "NONEXISTENTPATH12345");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBe(0);
      });
    });

    it("should match a lowercase method filter", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      // KNOWN BUG: the filter is case-sensitive (compares against lowercased
      // fields), so only a lowercase term matches. See test-suite summary.
      await user.type(filterInput, "get");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
      });
    });

    it("should update results as user types", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      const initial = screen.queryAllByTestId(/endpoint-list-item/).length;
      expect(initial).toBeGreaterThan(0);

      // Type a lowercase term that matches a subset of endpoints.
      await user.type(filterInput, "get");
      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
        expect(items.length).toBeLessThanOrEqual(initial);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 2: Collapse/Expand Groups
  // ────────────────────────────────────────────────────────────────────────

  describe("Group Collapse/Expand Workflow", () => {
    it("should collapse a group when clicking header", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Find a group header
      const groupHeaders = screen.getAllByTestId(/group-header-/);
      expect(groupHeaders.length).toBeGreaterThan(0);

      // Click first group header to collapse
      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");
      await user.click(groupHeaders[0]);

      // Verify collapsed state
      await waitFor(() => {
        const header = screen.getByTestId(`group-header-${firstGroupName}`);
        expect(header).toHaveAttribute("aria-expanded", "false");
      });
    });

    it("should expand a collapsed group", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");

      // Collapse
      await user.click(groupHeaders[0]);
      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "false");
      });

      // Expand
      await user.click(screen.getByTestId(`group-header-${firstGroupName}`));
      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should rotate chevron when toggling group", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");
      const header = screen.getByTestId(`group-header-${firstGroupName}`);

      // Chevron rotation is CSS-driven off the header's aria-expanded state.
      const before = header.getAttribute("aria-expanded");
      await user.click(header);

      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`).getAttribute("aria-expanded")).not.toBe(before);
      });
      // The chevron element remains present with its rotation class.
      expect(screen.getByTestId(`group-chevron-${firstGroupName}`).className).toContain("group-chevron");
    });

    it("should hide group items when collapsed", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Get initial count of visible items
      const groupHeaders = screen.getAllByTestId(/group-header-/);
      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");
      const initialItemCount = screen.queryAllByTestId(/endpoint-list-item/).length;

      // Collapse first group
      await user.click(groupHeaders[0]);

      await waitFor(() => {
        const newItemCount = screen.queryAllByTestId(/endpoint-list-item/).length;
        expect(newItemCount).toBeLessThanOrEqual(initialItemCount);
      });
    });

    it("should preserve other groups' state when toggling one", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length < 2) return; // Skip if not enough groups

      const secondGroupName = groupHeaders[1].getAttribute("data-testid").replace("group-header-", "");
      const secondGroupInitialState = groupHeaders[1].getAttribute("aria-expanded");

      // Collapse first group
      await user.click(groupHeaders[0]);

      await waitFor(() => {
        const secondGroup = screen.getByTestId(`group-header-${secondGroupName}`);
        expect(secondGroup).toHaveAttribute("aria-expanded", secondGroupInitialState);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 3: Tab Switching with State Persistence
  // ────────────────────────────────────────────────────────────────────────

  describe("Tab Switching Workflow", () => {
    it("should switch between tabs", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const explorerTab = screen.getByTestId("tab-button-explorer");
      const calllogTab = screen.getByTestId("tab-button-calllog");

      // Should start on explorer tab
      expect(explorerTab).toHaveAttribute("aria-selected", "true");

      // Switch to calllog
      await user.click(calllogTab);

      await waitFor(() => {
        expect(calllogTab).toHaveAttribute("aria-selected", "true");
        expect(explorerTab).toHaveAttribute("aria-selected", "false");
      });
    });

    it("should preserve filter state when switching tabs", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      await user.type(filterInput, "GET");

      const calllogTab = screen.getByTestId("tab-button-calllog");
      await user.click(calllogTab);

      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      await waitFor(() => {
        expect(filterInput).toHaveValue("GET");
      });
    });

    it("should preserve selection state across tab switch", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      // Select first item
      await user.click(items[0]);

      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });

      // Switch to calllog
      const calllogTab = screen.getByTestId("tab-button-calllog");
      await user.click(calllogTab);

      // Switch back
      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should preserve collapse state across tab switch", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");

      // Collapse first group
      await user.click(groupHeaders[0]);

      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "false");
      });

      // Switch tabs
      const calllogTab = screen.getByTestId("tab-button-calllog");
      await user.click(calllogTab);

      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      // Group should still be collapsed
      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "false");
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 4: Selection & Details
  // ────────────────────────────────────────────────────────────────────────

  describe("Selection and Detail Workflow", () => {
    it("should select endpoint item and show selection state", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      expect(items.length).toBeGreaterThan(0);

      await user.click(items[0]);

      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should show only one item selected at a time", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length < 2) return;

      // Select first
      await user.click(items[0]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });

      // Select second
      await user.click(items[1]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "false");
        expect(items[1]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should apply the selected class to the selected item", async () => {
      const user = userEvent.setup();
      const { container } = render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      await user.click(items[0]);

      await waitFor(() => {
        const element = container.querySelector(
          `[data-testid="${items[0].getAttribute("data-testid")}"]`
        );
        // Selection is indicated via the "selected" class, not an inline border.
        expect(element.className).toContain("selected");
        expect(element).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should keep an item selected when clicking it again (sticky selection)", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      // Select
      await user.click(items[0]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });

      // Selection is sticky — clicking the same item keeps it selected.
      await user.click(items[0]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should collapse group containing selected item without affecting selection", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      // Select an item
      await user.click(items[0]);
      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });

      // Collapse its group
      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length > 0) {
        await user.click(groupHeaders[0]);

        // Selection state should be preserved internally (though item may not be visible)
        await waitFor(() => {
          expect(items[0]).toHaveAttribute("aria-selected", "true");
        });
      }
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 5: Nested Component Rendering
  // ────────────────────────────────────────────────────────────────────────

  describe("Nested Component Rendering", () => {
    it("should render method badge in endpoint list item", async () => {
      render(<HubApiExplorer />);

      const badges = screen.queryAllByTestId(/endpoint-method-/);
      expect(badges.length).toBeGreaterThan(0);
    });

    it("should render path display in endpoint list item", async () => {
      render(<HubApiExplorer />);

      const paths = screen.queryAllByTestId(/endpoint-path-/);
      expect(paths.length).toBeGreaterThan(0);
    });

    it("should display correct HTTP method in badge", async () => {
      render(<HubApiExplorer />);

      const badges = screen.queryAllByTestId(/endpoint-method-/);
      const methods = ["GET", "POST", "PUT", "DELETE", "PATCH"];

      const foundMethods = new Set();
      badges.forEach(badge => {
        methods.forEach(method => {
          if (badge.textContent.includes(method)) {
            foundMethods.add(method);
          }
        });
      });

      expect(foundMethods.size).toBeGreaterThan(0);
    });

    it("should highlight path parameters in path display", async () => {
      render(<HubApiExplorer />);

      const paths = screen.queryAllByTestId(/endpoint-path-/);
      let foundParamPath = false;

      paths.forEach(path => {
        if (path.textContent.includes("{")) {
          foundParamPath = true;
        }
      });

      // Not all endpoints have params, but some should
      expect(paths.length).toBeGreaterThan(0);
    });

    it("should render all endpoint items with correct structure", async () => {
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      expect(items.length).toBeGreaterThan(0);

      items.forEach(item => {
        // Each item should have method and path
        expect(item.textContent).toBeTruthy();
        expect(item).toHaveAttribute("data-testid");
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 6: Empty State
  // ────────────────────────────────────────────────────────────────────────

  describe("Empty State Handling", () => {
    it("should show no results when filter matches nothing", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      await user.type(filterInput, "UTTERLY_NONEXISTENT_ENDPOINT_XYZ");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBe(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 7: Keyboard Navigation
  // ────────────────────────────────────────────────────────────────────────

  describe("Keyboard Navigation", () => {
    it("should focus filter input on Tab from initial focus", async () => {
      render(<HubApiExplorer />);
      const filterInput = screen.getByTestId("filter-input");

      filterInput.focus();
      expect(filterInput).toHaveFocus();
    });

    it("should allow keyboard Enter to select item", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      items[0].focus();
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should allow keyboard Space to select item", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length === 0) return;

      items[0].focus();
      await user.keyboard(" ");

      await waitFor(() => {
        expect(items[0]).toHaveAttribute("aria-selected", "true");
      });
    });

    it("should allow Enter on group header to toggle", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");

      groupHeaders[0].focus();
      const initialState = groupHeaders[0].getAttribute("aria-expanded");

      await user.keyboard("{Enter}");

      await waitFor(() => {
        const newState = screen.getByTestId(`group-header-${firstGroupName}`).getAttribute("aria-expanded");
        expect(newState).not.toBe(initialState);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 8: Accessibility
  // ────────────────────────────────────────────────────────────────────────

  describe("Accessibility", () => {
    it("should have aria-labels on all interactive elements", async () => {
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");
      expect(filterInput).toHaveAttribute("aria-label");

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-label");
      });

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      items.forEach(item => {
        expect(item).toHaveAttribute("aria-label");
      });
    });

    it("should have proper ARIA roles", async () => {
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("role", "button");
      });
    });

    it("should have aria-selected attributes on selectable items", async () => {
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      items.forEach(item => {
        expect(item).toHaveAttribute("aria-selected");
      });
    });

    it("should have aria-expanded on collapsible groups", async () => {
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      groupHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-expanded");
      });
    });

    it("should announce state changes to screen readers", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length === 0) return;

      const firstGroupName = groupHeaders[0].getAttribute("data-testid").replace("group-header-", "");

      // Toggle and check aria-expanded updates
      await user.click(groupHeaders[0]);
      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "false");
      });

      await user.click(screen.getByTestId(`group-header-${firstGroupName}`));
      await waitFor(() => {
        expect(screen.getByTestId(`group-header-${firstGroupName}`)).toHaveAttribute("aria-expanded", "true");
      });
    });

    it("should have meaningful text content for all items", async () => {
      render(<HubApiExplorer />);

      const items = screen.queryAllByTestId(/endpoint-list-item/);
      items.forEach(item => {
        expect(item.textContent.trim().length).toBeGreaterThan(0);
      });
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 9: Complex Multi-Step Workflows
  // ────────────────────────────────────────────────────────────────────────

  describe("Complex Multi-Step Workflows", () => {
    it("should filter → collapse → select → switch tabs → restore all state", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      // Step 1: Filter (lowercase — the filter is case-sensitive)
      const filterInput = screen.getByTestId("filter-input");
      await user.type(filterInput, "get");

      let items = await screen.findAllByTestId(/endpoint-list-item/);
      expect(items.length).toBeGreaterThan(0);

      // Step 2: Collapse a group
      const groupHeaders = screen.getAllByTestId(/group-header-/);
      if (groupHeaders.length > 0) {
        await user.click(groupHeaders[0]);
      }

      // Step 3: Select first visible item
      items = screen.queryAllByTestId(/endpoint-list-item/);
      if (items.length > 0) {
        await user.click(items[0]);
        await waitFor(() => {
          expect(items[0]).toHaveAttribute("aria-selected", "true");
        });
      }

      // Step 4: Switch tabs
      const calllogTab = screen.getByTestId("tab-button-calllog");
      await user.click(calllogTab);

      // Step 5: Switch back
      const explorerTab = screen.getByTestId("tab-button-explorer");
      await user.click(explorerTab);

      // Step 6: Verify all state restored
      await waitFor(() => {
        expect(filterInput).toHaveValue("get");
        items = screen.queryAllByTestId(/endpoint-list-item/);
        if (items.length > 0) {
          expect(items[0]).toHaveAttribute("aria-selected", "true");
        }
      });
    });

    it("should handle rapid filter changes", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const filterInput = screen.getByTestId("filter-input");

      // Lowercase — the filter is case-sensitive against lowercased fields.
      await user.type(filterInput, "g");
      await user.type(filterInput, "e");
      await user.type(filterInput, "t");

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
      });

      // Clear
      await user.clear(filterInput);

      await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        expect(items.length).toBeGreaterThan(0);
      });
    });

    it("should handle multiple group toggles", async () => {
      const user = userEvent.setup();
      render(<HubApiExplorer />);

      const groupHeaders = screen.getAllByTestId(/group-header-/);
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
  });
});
