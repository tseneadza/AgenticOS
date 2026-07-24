# GUI / Frontend conventions & lessons

Hard-won rules for the Tauri React GUI (`gui/desktop/`). Read this before
building or editing any view/component. Each rule exists because we broke it
once — the WebNewsView case study at the end shows how.

## 1. Use the real theme tokens — never invent CSS variables

The theme is defined once in `gui/desktop/src/App.css` under `:root`. These are
the **only** custom properties that exist. Anything else resolves to nothing and
silently falls back (usually to the inherited color), which quietly destroys the
visual hierarchy without any error.

Canonical tokens (keep this list in sync with `App.css :root`):

| Token            | Value     | Use                                   |
|------------------|-----------|---------------------------------------|
| `--bg`           | `#1b1b19` | App background                        |
| `--bg-panel`     | `#222220` | Panel / card surface                 |
| `--bg-inset`     | `#191917` | Inset surfaces, toolbars, inputs     |
| `--border`       | `#888780` | Strong section borders               |
| `--border-soft`  | `#4a4a46` | Card / control borders               |
| `--text`         | `#e8e6df` | Primary text                         |
| `--text-dim`     | `#a09e95` | Muted text (timestamps, labels)      |
| `--accent`       | `#d97b4f` | Accent (amber/orange)                |
| `--green`        | `#7fb069` | Success / positive                   |
| `--red`          | `#d9534f` | Error                                |
| `--yellow`       | `#e0b84c` | Warning / highlight                  |
| `--mono`         | font     | Monospace stack                      |

**Rules:**
- There is **no** `--fg` / `--fg-muted`. Use `--text` / `--text-dim`. Shape
  tokens DO exist since FR-60: `--radius`, `--radius-sm` (derived,
  chips/inputs), `--glow` (elevation), `--accent2`, `--sans` — defined in
  `theme.css` (the single source of truth; the table above shows terra
  defaults). New tokens go in `theme.css :root` first — never reference a
  token that doesn't exist.
- Prefer tokens over literals: `border-radius: var(--radius)` (panels/cards)
  / `var(--radius-sm)` (chips, inputs, badges); elevation shadows =
  `box-shadow: var(--glow)`; fixed semantic hues get token-derived
  backgrounds via `color-mix(in srgb, <hue> 14%, var(--bg-inset))`.
  Pills (`50%`/`999px`) and hairline radii (≤2px) stay literal.
- When you paste a component from elsewhere (or another design system), grep it
  for `var(--` and confirm **every** token appears in `App.css :root`.
- Undefined CSS vars fail silently. A component can "work" and still be wrong.
  Verify muted text is actually dimmer than primary text in the running app.

## 2. Text on accent backgrounds

`--accent` is light enough that black-on-accent reads best. Use `color: #1b1b19`
(the app bg) for text/icons sitting on an `--accent` fill (primary buttons,
active pills), not `#000` and not `--text`.

## 3. Hover / transitions / keyframes — inject a scoped stylesheet

Inline styles can't express `:hover`, transitions that depend on pseudo-states,
or `@keyframes`. Instead of `onMouseEnter`/`onMouseLeave` handlers, inject a
small component-scoped `<style>` block once (see `WebNewsView.jsx`
`useScopedStyles` + `wnv-*` classes) and use real CSS. Keep class names
component-prefixed to avoid collisions.

## 4. RSS / feed-reader rules (sidecar `_fetch_rss` in `gui/sidecar/app.py`)

- **Extract images BEFORE stripping HTML.** Article images live in
  `media:content` / `media:thumbnail`, `<enclosure>`, Atom enclosure `<link>`,
  or embedded `<img>` inside `content:encoded` / `description`. The summary
  HTML-strip (`re.sub(r"<[^>]+>", "", ...)`) destroys embedded `<img>`, so grab
  the image off the raw element/HTML first. See `_extract_image`.
