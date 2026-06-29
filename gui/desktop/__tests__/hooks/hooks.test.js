import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useGroupState } from "../../src/hooks/useGroupState";
import { useFilter } from "../../src/hooks/useFilter";
import { useExplorer } from "../../src/hooks/useExplorer";
import { useHealthCheck } from "../../src/hooks/useHealthCheck";

describe("Custom Hooks", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // useGroupState tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("useGroupState", () => {
    it("should initialize with all keys set to true", () => {
      const { result } = renderHook(() =>
        useGroupState(["type", "project"])
      );
      expect(result.current.groupOpen).toEqual({
        type: true,
        project: true,
      });
    });

    it("should toggle a group open/closed", () => {
      const { result } = renderHook(() =>
        useGroupState(["type"])
      );
      expect(result.current.groupOpen.type).toBe(true);

      act(() => {
        result.current.toggleGroup("type");
      });
      expect(result.current.groupOpen.type).toBe(false);

      act(() => {
        result.current.toggleGroup("type");
      });
      expect(result.current.groupOpen.type).toBe(true);
    });

    it("should expand all groups", () => {
      const { result } = renderHook(() =>
        useGroupState(["type", "project"])
      );

      act(() => {
        result.current.collapseAll();
      });
      expect(result.current.groupOpen.type).toBe(false);
      expect(result.current.groupOpen.project).toBe(false);

      act(() => {
        result.current.expandAll();
      });
      expect(result.current.groupOpen.type).toBe(true);
      expect(result.current.groupOpen.project).toBe(true);
    });

    it("should collapse all groups", () => {
      const { result } = renderHook(() =>
        useGroupState(["type", "project"])
      );

      act(() => {
        result.current.collapseAll();
      });
      expect(result.current.groupOpen.type).toBe(false);
      expect(result.current.groupOpen.project).toBe(false);
    });

    it("should set all to a specific state", () => {
      const { result } = renderHook(() =>
        useGroupState(["a", "b", "c"])
      );

      act(() => {
        result.current.setAll(["a", "b"], false);
      });
      expect(result.current.groupOpen.a).toBe(false);
      expect(result.current.groupOpen.b).toBe(false);
      expect(result.current.groupOpen.c).toBe(true);
    });

    it("should handle empty initial keys", () => {
      const { result } = renderHook(() =>
        useGroupState([])
      );
      expect(result.current.groupOpen).toEqual({});
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // useFilter tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("useFilter", () => {
    it("should initialize with default sort options", () => {
      const filterFn = vi.fn();
      const sortFn = vi.fn();
      const { result } = renderHook(() =>
        useFilter(filterFn, sortFn)
      );

      expect(result.current.filter).toBe("");
      expect(result.current.sortBy).toBe("name");
      expect(result.current.sortDir).toBe("asc");
    });

    it("should update filter", () => {
      const filterFn = vi.fn();
      const sortFn = vi.fn();
      const { result } = renderHook(() =>
        useFilter(filterFn, sortFn)
      );

      act(() => {
        result.current.setFilter("test");
      });
      expect(result.current.filter).toBe("test");
    });

    it("should toggle sort direction", () => {
      const filterFn = vi.fn();
      const sortFn = vi.fn();
      const { result } = renderHook(() =>
        useFilter(filterFn, sortFn)
      );

      expect(result.current.sortDir).toBe("asc");

      act(() => {
        result.current.toggleSort("name");
      });
      expect(result.current.sortDir).toBe("desc");

      act(() => {
        result.current.toggleSort("name");
      });
      expect(result.current.sortDir).toBe("asc");
    });

    it("should change sort field", () => {
      const filterFn = vi.fn();
      const sortFn = vi.fn();
      const { result } = renderHook(() =>
        useFilter(filterFn, sortFn)
      );

      act(() => {
        result.current.toggleSort("type");
      });
      expect(result.current.sortBy).toBe("type");
      expect(result.current.sortDir).toBe("asc");
    });

    it("should reset filter state", () => {
      const filterFn = vi.fn();
      const sortFn = vi.fn();
      const { result } = renderHook(() =>
        useFilter(filterFn, sortFn)
      );

      act(() => {
        result.current.setFilter("test");
        result.current.toggleSort("type");
        result.current.toggleSort("type"); // make it desc
      });

      act(() => {
        result.current.reset();
      });

      expect(result.current.filter).toBe("");
      expect(result.current.sortBy).toBe("name");
      expect(result.current.sortDir).toBe("asc");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // useExplorer tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("useExplorer", () => {
    it("should initialize with default state", () => {
      const { result } = renderHook(() => useExplorer());

      expect(result.current.selected).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.data).toBeNull();
    });

    it("should select an item", () => {
      const { result } = renderHook(() => useExplorer());

      act(() => {
        result.current.selectItem("item-1");
      });

      expect(result.current.selected).toBe("item-1");
    });

    it("should clear selection", () => {
      const { result } = renderHook(() => useExplorer());

      act(() => {
        result.current.selectItem("item-1");
      });
      expect(result.current.selected).toBe("item-1");

      act(() => {
        result.current.clearSelection();
      });
      expect(result.current.selected).toBeNull();
    });

    it("should set data", () => {
      const { result } = renderHook(() => useExplorer());
      const testData = [{ id: 1 }, { id: 2 }];

      act(() => {
        result.current.setData(testData);
      });

      expect(result.current.data).toEqual(testData);
    });

    it("should manage loading state", () => {
      const { result } = renderHook(() => useExplorer());

      act(() => {
        result.current.setLoading(true);
      });
      expect(result.current.loading).toBe(true);

      act(() => {
        result.current.setLoading(false);
      });
      expect(result.current.loading).toBe(false);
    });

    it("should manage error state", () => {
      const { result } = renderHook(() => useExplorer());

      act(() => {
        result.current.setError("Test error");
      });
      expect(result.current.error).toBe("Test error");

      act(() => {
        result.current.setError(null);
      });
      expect(result.current.error).toBeNull();
    });

    it("should manage details loading state", () => {
      const { result } = renderHook(() => useExplorer());

      act(() => {
        result.current.setDetailsLoading(true);
      });
      expect(result.current.detailsLoading).toBe(true);

      act(() => {
        result.current.setDetailsLoading(false);
      });
      expect(result.current.detailsLoading).toBe(false);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // useHealthCheck tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("useHealthCheck", () => {
    it("should initialize with checking state", () => {
      vi.mock("fetch");
      const { result } = renderHook(() =>
        useHealthCheck("http://localhost:5130/health", 1000000) // Long interval to avoid auto-check
      );

      expect(result.current.label).toBe("checking…");
      expect(result.current.color).toBe("#e0b84c");
    });

    it("should handle null URL gracefully", () => {
      const { result } = renderHook(() =>
        useHealthCheck(null)
      );

      expect(result.current.ok).toBeNull();
      expect(result.current.label).toBe("checking…");
    });

    it("should update when no URL provided", () => {
      const { result, rerender } = renderHook(
        ({ url }) => useHealthCheck(url),
        { initialProps: { url: null } }
      );

      expect(result.current.ok).toBeNull();

      rerender({ url: null });
      expect(result.current.ok).toBeNull();
    });
  });
});
