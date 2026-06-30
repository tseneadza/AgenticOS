# Phase 7: Integration Testing Strategy

**Goal:** Verify that extracted components work together correctly in real explorer workflows  
**Scope:** HubApiExplorer + ScriptsExplorer integration tests  
**Entry Criteria:** All 238 Phase 6 tests passing ✅  
**Target:** 50+ integration tests covering end-to-end workflows

---

## What We're Testing

### Workflow 1: Filter → Collapse → Select → View Details

**HubApiExplorer:**
```
1. Load explorer (endpoints rendered in groups)
2. User types in FilterBar ("GET")
3. Endpoints filtered dynamically
4. User clicks GroupHeader to collapse "Cards" group
5. Group collapses (items hidden, chevron rotates)
6. User clicks EndpointListItem to select endpoint
7. Right panel shows ResponseDisplay (empty initially)
```

**Test:** All 5 components work together without conflicts

### Workflow 2: Run Script → Log Entry Appears

**ScriptsExplorer:**
```
1. User selects script from ScriptItem list
2. Details panel shows script info
3. User clicks Run button
4. Script executes (runs in sidecar)
5. Call log updates immediately
6. New CallLogEntry appears with status + duration
7. Color-coded by success/failure (green/red)
```

**Test:** Data flows from UI → sidecar → back to UI correctly

### Workflow 3: Tab Switching with State Persistence

**HubApiExplorer:**
```
1. User clicks "Call Log" tab (TabSwitcher)
2. Explorer view hides, call log shows
3. User clicks "Explorer" tab
4. Explorer state restored (same selection, same filter)
5. No data lost on switch
```

**Test:** Tab switching preserves component state correctly

### Workflow 4: Multi-Component Rendering

**HubApiExplorer EndpointListItem + subcomponents:**
```
1. EndpointListItem renders
2. MethodBadge inside shows correct color for HTTP method
3. PathDisplay inside highlights parameters {id}
4. Selection border appears/disappears on click
5. Keyboard navigation works (Tab → focus → Enter selects)
```

**Test:** Nested components render and sync correctly

---

## Test Structure

```
src/__tests__/integration/
├── HubApiExplorer.integration.test.jsx
│   ├── Filter workflow
│   ├── Collapse/expand workflow
│   ├── Tab switching workflow
│   └── Selection + detail workflow
│
├── ScriptsExplorer.integration.test.jsx
│   ├── Script selection workflow
│   ├── Run script workflow (mock sidecar)
│   ├── Call log entry workflow
│   └── Group collapse workflow
│
└── CrossExplorer.integration.test.jsx
    ├── Theme switching across explorers
    ├── Layout consistency
    └── Error handling across components
```

---

## Test Techniques

### 1. Mock User Interactions
```javascript
it("filter → collapse → select workflow", async () => {
  const { user } = render(<HubApiExplorer />);
  
  // Step 1: Type in filter
  const filterInput = screen.getByTestId("filter-input");
  await user.type(filterInput, "GET");
  
  // Step 2: Verify filtered endpoints
  expect(screen.getByTestId("endpoint-GET-/cards")).toBeInTheDocument();
  expect(screen.queryByTestId("endpoint-POST-/scripts")).not.toBeInTheDocument();
  
  // Step 3: Click collapse button
  const groupHeader = screen.getByTestId("group-header-Cards");
  await user.click(groupHeader);
  
  // Step 4: Verify items hidden
  expect(screen.queryByTestId("endpoint-GET-/cards/favorites")).not.toBeInTheDocument();
});
```

### 2. Verify State Synchronization
```javascript
it("selection persists across tab switch", async () => {
  const { user } = render(<HubApiExplorer />);
  
  // Select endpoint
  const item = screen.getByTestId("endpoint-list-item-GET-/cards");
  await user.click(item);
  expect(item).toHaveAttribute("aria-selected", "true");
  
  // Switch to call log tab
  const callLogTab = screen.getByTestId("tab-button-calllog");
  await user.click(callLogTab);
  
  // Switch back to explorer
  const explorerTab = screen.getByTestId("tab-button-explorer");
  await user.click(explorerTab);
  
  // Selection should be preserved
  expect(item).toHaveAttribute("aria-selected", "true");
});
```

