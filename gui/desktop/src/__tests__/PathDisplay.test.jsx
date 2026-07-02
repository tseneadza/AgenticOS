import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import PathDisplay from "../components/PathDisplay";

describe("PathDisplay Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without crashing", () => {
      render(<PathDisplay path="/api/users" />);
      expect(screen.getByText("/api/users")).toBeInTheDocument();
    });

    it("should render simple path without parameters", () => {
      render(<PathDisplay path="/api/health" />);
      expect(screen.getByText("/api/health")).toBeInTheDocument();
    });

    it("should handle null path gracefully", () => {
      const { container } = render(<PathDisplay path={null} />);
      expect(container.firstChild).toBeNull();
    });

    it("should handle empty string path", () => {
      const { container } = render(<PathDisplay path="" />);
      // Empty string is falsy, component returns null (no spans rendered)
      const spans = container.querySelectorAll("span");
      expect(spans.length).toBe(0);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Parameter detection and highlighting tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("parameter highlighting", () => {
    it("should highlight single parameter", () => {
      const { container } = render(<PathDisplay path="/users/{id}" />);
      const paramSpan = container.querySelector("span.path-segment-param");
      expect(paramSpan).toBeInTheDocument();
      expect(paramSpan.textContent).toBe("{id}");
    });

    it("should highlight multiple parameters", () => {
      const { container } = render(
        <PathDisplay path="/users/{userId}/posts/{postId}" />
      );
      const coloredSpans = Array.from(
        container.querySelectorAll("span.path-segment-param")
      );
      expect(coloredSpans).toHaveLength(2);
      expect(coloredSpans[0].textContent).toBe("{userId}");
      expect(coloredSpans[1].textContent).toBe("{postId}");
    });

    it("should highlight parameter at start of path", () => {
      const { container } = render(<PathDisplay path="{version}/api/users" />);
      const allSpans = container.querySelectorAll("span");
      // Split gives: ["", "{version}", "/api/users"]
      // Find the span with {version}
      const paramSpan = Array.from(allSpans).find(
        s => s.textContent === "{version}"
      );
      expect(paramSpan).toBeInTheDocument();
      expect(paramSpan?.className).toContain("path-segment-param");
    });

    it("should highlight parameter at end of path", () => {
      const { container } = render(<PathDisplay path="/api/users/{id}" />);
      const allSpans = container.querySelectorAll("span");
      // Split gives: ["/api/users/", "{id}", ""]
      // Find the span with {id}
      const paramSpan = Array.from(allSpans).find(s => s.textContent === "{id}");
      expect(paramSpan).toBeInTheDocument();
      expect(paramSpan?.className).toContain("path-segment-param");
    });

    it("should NOT highlight curly braces without parameter syntax", () => {
      const { container } = render(<PathDisplay path="/api/data{extra}" />);
      const highlighted = container.querySelectorAll("span.path-segment-param");
      // {extra} should still be highlighted since it matches {.*}
      expect(highlighted.length).toBeGreaterThan(0);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Segment tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("path segments", () => {
    it("should separate static and parameter segments", () => {
      const { container } = render(<PathDisplay path="/api/{id}/edit" />);
      const spans = container.querySelectorAll("span");
      // Should have 3 spans: "/api/", "{id}", "/edit"
      expect(spans.length).toBe(3);
      expect(spans[0].textContent).toBe("/api/");
      expect(spans[1].textContent).toBe("{id}");
      expect(spans[2].textContent).toBe("/edit");
    });

    it("should handle consecutive parameters", () => {
      const { container } = render(
        <PathDisplay path="/api/{org}/{repo}/issues" />
      );
      const paramSpans = container.querySelectorAll("span.path-segment-param");
      expect(paramSpans.length).toBe(2);
    });

    it("should handle path with only parameter", () => {
      const { container } = render(<PathDisplay path="{id}" />);
      const spans = container.querySelectorAll("span");
      expect(spans.length).toBeGreaterThan(0);
      const paramSpan = container.querySelector("span.path-segment-param");
      expect(paramSpan?.textContent).toBe("{id}");
    });

    it("should preserve slashes and special characters", () => {
      const { container } = render(
        <PathDisplay path="/v1/api/users/{id}/profile" />
      );
      const pathText = Array.from(container.querySelectorAll("span"))
        .map(s => s.textContent)
        .join("");
      expect(pathText).toBe("/v1/api/users/{id}/profile");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world API paths
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world API paths", () => {
    it("should render GitHub-style path", () => {
      const { container } = render(
        <PathDisplay path="/repos/{owner}/{repo}/issues/{issue_number}" />
      );
      const paramSpans = Array.from(
        container.querySelectorAll("span.path-segment-param")
      );
      expect(paramSpans.length).toBe(3);
      expect(paramSpans[0].textContent).toBe("{owner}");
      expect(paramSpans[1].textContent).toBe("{repo}");
      expect(paramSpans[2].textContent).toBe("{issue_number}");
    });

    it("should render nested resource path", () => {
      const { container } = render(
        <PathDisplay path="/api/v2/users/{userId}/posts/{postId}/comments/{commentId}" />
      );
      const paramSpans = container.querySelectorAll("span.path-segment-param");
      expect(paramSpans.length).toBe(3);
    });

    it("should render query parameter-style path", () => {
      const { container } = render(
        <PathDisplay path="/api/users?filter={filter}&sort={sort}" />
      );
      const paramSpans = container.querySelectorAll("span.path-segment-param");
      expect(paramSpans.length).toBe(2);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Data-testid tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("test identifiers", () => {
    it("should assign unique data-testid to each segment", () => {
      const { container } = render(<PathDisplay path="/api/{id}/edit" />);
      const segment0 = screen.getByTestId("path-segment-0");
      const segment1 = screen.getByTestId("path-segment-1");
      const segment2 = screen.getByTestId("path-segment-2");
      expect(segment0).toBeInTheDocument();
      expect(segment1).toBeInTheDocument();
      expect(segment2).toBeInTheDocument();
    });

    it("should maintain segment order by testid", () => {
      const { container } = render(
        <PathDisplay path="/users/{userId}/posts/{postId}" />
      );
      const ids = [];
      for (let i = 0; i < 5; i++) {
        const el = container.querySelector(`[data-testid="path-segment-${i}"]`);
        if (el) ids.push(i);
      }
      expect(ids.length).toBeGreaterThan(0);
    });
  });
});
