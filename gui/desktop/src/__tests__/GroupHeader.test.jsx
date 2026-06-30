import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import GroupHeader from "../components/GroupHeader";

describe("GroupHeader Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without crashing", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      expect(screen.getByText("Cards")).toBeInTheDocument();
    });

    it("should display group name", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Scripts" isOpen={true} onToggle={onToggle} />);
      expect(screen.getByText("Scripts")).toBeInTheDocument();
    });

    it("should render chevron icon", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      expect(screen.getByTestId("group-chevron-Cards")).toBeInTheDocument();
      expect(screen.getByTestId("group-chevron-Cards")).toHaveTextContent("▶");
    });

    it("should handle null name gracefully", () => {
      const onToggle = vi.fn();
      const { container } = render(
        <GroupHeader name={null} isOpen={true} onToggle={onToggle} />
      );
      expect(container.firstChild).toBeNull();
    });

    it("should have correct test ids", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Analytics" isOpen={false} onToggle={onToggle} />);
      expect(screen.getByTestId("group-header-Analytics")).toBeInTheDocument();
      expect(screen.getByTestId("group-name-Analytics")).toBeInTheDocument();
      expect(screen.getByTestId("group-chevron-Analytics")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Open/Closed state tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("open/closed state", () => {
    it("should show chevron rotated 90deg when open", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      const chevron = screen.getByTestId("group-chevron-Cards");
      expect(chevron.style.transform).toContain("rotate(90deg)");
    });

    it("should show chevron not rotated when closed", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={false} onToggle={onToggle} />);
      const chevron = screen.getByTestId("group-chevron-Cards");
      expect(chevron.style.transform).toContain("rotate(0deg)");
    });

    it("should have aria-expanded=true when open", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      expect(screen.getByTestId("group-header-Cards")).toHaveAttribute(
        "aria-expanded",
        "true"
      );
    });

    it("should have aria-expanded=false when closed", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={false} onToggle={onToggle} />);
      expect(screen.getByTestId("group-header-Cards")).toHaveAttribute(
        "aria-expanded",
        "false"
      );
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Toggle functionality tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("toggle functionality", () => {
    it("should call onToggle when clicked", async () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);

      const header = screen.getByTestId("group-header-Cards");
      await userEvent.click(header);

      expect(onToggle).toHaveBeenCalledOnce();
    });

    it("should call onToggle on Enter key press", async () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);

      const header = screen.getByTestId("group-header-Cards");
      header.focus();
      await userEvent.keyboard("{Enter}");

      expect(onToggle).toHaveBeenCalledOnce();
    });

    it("should call onToggle on Space key press", async () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);

      const header = screen.getByTestId("group-header-Cards");
      header.focus();
      await userEvent.keyboard(" ");

      expect(onToggle).toHaveBeenCalledOnce();
    });

    it("should not call onToggle for other keys", async () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);

      const header = screen.getByTestId("group-header-Cards");
      header.focus();
      await userEvent.keyboard("{ArrowDown}");

      expect(onToggle).not.toHaveBeenCalled();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Item count tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("item count", () => {
    it("should not display count when itemCount is 0", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} itemCount={0} />
      );
      expect(screen.queryByTestId("group-count-Cards")).not.toBeInTheDocument();
    });

    it("should display count when itemCount > 0", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} itemCount={5} />
      );
      expect(screen.getByTestId("group-count-Cards")).toBeInTheDocument();
      expect(screen.getByTestId("group-count-Cards")).toHaveTextContent("(5)");
    });

    it("should display large item count", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader
          name="Scripts"
          isOpen={true}
          onToggle={onToggle}
          itemCount={42}
        />
      );
      expect(screen.getByTestId("group-count-Scripts")).toHaveTextContent("(42)");
    });

    it("should format item count correctly", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader
          name="Analytics"
          isOpen={false}
          onToggle={onToggle}
          itemCount={1}
        />
      );
      expect(screen.getByTestId("group-count-Analytics")).toHaveTextContent("(1)");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Accessibility tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("accessibility", () => {
    it("should be keyboard focusable", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      const header = screen.getByTestId("group-header-Cards");
      expect(header).toHaveAttribute("tabIndex", "0");
    });

    it("should have descriptive aria-label", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      const header = screen.getByTestId("group-header-Cards");
      expect(header.getAttribute("aria-label")).toContain("Cards");
      expect(header.getAttribute("aria-label")).toContain("expanded");
    });

    it("should have aria-label indicating closed state", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={false} onToggle={onToggle} />);
      const header = screen.getByTestId("group-header-Cards");
      expect(header.getAttribute("aria-label")).toContain("collapsed");
    });

    it("should have role=button", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      expect(screen.getByTestId("group-header-Cards")).toHaveAttribute(
        "role",
        "button"
      );
    });

    it("should hide chevron from screen readers", () => {
      const onToggle = vi.fn();
      render(<GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />);
      const chevron = screen.getByTestId("group-chevron-Cards");
      expect(chevron).toHaveAttribute("aria-hidden", "true");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Styling tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("styling", () => {
    it("should have uppercase text", () => {
      const onToggle = vi.fn();
      const { container } = render(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />
      );
      const header = container.querySelector('[data-testid="group-header-Cards"]');
      expect(header.style.textTransform).toBe("uppercase");
    });

    it("should have pointer cursor", () => {
      const onToggle = vi.fn();
      const { container } = render(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />
      );
      const header = container.querySelector('[data-testid="group-header-Cards"]');
      expect(header.style.cursor).toBe("pointer");
    });

    it("should have smooth chevron transition", () => {
      const onToggle = vi.fn();
      const { container } = render(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />
      );
      const chevron = container.querySelector('[data-testid="group-chevron-Cards"]');
      expect(chevron.style.transition).toContain("transform");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world scenarios", () => {
    it("should handle group names with spaces", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader
          name="Logs & Env"
          isOpen={true}
          onToggle={onToggle}
          itemCount={5}
        />
      );
      expect(screen.getByText("Logs & Env")).toBeInTheDocument();
    });

    it("should handle group names with parentheses", () => {
      const onToggle = vi.fn();
      render(
        <GroupHeader
          name="News (Sidecar)"
          isOpen={false}
          onToggle={onToggle}
          itemCount={8}
        />
      );
      expect(screen.getByText("News (Sidecar)")).toBeInTheDocument();
    });

    it("should work as collapsible section header", () => {
      const onToggle = vi.fn();
      const { rerender } = render(
        <GroupHeader name="Cards" isOpen={false} onToggle={onToggle} />
      );

      // Initially closed
      expect(
        screen.getByTestId("group-header-Cards").getAttribute("aria-expanded")
      ).toBe("false");

      // After toggle (simulated)
      rerender(
        <GroupHeader name="Cards" isOpen={true} onToggle={onToggle} />
      );

      expect(
        screen.getByTestId("group-header-Cards").getAttribute("aria-expanded")
      ).toBe("true");
    });

    it("should show all groups in API explorer", () => {
      const onToggle = vi.fn();
      const groups = ["Cards", "Scripts", "Analytics", "Discovery", "System"];

      groups.forEach(group => {
        const { unmount } = render(
          <GroupHeader
            name={group}
            isOpen={true}
            onToggle={onToggle}
            itemCount={5}
          />
        );
        expect(screen.getByText(group)).toBeInTheDocument();
        unmount();
      });
    });
  });
});
