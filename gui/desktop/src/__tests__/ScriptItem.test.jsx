import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScriptItem from "../components/ScriptItem";

describe("ScriptItem", () => {
  const mockScript = {
    id: "script-1",
    type: "Launcher",
    name: "start-server",
    project: "MyProject",
  };

  it("renders script item", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("script-item-script-1")).toBeInTheDocument();
  });

  it("displays script name", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    expect(screen.getByText("start-server")).toBeInTheDocument();
  });

  it("displays project name", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    expect(screen.getByText("MyProject")).toBeInTheDocument();
  });

  it("displays type badge", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    expect(screen.getByText("Launcher")).toBeInTheDocument();
  });

  it("shows selection state with the selected class", () => {
    render(
      <ScriptItem script={mockScript} isSelected={true} onSelect={vi.fn()} />
    );
    const item = screen.getByTestId("script-item-script-1");
    expect(item.className).toContain("selected");
    expect(item).toHaveAttribute("aria-selected", "true");
  });

  it("does not apply the selected class when not selected", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    const item = screen.getByTestId("script-item-script-1");
    expect(item.className).not.toContain("selected");
    expect(item).toHaveAttribute("aria-selected", "false");
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={onSelect} />
    );
    const item = screen.getByTestId("script-item-script-1");
    await userEvent.click(item);
    expect(onSelect).toHaveBeenCalled();
  });

  it("handles keyboard Enter key", async () => {
    const onSelect = vi.fn();
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={onSelect} />
    );
    const item = screen.getByTestId("script-item-script-1");
    item.focus();
    await userEvent.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalled();
  });

  it("handles keyboard Space key", async () => {
    const onSelect = vi.fn();
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={onSelect} />
    );
    const item = screen.getByTestId("script-item-script-1");
    item.focus();
    await userEvent.keyboard(" ");
    expect(onSelect).toHaveBeenCalled();
  });

  it("renders null for undefined script", () => {
    const { container } = render(
      <ScriptItem script={undefined} isSelected={false} onSelect={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders null for null script", () => {
    const { container } = render(
      <ScriptItem script={null} isSelected={false} onSelect={vi.fn()} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("handles different script types", () => {
    const types = ["Launcher", "Test", "Data", "Scraper", "Diagnostic", "Maintenance", "Dev Setup"];
    types.forEach(t => {
      const script = { ...mockScript, type: t };
      const { unmount } = render(
        <ScriptItem script={script} isSelected={false} onSelect={vi.fn()} />
      );
      expect(screen.getByText(t)).toBeInTheDocument();
      unmount();
    });
  });

  it("has correct aria-selected state", () => {
    render(
      <ScriptItem script={mockScript} isSelected={true} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("script-item-script-1")).toHaveAttribute("aria-selected", "true");
  });

  it("has descriptive aria-label", () => {
    render(
      <ScriptItem script={mockScript} isSelected={false} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("script-item-script-1")).toHaveAttribute(
      "aria-label",
      "start-server, MyProject"
    );
  });
});
