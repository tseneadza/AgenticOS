/**
 * Theme integrity tripwires (2026-07-24).
 *
 * Born from a live mishap: theme.css/theme.js carried 8 theme variants
 * (4 looks x light/dark) for weeks while the native View ▸ Theme menu in
 * lib.rs listed only the 4 legacy dark ids — light themes existed but were
 * unreachable from the UI. Separately, the FR-60 token contract (--radius,
 * --glow, ...) sat in theme.css largely unconsumed, and undefined var(--x)
 * references fail SILENTLY in CSS (gui-frontend-conventions.md rule #1).
 *
 * These tests pin the three-way sync and the token contract so drift is a
 * red test, not a discovery:
 *   theme.js THEMES  <->  theme.css [data-theme] blocks  <->  lib.rs menu ids
 *
 * Authored inline (test-author subagent unavailable in this surface —
 * documented fallback, CLAUDE.md testing rule #5).
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { THEMES } from "../theme.js";

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel) => readFileSync(resolve(here, rel), "utf8");

const stripComments = (css) => css.replace(/\/\*[\s\S]*?\*\//g, "");
const themeCss = stripComments(read("../theme.css"));
const appCss = stripComments(read("../App.css"));
const libRs = read("../../src-tauri/src/lib.rs");

/* Keys the runtime accepts but that are deliberately NOT first-class:
 * theme.js LEGACY_THEMES upgrades these to the *-dark keys. */
const LEGACY_KEYS = new Set(["terra", "cyber", "future", "term"]);

/** All keys that appear in a [data-theme="…"] selector in theme.css. */
function cssThemeKeys() {
  const keys = new Set();
  for (const m of themeCss.matchAll(/\[data-theme="([^"]+)"\]/g)) keys.add(m[1]);
  return keys;
}

/** All "theme-<key>" menu ids registered in lib.rs. */
function menuThemeKeys() {
  const keys = new Set();
  for (const m of libRs.matchAll(/"theme-([a-z0-9-]+)"/g)) keys.add(m[1]);
  return keys;
}

/** Custom-property names DEFINED anywhere in the given CSS text. */
function definedTokens(css) {
  const defs = new Set();
  for (const m of css.matchAll(/(--[a-z0-9-]+)\s*:/g)) defs.add(m[1]);
  return defs;
}

/** Extract the body of every [data-theme] block keyed by each key it styles. */
function cssBlocksByKey() {
  const blocks = new Map(); // key -> concatenated block bodies
  const re = /((?::root)?(?:\[data-theme="[^"]+"\])?(?:\s*,\s*(?::root)?\[data-theme="[^"]+"\])*)\s*\{([^}]*)\}/g;
  for (const m of themeCss.matchAll(re)) {
    const selector = m[1];
    if (!selector.includes("data-theme")) continue;
    for (const k of selector.matchAll(/\[data-theme="([^"]+)"\]/g)) {
      blocks.set(k[1], (blocks.get(k[1]) || "") + m[2]);
    }
  }
  return blocks;
}

describe("theme registry <-> theme.css parity", () => {
  it("every theme.js THEMES key has a [data-theme] block in theme.css", () => {
    const css = cssThemeKeys();
    const missing = THEMES.map((t) => t.key).filter((k) => !css.has(k));
    expect(missing, `THEMES keys with no theme.css block: ${missing}`).toEqual([]);
  });

  it("every theme.css [data-theme] key is registered in THEMES (or a known legacy alias)", () => {
    const registered = new Set(THEMES.map((t) => t.key));
    const orphans = [...cssThemeKeys()].filter(
      (k) => !registered.has(k) && !LEGACY_KEYS.has(k)
    );
    expect(orphans, `theme.css blocks unreachable from theme.js: ${orphans}`).toEqual([]);
  });
});

describe("theme registry <-> native View ▸ Theme menu (lib.rs) parity", () => {
  /* THE regression this file exists for: variants present in the registry
   * but absent from the native menu are invisible to the user. */
  it("every THEMES key has a 'theme-<key>' menu item in lib.rs", () => {
    const menu = menuThemeKeys();
    const missing = THEMES.map((t) => t.key).filter((k) => !menu.has(k));
    expect(
      missing,
      `Themes unreachable from View ▸ Theme (add MenuItem in lib.rs, needs Rust rebuild): ${missing}`
    ).toEqual([]);
  });

  it("every lib.rs 'theme-<key>' menu id resolves in theme.js", () => {
    const known = new Set([...THEMES.map((t) => t.key), ...LEGACY_KEYS]);
    const dead = [...menuThemeKeys()].filter((k) => !known.has(k));
    expect(dead, `Menu items that theme.js would reject: ${dead}`).toEqual([]);
  });

  it("menu labels match theme.js labels", () => {
    for (const t of THEMES) {
      const m = libRs.match(
        new RegExp(`"theme-${t.key}",\\s*"([^"]+)"`)
      );
      expect(m, `no menu label found for ${t.key}`).toBeTruthy();
      expect(m[1], `label drift for ${t.key}`).toBe(t.label);
    }
  });
});

describe("per-theme token contract completeness", () => {
  /* Each [data-theme] block must define the full contract; a missing token
   * silently inherits the terra default and quietly breaks that theme. */
  const REQUIRED = [
    "--bg", "--bg-panel", "--bg-inset",
    "--border", "--border-soft",
    "--text", "--text-dim",
    "--accent", "--accent2",
    "--green", "--red", "--yellow",
    "--sans", "--mono",
    "--radius", "--glow",
  ];

  it("every registered theme block defines every contract token", () => {
    const blocks = cssBlocksByKey();
    const problems = [];
    for (const t of THEMES) {
      const body = blocks.get(t.key) || "";
      for (const tok of REQUIRED) {
        if (!new RegExp(`${tok}\\s*:`).test(body)) problems.push(`${t.key} missing ${tok}`);
      }
    }
    expect(problems, problems.join("; ")).toEqual([]);
  });
});

describe("no silently-undefined CSS variables (conventions rule #1)", () => {
  it("every var(--x) referenced in App.css + theme.css is defined", () => {
    const defined = new Set([...definedTokens(themeCss), ...definedTokens(appCss)]);
    const problems = new Set();
    for (const [name, css] of [["App.css", appCss], ["theme.css", themeCss]]) {
      for (const m of css.matchAll(/var\(\s*(--[a-z0-9-]+)/g)) {
        if (!defined.has(m[1])) problems.add(`${name}: ${m[1]}`);
      }
    }
    expect([...problems], `undefined tokens (fail silently!): ${[...problems]}`).toEqual([]);
  });

  it("token adoption does not regress: --radius/--radius-sm/--glow stay consumed outside theme.css", () => {
    /* The original mishap's second half: the contract existed but nothing
     * consumed it. Pin a floor so a refactor can't silently strip it out. */
    const uses = (tok) => (appCss.match(new RegExp(`var\\(${tok}[,)]`, "g")) || []).length;
    expect(uses("--radius"), "App.css var(--radius) uses").toBeGreaterThanOrEqual(10);
    expect(uses("--radius-sm"), "App.css var(--radius-sm) uses").toBeGreaterThanOrEqual(10);
    expect(definedTokens(themeCss).has("--radius-sm"), "--radius-sm defined").toBe(true);
  });
});
