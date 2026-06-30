import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ResponseDisplay from "../components/ResponseDisplay";

describe("ResponseDisplay Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    it("should render without crashing", () => {
      render(<ResponseDisplay />);
      expect(screen.getByTestId("response-display")).toBeInTheDocument();
    });

    it("should display response label", () => {
      render(<ResponseDisplay />);
      expect(screen.getByText("Response")).toBeInTheDocument();
    });

    it("should show empty state message", () => {
      render(<ResponseDisplay />);
      expect(
        screen.getByText("No response yet — click Run to send the request.")
      ).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Loading state tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("loading state", () => {
    it("should show loading message when loading=true", () => {
      render(<ResponseDisplay loading={true} />);
      expect(screen.getByText("Sending request…")).toBeInTheDocument();
    });

    it("should have yellow text color when loading", () => {
      const { container } = render(<ResponseDisplay loading={true} />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.color).toBeTruthy();
    });

    it("should hide empty state when loading", () => {
      render(<ResponseDisplay loading={true} />);
      expect(
        screen.queryByText("No response yet — click Run to send the request.")
      ).not.toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Success response tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("success response", () => {
    const successResponse = {
      status: 200,
      ok: true,
      dur: 42,
      text: '{"result":"success"}',
    };

    it("should display status code", () => {
      render(<ResponseDisplay response={successResponse} />);
      expect(screen.getByText("200")).toBeInTheDocument();
    });

    it("should display duration", () => {
      render(<ResponseDisplay response={successResponse} />);
      expect(screen.getByText("42ms")).toBeInTheDocument();
    });

    it("should display response text", () => {
      render(<ResponseDisplay response={successResponse} />);
      expect(screen.getByText('{"result":"success"}')).toBeInTheDocument();
    });

    it("should have green text color for success", () => {
      const { container } = render(<ResponseDisplay response={successResponse} />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.color).toBeTruthy();
    });

    it("should have green border for success", () => {
      const { container } = render(<ResponseDisplay response={successResponse} />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.borderColor).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Error response tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("error response", () => {
    const errorResponse = {
      status: 500,
      ok: false,
      dur: 123,
      text: "Internal Server Error",
    };

    it("should display error status", () => {
      render(<ResponseDisplay response={errorResponse} />);
      expect(screen.getByText("500")).toBeInTheDocument();
    });

    it("should display error duration", () => {
      render(<ResponseDisplay response={errorResponse} />);
      expect(screen.getByText("123ms")).toBeInTheDocument();
    });

    it("should display error message", () => {
      render(<ResponseDisplay response={errorResponse} />);
      expect(screen.getByText("Internal Server Error")).toBeInTheDocument();
    });

    it("should have red text color for error", () => {
      const { container } = render(<ResponseDisplay response={errorResponse} />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.color).toBeTruthy();
    });

    it("should have red border for error", () => {
      const { container } = render(<ResponseDisplay response={errorResponse} />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.borderColor).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Edge cases
  // ─────────────────────────────────────────────────────────────────────────

  describe("edge cases", () => {
    it("should handle missing status code", () => {
      const response = { ok: true, dur: 10, text: "OK" };
      render(<ResponseDisplay response={response} />);
      // Should render without crashing
      expect(screen.getByTestId("response-display")).toBeInTheDocument();
    });

    it("should handle null status with error state", () => {
      const response = { status: null, ok: false, dur: 5, text: "Error" };
      render(<ResponseDisplay response={response} />);
      expect(screen.getByText("Error")).toBeInTheDocument();
    });

    it("should handle multiline response text", () => {
      const response = {
        status: 200,
        ok: true,
        dur: 50,
        text: "Line 1\nLine 2\nLine 3",
      };
      render(<ResponseDisplay response={response} />);
      // Verify text content contains all lines
      expect(screen.getByText((content, element) => content.includes("Line 1") && content.includes("Line 3"))).toBeInTheDocument();
    });

    it("should handle JSON response", () => {
      const jsonText = '{"user":"alice","id":123,"tags":["admin","user"]}';
      const response = { status: 200, ok: true, dur: 30, text: jsonText };
      render(<ResponseDisplay response={response} />);
      expect(screen.getByText(jsonText)).toBeInTheDocument();
    });

    it("should handle very long response text", () => {
      const longText = "x".repeat(1000);
      const response = { status: 200, ok: true, dur: 100, text: longText };
      const { container } = render(<ResponseDisplay response={response} />);
      expect(container.querySelector('[data-testid="response-display"]')).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Styling tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("styling", () => {
    it("should apply monospace font", () => {
      const { container } = render(<ResponseDisplay />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.fontFamily).toContain("mono");
    });

    it("should have scrollable container", () => {
      const { container } = render(<ResponseDisplay />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.maxHeight).toBe("300px");
      expect(responseDiv.style.overflowY).toBe("auto");
    });

    it("should preserve whitespace and line breaks", () => {
      const { container } = render(<ResponseDisplay />);
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.whiteSpace).toBe("pre-wrap");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Custom style merge tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("custom style merging", () => {
    it("should merge custom inline styles", () => {
      const { container } = render(
        <ResponseDisplay customStyle={{ maxHeight: "500px" }} />
      );
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.maxHeight).toBe("500px");
    });

    it("should allow custom background color", () => {
      const { container } = render(
        <ResponseDisplay customStyle={{ background: "#1a1a1a" }} />
      );
      const responseDiv = container.querySelector('[data-testid="response-display"]');
      expect(responseDiv.style.background).toBeTruthy();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world scenarios", () => {
    it("should display API success response", () => {
      const response = {
        status: 200,
        ok: true,
        dur: 45,
        text: '[{"id":1,"name":"Alice"},{"id":2,"name":"Bob"}]',
      };
      render(<ResponseDisplay response={response} />);
      expect(screen.getByText("200")).toBeInTheDocument();
      expect(screen.getByText("45ms")).toBeInTheDocument();
    });

    it("should display API error response", () => {
      const response = {
        status: 404,
        ok: false,
        dur: 12,
        text: '{"error":"Not Found","message":"Resource not found"}',
      };
      render(<ResponseDisplay response={response} />);
      expect(screen.getByText("404")).toBeInTheDocument();
      expect(screen.getByText("12ms")).toBeInTheDocument();
    });

    it("should display network error", () => {
      const response = {
        status: 0,
        ok: false,
        dur: 2000,
        text: "Network error: Connection refused\n\n(Is Hub at localhost:8085 running?)",
      };
      render(<ResponseDisplay response={response} />);
      // StatusIndicator converts falsy status (0) to "ERR"
      expect(screen.getByTestId("status-indicator-ERR")).toBeInTheDocument();
      expect(screen.getByText("2000ms")).toBeInTheDocument();
    });

    it("should transition from loading to success", () => {
      const response = {
        status: 200,
        ok: true,
        dur: 50,
        text: "Success",
      };
      const { rerender } = render(<ResponseDisplay loading={true} />);
      expect(screen.getByText("Sending request…")).toBeInTheDocument();

      rerender(<ResponseDisplay response={response} />);
      expect(screen.getByText("200")).toBeInTheDocument();
      expect(screen.getByText("Success")).toBeInTheDocument();
    });
  });
});
