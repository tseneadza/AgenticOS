# API registry — keeping Codehome APIs visible in AgenticOS

AgenticOS exposes **two** HTTP API surfaces, and every endpoint on either must
be discoverable + runnable from the in-app **API Explorer**
(`gui/desktop/src/components/HubApiExplorer.jsx`, the "Hub API" nav view).

| Surface | Process | Port | Base in Explorer | `server` field |
|---|---|---|---|---|
| **Hub** | Codehome Hub (Go) | `8085` | `http://localhost:8085/api` | omit (default) |
| **Sidecar** | AgenticOS FastAPI | `5130` | `http://localhost:5130` (paths already include `/api`) | `"sidecar"` |

The Explorer shows a live health dot for each server and lets you fill params,
run requests, copy curl, and see a call log.

## The rule (MANDATORY)

**When you add, rename, or remove an HTTP route anywhere under the Codehome
umbrella (a new sidecar route in `gui/sidecar/`, or a new Hub endpoint), you
MUST register the change in `HubApiExplorer.jsx` `ENDPOINTS` in the *same*
commit.** A shipped endpoint that isn't in the Explorer is considered
incomplete. This keeps the app self-documenting and gives the governing agent a
single place to discover everything the app can do.

## Registration contract

Each entry in the `ENDPOINTS` array:

```js
{
  group:  "News (Sidecar)",   // collapsible section; group new surfaces clearly
  server: "sidecar",          // "sidecar" → :5130; omit for Hub (:8085)
  method: "POST",             // GET | POST | PATCH | PUT | DELETE
  path:   "/api/news/feeds",  // sidecar: full path incl /api; Hub: path after /api
  desc:   "Create a feed",
  params: [
    { name: "id",   _in: "path",  type: "string",  required: true },
    { name: "q",    _in: "query", type: "string",  required: false, hint: "search" },
    { name: "body", _in: "body",  type: "json",    required: true,  hint: '{"label":"…"}' },
  ],
  // rootPath: true   // Hub only — endpoint lives at :8085 root, not under /api
}
```

Notes:
- Hub paths are written *relative to* `/api` (e.g. `/cards`); the base adds it.
  A Hub root path (e.g. `/health`) uses `rootPath: true`.
- Sidecar paths are written in full including `/api` (e.g. `/api/news/rank`)
  and `server: "sidecar"`.
- A new `group` name automatically becomes a new collapsible section.

## Adding a new Codehome API — checklist

1. Implement the route (sidecar router under `gui/sidecar/routes/`, or Hub).
2. Add an `ENDPOINTS` entry per the contract above (correct `server`, `method`,
   `path`, `params`, `group`).
3. If it's a new sidecar router, mount it in `gui/sidecar/app.py`.
4. Update `docs/CHANGELOG.md`.
5. Verify in the Explorer: the endpoint appears under its group, the server dot
   is green, and **Run** returns the expected response.

## Recommended automation (so this never drifts)

- **Sidecar (FastAPI):** the sidecar already serves an OpenAPI schema at
  `http://localhost:5130/openapi.json`. The durable fix is to have the Explorer
  **fetch `/openapi.json` at runtime and merge those routes into `ENDPOINTS`
  automatically** — then every new sidecar route self-registers with zero manual
  edits, and the static sidecar entries here can be dropped. (Recommended next
  step; not yet wired.)
- **Hub (Go):** no OpenAPI. Either keep the static list in sync per the rule
  above, or generate it with a script (`hub/scripts/gen_api_explorer.py`) that
  parses route registrations in `hub/cmd/server/main.go` and emits the Hub
  portion of `ENDPOINTS`.
