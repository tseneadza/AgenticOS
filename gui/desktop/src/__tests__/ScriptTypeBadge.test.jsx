import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ScriptTypeBadge from "../components/ScriptTypeBadge";

describe("ScriptTypeBadge", () => {
  it("renders badge with type", () => {
    render(<ScriptTypeBadge type="Launcher" />);
    expect(screen.getByText("Launcher")).toBeInTheDocument();
  });

  it("renders each type", () => {
    const types = ["Launcher", "Test", "Data", "Scraper", "Diagnostic", "Maintenance", "Dev Setup", "Unknown"];
    types.forEach(t => {
      const { unmount } = render(<ScriptTypeBadge type={t} />);
      expect(screen.getByText(t)).toBeInTheDocument();
      unmount();
    });
  });

  it("applies correct styling for Launcher type", () => {
    render(<ScriptTypeBadge type="Launcher" />);
    const badge = screen.getByTestId("script-type-badge-Launcher");
    expect(badge.style.color).toBeTruthy();
  });

  it("applies correct styling for Test type", () => {
    render(<ScriptTypeBadge type="Test" />);
    const badge = screen.getByTestId("script-type-badge-Test");
    expect(badge.style.background).toBeTruthy();
  });

  it("handles Unknown type with fallback styling", () => {
    render(<ScriptTypeBadge type="UnknownType" />);
    const badge = screen.getByTestId("script-type-badge-UnknownType");
    expect(badge).toBeInTheDocument();
  });

  it("applies custom style overrides", () => {
    render(<ScriptTypeBadge type="Launcher" customStyle={{ fontSize: 12 }} />);
    const badge = screen.getByTestId("script-type-badge-Launcher");
    expect(badge.style.fontSize).toBe("12px");
  });

  it("has correct aria-label", () => {
    render(<ScriptTypeBadge type="Launcher" />);
    expect(screen.getByTestId("script-type-badge-Launcher")).toHaveAttribute("aria-label", "Script type: Launcher");
  });

  it("displays text in monospace font", () => {
    render(<ScriptTypeBadge type="Data" />);
    const badge = screen.getByTestId("script-type-badge-Data");
    expect(badge.style.fontFamily).toContain("mono");
  });

  it("renders as inline-block", () => {
    render(<ScriptTypeBadge type="Scraper" />);
    const badge = screen.getByTestId("script-type-badge-Scraper");
    expect(badge.style.display).toBe("inline-block");
  });
});
