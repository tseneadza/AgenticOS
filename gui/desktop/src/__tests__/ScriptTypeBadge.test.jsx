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
    expect(badge.className).toContain("script-type-badge");
    expect(badge.className).toContain("launcher");
  });

  it("applies correct styling for Test type", () => {
    render(<ScriptTypeBadge type="Test" />);
    const badge = screen.getByTestId("script-type-badge-Test");
    expect(badge.className).toContain("test");
  });

  it("maps multi-word type to a hyphenated class", () => {
    render(<ScriptTypeBadge type="Dev Setup" />);
    const badge = screen.getByTestId("script-type-badge-Dev Setup");
    expect(badge.className).toContain("dev-setup");
  });

  it("handles Unknown type with fallback styling", () => {
    render(<ScriptTypeBadge type="UnknownType" />);
    const badge = screen.getByTestId("script-type-badge-UnknownType");
    expect(badge).toBeInTheDocument();
  });

  it("falls back to unknown class when type is missing", () => {
    render(<ScriptTypeBadge type={undefined} />);
    const badge = screen.getByTestId("script-type-badge-undefined");
    expect(badge.className).toContain("unknown");
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

  it("applies the data type class", () => {
    render(<ScriptTypeBadge type="Data" />);
    const badge = screen.getByTestId("script-type-badge-Data");
    expect(badge.className).toContain("data");
  });

  it("applies the scraper type class", () => {
    render(<ScriptTypeBadge type="Scraper" />);
    const badge = screen.getByTestId("script-type-badge-Scraper");
    expect(badge.className).toContain("scraper");
  });
});
