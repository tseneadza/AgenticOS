import { describe, it, expect } from "vitest";
import {
  classifyScript,
  parseScriptContent,
  filterScripts,
  buildUrl,
  filterEndpoints,
  sortByField,
  convertOpenAPIToEndpoints,
  TYPE_STYLE,
  METHOD_COLOR,
} from "../../src/utils/explorers";
import { mockScripts, mockScriptContent, mockScriptInfo } from "../fixtures/mockScripts";
import { mockEndpoints } from "../fixtures/mockEndpoints";

describe("Explorer Utilities", () => {
  // ─────────────────────────────────────────────────────────────────────────
  // classifyScript tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("classifyScript", () => {
    it("should classify launcher scripts by name", () => {
      expect(classifyScript({ name: "start-server" })).toBe("Launcher");
      expect(classifyScript({ name: "launch-app" })).toBe("Launcher");
      expect(classifyScript({ name: "serve" })).toBe("Launcher");
    });

    it("should classify test scripts", () => {
      expect(classifyScript({ name: "run-tests" })).toBe("Test");
      expect(classifyScript({ name: "smoke-test" })).toBe("Test");
      expect(classifyScript({ name: "spec.js" })).toBe("Test");
    });

    it("should classify data scripts", () => {
      expect(classifyScript({ name: "seed-db" })).toBe("Data");
      expect(classifyScript({ name: "import-data" })).toBe("Data");
      expect(classifyScript({ name: "populate-cache" })).toBe("Data");
    });

    it("should classify scraper scripts", () => {
      expect(classifyScript({ name: "fetch-data" })).toBe("Scraper");
      expect(classifyScript({ name: "crawl-web" })).toBe("Scraper");
      expect(classifyScript({ name: "download-files" })).toBe("Scraper");
    });

    it("should classify diagnostic scripts", () => {
      expect(classifyScript({ name: "diagnose-system" })).toBe("Diagnostic");
      expect(classifyScript({ name: "inspect-logs" })).toBe("Diagnostic");
      expect(classifyScript({ name: "debug-app" })).toBe("Diagnostic");
    });

    it("should classify maintenance scripts", () => {
      expect(classifyScript({ name: "clear-cache" })).toBe("Maintenance");
      expect(classifyScript({ name: "sync-files" })).toBe("Maintenance");
      expect(classifyScript({ name: "clean-build" })).toBe("Maintenance");
    });

    it("should classify dev setup scripts", () => {
      expect(classifyScript({ name: "setup-env" })).toBe("Dev Setup");
      expect(classifyScript({ name: "install-deps" })).toBe("Dev Setup");
      expect(classifyScript({ name: "init-database" })).toBe("Dev Setup");
    });

    it("should fallback to description for classification", () => {
      expect(classifyScript({ name: "script.sh", description: "Start the server" })).toBe("Launcher");
      expect(classifyScript({ name: "script.sh", description: "Test the app" })).toBe("Test");
    });

    it("should return Unknown for unclassifiable scripts", () => {
      expect(classifyScript({ name: "unknown-script" })).toBe("Unknown");
      expect(classifyScript({ name: "", description: "" })).toBe("Unknown");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // parseScriptContent tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("parseScriptContent", () => {
    it("should return null for empty content", () => {
      expect(parseScriptContent("", { name: "script.sh", path: "script.sh" })).toBeNull();
      expect(parseScriptContent(null, { name: "script.sh", path: "script.sh" })).toBeNull();
    });

    it("should extract purpose from script header", () => {
      const result = parseScriptContent(mockScriptContent, {
        name: "run-tests.sh",
        path: "run-tests.sh",
        description: "Run tests",
      });
      expect(result.purpose).toBe("Run tests for the application");
    });

    it("should extract usage lines", () => {
      const result = parseScriptContent(mockScriptContent, {
        name: "run-tests.sh",
        path: "run-tests.sh",
        description: "Run tests",
      });
      expect(result.usageLines.length).toBeGreaterThan(0);
      expect(result.usageLines[0]).toContain("run-tests");
    });

    it("should extract parameter lines", () => {
      const result = parseScriptContent(mockScriptContent, {
        name: "run-tests.sh",
        path: "run-tests.sh",
      });
      expect(result.paramLines.length).toBeGreaterThan(0);
    });

    it("should extract environment variables", () => {
      const content = `#!/bin/bash
# Script that uses env vars
# Requires: NODE_ENV, API_KEY, DB_PASSWORD
echo $NODE_ENV
echo $API_KEY
`;
      const result = parseScriptContent(content, {
        name: "test.sh",
        path: "test.sh",
      });
      expect(result.envVars).toContain("NODE_ENV");
      expect(result.envVars).toContain("API_KEY");
    });

    it("should count lines correctly", () => {
      const result = parseScriptContent(mockScriptContent, {
        name: "run-tests.sh",
        path: "run-tests.sh",
      });
      expect(result.lineCount).toBeGreaterThan(0);
    });

    it("should handle python docstrings", () => {
      const pyContent = `#!/usr/bin/env python3
"""
Run the test suite
This is a description
"""
print("test")
`;
      const result = parseScriptContent(pyContent, {
        name: "test.py",
        path: "test.py",
      });
      expect(result).not.toBeNull();
      expect(result.purpose).toContain("Run the test suite");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // filterScripts tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("filterScripts", () => {
    it("should return all scripts when filter is empty", () => {
      expect(filterScripts(mockScripts, "")).toHaveLength(mockScripts.length);
      expect(filterScripts(mockScripts, null)).toHaveLength(mockScripts.length);
    });

    it("should filter by script name", () => {
      const result = filterScripts(mockScripts, "start");
      expect(result.length).toBeGreaterThan(0);
      expect(result.some(s => s.name.includes("start"))).toBe(true);
    });

    it("should filter by script type", () => {
      const result = filterScripts(mockScripts, "Test");
      expect(result.every(s => s.type === "Test")).toBe(true);
    });

    it("should filter by project", () => {
      const result = filterScripts(mockScripts, "app1");
      expect(result.every(s => s.project === "app1")).toBe(true);
    });

    it("should be case insensitive", () => {
      const lower = filterScripts(mockScripts, "test");
      const upper = filterScripts(mockScripts, "TEST");
      expect(lower).toEqual(upper);
    });

    it("should filter by description", () => {
      const result = filterScripts(mockScripts, "database");
      expect(result.length).toBeGreaterThan(0);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // buildUrl tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("buildUrl", () => {
    it("should build simple GET URL", () => {
      const ep = { path: "/cards", method: "GET", params: [] };
      const url = buildUrl(ep, {});
      expect(url).toContain("/cards");
    });

    it("should substitute path parameters", () => {
      const ep = {
        path: "/cards/{id}",
        method: "GET",
        params: [{ name: "id", _in: "path" }],
      };
      const url = buildUrl(ep, { id: "my-app" });
      expect(url).toContain("my-app");
      expect(url).not.toContain("{id}");
    });

    it("should add query parameters", () => {
      const ep = {
        path: "/logs",
        method: "GET",
        params: [{ name: "lines", _in: "query" }],
      };
      const url = buildUrl(ep, { lines: "50" });
      expect(url).toContain("lines=50");
    });

    it("should URL encode query parameters", () => {
      const ep = {
        path: "/search",
        method: "GET",
        params: [{ name: "q", _in: "query" }],
      };
      const url = buildUrl(ep, { q: "hello world" });
      expect(url).toContain("hello%20world");
    });

    it("should handle missing path parameters gracefully", () => {
      const ep = {
        path: "/cards/{id}",
        method: "GET",
        params: [{ name: "id", _in: "path" }],
      };
      const url = buildUrl(ep, {});
      expect(url).toContain("{id}");
    });

    it("should use sidecar URL for sidecar endpoints", () => {
      const ep = {
        server: "sidecar",
        path: "/api/health",
        method: "GET",
        params: [],
      };
      const url = buildUrl(ep, {});
      expect(url).toContain("localhost:5130");
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // filterEndpoints tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("filterEndpoints", () => {
    it("should filter by group", () => {
      const result = filterEndpoints(mockEndpoints, "Cards", "");
      expect(result.every(e => e.group === "Cards")).toBe(true);
    });

    it("should filter by path", () => {
      const result = filterEndpoints(mockEndpoints, "Logs & Env", "logs");
      expect(result.length).toBeGreaterThan(0);
      expect(result.some(e => e.path.includes("logs"))).toBe(true);
    });

    it("should filter by method", () => {
      const result = filterEndpoints(mockEndpoints, "Cards", "POST");
      expect(result.length).toBeGreaterThan(0);
      expect(result.some(e => e.method === "POST")).toBe(true);
    });

    it("should be case insensitive", () => {
      const lower = filterEndpoints(mockEndpoints, "Cards", "post");
      const upper = filterEndpoints(mockEndpoints, "Cards", "POST");
      expect(lower).toEqual(upper);
    });

    it("should include original indices", () => {
      const result = filterEndpoints(mockEndpoints, "Cards", "");
      expect(result.every(e => typeof e._i === "number")).toBe(true);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // sortByField tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("sortByField", () => {
    it("should sort ascending by default", () => {
      const items = [
        { name: "zebra" },
        { name: "apple" },
        { name: "banana" },
      ];
      const result = sortByField(items, "name");
      expect(result[0].name).toBe("apple");
      expect(result[2].name).toBe("zebra");
    });

    it("should sort descending when specified", () => {
      const items = [
        { name: "apple" },
        { name: "zebra" },
        { name: "banana" },
      ];
      const result = sortByField(items, "name", "desc");
      expect(result[0].name).toBe("zebra");
      expect(result[2].name).toBe("apple");
    });

    it("should handle null/undefined values", () => {
      const items = [
        { val: "b" },
        { val: null },
        { val: "a" },
      ];
      const result = sortByField(items, "val", "asc");
      expect(result).toHaveLength(3);
    });

    it("should be case insensitive", () => {
      const items = [{ name: "Apple" }, { name: "apple" }, { name: "APPLE" }];
      const result = sortByField(items, "name", "asc");
      expect(result).toHaveLength(3);
    });

    it("should not mutate original array", () => {
      const original = [{ name: "b" }, { name: "a" }];
      const copy = [...original];
      sortByField(original, "name");
      expect(original).toEqual(copy);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // convertOpenAPIToEndpoints tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("convertOpenAPIToEndpoints", () => {
    it("should return empty array for empty spec", () => {
      expect(convertOpenAPIToEndpoints(null)).toEqual([]);
      expect(convertOpenAPIToEndpoints({})).toEqual([]);
      expect(convertOpenAPIToEndpoints({ paths: {} })).toEqual([]);
    });

    it("should convert basic endpoint", () => {
      const spec = {
        paths: {
          "/test": {
            get: {
              summary: "Test endpoint",
              description: "A test endpoint",
              tags: ["Test"],
            },
          },
        },
      };
      const result = convertOpenAPIToEndpoints(spec);
      expect(result).toHaveLength(1);
      expect(result[0].method).toBe("GET");
      expect(result[0].path).toBe("/test");
      expect(result[0].desc).toBe("Test endpoint");
    });

    it("should skip invalid HTTP methods", () => {
      const spec = {
        paths: {
          "/test": {
            invalid: { summary: "Invalid" },
            get: { summary: "Valid" },
          },
        },
      };
      const result = convertOpenAPIToEndpoints(spec);
      expect(result).toHaveLength(1);
      expect(result[0].method).toBe("GET");
    });

    it("should extract parameters from spec", () => {
      const spec = {
        paths: {
          "/items/{id}": {
            get: {
              parameters: [
                { name: "id", in: "path", required: true, schema: { type: "string" } },
              ],
            },
          },
        },
      };
      const result = convertOpenAPIToEndpoints(spec);
      expect(result[0].params).toHaveLength(1);
      expect(result[0].params[0].name).toBe("id");
      expect(result[0].params[0]._in).toBe("path");
    });

    it("should handle request body parameters", () => {
      const spec = {
        paths: {
          "/items": {
            post: {
              requestBody: {
                required: true,
                content: { "application/json": {} },
              },
            },
          },
        },
      };
      const result = convertOpenAPIToEndpoints(spec);
      expect(result[0].params.some(p => p._in === "body")).toBe(true);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Constants tests
  // ─────────────────────────────────────────────────────────────────────────

  describe("Constants", () => {
    it("should have TYPE_STYLE for all script types", () => {
      const types = [
        "Launcher",
        "Test",
        "Data",
        "Scraper",
        "Diagnostic",
        "Maintenance",
        "Dev Setup",
        "Unknown",
      ];
      types.forEach(type => {
        expect(TYPE_STYLE[type]).toBeDefined();
        expect(TYPE_STYLE[type]).toHaveProperty("bg");
        expect(TYPE_STYLE[type]).toHaveProperty("color");
      });
    });

    it("should have METHOD_COLOR for all HTTP methods", () => {
      const methods = ["GET", "POST", "DELETE", "PUT"];
      methods.forEach(method => {
        expect(METHOD_COLOR[method]).toBeDefined();
        expect(METHOD_COLOR[method]).toHaveProperty("bg");
        expect(METHOD_COLOR[method]).toHaveProperty("color");
      });
    });
  });
});
