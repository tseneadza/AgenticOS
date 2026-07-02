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
    it("should carry the base method-badge class", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("method-badge");
    });

    it("should apply the GET method class", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("get");
    });

    it("should apply the POST method class", () => {
      const { container } = render(<MethodBadge method="POST" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("post");
    });

    it("should apply the PUT method class", () => {
      const { container } = render(<MethodBadge method="PUT" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("put");
    });

    it("should apply the DELETE method class", () => {
      const { container } = render(<MethodBadge method="DELETE" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("delete");
    });

    it("should apply the PATCH method class", () => {
      const { container } = render(<MethodBadge method="PATCH" />);
      const span = container.querySelector("span");
      expect(span.className).toContain("patch");
    });

    it("should lowercase the method for the class name", () => {
      const { container } = render(<MethodBadge method="GET" />);
      const span = container.querySelector("span");
      expect(span.className).toBe("method-badge get");
    });

    it("should default to the get class when method is missing", () => {
      const { container } = render(<MethodBadge method={undefined} />);
      const span = container.querySelector("span");
      expect(span.className).toContain("get");
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
      // Should still carry the semantic method classes
      expect(span.className).toContain("method-badge");
      expect(span.className).toContain("get");
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
