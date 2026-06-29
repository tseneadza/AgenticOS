/**
 * Mock API endpoint data for testing
 */

export const mockEndpoint = {
  group: "Cards",
  method: "GET",
  path: "/cards",
  desc: "List all registered project cards",
  params: [],
};

export const mockEndpoints = [
  {
    group: "Cards",
    method: "GET",
    path: "/cards",
    desc: "List all registered project cards",
    params: [],
  },
  {
    group: "Cards",
    method: "GET",
    path: "/cards/{id}",
    desc: "Single card detail",
    params: [{ name: "id", _in: "path", type: "string", required: true, hint: "e.g. dreamcatcher" }],
  },
  {
    group: "Cards",
    method: "POST",
    path: "/cards/{id}/start",
    desc: "Start the card service",
    params: [{ name: "id", _in: "path", type: "string", required: true }],
  },
  {
    group: "Logs & Env",
    method: "GET",
    path: "/cards/{id}/logs",
    desc: "Fetch recent log output",
    params: [
      { name: "id", _in: "path", type: "string", required: true },
      { name: "lines", _in: "query", type: "number", required: false, hint: "50" },
    ],
  },
  {
    group: "Scripts",
    method: "GET",
    path: "/scripts",
    desc: "All registered scripts",
    params: [],
  },
  {
    group: "Scripts",
    method: "POST",
    path: "/scripts/run",
    desc: "Execute a script",
    params: [{ name: "body", _in: "body", type: "json", required: true }],
  },
  {
    group: "System",
    method: "GET",
    path: "/health",
    desc: "Hub server health",
    params: [],
    rootPath: true,
  },
];

export const mockResponse = {
  status: 200,
  text: JSON.stringify({ success: true, data: { cards: [] } }, null, 2),
  ok: true,
  dur: 125,
};

export const mockErrorResponse = {
  status: 404,
  text: JSON.stringify({ error: "Not found" }, null, 2),
  ok: false,
  dur: 85,
};

export const mockCallLog = [
  {
    method: "GET",
    path: "/cards",
    status: 200,
    ok: true,
    dur: 125,
    ts: new Date(),
  },
  {
    method: "POST",
    path: "/cards/my-app/start",
    status: 200,
    ok: true,
    dur: 456,
    ts: new Date(Date.now() - 5000),
  },
  {
    method: "GET",
    path: "/cards/nonexistent",
    status: 404,
    ok: false,
    dur: 85,
    ts: new Date(Date.now() - 10000),
  },
];
