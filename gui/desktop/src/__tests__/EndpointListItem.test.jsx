import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import EndpointListItem from "../components/EndpointListItem";

describe("EndpointListItem", () => {
  const mockEndpoint = {
    method: "GET",
    path: "/api/cards",
    _i: 0,
  };

  it("renders endpoint item", () => {
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId("endpoint-list-item-GET-/api/cards")).toBeInTheDocument();
  });

  it("renders method badge", () => {
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId("endpoint-method-GET")).toBeInTheDocument();
  });

  it("renders path", () => {
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId("endpoint-path-/api/cards")).toBeInTheDocument();
  });

  it("shows selection state with the selected class", () => {
    render(
      <EndpointListItem endpoint={mockEndpoint} isSelected={true} onSelect={vi.fn()} />
    );
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    expect(item.className).toContain("selected");
    expect(item).toHaveAttribute("aria-selected", "true");
  });

  it("does not apply the selected class when not selected", () => {
    render(
      <EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={vi.fn()} />
    );
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    expect(item.className).not.toContain("selected");
    expect(item).toHaveAttribute("aria-selected", "false");
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={onSelect} />);
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    await userEvent.click(item);
    expect(onSelect).toHaveBeenCalled();
  });

  it("handles keyboard Enter key", async () => {
    const onSelect = vi.fn();
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={onSelect} />);
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    item.focus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalled();
  });

  it("handles keyboard Space key", async () => {
    const onSelect = vi.fn();
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={onSelect} />);
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    item.focus();
    await userEvent.keyboard(" ");
    expect(onSelect).toHaveBeenCalled();
  });

  it("renders null for undefined endpoint", () => {
    const { container } = render(
      <EndpointListItem endpoint={undefined} isSelected={false} onSelect={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders with parameterized path", () => {
    const paramEndpoint = { method: "GET", path: "/api/cards/{id}", _i: 1 };
    render(<EndpointListItem endpoint={paramEndpoint} isSelected={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId("endpoint-path-/api/cards/{id}")).toBeInTheDocument();
  });

  it("has proper aria labels", () => {
    render(<EndpointListItem endpoint={mockEndpoint} isSelected={false} onSelect={vi.fn()} />);
    const item = screen.getByTestId("endpoint-list-item-GET-/api/cards");
    expect(item).toHaveAttribute("aria-label", "GET /api/cards");
  });
});
