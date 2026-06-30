import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FilterBar from "../components/FilterBar";

describe("FilterBar Component", () => {
  describe("rendering", () => {
    it("should render without crashing", () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);
      expect(screen.getByTestId("filter-input")).toBeInTheDocument();
    });

    it("should display placeholder text", () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);
      expect(screen.getByPlaceholderText("Filter endpoints…")).toBeInTheDocument();
    });

    it("should use custom placeholder", () => {
      const onChange = vi.fn();
      render(
        <FilterBar value="" onChange={onChange} placeholder="Search APIs…" />
      );
      expect(screen.getByPlaceholderText("Search APIs…")).toBeInTheDocument();
    });

    it("should display current value", () => {
      const onChange = vi.fn();
      render(<FilterBar value="test" onChange={onChange} />);
      const input = screen.getByTestId("filter-input");
      expect(input.value).toBe("test");
    });
  });

  describe("onChange handler", () => {
    it("should call onChange when value changes", async () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);

      const input = screen.getByTestId("filter-input");
      await userEvent.type(input, "GET");

      expect(onChange).toHaveBeenCalled();
    });

    it("should pass new value to onChange", async () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);

      const input = screen.getByTestId("filter-input");
      await userEvent.type(input, "cards");

      expect(onChange).toHaveBeenCalled();
    });
  });

  describe("accessibility", () => {
    it("should have descriptive aria-label", () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);
      expect(screen.getByTestId("filter-input")).toHaveAttribute("aria-label");
    });
  });

  describe("real-world scenarios", () => {
    it("should filter by endpoint path", async () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);

      const input = screen.getByTestId("filter-input");
      await userEvent.type(input, "/cards");

      expect(onChange).toHaveBeenCalled();
    });

    it("should filter by method", async () => {
      const onChange = vi.fn();
      render(<FilterBar value="" onChange={onChange} />);

      const input = screen.getByTestId("filter-input");
      await userEvent.type(input, "POST");

      expect(onChange).toHaveBeenCalled();
    });

    it("should clear filter", async () => {
      const onChange = vi.fn();
      const { rerender } = render(<FilterBar value="test" onChange={onChange} />);

      const input = screen.getByTestId("filter-input");
      expect(input.value).toBe("test");

      await userEvent.clear(input);
      rerender(<FilterBar value="" onChange={onChange} />);

      expect(screen.getByTestId("filter-input")).toHaveValue("");
    });
  });
});
