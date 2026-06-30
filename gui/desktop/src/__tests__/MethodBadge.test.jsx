import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import MethodBadge from "../components/MethodBadge";

describe("MethodBadge Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without crashing", () => {
      render(<MethodBadge method="GET" />);
      expect(screen.getByText("GET")).toBeInTheDocument();
    });

    it("should display the method text", () => {
      render(<MethodBadge method="POST" />);
      expect(screen.getByText("POST")).toBeInTheDocument();
    });

    it("should render all standard HTTP methods", () => {
      const methods = ["GET", "POST", "PUT", "DELETE", "PATCH"];
      methods.forEach(method => {
        const { unmount } = render(<MethodBadge method={method} />);
        expect(screen.getByText(method)).toBeInTheDocument();
        unmount();
      });
    });

    it("should have correct test id", () => {
      render(<MethodBadge method="GET" />);
      expect(screen.getByTestId("method-badge-GET")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Styling tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("styling", () => {
    it("should have monospace font", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.fontFamily).toBe("var(--mono)");
    });

    it("should have correct font size", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.fontSize).toBe("10px");
    });

    it("should be bold", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.fontWeight).toBe("700");
    });

    it("should have rounded corners", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.borderRadius).toBe("3px");
    });

    it("should be displayed as inline-block", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.display).toBe("inline-block");
    });

    it("should have minimum width for alignment", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.minWidth).toBe("44px");
    });

    it("should center text", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.textAlign).toBe("center");
    });

    it("should have padding", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.padding).toBe("2px 6px");
    });

    it("should prevent text selection", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.style.userSelect).toBe("none");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Method type tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("method types", () => {
    it("should render GET", () => {
      render(<MethodBadge method="GET" />);
      expect(screen.getByText("GET")).toBeInTheDocument();
    });

    it("should render POST", () => {
      render(<MethodBadge method="POST" />);
      expect(screen.getByText("POST")).toBeInTheDocument();
    });

    it("should render PUT", () => {
      render(<MethodBadge method="PUT" />);
      expect(screen.getByText("PUT")).toBeInTheDocument();
    });

    it("should render DELETE", () => {
      render(<MethodBadge method="DELETE" />);
      expect(screen.getByText("DELETE")).toBeInTheDocument();
    });

    it("should render PATCH", () => {
      render(<MethodBadge method="PATCH" />);
      expect(screen.getByText("PATCH")).toBeInTheDocument();
    });

    it("should render custom methods", () => {
      render(<MethodBadge method="CUSTOM" />);
      expect(screen.getByText("CUSTOM")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Custom style merge tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("custom style merging", () => {
    it("should merge custom inline styles", () => {
      const { container } = render(
        <MethodBadge method="GET" style={{ fontSize: "12px" }} />
      );
      const span = container.querySelector("span");
      expect(span.style.fontSize).toBe("12px");
      // Should still have other default styles
      expect(span.style.fontWeight).toBe("700");
      expect(span.style.color).toBeTruthy();
    });

    it("should allow overriding padding", () => {
      const { container } = render(
        <MethodBadge method="GET" style={{ padding: "4px 8px" }} />
      );
      const span = container.querySelector("span");
      expect(span.style.padding).toBe("4px 8px");
    });

    it("should allow adding custom margin", () => {
      const { container } = render(
        <MethodBadge method="GET" style={{ marginRight: "8px" }} />
      );
      const span = container.querySelector("span");
      expect(span.style.marginRight).toBe("8px");
    });
  });
});
