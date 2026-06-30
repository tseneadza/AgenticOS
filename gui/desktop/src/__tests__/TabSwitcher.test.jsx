import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TabSwitcher from "../components/TabSwitcher";

describe("TabSwitcher", () => {
  it("renders tabs", () => {
    render(<TabSwitcher activeTab="explorer" onTabChange={vi.fn()} />);
    expect(screen.getByTestId("tab-button-explorer")).toBeInTheDocument();
    expect(screen.getByTestId("tab-button-calllog")).toBeInTheDocument();
  });

  it("highlights active tab", () => {
    const { container } = render(<TabSwitcher activeTab="explorer" onTabChange={vi.fn()} />);
    const button = screen.getByTestId("tab-button-explorer");
    expect(button.style.background).toBe("var(--accent)");
  });

  it("calls onTabChange when tab clicked", async () => {
    const onTabChange = vi.fn();
    render(<TabSwitcher activeTab="explorer" onTabChange={onTabChange} />);
    await userEvent.click(screen.getByTestId("tab-button-calllog"));
    expect(onTabChange).toHaveBeenCalledWith("calllog");
  });

  it("displays call log count", () => {
    render(<TabSwitcher activeTab="explorer" onTabChange={vi.fn()} callLogCount={5} />);
    expect(screen.getByText(/Call Log \(5\)/)).toBeInTheDocument();
  });

  it("handles keyboard navigation", async () => {
    const onTabChange = vi.fn();
    render(<TabSwitcher activeTab="explorer" onTabChange={onTabChange} />);
    const button = screen.getByTestId("tab-button-calllog");
    button.focus();
    await userEvent.keyboard("{Enter}");
    expect(onTabChange).toHaveBeenCalled();
  });

  it("supports custom tabs", () => {
    const customTabs = [
      { id: "tab1", label: "Tab 1" },
      { id: "tab2", label: "Tab 2" },
    ];
    render(<TabSwitcher activeTab="tab1" onTabChange={vi.fn()} tabs={customTabs} />);
    expect(screen.getByText("Tab 1")).toBeInTheDocument();
    expect(screen.getByText("Tab 2")).toBeInTheDocument();
  });
});
