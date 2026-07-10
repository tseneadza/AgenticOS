# AgenticOS — UI Vision (the "shock and awe" north star)

> **Purpose.** A design north-star for evolving the AgenticOS desktop GUI
> (`gui/desktop/`) from *typical/expected application chrome* into a
> **fresh, attention-grabbing, desirably-functional space**. Captured
> 2026-07-09 from Tony's brief. This is a **vision + phased execution plan**,
> NOT a commitment to build it all at once — OSA functionality is the active
> priority; this doc exists so the visual vision is preserved and can be
> pulled in incrementally, one ponytail-sized slice at a time.

> **Read first:** `docs/gui-frontend-conventions.md` (the hard-won rules —
> theme tokens only, scoped stylesheets for hover/keyframes, verify edits
> persisted) and `gui/desktop/src/theme.css` (the token contract). Every
> idea below MUST be expressible in the existing token system or extend it
> deliberately in `theme.css` — no inline one-off colors.

---

## 1. The brief (Tony's words, distilled)

- **Vibe:** a combination of **sci-fi/cyberpunk × playful/modern**. Not one or
  the other — the tension between the two is the identity.
- **Component polish:** "shock and awe." Individual components should feel
  alive and considered, not stock.
- **Sidebar / rail / dashboards:** today they're *typical — what's expected of
  an application*. The goal is a **new, desirable, functional space** that
  presents the necessary content and purpose in a way that grabs attention and
  feels genuinely new to inhabit.
- **The orb:** already lands ("looks great") — it's the tuning fork. Everything
  around it should rise to meet its energy. Room for refinement, not a rebuild.
- **Scope:** a full polish pass across the whole UI — executed incrementally.

**The one-line test for any change:** *does this make the surface feel like a
living system you want to operate, rather than a form you have to fill out?*

---

## 2. Design language

The orb (`OSAOrb.jsx`) already encodes the target aesthetic; treat it as the
source palette for the whole shell. Its vocabulary:

- **Luminous depth** — layered radial glows, white-hot cores fading through a
  state hue to transparent. Nothing is flat-filled; light has a source.
- **State as color** — one hue triple (`--orb`) drives every derived glow. The
  shell should adopt the same discipline: a small set of semantic hues,
  everything else derived via `rgba(var(--hue), a)` and `color-mix`.
- **Orbital motion** — slow dashed/dotted rings, counter-rotation, ripples that
  expand and fade. Motion is ambient and calm at rest, quickening under load.
- **Concentric focus** — layers stack toward a center of attention.

Translating that to chrome (the sci-fi/cyberpunk × playful blend):

| Axis | Sci-fi/cyberpunk pull | Playful/modern pull | Resolution |
|---|---|---|---|
| Surfaces | deep near-black glass, faint grid/scanline texture | soft rounded cards, breathing room | glassy panels with a *subtle* texture + generous radius (`--radius`) |
| Edges | thin neon hairlines, glow on focus | soft shadows, no harsh lines | hairline borders that **bloom** (`--glow`) on hover/active, not static neon everywhere |
| Type | mono for data, wide tracking for labels | friendly sans for prose | keep `--mono` for metrics/IDs, `--sans` for reading; uppercase micro-labels with letter-spacing for the "HUD" feel |
| Motion | HUD sweeps, telemetry ticks | bouncy, springy micro-interactions | ambient ambient-drift by default; springy easing on user actions |
| Color | saturated accent on dark | warm, optimistic accents | the existing per-theme `--accent`/`--accent2`, pushed a touch more saturated in the dark variants |

**Restraint clause.** Cyberpunk fails when *everything* glows. The rule:
**one focal glow per view** (usually the thing OSA wants you to look at), calm
everywhere else. Playfulness lives in the *micro-interactions* (hover, state
transitions, empty states), not in constant motion.

---

## 3. Surface-by-surface vision

Grounded in the real components in `gui/desktop/src/`. Each entry: *today →
target → cheapest first slice.*

### 3.1 The left sidebar (nav — `App.jsx`)
- **Today:** a plain vertical list of view links + a static DIAGNOSTICS box.
- **Target:** a **command spine**. Each nav item is a live cell — a faint
  activity glyph when that subsystem has something happening (a running
  workflow, unread news, a pending approval), so the sidebar *reports* as well
  as *navigates*. The active item gets the focal glow. DIAGNOSTICS becomes a
  compact live "vitals" readout (CPU/RAM/Net) with sparklines, not static text.
- **First slice (S):** active-item glow + hover bloom using `--glow`/`--accent`;
  animate the active indicator with a spring. No new data needed.