- **Don't over-truncate summaries.** A tight server-side cap (we had `[:400]`)
  silently caps what the client can ever show — "show more" then reveals
  nothing new. arXiv abstracts run ~1000–1500 chars; the cap is `[:2000]`.
- Per-item shape returned to the client:
  `{ id, title, link, summary, image, published, domain }`.
- The feed cache has a 15-minute TTL (`_RSS_TTL`). After changing the parser you
  must restart the sidecar (or wait out the cache) to see re-parsed items —
  old cached entries keep the old shape.

## 5. "Show more / less" — gate on real overflow, not character count

Don't decide whether to show an expand toggle from `summary.length > N`. A long
string can still fit the clamp on a wide card, so the button does nothing.
Measure actual overflow with a ref:

```jsx
const ref = useRef(null);
const [overflowing, setOverflowing] = useState(false);
useLayoutEffect(() => {
  const el = ref.current;
  if (!el || expanded) return;
  setOverflowing(el.scrollHeight > el.clientHeight + 2);
}, [text, expanded]);
// render the toggle only when (overflowing || expanded)
```

When expanded, render plain unclamped text (`white-space: pre-wrap`), not a
`-webkit-box` with `line-clamp: unset` — fully drop the clamp so nothing
lingers.

## 6. Images from third-party feeds

Render with `loading="lazy"` and `referrerPolicy="no-referrer"`, and add an
`onError` handler that hides the `<img>` (some publishers block hotlinking).
A missing/blocked image must degrade gracefully, never leave a broken-image box.

## 7. Verify edits actually persisted

Large files have bitten us: an edit tool can report success while the change
isn't on disk (or a later write clobbers it). After editing a big component,
**read the region back** and confirm the change is present before claiming it's
done — especially when the user reports "nothing changed."

## 8. You can't run the Tauri build from the assistant sandbox

The repo isn't mounted in the bash sandbox, so `npm run tauri dev` / `pytest`
can't run here. Verify changes by (a) reading diffs back, (b) parsing isolated
logic (e.g. a regex) in the sandbox, and (c) handing Tony the exact build/verify
command. Frontend JS/CSS-only changes hot-reload; sidecar changes need a
restart.

## 9. Layered/concentric visuals — siblings don't overlap by default

Orbs, spinners, gauges, badges: siblings never stack on top of each other in
normal flow, flex, OR grid. `display: grid; place-items: center` alone puts
each child in its **own implicit row** — the layers scatter vertically (the
2026-07-10 "exploded OSAOrb" bug: rings at the rail top, core at the bottom,
all 43 tests green). Opt in explicitly:

```css
.stage > * { grid-area: 1 / 1; }   /* grid stack — never omit */
```

or `position: absolute` centering (beware: transform-centering fights
transform keyframes). **jsdom computes no layout, so vitest can NEVER catch
this** — a layered-visual change is unverified until seen on-device
(`npm run tauri dev`; a built bundle won't show file edits). Full patterns +
mockup-porting checklist: `skills/css-layered-visuals`.

---

## Case study — WebNews view polish (2026-06-23)

Symptoms reported, root causes, fixes:

1. *"It looks flat / off."* → The component used `var(--fg)` / `var(--fg-muted)`,
   which don't exist in the theme, so all "muted" text rendered at full strength.
   **Fix:** switched to `--text` / `--text-dim` (rule 1).
2. *"Some articles have a show-more button that does nothing."* → Button gated on
   `summary.length > 150`; many such summaries fit the 2-line clamp.
   **Fix:** overflow measurement (rule 5).
3. *"Show me images if the article has one."* → Backend never extracted images
   and stripped the HTML that held them. **Fix:** `_extract_image` before strip
   + thumbnail in the card (rules 4, 6).
4. *"When I click show more, not all the text is visible."* → Two causes: the
   server `[:400]` summary cap, and an earlier component edit that hadn't
   persisted. **Fix:** raised cap to `[:2000]`; re-applied and verified the edit
   by reading it back (rules 4, 7).
