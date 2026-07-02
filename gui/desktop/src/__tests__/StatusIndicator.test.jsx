import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusIndicator from "../components/StatusIndicator";

describe("StatusIndicator Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without crashing", () => {
      render(<StatusIndicator status={200} />);
      expect(screen.getByText("200")).toBeInTheDocument();
    });

    it("should display status code as text", () => {
      render(<StatusIndicator status={404} />);
      expect(screen.getByText("404")).toBeInTheDocument();
    });

    it("should handle string status", () => {
      render(<StatusIndicator status="ERR" />);
      expect(screen.getByText("ERR")).toBeInTheDocument();
    });

    it("should handle null status gracefully", () => {
      const { container } = render(<StatusIndicator status={null} />);
      expect(container.firstChild).toBeNull();
    });

    it("should have correct test id", () => {
      render(<StatusIndicator status={200} />);
      expect(screen.getByTestId("status-indicator-200")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Success status (2xx) tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("success status (2xx)", () => {
    it("should render 200 with success category class", () => {
      render(<StatusIndicator status={200} />);
      const span = screen.getByTestId("status-indicator-200");
      expect(span.className).toContain("status-badge-success");
    });

    it("should render 201 with success category class", () => {
      render(<StatusIndicator status={201} />);
      const span = screen.getByTestId("status-indicator-201");
      expect(span.className).toContain("status-badge-success");
    });

    it("should render 204 with success category class", () => {
      render(<StatusIndicator status={204} />);
      const span = screen.getByTestId("status-indicator-204");
      expect(span.className).toContain("status-badge-success");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Error status (4xx, 5xx) tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("error status (4xx, 5xx)", () => {
    it("should render 400 with error category class", () => {
      render(<StatusIndicator status={400} />);
      const span = screen.getByTestId("status-indicator-400");
      expect(span.className).toContain("status-badge-error");
    });

    it("should render 404 with error category class", () => {
      render(<StatusIndicator status={404} />);
      const span = screen.getByTestId("status-indicator-404");
      expect(span.className).toContain("status-badge-error");
    });

    it("should render 500 with error category class", () => {
      render(<StatusIndicator status={500} />);
      const span = screen.getByTestId("status-indicator-500");
      expect(span.className).toContain("status-badge-error");
    });

    it("should render 503 with error category class", () => {
      render(<StatusIndicator status={503} />);
      const span = screen.getByTestId("status-indicator-503");
      expect(span.className).toContain("status-badge-error");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Warning status (3xx) tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("warning status (3xx)", () => {
    it("should render 301 with warning category class", () => {
      render(<StatusIndicator status={301} />);
      const span = screen.getByTestId("status-indicator-301");
      expect(span.className).toContain("status-badge-warning");
    });

    it("should render 302 with warning category class", () => {
      render(<StatusIndicator status={302} />);
      const span = screen.getByTestId("status-indicator-302");
      expect(span.className).toContain("status-badge-warning");
    });

    it("should render 304 with warning category class", () => {
      render(<StatusIndicator status={304} />);
      const span = screen.getByTestId("status-indicator-304");
      expect(span.className).toContain("status-badge-warning");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // OK flag override tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("ok flag override", () => {
    it("should use success class when ok=true regardless of status", () => {
      render(<StatusIndicator status={500} ok={true} />);
      const span = screen.getByTestId("status-indicator-500");
      expect(span.className).toContain("status-badge-success");
      expect(span.className).not.toContain("status-badge-error");
    });

    it("should use error class when ok=false regardless of status", () => {
      render(<StatusIndicator status={200} ok={false} />);
      const span = screen.getByTestId("status-indicator-200");
      expect(span.className).toContain("status-badge-error");
      expect(span.className).not.toContain("status-badge-success");
    });

    it("should treat ok=true as success", () => {
      render(<StatusIndicator status="OK" ok={true} />);
      const span = screen.getByTestId("status-indicator-OK");
      expect(span.className).toContain("status-badge-success");
    });

    it("should treat ok=false as error", () => {
      render(<StatusIndicator status="ERR" ok={false} />);
      const span = screen.getByTestId("status-indicator-ERR");
      expect(span.className).toContain("status-badge-error");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Style mode tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("style modes", () => {
    it("should render as badge by default", () => {
      render(<StatusIndicator status={200} />);
      const span = screen.getByTestId("status-indicator-200");
      expect(span.className).toContain("status-badge");
      expect(span.className).not.toContain("status-text");
    });

    it("should render as text when style='text'", () => {
      render(<StatusIndicator status={200} style="text" />);
      const span = screen.getByTestId("status-indicator-200");
      expect(span.className).toContain("status-text");
      expect(span.className).not.toContain("status-badge");
    });

    it("should apply text category class in text mode", () => {
      render(<StatusIndicator status={200} style="text" />);
      const span = screen.getByTestId("status-indicator-200");
      expect(span.className).toContain("status-text-success");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Custom style merge tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("custom style merging", () => {
    it("should merge custom inline styles", () => {
      render(
        <StatusIndicator status={200} customStyle={{ fontSize: "14px" }} />
      );
      const span = screen.getByTestId("status-indicator-200");
      expect(span.style.fontSize).toBe("14px");
      // Should still carry the semantic badge class
      expect(span.className).toContain("status-badge-success");
    });

    it("should allow custom margin", () => {
      render(
        <StatusIndicator status={200} customStyle={{ marginRight: "16px" }} />
      );
      const span = screen.getByTestId("status-indicator-200");
      expect(span.style.marginRight).toBe("16px");
    });

    it("should allow custom padding in text mode", () => {
      render(
        <StatusIndicator
          status={200}
          style="text"
          customStyle={{ padding: "4px 8px" }}
        />
      );
      const span = screen.getByTestId("status-indicator-200");
      expect(span.style.padding).toBe("4px 8px");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world scenarios", () => {
    it("should handle common success codes", () => {
      [200, 201, 204].forEach(code => {
        const { unmount } = render(<StatusIndicator status={code} />);
        expect(screen.getByText(String(code))).toBeInTheDocument();
        unmount();
      });
    });

    it("should handle common error codes", () => {
      [400, 401, 403, 404, 500, 502, 503].forEach(code => {
        const { unmount } = render(<StatusIndicator status={code} />);
        expect(screen.getByText(String(code))).toBeInTheDocument();
        unmount();
      });
    });

    it("should work with API response success", () => {
      const response = { status: 200, ok: true };
      render(
        <StatusIndicator status={response.status} ok={response.ok} />
      );
      expect(screen.getByText("200")).toBeInTheDocument();
    });

    it("should work with API response error", () => {
      const response = { status: 500, ok: false };
      render(
        <StatusIndicator status={response.status} ok={response.ok} />
      );
      expect(screen.getByText("500")).toBeInTheDocument();
    });

    it("should work with network error", () => {
      render(
        <StatusIndicator status={0} ok={false} />
      );
      expect(screen.getByText("0")).toBeInTheDocument();
    });

    it("should work with ERR label", () => {
      render(
        <StatusIndicator status="ERR" ok={false} />
      );
      expect(screen.getByText("ERR")).toBeInTheDocument();
    });
  });
});
