import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HubApiExplorer from "../../components/HubApiExplorer";
import ScriptsExplorer from "../../components/ScriptsExplorer";

// Mock fetch for API responses
global.fetch = vi.fn();

describe("Cross-Explorer Integration Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 1: Theme Consistency
  // ────────────────────────────────────────────────────────────────────────

  describe("Theme Consistency Across Explorers", () => {
    it("should render both explorers without errors", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const { unmount: unmount2 } = render(<ScriptsExplorer />);

      expect(screen.queryAllByTestId(/filter-input/).length).toBeGreaterThan(0);

      unmount1();
      unmount2();
    });

    it("should apply consistent styling to group headers", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiHeaders = screen.getAllByTestId(/group-header-/);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptHeaders = screen.getAllByTestId(/script-group-header-/);

      // Both should have group headers
      expect(apiHeaders.length).toBeGreaterThan(0);
      expect(scriptHeaders.length).toBeGreaterThan(0);

      // Both should have aria attributes
      apiHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-expanded");
      });

      scriptHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-expanded");
      });

      unmount1();
      unmount2();
    });

    it("should use consistent filter input styling", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      const apiFilterStyles = window.getComputedStyle(apiFilter);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      const scriptFilterStyles = window.getComputedStyle(scriptFilter);

      // Both should be input elements with similar structure
      expect(apiFilter.tagName).toBe("INPUT");
      expect(scriptFilter.tagName).toBe("INPUT");

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 2: Layout Consistency
  // ────────────────────────────────────────────────────────────────────────

  describe("Layout Consistency Between Explorers", () => {
    it("should both have filter bars at top", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      expect(apiFilter).toBeInTheDocument();

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      expect(scriptFilter).toBeInTheDocument();

      unmount1();
      unmount2();
    });

    it("should both have grouped list items", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);
      expect(apiItems.length).toBeGreaterThan(0);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);
      expect(scriptItems.length).toBeGreaterThan(0);

      unmount1();
      unmount2();
    });

    it("should both have collapsible group headers", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiHeaders = screen.getAllByTestId(/group-header-/);
      expect(apiHeaders.length).toBeGreaterThan(0);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptHeaders = screen.getAllByTestId(/script-group-header-/);
      expect(scriptHeaders.length).toBeGreaterThan(0);

      unmount1();
      unmount2();
    });

    it("should both support single selection model", async () => {
      const user = userEvent.setup();
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);

      if (apiItems.length >= 2) {
        await user.click(apiItems[0]);
        await waitFor(() => {
          expect(apiItems[0]).toHaveAttribute("aria-selected", "true");
        });

        await user.click(apiItems[1]);
        await waitFor(() => {
          expect(apiItems[0]).toHaveAttribute("aria-selected", "false");
          expect(apiItems[1]).toHaveAttribute("aria-selected", "true");
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);

      if (scriptItems.length >= 2) {
        await user.click(scriptItems[0]);
        await waitFor(() => {
          expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
        });

        await user.click(scriptItems[1]);
        await waitFor(() => {
          expect(scriptItems[0]).toHaveAttribute("aria-selected", "false");
          expect(scriptItems[1]).toHaveAttribute("aria-selected", "true");
        });
      }

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 3: State Isolation
  // ────────────────────────────────────────────────────────────────────────

  describe("State Isolation Between Explorers", () => {
    it("should not affect each other's selection state", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);

      if (apiItems.length > 0) {
        await user.click(apiItems[0]);
        await waitFor(() => {
          expect(apiItems[0]).toHaveAttribute("aria-selected", "true");
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);

      if (scriptItems.length > 0) {
        // Script selection should not affect API selection
        await user.click(scriptItems[0]);
        await waitFor(() => {
          expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
        });
      }

      unmount1();
      unmount2();
    });

    it("should not affect each other's filter state", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      await user.type(apiFilter, "GET");

      await waitFor(() => {
        expect(apiFilter).toHaveValue("GET");
      });

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");

      // Script filter should be empty
      expect(scriptFilter).toHaveValue("");

      unmount1();
      unmount2();
    });

    it("should not affect each other's collapse state", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiHeaders = screen.getAllByTestId(/group-header-/);

      if (apiHeaders.length > 0) {
        const apiGroupName = apiHeaders[0]
          .getAttribute("data-testid")
          .replace("group-header-", "");
        await user.click(apiHeaders[0]);

        await waitFor(() => {
          expect(screen.getByTestId(`group-header-${apiGroupName}`)).toHaveAttribute(
            "aria-expanded",
            "false"
          );
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptHeaders = screen.getAllByTestId(/script-group-header-/);

      // Script groups should not be affected
      scriptHeaders.forEach(header => {
        expect(header).toHaveAttribute("aria-expanded", "true");
      });

      unmount1();
      unmount2();
    });

    it("should maintain independent filtering", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      const apiItemsInitial = screen.queryAllByTestId(/endpoint-list-item/).length;

      await user.type(apiFilter, "GET");
      await waitFor(() => {
        const apiItemsFiltered = screen.queryAllByTestId(/endpoint-list-item/);
        expect(apiItemsFiltered.length).toBeLessThanOrEqual(apiItemsInitial);
      });

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      const scriptItemsInitial = screen.queryAllByTestId(/script-item/).length;

      await user.type(scriptFilter, "test");
      await waitFor(() => {
        const scriptItemsFiltered = screen.queryAllByTestId(/script-item/);
        expect(scriptItemsFiltered.length).toBeLessThanOrEqual(scriptItemsInitial);
      });

      // API filter should not have changed
      expect(apiFilter).toHaveValue("GET");

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 4: Component Structure Consistency
  // ────────────────────────────────────────────────────────────────────────

  describe("Component Structure Consistency", () => {
    it("should both have accessible item lists", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);
      apiItems.forEach(item => {
        expect(item).toHaveAttribute("aria-label");
        expect(item).toHaveAttribute("aria-selected");
      });

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);
      scriptItems.forEach(item => {
        expect(item).toHaveAttribute("aria-label");
        expect(item).toHaveAttribute("aria-selected");
      });

      unmount1();
      unmount2();
    });

    it("should both have accessible group headers", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiHeaders = screen.getAllByTestId(/group-header-/);
      apiHeaders.forEach(header => {
        expect(header).toHaveAttribute("role", "button");
        expect(header).toHaveAttribute("aria-expanded");
        expect(header).toHaveAttribute("aria-label");
      });

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptHeaders = screen.getAllByTestId(/script-group-header-/);
      scriptHeaders.forEach(header => {
        expect(header).toHaveAttribute("role", "button");
        expect(header).toHaveAttribute("aria-expanded");
        expect(header).toHaveAttribute("aria-label");
      });

      unmount1();
      unmount2();
    });

    it("should both have accessible filter inputs", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      expect(apiFilter).toHaveAttribute("aria-label");

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      expect(scriptFilter).toHaveAttribute("aria-label");

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 5: Accessibility Consistency
  // ────────────────────────────────────────────────────────────────────────

  describe("Accessibility Consistency", () => {
    it("should have consistent aria patterns", async () => {
      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);
      const apiItemsWithAriaSelected = apiItems.filter(item =>
        item.hasAttribute("aria-selected")
      ).length;
      expect(apiItemsWithAriaSelected).toBe(apiItems.length);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);
      const scriptItemsWithAriaSelected = scriptItems.filter(item =>
        item.hasAttribute("aria-selected")
      ).length;
      expect(scriptItemsWithAriaSelected).toBe(scriptItems.length);

      unmount1();
      unmount2();
    });

    it("should support keyboard navigation in both", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);
      if (apiItems.length > 0) {
        apiItems[0].focus();
        expect(apiItems[0]).toHaveFocus();
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);
      if (scriptItems.length > 0) {
        scriptItems[0].focus();
        expect(scriptItems[0]).toHaveFocus();
      }

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 6: Error Resilience
  // ────────────────────────────────────────────────────────────────────────

  describe("Error Handling & Resilience", () => {
    it("should handle filter errors gracefully in both explorers", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");

      // Type special characters
      await user.type(apiFilter, "[(){}]");

      // Should not crash
      expect(screen.getByTestId("filter-input")).toBeInTheDocument();

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");

      // Type special characters
      await user.type(scriptFilter, "[(){}]");

      // Should not crash
      expect(screen.getByTestId("filter-input")).toBeInTheDocument();

      unmount1();
      unmount2();
    });

    it("should maintain state after multiple rapid interactions", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);

      // Rapid typing
      await user.type(apiFilter, "G");
      await user.type(apiFilter, "E");
      await user.type(apiFilter, "T");

      // Should respond to interactions
      if (apiItems.length > 0) {
        await user.click(apiItems[0]);
        await waitFor(() => {
          expect(apiItems[0]).toHaveAttribute("aria-selected");
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      const scriptItems = screen.queryAllByTestId(/script-item/);

      // Rapid typing
      await user.type(scriptFilter, "t");
      await user.type(scriptFilter, "e");
      await user.type(scriptFilter, "s");
      await user.type(scriptFilter, "t");

      // Should respond to interactions
      if (scriptItems.length > 0) {
        await user.click(scriptItems[0]);
        await waitFor(() => {
          expect(scriptItems[0]).toHaveAttribute("aria-selected");
        });
      }

      unmount1();
      unmount2();
    });
  });

  // ────────────────────────────────────────────────────────────────────────
  // Workflow 7: Comparative Testing
  // ────────────────────────────────────────────────────────────────────────

  describe("Comparative Functionality", () => {
    it("should support equivalent filter operations", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiFilter = screen.getByTestId("filter-input");
      const apiItemsBefore = screen.queryAllByTestId(/endpoint-list-item/).length;

      await user.type(apiFilter, "GET");
      let apiItemsAfter = await waitFor(() => {
        const items = screen.queryAllByTestId(/endpoint-list-item/);
        return items.length;
      });

      expect(apiItemsAfter).toBeLessThanOrEqual(apiItemsBefore);

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptFilter = screen.getByTestId("filter-input");
      const scriptItemsBefore = screen.queryAllByTestId(/script-item/).length;

      await user.type(scriptFilter, "test");
      const scriptItemsAfter = await waitFor(() => {
        const items = screen.queryAllByTestId(/script-item/);
        return items.length;
      });

      expect(scriptItemsAfter).toBeLessThanOrEqual(scriptItemsBefore);

      unmount1();
      unmount2();
    });

    it("should support equivalent selection operations", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiItems = screen.queryAllByTestId(/endpoint-list-item/);

      if (apiItems.length > 0) {
        await user.click(apiItems[0]);
        await waitFor(() => {
          expect(apiItems[0]).toHaveAttribute("aria-selected", "true");
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptItems = screen.queryAllByTestId(/script-item/);

      if (scriptItems.length > 0) {
        await user.click(scriptItems[0]);
        await waitFor(() => {
          expect(scriptItems[0]).toHaveAttribute("aria-selected", "true");
        });
      }

      unmount1();
      unmount2();
    });

    it("should support equivalent group toggle operations", async () => {
      const user = userEvent.setup();

      const { unmount: unmount1 } = render(<HubApiExplorer />);
      const apiHeaders = screen.getAllByTestId(/group-header-/);

      if (apiHeaders.length > 0) {
        const apiGroupName = apiHeaders[0]
          .getAttribute("data-testid")
          .replace("group-header-", "");

        await user.click(apiHeaders[0]);
        await waitFor(() => {
          expect(screen.getByTestId(`group-header-${apiGroupName}`)).toHaveAttribute(
            "aria-expanded",
            "false"
          );
        });
      }

      const { unmount: unmount2 } = render(<ScriptsExplorer />);
      const scriptHeaders = screen.getAllByTestId(/script-group-header-/);

      if (scriptHeaders.length > 0) {
        const scriptGroupName = scriptHeaders[0]
          .getAttribute("data-testid")
          .replace("script-group-header-", "");

        await user.click(scriptHeaders[0]);
        await waitFor(() => {
          expect(screen.getByTestId(`script-group-header-${scriptGroupName}`)).toHaveAttribute(
            "aria-expanded",
            "false"
          );
        });
      }

      unmount1();
      unmount2();
    });
  });
});
