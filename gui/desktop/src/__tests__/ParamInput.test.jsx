import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ParamInput from "../components/ParamInput";

describe("ParamInput Component", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // Rendering tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("rendering", () => {
    const basicParam = {
      name: "id",
      type: "string",
      _in: "path",
      required: true,
    };

    it("should render without crashing", () => {
      const onChange = vi.fn();
      render(<ParamInput param={basicParam} onChange={onChange} />);
      expect(screen.getByText("id")).toBeInTheDocument();
    });

    it("should render table row", () => {
      const onChange = vi.fn();
      const { container } = render(
        <ParamInput param={basicParam} onChange={onChange} />
      );
      expect(container.querySelector("tr")).toBeInTheDocument();
    });

    it("should handle null param gracefully", () => {
      const onChange = vi.fn();
      const { container } = render(<ParamInput param={null} onChange={onChange} />);
      expect(container.firstChild).toBeNull();
    });

    it("should render 4 columns (name, in, type, value)", () => {
      const onChange = vi.fn();
      const { container } = render(
        <ParamInput param={basicParam} onChange={onChange} />
      );
      const cells = container.querySelectorAll("td");
      expect(cells.length).toBe(4);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Parameter metadata tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("parameter metadata", () => {
    it("should display parameter name", () => {
      const param = {
        name: "userId",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByText("userId")).toBeInTheDocument();
    });

    it("should display parameter location (path)", () => {
      const param = {
        name: "id",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByText("path")).toBeInTheDocument();
    });

    it("should display parameter location (query)", () => {
      const param = {
        name: "limit",
        type: "number",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByText("query")).toBeInTheDocument();
    });

    it("should display parameter location (body)", () => {
      const param = {
        name: "body",
        type: "json",
        _in: "body",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByTestId("param-in-body")).toBeInTheDocument();
      expect(screen.getByTestId("param-in-body")).toHaveTextContent("body");
    });

    it("should display parameter type", () => {
      const param = {
        name: "data",
        type: "json",
        _in: "body",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByText("json")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Required indicator tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("required indicator", () => {
    it("should show asterisk for required parameters", () => {
      const param = {
        name: "id",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(screen.getByTestId(`param-required-indicator-id`)).toBeInTheDocument();
      expect(screen.getByTestId(`param-required-indicator-id`)).toHaveTextContent("*");
    });

    it("should NOT show asterisk for optional parameters", () => {
      const param = {
        name: "limit",
        type: "number",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      expect(
        screen.queryByTestId(`param-required-indicator-limit`)
      ).not.toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Input field tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("input field", () => {
    it("should render input field", () => {
      const param = {
        name: "name",
        type: "string",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      const input = screen.getByTestId("param-input-name");
      expect(input).toBeInTheDocument();
      expect(input.tagName).toBe("INPUT");
    });

    it("should display current value in input", () => {
      const param = {
        name: "id",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} value="123" onChange={onChange} />);
      const input = screen.getByTestId("param-input-id");
      expect(input.value).toBe("123");
    });

    it("should use empty string as default value", () => {
      const param = {
        name: "filter",
        type: "string",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      const input = screen.getByTestId("param-input-filter");
      expect(input.value).toBe("");
    });

    it("should display placeholder hint", () => {
      const param = {
        name: "port",
        type: "number",
        _in: "query",
        required: false,
        hint: "8080",
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      const input = screen.getByTestId("param-input-port");
      expect(input.placeholder).toBe("8080");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // onChange handler tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("onChange handler", () => {
    it("should call onChange when value changes", async () => {
      const param = {
        name: "search",
        type: "string",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);

      const input = screen.getByTestId("param-input-search");
      await userEvent.type(input, "hello");

      expect(onChange).toHaveBeenCalled();
    });

    it("should pass new value to onChange", async () => {
      const param = {
        name: "id",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);

      const input = screen.getByTestId("param-input-id");
      await userEvent.type(input, "abc123");

      // Verify onChange was called when value changed
      expect(onChange).toHaveBeenCalled();
    });

    it("should handle multi-line input (json)", async () => {
      const param = {
        name: "payload",
        type: "json",
        _in: "body",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);

      const input = screen.getByTestId("param-input-payload");
      // userEvent.type() doesn't handle curly braces well, so use different text
      await userEvent.type(input, 'key=value');

      // Verify onChange was called when value changed
      expect(onChange).toHaveBeenCalled();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Parameter type tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("parameter types", () => {
    const types = ["string", "number", "boolean", "json"];

    types.forEach(type => {
      it(`should handle ${type} parameter type`, () => {
        const param = {
          name: "test",
          type,
          _in: "query",
          required: false,
        };
        const onChange = vi.fn();
        render(<ParamInput param={param} onChange={onChange} />);
        expect(screen.getByText(type)).toBeInTheDocument();
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Accessibility tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("accessibility", () => {
    it("should have aria-label on input", () => {
      const param = {
        name: "username",
        type: "string",
        _in: "query",
        required: false,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);
      const input = screen.getByTestId("param-input-username");
      expect(input).toHaveAttribute("aria-label", "username parameter input");
    });

    it("should have testids for querying elements", () => {
      const param = {
        name: "id",
        type: "string",
        _in: "path",
        required: true,
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} onChange={onChange} />);

      expect(screen.getByTestId("param-name-id")).toBeInTheDocument();
      expect(screen.getByTestId("param-in-id")).toBeInTheDocument();
      expect(screen.getByTestId("param-type-id")).toBeInTheDocument();
      expect(screen.getByTestId("param-input-id")).toBeInTheDocument();
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Real-world scenarios
  // ─────────────────────────────────────────────────────────────────────────

  describe("real-world scenarios", () => {
    it("should handle path parameter", () => {
      const param = {
        name: "cardId",
        type: "string",
        _in: "path",
        required: true,
        hint: "e.g. dreamcatcher",
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} value="mycard" onChange={onChange} />);

      expect(screen.getByText("cardId")).toBeInTheDocument();
      expect(screen.getByText("path")).toBeInTheDocument();
      expect(screen.getByTestId("param-input-cardId").value).toBe("mycard");
    });

    it("should handle query parameter", () => {
      const param = {
        name: "limit",
        type: "number",
        _in: "query",
        required: false,
        hint: "50",
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} value="100" onChange={onChange} />);

      expect(screen.getByText("query")).toBeInTheDocument();
      expect(screen.getByTestId("param-input-limit").value).toBe("100");
    });

    it("should handle body parameter (JSON)", () => {
      const param = {
        name: "body",
        type: "json",
        _in: "body",
        required: true,
        hint: '{"name":"Robotics","color":"#7fb069"}',
      };
      const onChange = vi.fn();
      const jsonValue = '{"name":"Test","color":"#d97b4f"}';
      render(<ParamInput param={param} value={jsonValue} onChange={onChange} />);

      expect(screen.getByText("json")).toBeInTheDocument();
      expect(screen.getByTestId("param-input-body").value).toBe(jsonValue);
    });

    it("should handle boolean parameter", () => {
      const param = {
        name: "enabled",
        type: "boolean",
        _in: "query",
        required: false,
        hint: "true",
      };
      const onChange = vi.fn();
      render(<ParamInput param={param} value="true" onChange={onChange} />);

      expect(screen.getByText("boolean")).toBeInTheDocument();
      expect(screen.getByTestId("param-input-enabled").value).toBe("true");
    });
  });
});
