import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ProjectsView from "../components/ProjectsView";

// ProjectsView fetches /api/projects once and polls /api/apps; expanding a
// card adds /api/apps/{id}/status + /api/apps/{id}/launch-plan. Start/Stop
// POST to /api/apps/{id}/start|stop. We stub global fetch per-path.
const PROJECTS = {
  available: true,
  total: 2,
  projects: [
    { id: "worldwise", name: "worldwise", template: "imported", subfolder: "SpecProj",
      port: 5173, path: "/tmp/worldwise", github_repo_url: "https://github.com/t/worldwise",
      created_at: "2026-07-01T00:00:00" },
    { id: "keno", name: "keno", template: "imported", subfolder: "Games",
      port: 5115, path: "/tmp/keno", github_repo_url: null,
      created_at: "2026-07-01T00:00:00" },
  ],
};

const APPS = {
  available: true,
  apps: [
    { id: "worldwise", running: true, pid: 111, port_live: 5173, url: "http://localhost:5173" },
    { id: "keno", running: false, pid: null, port_live: null, url: null },
  ],
};

const STATUS_WORLDWISE = {
  app_id: "worldwise", running: true, pid: 111, port: 5173,
  processes: [
    { pid: 111, port: 8000, port_type: "backend", status: "running", started_at: "2026-07-03T10:00:00",
      is_healthy: true, last_health_check: "2026-07-03T10:05:00" },
    { pid: 112, port: 5173, port_type: "frontend", status: "stopped", started_at: "2026-07-03T10:00:01",
      is_healthy: true, last_health_check: null },
  ],
};

const HEALTH = {
  available: true, total: 1,
  apps: {
    worldwise: {
      healthy: true,
      ports: [{ port: 8000, is_healthy: true, last_health_check: "2026-07-03T10:05:00" }],
    },
  },
};

const PLAN_WORLDWISE = {
  available: true, configured: true, app_id: "worldwise", total: 2,
  steps: [
    { step: 1, command: "uvicorn", args: ["main:app", "--port", "8000"], cwd: "/tmp/worldwise/backend",
      port: 8000, port_type: "backend", wait_for_completion: false, wait_for_port: true, timeout_seconds: 30 },
    { step: 2, command: "npm", args: ["run", "dev"], cwd: "/tmp/worldwise/web",
      port: 5173, port_type: "frontend", wait_for_completion: false, wait_for_port: false, timeout_seconds: 30 },
  ],
};

function stubFetch(overrides = {}) {
  const calls = [];
  global.fetch = vi.fn((url, opts = {}) => {
    calls.push({ url, method: opts.method || "GET" });
    const respond = (body) =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    if (url.includes("/api/projects")) return respond(overrides.projects ?? PROJECTS);
    if (url.includes("/launch-plan")) return respond(overrides.plan ?? PLAN_WORLDWISE);
    if (url.includes("/status")) return respond(overrides.status ?? STATUS_WORLDWISE);
    if (url.includes("/start") || url.includes("/stop")) return respond({ ok: true });
    if (url.includes("/api/apps/health")) return respond(overrides.health ?? HEALTH);
    if (url.includes("/api/apps")) return respond(overrides.apps ?? APPS);
    return Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({}) });
  });
  return calls;
}

describe("ProjectsView", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    delete global.fetch;
  });

  it("renders a card per ledger project with the count header", async () => {
    stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-worldwise")).toBeInTheDocument());
    expect(screen.getByTestId("pv-card-keno")).toBeInTheDocument();
    expect(screen.getByText(/2 projects · 1 running/)).toBeInTheDocument();
  });

  it("shows green badge for running and red for stopped apps", async () => {
    stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-badge-running")).toBeInTheDocument());
    expect(screen.getByTestId("pv-badge-stopped")).toBeInTheDocument();
  });

  it("expanding a card loads process detail and the launch plan", async () => {
    stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-worldwise")).toBeInTheDocument());

    const card = screen.getByTestId("pv-card-worldwise");
    fireEvent.click(card.querySelector(".pv-expand-toggle"));

    await waitFor(() => expect(screen.getByTestId("pv-procs-worldwise")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("pv-plan-worldwise")).toBeInTheDocument());
    expect(screen.getByText(/uvicorn main:app --port 8000/)).toBeInTheDocument();
    // mixed process states → partial (yellow) badge
    await waitFor(() => expect(screen.getByTestId("pv-badge-partial")).toBeInTheDocument());
  });

  it("shows the no-launch-config note for unconfigured apps", async () => {
    stubFetch({
      plan: { available: true, configured: false, steps: [], total: 0,
              reason: "no app_commands configured for 'worldwise'" },
      status: { app_id: "worldwise", running: true, pid: 111, processes: [] },
    });
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-worldwise")).toBeInTheDocument());
    fireEvent.click(
      screen.getByTestId("pv-card-worldwise").querySelector(".pv-expand-toggle"));
    await waitFor(() =>
      expect(screen.getByText(/No launch config/)).toBeInTheDocument());
  });

  it("Stop POSTs to /api/apps/{id}/stop for a running app", async () => {
    const calls = stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-worldwise")).toBeInTheDocument());

    const stopBtn = screen.getByTestId("pv-card-worldwise")
      .querySelector(".pv-btn-stop");
    fireEvent.click(stopBtn);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/apps/worldwise/stop")))
        .toBe(true));
  });

  it("Start POSTs to /api/apps/{id}/start for a stopped app", async () => {
    const calls = stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-keno")).toBeInTheDocument());

    const startBtn = screen.getByTestId("pv-card-keno").querySelector(".pv-btn-start");
    fireEvent.click(startBtn);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && c.url.includes("/api/apps/keno/start")))
        .toBe(true));
  });

  it("shows the health chip for running apps with HTTP health data (13e)", async () => {
    stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-health-healthy")).toBeInTheDocument());
    // keno is stopped + unchecked — exactly one chip
    expect(screen.getAllByText(/healthy/).length).toBe(1);
  });

  it("shows an unhealthy chip when a checked port is failing", async () => {
    stubFetch({
      health: {
        available: true, total: 1,
        apps: { worldwise: { healthy: false,
          ports: [{ port: 8000, is_healthy: false, last_health_check: "2026-07-03T10:05:00" }] } },
      },
    });
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-health-unhealthy")).toBeInTheDocument());
  });

  it("renders per-process health marks in the expanded detail", async () => {
    stubFetch();
    render(<ProjectsView />);
    await waitFor(() => expect(screen.getByTestId("pv-card-worldwise")).toBeInTheDocument());
    fireEvent.click(
      screen.getByTestId("pv-card-worldwise").querySelector(".pv-expand-toggle"));
    await waitFor(() => expect(screen.getByTestId("pv-procs-worldwise")).toBeInTheDocument());
    const table = screen.getByTestId("pv-procs-worldwise");
    expect(table.textContent).toContain("✓");    // checked + healthy row
    expect(table.textContent).toContain("—");    // unchecked row
  });

  it("degrades gracefully when the ledger is unavailable", async () => {
    stubFetch({ projects: { available: false, total: 0, projects: [] } });
    render(<ProjectsView />);
    await waitFor(() =>
      expect(screen.getByText(/ledger unavailable/)).toBeInTheDocument());
    expect(screen.getByText(/No projects in the ledger/)).toBeInTheDocument();
  });
});
