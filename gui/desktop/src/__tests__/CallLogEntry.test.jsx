import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CallLogEntry from "../components/CallLogEntry";

describe("CallLogEntry Component", () => {
  const mockEntry = {
    ts: new Date("2026-06-29T12:00:00"),
    method: "GET",
    path: "/cards",
    status: 200,
    ok: true,
    dur: 42,
  };

  describe("rendering", () => {
    it("should render without crashing", () => {
      render(<CallLogEntry entry={mockEntry} />);
      expect(screen.getByTestId("call-log-entry")).toBeInTheDocument();
    });

    it("should display all entry components", () => {
      render(<CallLogEntry entry={mockEntry} />);
      expect(screen.getByTestId("call-timestamp")).toBeInTheDocument();
      expect(screen.getByTestId("call-method")).toBeInTheDocument();
      expect(screen.getByTestId("call-path")).toBeInTheDocument();
      expect(screen.getByTestId("call-status")).toBeInTheDocument();
      expect(screen.getByTestId("call-duration")).toBeInTheDocument();
    });

    it("should handle null entry gracefully", () => {
      const { container } = render(<CallLogEntry entry={null} />);
      expect(container.firstChild).toBeNull();
    });

    it("should display timestamp", () => {
      render(<CallLogEntry entry={mockEntry} />);
      expect(screen.getByTestId("call-timestamp")).toHaveTextContent("12:00:00");
    });

    it("should display path", () => {
      render(<CallLogEntry entry={mockEntry} />);
      expect(screen.getByTestId("call-path")).toHaveTextContent("/cards");
    });

    it("should display duration", () => {
      render(<CallLogEntry entry={mockEntry} />);
      expect(screen.getByTestId("call-duration")).toHaveTextContent("42ms");
    });
  });

  describe("success/error styling", () => {
    it("should have the success class for a successful call", () => {
      const { container } = render(<CallLogEntry entry={mockEntry} />);
      const entry = container.querySelector('[data-testid="call-log-entry"]');
      expect(entry.className).toContain("success");
      expect(entry.className).not.toContain("error");
    });

    it("should have the error class for a failed call", () => {
      const failedEntry = { ...mockEntry, ok: false, status: 500 };
      const { container } = render(<CallLogEntry entry={failedEntry} />);
      const entry = container.querySelector('[data-testid="call-log-entry"]');
      expect(entry.className).toContain("error");
      expect(entry.className).not.toContain("success");
    });
  });

  describe("onSelect handler", () => {
    it("should not be a button without onSelect prop", () => {
      const { container } = render(<CallLogEntry entry={mockEntry} />);
      const entry = container.querySelector('[data-testid="call-log-entry"]');
      expect(entry).not.toHaveAttribute("role", "button");
      expect(entry).not.toHaveAttribute("tabindex");
    });

    it("should be an interactive button with onSelect", () => {
      const onSelect = vi.fn();
      const { container } = render(
        <CallLogEntry entry={mockEntry} onSelect={onSelect} />
      );
      const entry = container.querySelector('[data-testid="call-log-entry"]');
      expect(entry).toHaveAttribute("role", "button");
      expect(entry).toHaveAttribute("tabindex", "0");
    });

    it("should call onSelect when clicked", async () => {
      const onSelect = vi.fn();
      render(<CallLogEntry entry={mockEntry} onSelect={onSelect} />);

      const entry = screen.getByTestId("call-log-entry");
      await userEvent.click(entry);

      expect(onSelect).toHaveBeenCalledOnce();
      expect(onSelect).toHaveBeenCalledWith(mockEntry);
    });

    it("should call onSelect on Enter key", async () => {
      const onSelect = vi.fn();
      render(<CallLogEntry entry={mockEntry} onSelect={onSelect} />);

      const entry = screen.getByTestId("call-log-entry");
      entry.focus();
      await userEvent.keyboard("{Enter}");

      expect(onSelect).toHaveBeenCalledOnce();
    });

    it("should call onSelect on Space key", async () => {
      const onSelect = vi.fn();
      render(<CallLogEntry entry={mockEntry} onSelect={onSelect} />);

      const entry = screen.getByTestId("call-log-entry");
      entry.focus();
      await userEvent.keyboard(" ");

      expect(onSelect).toHaveBeenCalledOnce();
    });
  });

  describe("real-world scenarios", () => {
    it("should handle different HTTP methods", () => {
      const methods = ["GET", "POST", "PUT", "DELETE", "PATCH"];

      methods.forEach(method => {
        const entry = { ...mockEntry, method };
        const { unmount } = render(<CallLogEntry entry={entry} />);
        expect(screen.getByTestId("call-method")).toBeInTheDocument();
        unmount();
      });
    });

    it("should handle different status codes", () => {
      const codes = [200, 201, 404, 500, 0];

      codes.forEach(status => {
        const entry = {
          ...mockEntry,
          status,
          ok: status >= 200 && status < 300,
        };
        const { unmount } = render(<CallLogEntry entry={entry} />);
        expect(screen.getByTestId("call-status")).toBeInTheDocument();
        unmount();
      });
    });

    it("should handle various paths", () => {
      const paths = ["/cards", "/scripts/run", "/api/news/feeds/{id}"];

      paths.forEach(path => {
        const entry = { ...mockEntry, path };
        const { unmount } = render(<CallLogEntry entry={entry} />);
        expect(screen.getByTestId("call-path")).toHaveTextContent(path);
        unmount();
      });
    });

    it("should format timestamps correctly", () => {
      const times = [
        new Date("2026-06-29T08:30:45"),
        new Date("2026-06-29T14:15:30"),
        new Date("2026-06-29T23:59:59"),
      ];

      times.forEach(ts => {
        const entry = { ...mockEntry, ts };
        const { unmount } = render(<CallLogEntry entry={entry} />);
        expect(screen.getByTestId("call-timestamp")).toBeInTheDocument();
        unmount();
      });
    });

    it("should show fast and slow requests", () => {
      const fastEntry = { ...mockEntry, dur: 5 };
      const slowEntry = { ...mockEntry, dur: 5000 };

      const { unmount: unmountFast } = render(
        <CallLogEntry entry={fastEntry} />
      );
      expect(screen.getByTestId("call-duration")).toHaveTextContent("5ms");
      unmountFast();

      const { unmount: unmountSlow } = render(
        <CallLogEntry entry={slowEntry} />
      );
      expect(screen.getByTestId("call-duration")).toHaveTextContent("5000ms");
      unmountSlow();
    });
  });
});
