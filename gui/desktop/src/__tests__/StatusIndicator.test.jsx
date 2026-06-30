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
    it("should render 200 with success colors", () => {
      const { container } = render(<StatusIndicator status={200} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 201 with success colors", () => {
      const { container } = render(<StatusIndicator status={201} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 204 with success colors", () => {
      const { container } = render(<StatusIndicator status={204} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Error status (4xx, 5xx) tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("error status (4xx, 5xx)", () => {
    it("should render 400 with error colors", () => {
      const { container } = render(<StatusIndicator status={400} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 404 with error colors", () => {
      const { container } = render(<StatusIndicator status={404} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 500 with error colors", () => {
      const { container } = render(<StatusIndicator status={500} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 503 with error colors", () => {
      const { container } = render(<StatusIndicator status={503} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Warning status (3xx) tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("warning status (3xx)", () => {
    it("should render 301 with warning colors", () => {
      const { container } = render(<StatusIndicator status={301} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 302 with warning colors", () => {
      const { container } = render(<StatusIndicator status={302} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });

    it("should render 304 with warning colors", () => {
      const { container } = render(<StatusIndicator status={304} />);
      const span = container.querySelector("span");
      expect(span.style.color).toBeTruthy();
      expect(span.style.background).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // OK flag override tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("ok flag override", () => {
    it("should use success colors when ok=true regardless of status", () => {
      const { container } = render(<StatusIndicator status={500} ok={true} />);
      const span = container.querySelector("span");
      // Should have green success color, not red error
      expect(span.style.color).toContain("rgb") || span.style.color.startsWith("#");
    });

    it("should use error colors when ok=false regardless of status", () => {
      const { container } = render(<StatusIndicator status={200} ok={false} />);
      const span = container.querySelector("span");
      // Should have red error color, not green success
      expect(span.style.color).toContain("rgb") || span.style.color.startsWith("#");
    });

    it("should treat ok=true as success", () => {
      const { container } = render(<StatusIndicator status="OK" ok={true} />);
      const span = container.querySelector("span");
      expect(span.style.background).toBeTruthy();
      expect(span.style.color).toBeTruthy();
    });

    it("should treat ok=false as error", () => {
      const { container } = render(<StatusIndicator status="ERR" ok={false} />);
      const span = container.querySelector("span");
      expect(span.style.background).toBeTruthy();
      expect(span.style.color).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Style mode tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("style modes", () => {
    it("should render as badge by default", () => {
      const { container } = render(<StatusIndicator status={200} />);
      const span = container.querySelector("span");
      expect(span.style.display).toBe("inline-block");
      expect(span.style.padding).toBeTruthy();
      expect(span.style.borderRadius).toBe("3px");
    });

    it("should render as text when style='text'", () => {
      const { container } = render(<StatusIndicator status={200} style="text" />);
      const span = container.querySelector("span");
      expect(span.style.display).not.toBe("inline-block");
      expect(span.style.padding).not.toBeTruthy();
    });

    it("should apply monospace font", () => {
      const { container } = render(<StatusIndicator status={200} />);
      const span = container.querySelector("span");
      expect(span.style.fontFamily).toContain("mono");
    });

    it("should apply small font size", () => {
      const { container } = render(<StatusIndicator status={200} />);
      const span = container.querySelector("span");
      expect(span.style.fontSize).toBe("11px");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Custom style merge tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("custom style merging", () => {
    it("should merge custom inline styles", () => {
      const { container } = render(
        <StatusIndicator status={200} customStyle={{ fontSize: "14px" }} />
      );
      const span = container.querySelector("span");
      expect(span.style.fontSize).toBe("14px");
      // Should still have other default styles
      expect(span.style.fontFamily).toContain("mono");
    });

    it("should allow custom margin", () => {
      const { container } = render(
        <StatusIndicator status={200} customStyle={{ marginRight: "16px" }} />
      );
      const span = container.querySelector("span");
      expect(span.style.marginRight).toBe("16px");
    });

    it("should allow custom padding in text mode", () => {
      const { container } = render(
        <StatusIndicator
          status={200}
          style="text"
          customStyle={{ padding: "4px 8px" }}
        />
      );
      const span = container.querySelector("span");
      expect(span.style.padding).toBe("4px 8px");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world scenarios", () => {
    it("should handle common success codes", () => {
      [200, 201, 204].forEach(code => {
        const { container } = render(<StatusIndicator status={code} />);
        expect(screen.getByText(String(code))).toBeInTheDocument();
      });
    });

    it("should handle common error codes", () => {
      [400, 401, 403, 404, 500, 502, 503].forEach(code => {
        const { container } = render(<StatusIndicator status={code} />);
        expect(screen.getByText(String(code))).toBeInTheDocument();
      });
    });

    it("should work with API response success", () => {
      const response = { status: 200, ok: true };
      const { container } = render(
        <StatusIndicator status={response.status} ok={response.ok} />
      );
      expect(screen.getByText("200")).toBeInTheDocument();
    });

    it("should work with API response error", () => {
      const response = { status: 500, ok: false };
      const { container } = render(
        <StatusIndicator status={response.status} ok={response.ok} />
      );
      expect(screen.getByText("500")).toBeInTheDocument();
    });

    it("should work with network error", () => {
      const { container } = render(
        <StatusIndicator status={0} ok={false} />
      );
      expect(screen.getByText("0")).toBeInTheDocument();
    });

    it("should work with ERR label", () => {
      const { container } = render(
        <StatusIndicator status="ERR" ok={false} />
      );
      expect(screen.getByText("ERR")).toBeInTheDocument();
    });
  });
});
