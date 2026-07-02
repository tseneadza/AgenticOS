import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ScriptGroupHeader from "../components/ScriptGroupHeader";

describe("ScriptGroupHeader", () => {
  it("renders group name", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={5}
      />
    );
    expect(screen.getByText("Launcher")).toBeInTheDocument();
  });

  it("displays item count", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={5}
      />
    );
    expect(screen.getByText(/· 5/)).toBeInTheDocument();
  });

  it("shows chevron pointing right when closed", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={false}
        onToggle={vi.fn()}
        itemCount={3}
      />
    );
    // Rotation is CSS-driven off aria-expanded on the header.
    const header = screen.getByTestId("script-group-header-Launcher");
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("script-group-chevron-Launcher").className).toContain(
      "script-group-chevron"
    );
  });

  it("rotates chevron when open", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={3}
      />
    );
    const header = screen.getByTestId("script-group-header-Launcher");
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("script-group-chevron-Launcher").className).toContain(
      "script-group-chevron"
    );
  });

  it("calls onToggle when clicked", async () => {
    const onToggle = vi.fn();
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={false}
        onToggle={onToggle}
        itemCount={5}
      />
    );
    const header = screen.getByTestId("script-group-header-Launcher");
    await userEvent.click(header);
    expect(onToggle).toHaveBeenCalled();
  });

  it("handles keyboard Enter key", async () => {
    const onToggle = vi.fn();
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={false}
        onToggle={onToggle}
        itemCount={5}
      />
    );
    const header = screen.getByTestId("script-group-header-Launcher");
    header.focus();
    await userEvent.keyboard("{Enter}");
    expect(onToggle).toHaveBeenCalled();
  });

  it("handles keyboard Space key", async () => {
    const onToggle = vi.fn();
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={false}
        onToggle={onToggle}
        itemCount={5}
      />
    );
    const header = screen.getByTestId("script-group-header-Launcher");
    header.focus();
    await userEvent.keyboard(" ");
    expect(onToggle).toHaveBeenCalled();
  });

  it("shows type indicator dot when groupBy='type'", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={5}
        groupBy="type"
      />
    );
    expect(screen.getByTestId("script-group-dot-Launcher")).toBeInTheDocument();
  });

  it("hides type indicator dot when groupBy='project'", () => {
    render(
      <ScriptGroupHeader
        name="MyProject"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={5}
        groupBy="project"
      />
    );
    expect(screen.queryByTestId("script-group-dot-MyProject")).not.toBeInTheDocument();
  });

  it("has correct aria-expanded state", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={true}
        onToggle={vi.fn()}
        itemCount={5}
      />
    );
    expect(screen.getByTestId("script-group-header-Launcher")).toHaveAttribute("aria-expanded", "true");
  });

  it("has descriptive aria-label", () => {
    render(
      <ScriptGroupHeader
        name="Launcher"
        isOpen={false}
        onToggle={vi.fn()}
        itemCount={5}
      />
    );
    expect(screen.getByTestId("script-group-header-Launcher")).toHaveAttribute("aria-label", expect.stringContaining("Launcher"));
  });
});
