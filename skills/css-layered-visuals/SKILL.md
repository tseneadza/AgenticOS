---
name: css-layered-visuals
description: |
  Build or port LAYERED/CONCENTRIC visual components (orbs, spinners, radial
  gauges, badges over avatars, ripple/glow effects — anything where multiple
  elements must stack on top of each other) without the "exploded layout" bug.
  Use this skill whenever creating a component whose siblings must overlap,
  whenever porting an HTML/CSS mockup (e.g. gui/mockups/*.html) into a React
  component, or whenever debugging a visual whose pieces are scattered,
  stacked vertically, or spilling out of their container. Encodes the
  2026-07-10 OSAOrb "exploded orb" incident: grid auto-placement scattered the
  orb's rings/core down the whole rail while all 43 vitest tests stayed green.
compatibility: AgenticOS gui/desktop (React + injected scoped stylesheets), any web frontend
---

# CSS Layered Visuals (make siblings actually stack)

## The rule

**Sibling elements never overlap by default.** Normal flow, flex, and grid all
lay siblings out NEXT to each other. If a component's layers must be
concentric/stacked, you must opt in explicitly — and then VERIFY IT VISUALLY,
because jsdom cannot see layout (see "Testing blind spot" below).

## The two sanctioned stacking patterns

Pick one; both are used in this repo.

### A. Grid single-cell stack (used by OSAOrb)

```css
.stage {
  position: relative;
  width: 240px; height: 240px;
  display: grid;
  place-items: center;
}
.stage > * { grid-area: 1 / 1; }   /* ← THE LINE. Never omit it. */
```

`place-items: center` alone is NOT enough — without `grid-area: 1 / 1`,
grid **auto-placement puts each child in its own implicit row**, and the
layers scatter vertically. This is exactly the 2026-07-10 OSAOrb bug: rings
rendered at the top of the rail, the orbit ring behind the proactive feed,
the core at the bottom.

### B. Absolute stack (what most HTML mockups use)

```css
.stage { position: relative; width: 240px; height: 240px; }
.stage > * {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}
```

Gotcha: `transform` here **collides with transform animations**
(scale/rotate keyframes overwrite the centering translate). If layers
animate with transforms, prefer pattern A, or bake the translate into every
keyframe.

## Porting an HTML mockup to React — checklist

Mockups (e.g. `gui/mockups/jarvis-orb.html`) usually rely on pattern B or on
body-level positioning that silently disappears when the markup is dropped
into a component. When porting:

1. Identify the stacking mechanism in the mockup (`position: absolute`?
   negative margins? grid?). Do not assume your restyle preserves it.
2. If you convert to grid, add `grid-area: 1 / 1` on the children in the
   SAME edit as `display: grid`.
3. Check for out-of-flow extras (waveforms, badges) — `position: absolute`
   children are unaffected by grid placement; leave them as-is.
4. **Visually verify before calling it done** (next section).

## Testing blind spot — jsdom CANNOT catch this

vitest + jsdom do not compute layout: no grid placement, no overflow, no
element positions. A component whose layers are scattered across the screen
still passes every render/assertion test. The OSAOrb shipped "green" (21/21
tests) while visually exploded.

Therefore, for any layered-visual change:

- **A green test suite is NOT visual verification.** Say so explicitly in
  the session notes if the on-device look is still pending.
- Verify by eye: `cd gui/desktop && npm run tauri dev` (frontend
  hot-reloads), or open the component's mockup HTML side-by-side.
- Remember the running app may be a **built bundle** — file edits won't
  appear in it. No AgenticOS vite process listening ⇒ Tony is on a build;
  a relaunch of `tauri dev` (or rebuild) is required to see the fix.
- Optionally add a unit test asserting the stylesheet string contains
  `grid-area: 1 / 1` (a regression tripwire — cheap, catches accidental
  deletion of THE LINE even though it can't prove layout).

## Debugging "the pieces are scattered"

Symptoms → cause table:

| Symptom | Likely cause |
|---|---|
| Layers stacked VERTICALLY in order of markup | grid/flex auto-placement — missing `grid-area: 1/1` (pattern A) or missing `position: absolute` (pattern B) |
| Layers spill outside the stage into siblings | children larger than the stage + no shared cell; fix stacking first, then decide if `overflow` clipping is wanted |
| Layers centered but animations "jump" | transform-centering (pattern B) fighting transform keyframes — switch to pattern A |
| Looks right in mockup HTML, wrong in React | stacking mechanism lost in the port — re-run the porting checklist |

## Related

- `skills/osa-orb-state` — what state the orb SHOWS (truth rules). This
  skill is about how the orb (or any layered visual) RENDERS.
- `docs/gui-frontend-conventions.md` rule 9 — the short-form version of
  this rule, read before any GUI work.
