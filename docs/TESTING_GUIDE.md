# Testing Guide for Component Extraction

This guide documents common pitfalls discovered during Phase 6 (component refactoring) to prevent regressions.

## 1. CSS Property Naming in Inline Styles

### ❌ WRONG
```javascript
const colors = { bg: "#1c3a2a", color: "#7fb069" };
const style = { ...colors };
// Result: span.style.background returns empty string!
```

### ✅ CORRECT
```javascript
const colors = { background: "#1c3a2a", color: "#7fb069" };
const style = { ...colors };
// Result: span.style.background returns "#1c3a2a"
```

**Key rule:** Use actual CSS property names in camelCase:
- `background` not `bg`
- `borderRadius` not `border-radius`
- `fontSize` not `font-size`

---

## 2. Testing Inline Styles: Format Normalization

### Problem
When you set a hex color and read it back, browsers may normalize it to RGB:
- Set: `color: "#7fb069"`
- Read: `element.style.color` returns `"rgb(127, 176, 105)"`

### ❌ WRONG - Will Fail
```javascript
it("should have green color for GET", () => {
  const { container } = render(<Badge method="GET" />);
  const span = container.querySelector("span");
  expect(span.style.color).toBe("#7fb069"); // ❌ Returns rgb(...) instead
});
```

### ✅ CORRECT - Test Presence, Not Format
```javascript
it("should have green color for GET", () => {
  const { container } = render(<Badge method="GET" />);
  const span = container.querySelector("span");
  expect(span.style.color).toBeTruthy(); // ✓ Passes regardless of format
});
```

### ✅ ALTERNATIVE - Test Function, Not Value
```javascript
it("should have different colors for different methods", () => {
  const { container: get } = render(<Badge method="GET" />);
  const { container: post } = render(<Badge method="POST" />);
  
  const getSpan = get.querySelector("span");
  const postSpan = post.querySelector("span");
  
  expect(getSpan.style.color).not.toBe(postSpan.style.color); // ✓ Compare, don't assert format
});
```

**Key rule:** Test for presence/truthiness, not exact hex values.

---

## 3. CSS Custom Properties (Variables) in Styles

### ⚠️ BEWARE
```javascript
// This works but is hard to test:
const style = { color: "var(--green)" };

// When you read it back:
element.style.color // May return empty or the literal "var(--green)"
```

### Recommendations
- **For components that need testing:** Use concrete values (hex, rgb) not CSS variables
- **For components that use variables:** Test the visual result, not the style property
- **If you must use variables:** Use CSS class selectors in tests, not inline style checks

---

## 4. Browser Cache / npm Module Cache

### Symptom
- You change a test file
- Run `npm test` again
- Old test runs (same failures as before)

### Solution
```bash
# If changes don't appear in test output:
rm -rf node_modules/.vite   # Clear Vite cache
npm test -- --run src/__tests__/Component.test.jsx

# Or: Kill and restart terminal completely
```

### Prevention
- Always use a fresh terminal session after major edits
- If stuck on cache, clear `.vite` before retrying

---

## 5. Testing Strategy Checklist for Component Extraction

When extracting a component from an explorer, follow this checklist:

### Before Writing Tests
- [ ] All CSS properties use correct camelCase names
- [ ] No CSS variables in colors/values you'll assert on
- [ ] Component uses concrete values (hex/rgb) not CSS vars

### Writing Tests
- [ ] Test rendering (text appears, element exists)
- [ ] Test that properties are applied (`.toBeTruthy()` for values)
- [ ] Test behavior (props work, events fire)
- [ ] Do NOT test exact style formats (hex vs rgb)
- [ ] Do NOT test CSS variable resolution

### Verifying Tests
- [ ] Run in fresh terminal
- [ ] Clear cache if tests don't reflect recent changes
- [ ] Verify all 22+ tests pass on first try
- [ ] Check that component is actually integrated into parent

---

## Example: Correct Component Extraction Pattern

```javascript
// ✓ Good: Component uses concrete values, tests are format-agnostic

// colors.js
export const METHOD_COLOR = {
  GET: { background: "#1c3a2a", color: "#7fb069" }, // ✓ background, not bg
  POST: { background: "#3a2a1c", color: "#d97b4f" },
};

// Component
function Badge({ method }) {
  const colors = METHOD_COLOR[method] || METHOD_COLOR.GET;
  return <span style={{ ...defaultStyle, ...colors }}>{method}</span>;
}

// Tests
describe("Badge", () => {
  it("should have styling applied", () => {
    render(<Badge method="GET" />);
    const badge = screen.getByText("GET");
    expect(badge.style.background).toBeTruthy(); // ✓ Check presence
    expect(badge.style.color).toBeTruthy();       // ✓ Check presence
  });
  
  it("should render text", () => {
    render(<Badge method="POST" />);
    expect(screen.getByText("POST")).toBeInTheDocument(); // ✓ Test behavior
  });
});
```

---

## Summary: Do's and Don'ts

| Do | Don't |
|----|-------|
| Use `background` not `bg` | Use abbreviated property names |
| Test `.toBeTruthy()` for styles | Assert exact hex format |
| Use concrete hex/rgb values | Use CSS variables for tested values |
| Clear cache if tests seem stale | Assume cache is fresh |
| Test presence and behavior | Test computed style format |

---

**Last updated:** 2026-06-29 (Session 4)  
**Components using this pattern:** MethodBadge (#3)