### 3.2 The OSA rail (`OSARail.jsx` + `OSAOrb.jsx`)
- **Today:** orb + caption + Brief-me + brain picker + a flat proactive feed.
- **Target:** the **presence console**. The orb stays the star. The feed below
  becomes a *telemetry stream* — entries slide in, announced events pulse a
  hairline in the state hue, timestamps tick. The brain picker reads like a
  HUD control (labelled, glowing on focus). Sectioned for a future **vitals**
  block (already scaffolded in the rail's structure).
- **First slice (S):** feed entries animate in (slideDown, already in
  `theme.css`) + announced entries get a bloom, not just a static accent bar.

### 3.3 Dashboard screens (SysOps, Workflows, WebNews, Scripts, Projects, HubApi)
- **Today:** left-list / right-detail panels — competent, conventional.
- **Target:** each becomes a **purpose-built operations surface**:
  - **SysOps** → a live *fleet-glance*: app/health/cost tiles that pulse on
    change, the focal glow on whatever needs attention (down app, pending
    approval). (Aligns with the parked "operate your fleet" redesign in
    CONTINUATION history.)
  - **Workflows** → a *run theatre*: the active run animates through its steps;
    idle runs sit calm. Tool-call chips light up as they fire.
  - **WebNews** → a *feed wall* with more editorial hierarchy (lead story,
    rankable stream) — the AI-ranking already exists; make it *feel* ranked.
  - **Projects** → the card grid gets health as ambient light (healthy = calm
    glow, unhealthy = alert pulse), Start/Stop as tactile controls.
- **First slice (S, per view):** promote panel headers to HUD micro-labels,
  give cards a hover bloom + spring, and route every "something changed" moment
  through a shared pulse animation. Pick ONE view to prove the pattern first
  (recommend SysOps — highest daily use), then template it across.

### 3.4 The HUD window (`Hud.jsx`)
- **Today:** slim orb + caption in a separate always-on-top window.
- **Target:** a true **ambient HUD** — minimal, glassy, glanceable; the orb's
  presence distilled. This is where the sci-fi register can run purest because
  there's no dense content to compete with.
- **First slice (S):** match the orb's refined glow + a translucent glass
  backdrop.

---

## 4. Token & infrastructure work (enables everything above)

Before the surfaces can be pushed, the token system should gain a few
deliberate additions in `theme.css` (per-theme, so all 8 variants stay
coherent):

- **Focus/hover bloom token** — a stronger `--glow` variant for the "focal"
  element (e.g. `--glow-focal`), so the one-focal-glow rule is a token, not a
  magic number.
- **State-hue triples as shell tokens** — promote the orb's idea (`--orb` as an
  `r,g,b` triple) to a small shell set (`--hue-accent`, `--hue-alert`,
  `--hue-ok`) so any component can derive glows/washes consistently.
- **Motion tokens** — a spring easing var (`--ease-spring`) + a standard
  ambient-drift duration, so micro-interactions feel uniform.
- **Texture layer** — an optional, very subtle grid/scanline background
  (CSS-only, `prefers-reduced-motion`- and opacity-gated) applied to `--bg`, so
  the "sci-fi glass" reads without imagery.

All additive. `:root` (terracotta-dark) stays the default; each `[data-theme]`
block gets the new tokens tuned to its palette. **No component references a
token that doesn't exist in every theme** (conventions rule #1).

---

## 5. Phased execution plan (ponytail-sized, subagent-friendly)

Each phase is independently shippable, testable, and small enough for a
budget-limited session. Do them in order; stop anywhere with a clean tree.

- **UV-0 — Token foundation.** Add the tokens in §4 to all 8 theme blocks.
  Pure CSS. No visual change until consumed. *(effort: S)*
- **UV-1 — Orb-adjacent polish (rail).** Feed animation + announced bloom +
  brain-picker HUD styling. Proves the language next to the orb. *(effort: S)*
- **UV-2 — Sidebar command spine.** Active glow, hover bloom, spring indicator;
  DIAGNOSTICS → live vitals readout. *(effort: S–M)*
- **UV-3 — Dashboard pattern (one view).** Pick SysOps; build the HUD-label +
  card-bloom + change-pulse pattern; write it up as the template. *(effort: M)*
- **UV-4 — Template across dashboards.** Apply the UV-3 pattern to Workflows,
  Projects, WebNews, Scripts, HubApi. Mostly mechanical once the pattern
  exists. *(effort: M, splittable per view)*
- **UV-5 — HUD glass pass.** Refine the ambient HUD window. *(effort: S)*
- **UV-6 — Texture + final tuning.** Enable the subtle background texture; a
  cohesion pass across all 8 themes. *(effort: S–M)*

**Subagents:** once UV-3 establishes the pattern, UV-4's per-view work is ideal
to fan out to subagents (one view each) with the template as the spec —
supervisor verifies each against the conventions + re-runs vitest. (Subject to
the standing subagent-spend guidance in CONTINUATION.)

---

## 6. Guardrails (don't undo hard-won lessons)

- **Theme tokens only.** Every color/shadow/radius comes from `theme.css`.
  Grep new CSS for `var(--` and confirm each token exists in *every* theme
  block (conventions rule #1). Undefined vars fail silently.
- **Scoped stylesheets for hover/keyframes** (conventions rule #3) — no inline
  pseudo-state styles.
- **`prefers-reduced-motion`** — all ambient motion + texture must gate behind
  it. Reduced-motion users get a calm, colored, *static* shell.
- **New paradigm = new nav link** (GUI principle #7) — polish existing
  surfaces; don't grow always-on panels for new paradigms.
- **Accessibility isn't optional** — maintain contrast (WCAG AA) even while
  chasing glow; the dark themes especially must keep `--text` vs `--bg`
  legible. Verify muted text is actually dimmer, not invisible.
- **Verify edits persisted** (conventions rule #7) — read big-component edits
  back before claiming done.
- **One focal glow per view.** The anti-cyberpunk-soup rule. Calm is the
  default; glow is a spotlight OSA controls.

---

## 7. Relationship to OSA (why this matters functionally)

This isn't only cosmetic. The shell's job is increasingly to be **OSA's body** —
the visible surface of an assistant that watches the system and acts. The
"living system" aesthetic and OSA's presence model are the same goal from two
directions: the shell should *show* what OSA knows (health, runs, approvals,
attention) as ambient light and motion, so glancing at the app tells you the
state of your world. Every "focal glow" is, ideally, OSA pointing at something.
That's why the orb is the tuning fork — the rest of the UI is the instrument it
plays.