### 3. Mock API Responses
```javascript
it("endpoint response appears in ResponseDisplay", async () => {
  // Mock the fetch response
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ data: "..." })
    })
  );
  
  render(<HubApiExplorer />);
  
  // Trigger API call (click try/execute button)
  // Verify ResponseDisplay shows result
});
```

### 4. Keyboard Navigation
```javascript
it("Tab navigation through interactive elements", async () => {
  render(<HubApiExplorer />);
  
  const filterInput = screen.getByTestId("filter-input");
  filterInput.focus();
  
  // Tab to first endpoint
  await user.keyboard("{Tab}");
  expect(screen.getByTestId("endpoint-0")).toHaveFocus();
  
  // Tab to group header
  await user.keyboard("{Tab}");
  expect(screen.getByTestId("group-header-0")).toHaveFocus();
});
```

---

## Success Criteria

Each workflow test must verify:
- [ ] All components render without errors
- [ ] User interactions work (click, type, keyboard)
- [ ] State updates correctly
- [ ] Data flows correctly between components
- [ ] No console errors or warnings
- [ ] Accessibility attributes present
- [ ] Performance acceptable (< 500ms per interaction)

---

## Baseline Metrics

**Current Status (Phase 6):**
- Unit tests: 238/238 passing ✅
- Component isolation: verified
- Individual component performance: < 100ms render

**Phase 7 Goals:**
- Integration tests: 50+ passing
- End-to-end workflows: all verified
- Performance regression: none
- Code coverage: maintain >80%

---

## Test Data Setup

Mock fixtures for integration tests:
```javascript
const mockEndpoints = [
  { _i: 0, method: "GET", path: "/cards", group: "Cards" },
  { _i: 1, method: "POST", path: "/scripts", group: "Scripts" },
  // ... 40 more
];

const mockScripts = [
  { id: "s1", name: "start-server", type: "Launcher", project: "Core" },
  { id: "s2", name: "run-tests", type: "Test", project: "Core" },
  // ... 150 more
];
```

---

## Phase 7 Execution Plan

### Week 1: HubApiExplorer Integration
- Filter workflow test
- Collapse/expand workflow test
- Tab switching workflow test
- Nested component rendering test

### Week 2: ScriptsExplorer Integration
- Script selection workflow test
- Script run workflow test (mock execution)
- Call log entry workflow test
- Group filtering workflow test

### Week 3: Cross-Explorer & Polish
- Cross-explorer theme switching
- Layout consistency
- Error recovery workflows
- Accessibility audit (all 50+ tests)

---

## Deliverables

- [ ] `src/__tests__/integration/HubApiExplorer.integration.test.jsx` (15+ tests)
- [ ] `src/__tests__/integration/ScriptsExplorer.integration.test.jsx` (20+ tests)
- [ ] `src/__tests__/integration/CrossExplorer.integration.test.jsx` (15+ tests)
- [ ] `docs/INTEGRATION_TESTING_GUIDE.md` (patterns + learnings)
- [ ] Updated test coverage report
- [ ] Git commits with clear test descriptions

---

## Estimated Effort

| Task | Estimated Time | Effort |
|------|-----------------|--------|
| HubApiExplorer workflows | 3 hours | Medium |
| ScriptsExplorer workflows | 3 hours | Medium |
| Cross-explorer tests | 2 hours | Medium |
| Documentation | 1 hour | Light |
| Total | ~9 hours | 1–2 sessions |

---

## Risk Mitigation

**Risk:** Tests fail due to state management complexity
**Mitigation:** Start simple (one filter, one click), build up

**Risk:** Mock API responses don't match real behavior
**Mitigation:** Use real API fixtures extracted from actual responses

**Risk:** Tests become flaky (timing issues)
**Mitigation:** Use `waitFor()` with sensible timeouts, avoid arbitrary sleeps

**Risk:** Performance regresses with all tests running
**Mitigation:** Benchmark component render times, keep within Phase 6 baseline

---

## Notes for Future Sessions

When starting Phase 7:
1. Read this document (5 min)
2. Run Phase 6 tests to confirm baseline (2 min)
3. Pick first workflow (filter → collapse → select)
4. Write one test end-to-end, get it passing
5. Use as template for remaining tests
6. Reference Phase 6 test patterns frequently

The Phase 6 components are well-tested in isolation. Phase 7 is about verifying they work together at scale.
