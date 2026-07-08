import { useState, useEffect } from "react";
import MethodBadge from "./MethodBadge";
import PathDisplay from "./PathDisplay";
import StatusIndicator from "./StatusIndicator";
import ResponseDisplay from "./ResponseDisplay";
import ParamInput from "./ParamInput";
import GroupHeader from "./GroupHeader";
import FilterBar from "./FilterBar";
import CallLogEntry from "./CallLogEntry";
import TabSwitcher from "./TabSwitcher";
import EndpointListItem from "./EndpointListItem";
import LogsExplorer from "./LogsExplorer";
import { pollMs, sidecarUrl, sidecarHost } from "../settings";

const HUB = "http://localhost:8085/api";  // decommissioned hub — left for a later phase

// All 75+ Hub + Sidecar + App API endpoints (comprehensive list)
const ENDPOINTS_HARDCODED = [
  // ─── UFC App (Flask) @ :5000 ───────────────────────────────────────────
  { group:"UFC (Flask)", method:"GET",    path:"/api/search",             desc:"Search fighters by name", params:[{name:"q",_in:"query",type:"string",required:true,hint:"e.g. Conor"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/fighters/{letter}",  desc:"Get fighters by last name letter", params:[{name:"letter",_in:"path",type:"string",required:true,hint:"a-z"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/fighter/details",    desc:"Get fighter detailed info", params:[{name:"url",_in:"query",type:"string",required:true,hint:"UFCStats URL"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/fighter/complete",   desc:"Get complete fighter info (merged sources)", params:[{name:"name",_in:"query",type:"string",required:true,hint:"e.g. Conor McGregor"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/popular",            desc:"Get data on popular UFC fighters", params:[] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/alphabet",           desc:"Get alphabet index for fighter search", params:[] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/favorites",          desc:"Get all favorite fighters", params:[] },
  { group:"UFC (Flask)", method:"POST",   path:"/api/favorites/{name}",   desc:"Add fighter to favorites", params:[{name:"name",_in:"path",type:"string",required:true}] },
  { group:"UFC (Flask)", method:"DELETE", path:"/api/favorites/{name}",   desc:"Remove fighter from favorites", params:[{name:"name",_in:"path",type:"string",required:true}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/cache/stats",        desc:"Get database cache statistics", params:[] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/upcoming",           desc:"Get upcoming UFC events", params:[{name:"limit",_in:"query",type:"number",required:false,hint:"10"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/completed",          desc:"Get completed UFC events", params:[{name:"limit",_in:"query",type:"number",required:false,hint:"3"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/event/details",      desc:"Get event details & fight card", params:[{name:"url",_in:"query",type:"string",required:true,hint:"UFCStats event URL"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/fight/stats",        desc:"Get detailed fight statistics", params:[{name:"url",_in:"query",type:"string",required:true,hint:"UFCStats fight URL"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/news",               desc:"Get latest UFC/MMA news", params:[{name:"limit",_in:"query",type:"number",required:false,hint:"10"}] },
  { group:"UFC (Flask)", method:"GET",    path:"/api/health/ufcstats",    desc:"Check UFC Stats website availability", params:[] },

  { group:"Cards", method:"GET",    path:"/cards",                    desc:"List all registered project cards", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/favorites",          desc:"Cards marked as favourite", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/recent",             desc:"Recently accessed cards", params:[] },
  { group:"Cards", method:"GET",    path:"/cards/{id}",               desc:"Single card detail", params:[{name:"id",_in:"path",type:"string",required:true,hint:"e.g. dreamcatcher"}] },
  { group:"Cards", method:"GET",    path:"/cards/{id}/status",        desc:"Running / stopped status", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"GET",    path:"/cards/{id}/health",        desc:"Health check for card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/start",         desc:"Start the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/stop",          desc:"Stop the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/restart",       desc:"Restart the card service", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"POST",   path:"/cards/{id}/favorite",      desc:"Mark card as favourite", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Cards", method:"DELETE", path:"/cards/{id}/favorite",      desc:"Remove from favourites", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/logs",        desc:"Fetch recent log output", params:[{name:"id",_in:"path",type:"string",required:true},{name:"lines",_in:"query",type:"number",required:false,hint:"50"}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/logs/stream", desc:"SSE stream of live logs", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"GET",    path:"/cards/{id}/env",         desc:"Get environment variables", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Logs & Env", method:"POST",   path:"/cards/{id}/env",         desc:"Set / update env vars", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"KEY":"value"}'}] },
  { group:"Logs & Env", method:"DELETE", path:"/cards/{id}/env/{key}",   desc:"Delete an env var", params:[{name:"id",_in:"path",type:"string",required:true},{name:"key",_in:"path",type:"string",required:true}] },
  { group:"Scripts", method:"GET",  path:"/scripts",             desc:"All registered scripts", params:[] },
  { group:"Scripts", method:"GET",  path:"/cards/{id}/scripts",  desc:"Scripts for a specific card", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Scripts", method:"POST", path:"/scripts/run",         desc:"Execute a script", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"script":"path/to/script.sh"}'}] },
  { group:"Scripts", method:"GET",  path:"/scripts/terminal",    desc:"Open terminal for scripts", params:[] },
  { group:"Analytics", method:"GET", path:"/analytics",              desc:"Global analytics data", params:[] },
  { group:"Analytics", method:"GET", path:"/cards/{id}/analytics",   desc:"Per-card analytics", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Discovery", method:"GET",  path:"/tags",      desc:"All card tags", params:[] },
  { group:"Discovery", method:"GET",  path:"/ports",     desc:"Port assignments", params:[] },
  { group:"Discovery", method:"POST", path:"/discover",  desc:"Re-discover local projects", params:[] },
  { group:"Discovery", method:"POST", path:"/stop-all",  desc:"Stop all running services", params:[] },
  { group:"Jupyter", method:"GET",  path:"/jupyter/directories", desc:"List notebook directories", params:[] },
  { group:"Jupyter", method:"POST", path:"/jupyter/launch",      desc:"Launch a Jupyter server", params:[{name:"body",_in:"body",type:"json",required:false,hint:'{"dir":"/path/to/notebooks"}'}] },
  { group:"Jupyter", method:"GET",  path:"/jupyter/status",      desc:"Jupyter running status", params:[] },
  { group:"Jupyter", method:"POST", path:"/jupyter/stop",        desc:"Stop Jupyter server", params:[] },
  { group:"System", method:"GET", path:"/health", desc:"Hub server health (root level)", params:[], rootPath:true },
  { group:"News (Sidecar)", server:"sidecar", method:"GET",    path:"/api/news/categories",      desc:"List feed categories (id, name, color)", params:[] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/categories",      desc:"Create a category", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"name":"Robotics","color":"#7fb069"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"PATCH",  path:"/api/news/categories/{id}", desc:"Update a category", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"color":"#d97b4f"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"DELETE", path:"/api/news/categories/{id}", desc:"Delete a category (and its feeds)", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"News (Sidecar)", server:"sidecar", method:"GET",    path:"/api/news/feeds",           desc:"List feeds (joined to category)", params:[{name:"enabled_only",_in:"query",type:"boolean",required:false,hint:"true"},{name:"category_id",_in:"query",type:"string",required:false}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/feeds",           desc:"Create a feed", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"label":"New Scientist","url":"https://...","category_id":"physics-space"}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"PATCH",  path:"/api/news/feeds/{id}",      desc:"Update a feed (enable/disable, recategorize)", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"enabled":false}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"DELETE", path:"/api/news/feeds/{id}",      desc:"Delete a feed", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/fetch",           desc:"Fetch + keyword-filter RSS items", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"urls":["https://..."],"keywords":["quantum"]}'}] },
  { group:"News (Sidecar)", server:"sidecar", method:"POST",   path:"/api/news/rank",            desc:"AI-rank articles via the app's active model", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"articles":[{"title":"…"}],"domains":[],"keywords":[]}'}] },

  // ─── Task Management (Sidecar) ─────────────────────────────────────────
  { group:"Tasks (Sidecar)", server:"sidecar", method:"GET",    path:"/api/tasks",        desc:"List all tasks", params:[] },
  { group:"Tasks (Sidecar)", server:"sidecar", method:"POST",   path:"/api/tasks",        desc:"Create a new task", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"title":"Task name","status":"pending"}'}] },
  { group:"Tasks (Sidecar)", server:"sidecar", method:"GET",    path:"/api/tasks/{task_id}", desc:"Get single task", params:[{name:"task_id",_in:"path",type:"string",required:true}] },
  { group:"Tasks (Sidecar)", server:"sidecar", method:"PATCH",  path:"/api/tasks/{task_id}", desc:"Update task", params:[{name:"task_id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"status":"completed"}'}] },
  { group:"Tasks (Sidecar)", server:"sidecar", method:"DELETE", path:"/api/tasks/{task_id}", desc:"Delete task", params:[{name:"task_id",_in:"path",type:"string",required:true}] },
  { group:"Tasks (Sidecar)", server:"sidecar", method:"GET",    path:"/api/tasks/stats",  desc:"Get task statistics", params:[] },

  // ─── Configuration (Sidecar) ────────────────────────────────────────────
  { group:"Config (Sidecar)", server:"sidecar", method:"GET",    path:"/api/config",      desc:"Get all configuration", params:[] },
  { group:"Config (Sidecar)", server:"sidecar", method:"PUT",    path:"/api/config",      desc:"Update configuration", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"key":"value"}'}] },
  { group:"Config (Sidecar)", server:"sidecar", method:"POST",   path:"/api/config/test",  desc:"Test configuration", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"config":"object"}'}] },

  // ─── Workflows & Approvals (Sidecar) ────────────────────────────────────
  { group:"Workflows (Sidecar)", server:"sidecar", method:"GET",  path:"/api/workflows",           desc:"List all workflows", params:[] },
  { group:"Workflows (Sidecar)", server:"sidecar", method:"POST", path:"/api/workflows/{name}/run", desc:"Run a workflow by name", params:[{name:"name",_in:"path",type:"string",required:true}] },
  { group:"Workflows (Sidecar)", server:"sidecar", method:"GET",  path:"/api/approvals",          desc:"Get pending approvals", params:[] },
  { group:"Workflows (Sidecar)", server:"sidecar", method:"POST", path:"/api/approvals/{approval_id}", desc:"Respond to approval", params:[{name:"approval_id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"approved":true}'}] },

  // ─── Agent (Sidecar) ───────────────────────────────────────────────────
  { group:"Agent (Sidecar)", server:"sidecar", method:"GET",  path:"/api/agent/models", desc:"List available LLM models", params:[] },
  { group:"Agent (Sidecar)", server:"sidecar", method:"POST", path:"/api/agent/model",  desc:"Set active LLM model", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"model":"gpt-4"}'}] },
  { group:"Agent (Sidecar)", server:"sidecar", method:"POST", path:"/api/agent/chat",   desc:"Chat with agent", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"message":"Hello"}'}] },

  // ─── Native App Registry (Sidecar) ─────────────────────────────────────
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps",           desc:"List all registered apps", params:[] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/manifests", desc:"Get app manifests", params:[] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/{app_id}", desc:"Get app details", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/processes", desc:"All DB-tracked running processes across apps (13c)", params:[] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/health", desc:"Aggregated per-app HTTP health (13e; apps without checks omitted)", params:[] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/{app_id}/status", desc:"Get app status (running/stopped + app_processes detail)", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/{app_id}/launch-plan", desc:"Resolved launch-config steps (13d; configured=false for legacy-launch apps)", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"POST",   path:"/api/apps/{app_id}/start", desc:"Start an app (launch-config plan or legacy registry)", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"POST",   path:"/api/apps/{app_id}/stop",  desc:"Stop an app (process-group kill; returns killed_pids)", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"POST",   path:"/api/apps/{app_id}/restart", desc:"Restart an app", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"GET",    path:"/api/apps/{app_id}/logs",  desc:"Get app logs", params:[{name:"app_id",_in:"path",type:"string",required:true}] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"POST",   path:"/api/apps/refresh",   desc:"Refresh app registry", params:[] },
  { group:"Apps (Sidecar)", server:"sidecar", method:"POST",   path:"/api/apps/stop-all",  desc:"Stop all running apps", params:[] },

  // ─── Projects (Sidecar) — Phase 11c project scaffolding ──────────────
  { group:"Projects (Sidecar)", server:"sidecar", method:"GET",  path:"/api/projects",            desc:"List scaffolded projects (DB ledger)", params:[] },
  { group:"Projects (Sidecar)", server:"sidecar", method:"GET",  path:"/api/projects/templates",  desc:"List the 10 built-in project templates", params:[] },
  { group:"Projects (Sidecar)", server:"sidecar", method:"GET",  path:"/api/projects/subfolders", desc:"~/Codehome subfolder discovery (suggested + all)", params:[] },
  { group:"Projects (Sidecar)", server:"sidecar", method:"GET",  path:"/api/projects/port-check", desc:"Check if a port is free (ledger + TCP probe)", params:[{name:"port",_in:"query",type:"number",required:true,hint:"5200"}] },
  // WS /api/projects/ws/create — streaming create_project_full (not HTTP-invocable from this Explorer)

  // ─── Diagnostics (Sidecar) — Phase 12 self-diagnostics dashboard ─────
  { group:"Diagnostics (Sidecar)", server:"sidecar", method:"GET", path:"/api/diagnostics/system", desc:"Live system self-checks (sidecar, MySQL, models, ports, constitution, workflows)", params:[] },
  { group:"Diagnostics (Sidecar)", server:"sidecar", method:"GET", path:"/api/diagnostics/cached", desc:"Last cached full diagnostics result (system + pytest + vitest)", params:[] },
  // WS /api/diagnostics/ws/run — streams a full pytest + vitest + system run (not HTTP-invocable from this Explorer)

  // ─── OSA Assistant (Sidecar) — Phase 14a text MVP ────────────────────
  { group:"OSA (Sidecar)", server:"sidecar", method:"POST", path:"/api/osa/chat",  desc:"Run one OSA turn — spoken-style reply + tool trace (routes local/cloud per turn)", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"message":"how\'s my memory?","thread_id":"osa-abc123"}'}] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"GET",  path:"/api/osa/state", desc:"OSA readiness: active model, Ollama up/warmed, ready flag + latest proactive event id (14e)", params:[] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"GET",  path:"/api/osa/events", desc:"Proactive ring buffer (14e): health up/down + briefings + model-pull completions; cursor via ?after=<id>", params:[{name:"after",_in:"query",type:"number",required:false,hint:"only messages with id > after"}] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"POST", path:"/api/osa/briefing", desc:"On-demand status briefing (14e follow-on): compose + announce now — always announced, quiet hours don't apply to an explicit ask", params:[] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"GET",  path:"/api/osa/history", desc:"Transcript restore: fold a checkpointed OSA thread back into UI turns (exists/available flags; degrades when MySQL is down)", params:[{name:"thread_id",_in:"query",type:"string",required:true,hint:"osa-abc123"}] },
  // WS /api/osa/ws/chat — streaming OSA turn: token deltas + live tool events + interrupt-based Allow/Deny confirms (not HTTP-invocable from this Explorer)
  { group:"OSA (Sidecar)", server:"sidecar", method:"GET",  path:"/api/osa/model", desc:"OSA brain pin: pinned model (null = auto), mode, pinnable choices = curated registry + installed Ollama models (discovered flag; may_not_fit_ram = warning, still pinnable)", params:[] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"POST", path:"/api/osa/model", desc:"Pin OSA's brain to a curated or installed-Ollama model id, or 'auto' (durable; 422 unknown, 409 unavailable-with-reason)", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"model":"claude-sonnet-4-6"}'}] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"GET",  path:"/api/osa/voice/state", desc:"Voice pipeline snapshot (14d scaffold): state machine, mute, deps_ok + missing, last error, latency stamps", params:[] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"POST", path:"/api/osa/voice/ptt",   desc:"Push-to-talk trigger (14d): one capture->chat->speak turn; 409 while disabled / deps missing / skeleton", params:[] },
  { group:"OSA (Sidecar)", server:"sidecar", method:"POST", path:"/api/osa/voice/mute",  desc:"Flip the global voice output mute (works even while disabled); returns post-flip state", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"mute":true}'}] },

  // ─── Keno (Georgia Lottery) (Flask @ :5000) ──────────────────────────
  { group:"Keno (Flask)", method:"GET",  path:"/api/status",        desc:"API health check", params:[] },
  { group:"Keno (Flask)", method:"GET",  path:"/api/draws/latest",  desc:"Get latest draws from database", params:[{name:"count",_in:"query",type:"number",required:false,hint:"5 (max 100)"}] },
  { group:"Keno (Flask)", method:"POST", path:"/api/draws/fetch",   desc:"Fetch new draws from Georgia Lottery API", params:[{name:"count",_in:"query",type:"number",required:false,hint:"20 (max 200)"}] },
  { group:"Keno (Flask)", method:"POST", path:"/api/draws/sync",    desc:"Sync database with API (fill gaps)", params:[{name:"max",_in:"query",type:"number",required:false,hint:"100 (max 500)"}] },
  { group:"Keno (Flask)", method:"GET",  path:"/api/predictions",   desc:"Generate keno ticket predictions", params:[{name:"spots",_in:"query",type:"number",required:false,hint:"10 (max 10)"},{name:"tickets",_in:"query",type:"number",required:false,hint:"3 (max 20)"},{name:"draws",_in:"query",type:"number",required:false,hint:"25 (max 200)"}] },
  { group:"Keno (Flask)", method:"GET",  path:"/api/stats",         desc:"Get database statistics & frequency analysis", params:[] },

  // ─── DreamCatcher (FastAPI @ :5111) ────────────────────────────────────
  { group:"DreamCatcher", method:"GET",  path:"/api/health",         desc:"Service health check", params:[] },
  { group:"DreamCatcher", method:"POST", path:"/api/auth/register",  desc:"Register new user", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"email":"...","password":"..."}'}] },
  { group:"DreamCatcher", method:"POST", path:"/api/auth/login",     desc:"OAuth2 token login", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"email":"...","password":"..."}'}] },
  { group:"DreamCatcher", method:"POST", path:"/api/dreams/",        desc:"Create dream entry", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"title":"...","description":"...","tags":[]}'}] },
  { group:"DreamCatcher", method:"GET",  path:"/api/dreams/tags",    desc:"Get all dream tags", params:[] },
  { group:"DreamCatcher", method:"GET",  path:"/api/goals/",         desc:"List goals", params:[] },
  { group:"DreamCatcher", method:"POST", path:"/api/goals/",         desc:"Create goal", params:[{name:"body",_in:"body",type:"json",required:true}] },
  { group:"DreamCatcher", method:"GET",  path:"/api/ideas/",         desc:"List ideas", params:[] },
  { group:"DreamCatcher", method:"POST", path:"/api/ideas/",         desc:"Capture new idea", params:[{name:"body",_in:"body",type:"json",required:true}] },
  { group:"DreamCatcher", method:"POST", path:"/api/sleep/",         desc:"Log sleep session", params:[{name:"body",_in:"body",type:"json",required:true}] },

  // ─── Weather (Flask @ :5000) ───────────────────────────────────────────
  { group:"Weather (Flask)", method:"GET",  path:"/",                     desc:"Main weather dashboard", params:[] },
  { group:"Weather (Flask)", method:"GET",  path:"/location/{id}",        desc:"Location detail page", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/weather/{id}",     desc:"Current daily weather", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/forecast/{id}",    desc:"7-day weather forecast", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/moon/{id}",        desc:"Moon phase & astronomy data", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/tides/{id}",       desc:"Tide data (US locations)", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/locations",        desc:"List all tracked locations", params:[] },
  { group:"Weather (Flask)", method:"POST", path:"/api/locations",        desc:"Add new location", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"name":"...","lat":0,"lon":0}'}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/search",           desc:"Search locations by name", params:[{name:"q",_in:"query",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/weekly-average/{id}", desc:"7-day weather average", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"Weather (Flask)", method:"GET",  path:"/api/health",           desc:"Weather API health check", params:[] },

  // ─── AI Voice Assistant (Flask @ :5000) ────────────────────────────────
  { group:"AI Voice", method:"GET",    path:"/",                          desc:"Serve frontend", params:[] },
  { group:"AI Voice", method:"GET",    path:"/api/health",                desc:"Service health & feature flags", params:[] },
  { group:"AI Voice", method:"GET",    path:"/api/llm-providers",         desc:"List available LLM providers", params:[] },
  { group:"AI Voice", method:"GET",    path:"/api/llm-providers/{name}/models", desc:"Provider's model list", params:[{name:"name",_in:"path",type:"string",required:true,hint:"openai,anthropic,ollama"}] },
  { group:"AI Voice", method:"GET",    path:"/api/agents",                desc:"List available agents", params:[] },
  { group:"AI Voice", method:"GET",    path:"/api/agents/{id}",           desc:"Single agent info", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"AI Voice", method:"POST",   path:"/api/agents/recommend",      desc:"Recommend agent by message", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"message":"..."}'}] },
  { group:"AI Voice", method:"POST",   path:"/api/chat",                  desc:"Single agent chat", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"message":"...","user_id":"...","agent_id":"..."}'}] },
  { group:"AI Voice", method:"POST",   path:"/api/chat/parallel",         desc:"Multi-agent parallel execution", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"message":"...","agent_ids":[]}'}] },
  { group:"AI Voice", method:"GET",    path:"/api/user",                  desc:"Get user profile", params:[{name:"user_id",_in:"query",type:"string",required:true}] },
  { group:"AI Voice", method:"POST",   path:"/api/user",                  desc:"Update user profile", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"name":"..."}'}] },
  { group:"AI Voice", method:"GET",    path:"/api/user/greeting",         desc:"Get personalized greeting", params:[{name:"user_id",_in:"query",type:"string",required:true}] },
  { group:"AI Voice", method:"GET",    path:"/api/user/facts",            desc:"Get stored user facts", params:[{name:"user_id",_in:"query",type:"string",required:true}] },
  { group:"AI Voice", method:"POST",   path:"/api/user/facts",            desc:"Set user fact", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"category":"...","key":"...","value":"..."}'}] },
  { group:"AI Voice", method:"GET",    path:"/api/conversation",          desc:"Get conversation history", params:[{name:"user_id",_in:"query",type:"string",required:true}] },
  { group:"AI Voice", method:"DELETE", path:"/api/conversation",          desc:"Clear conversation history", params:[{name:"user_id",_in:"query",type:"string",required:true}] },
  { group:"AI Voice", method:"POST",   path:"/api/voice/transcribe",      desc:"Transcribe audio to text", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"audio_file":"..."}'}] },
  { group:"AI Voice", method:"POST",   path:"/api/voice/synthesize",      desc:"Text to speech conversion", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"text":"...","voice":"..."}'}] },
  { group:"AI Voice", method:"GET",    path:"/api/voice/voices",          desc:"List available voice options", params:[] },
  { group:"AI Voice", method:"POST",   path:"/api/livekit/token",         desc:"Generate LiveKit token", params:[{name:"body",_in:"body",type:"json",required:true}] },
  { group:"AI Voice", method:"POST",   path:"/api/livekit/dispatch",      desc:"Dispatch agent for real-time chat", params:[{name:"body",_in:"body",type:"json",required:true}] },
  { group:"AI Voice", method:"GET",    path:"/api/livekit/status",        desc:"Get real-time session status", params:[] },
  { group:"AI Voice", method:"POST",   path:"/api/filesystem/read",       desc:"Read file content", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"path":"..."}'}] },
  { group:"AI Voice", method:"POST",   path:"/api/filesystem/create",     desc:"Create/write file", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"path":"...","content":"..."}'}] },
  { group:"AI Voice", method:"POST",   path:"/api/filesystem/list",       desc:"List directory contents", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"path":"..."}'}] },

  // ─── SongTrans (Flask @ :5000) ─────────────────────────────────────────
  { group:"SongTrans (Flask)", method:"GET",  path:"/",                 desc:"Serve frontend", params:[] },
  { group:"SongTrans (Flask)", method:"POST", path:"/api/translate",    desc:"Fetch & translate song lyrics", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"song_name":"...","artist_name":"...","language":"en"}'}] },
  { group:"SongTrans (Flask)", method:"GET",  path:"/api/search-artists", desc:"Autocomplete artist search", params:[{name:"q",_in:"query",type:"string",required:true}] },

  // ─── Cards/Blackjack (Flask @ :5000) ───────────────────────────────────
  { group:"Blackjack (Flask)", method:"GET",  path:"/",                    desc:"Serve index.html", params:[] },
  { group:"Blackjack (Flask)", method:"GET",  path:"/card-image/{rank}/{suit}", desc:"Serve card SVG files", params:[{name:"rank",_in:"path",type:"string",required:true,hint:"A,2-10,J,Q,K"},{name:"suit",_in:"path",type:"string",required:true,hint:"hearts,diamonds,clubs,spades"}] },
  { group:"Blackjack (Flask)", method:"POST", path:"/api/new-game",       desc:"Initialize game session", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"mode":"single","players":1}'}] },
  { group:"Blackjack (Flask)", method:"POST", path:"/api/place-bet",       desc:"Place initial bet", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"amount":10}'}] },

  // ─── Cards/Shuffle (Flask @ :5000) ────────────────────────────────────
  { group:"Shuffle (Flask)", method:"GET",  path:"/",              desc:"Serve frontend", params:[] },
  { group:"Shuffle (Flask)", method:"POST", path:"/api/deck/new",  desc:"Create shuffled 52-card deck", params:[] },
  { group:"Shuffle (Flask)", method:"POST", path:"/api/deck/deal",  desc:"Deal cards to dealer/player", params:[] },

  // ─── BatTester (FastAPI @ :8000) ──────────────────────────────────────
  { group:"BatTester", method:"GET",  path:"/",                  desc:"Battery test dashboard", params:[] },
  { group:"BatTester", method:"GET",  path:"/api/health",        desc:"Service health & active test ID", params:[] },
  { group:"BatTester", method:"GET",  path:"/api/tests",         desc:"List all battery tests", params:[] },
  { group:"BatTester", method:"POST", path:"/api/tests",         desc:"Create new test", params:[{name:"body",_in:"body",type:"json",required:true,hint:'{"chemistry":"LiPo","voltage":12,"capacity":5000}'}] },
  { group:"BatTester", method:"GET",  path:"/api/tests/{id}",    desc:"Get test details", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"BatTester", method:"POST", path:"/api/tests/{id}/start", desc:"Start discharge test", params:[{name:"id",_in:"path",type:"string",required:true},{name:"body",_in:"body",type:"json",required:true,hint:'{"rate":"1C"}'}] },
  { group:"BatTester", method:"POST", path:"/api/tests/{id}/stop", desc:"Stop active test", params:[{name:"id",_in:"path",type:"string",required:true}] },
  { group:"BatTester", method:"GET",  path:"/api/tests/{id}/readings", desc:"Tail test readings", params:[{name:"id",_in:"path",type:"string",required:true}] },

  // ─── System (Sidecar) ──────────────────────────────────────────────────
  { group:"System", server:"sidecar", method:"GET", path:"/api/health", desc:"Sidecar health", params:[] },
];

// Generate mock logs for initial display
function generateMockLogs() {
  const now = new Date();
  const mockMessages = [
    "Fetching news feed from RSS source",
    "Processing article: Quantum Computing Breakthrough",
    "Successfully ranked 12 articles",
    "API request failed with timeout",
    "Cache hit for category: Technology",
    "Invalid parameter in request",
    "Sidecar health check passed",
    "Starting news fetch operation",
    "Completed news fetch in 234ms",
    "Error: Connection refused to external service",
    "Filtering articles by keyword",
    "Database query executed",
    "Response sent successfully",
  ];

  const logs = [];
  const levels = ["DEBUG", "INFO", "WARN", "ERROR"];

  for (let i = 0; i < 25; i++) {
    const time = new Date(now.getTime() - i * 1000);
    const timestamp = time.toISOString().split('T')[1].substring(0, 8);
    logs.push({
      timestamp,
      level: levels[Math.floor(Math.random() * levels.length)],
      message: mockMessages[Math.floor(Math.random() * mockMessages.length)],
    });
  }

  return logs.reverse();
}

// Convert OpenAPI spec to explorer format
function convertOpenAPIToEndpoints(spec) {
  const endpoints = [];
  if (!spec?.paths) return endpoints;

  for (const [path, methods] of Object.entries(spec.paths)) {
    for (const [method, details] of Object.entries(methods)) {
      if (!["get", "post", "put", "delete", "patch"].includes(method.toLowerCase())) continue;

      const params = [];
      if (details.parameters) {
        details.parameters.forEach(p => {
          params.push({
            name: p.name,
            _in: p.in || "query",
            type: p.schema?.type || "string",
            required: p.required || false,
            hint: p.description || "",
          });
        });
      }
      if (details.requestBody) {
        params.push({
          name: "body",
          _in: "body",
          type: "json",
          required: details.requestBody.required || false,
          hint: "Request body",
        });
      }

      endpoints.push({
        group: details.tags?.[0] || "Other",
        method: method.toUpperCase(),
        path: path,
        desc: details.summary || details.description || "",
        params: params,
        server: path.startsWith("/api") ? "sidecar" : "hub",
      });
    }
  }
  return endpoints;
}

function buildUrl(ep, paramValues) {
  let path = ep.path;
  ep.params.filter(p => p._in === "path").forEach(p => {
    path = path.replace(`{${p.name}}`, paramValues[p.name] || `{${p.name}}`);
  });
  const qp = ep.params.filter(p => p._in === "query" && paramValues[p.name]);
  const qs = qp.map(p => `${p.name}=${encodeURIComponent(paramValues[p.name])}`).join("&");
  const base = ep.server === "sidecar" ? sidecarUrl()
             : ep.rootPath ? "http://localhost:8085" : HUB;
  return base + path + (qs ? "?" + qs : "");
}

export default function HubApiExplorer() {
  // ── localStorage helpers ────────────────────────────────────────────────────
  const loadFromLS = (key, defaultVal) => {
    try {
      const stored = localStorage.getItem(`hub-api-explorer-${key}`);
      return stored ? JSON.parse(stored) : defaultVal;
    } catch { return defaultVal; }
  };
  const saveToLS = (key, val) => {
    try { localStorage.setItem(`hub-api-explorer-${key}`, JSON.stringify(val)); } catch {}
  };

  const [endpoints, setEndpoints]   = useState(ENDPOINTS_HARDCODED);
  const [tab, setTab]               = useState(() => loadFromLS("tab", "explorer"));
  const [selected, setSelected]     = useState(null);
  const [groupOpen, setGroupOpen]   = useState(() => {
    const saved = loadFromLS("groupOpen", null);
    if (saved) return saved;
    // Default: open all groups
    return Object.fromEntries(
      [...new Set(ENDPOINTS_HARDCODED.map(e => e.group))].map(g => [g, true])
    );
  });
  const [filter, setFilter]         = useState(() => loadFromLS("filter", ""));
  const [paramValues, setParamValues] = useState({});
  const [response, setResponse]     = useState(null);
  const [loading, setLoading]       = useState(false);
  const [callLog, setCallLog]       = useState([]);
  const [logs, setLogs]             = useState(() => generateMockLogs());
  const [hubColor, setHubColor]     = useState("#e0b84c");
  const [hubLabel, setHubLabel]     = useState("localhost:8085");
  const [sidecarColor, setSidecarColor] = useState("#e0b84c");
  const [sidecarLabel, setSidecarLabel] = useState(sidecarHost());
  const [copied, setCopied]         = useState(false);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch("http://localhost:8085/health", { signal: AbortSignal.timeout(2000) });
        setHubColor(r.ok ? "#7fb069" : "#e0b84c");
        setHubLabel(r.ok ? "localhost:8085 · online" : `localhost:8085 · ${r.status}`);
      } catch {
        setHubColor("#d9534f");
        setHubLabel("localhost:8085 · offline");
      }
    };
    check();
    const id = setInterval(check, pollMs(5000));
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const check = async () => {
      const host = sidecarHost();
      try {
        const r = await fetch(`${sidecarUrl()}/api/health`, { signal: AbortSignal.timeout(2000) });
        setSidecarColor(r.ok ? "#7fb069" : "#e0b84c");
        setSidecarLabel(r.ok ? `${host} · online` : `${host} · ${r.status}`);
      } catch {
        setSidecarColor("#d9534f");
        setSidecarLabel(`${host} · offline`);
      }
    };
    check();
    const id = setInterval(check, pollMs(5000));
    return () => clearInterval(id);
  }, []);

  // ── Persist filter state to localStorage ─────────────────────────────────
  useEffect(() => { saveToLS("tab", tab); }, [tab]);
  useEffect(() => { saveToLS("filter", filter); }, [filter]);
  useEffect(() => { saveToLS("groupOpen", groupOpen); }, [groupOpen]);

  const groups = [...new Set(endpoints.map(e => e.group))];
  const ep  = selected !== null ? endpoints[selected] : null;
  const url = ep ? buildUrl(ep, paramValues) : "";
  const curlCmd = ep ? `curl -X ${ep.method} "${url}"` : "";

  const selectEndpoint = (idx) => {
    setSelected(idx);
    setParamValues({});
    setResponse(null);
    setTab("explorer");
  };

  const tryIt = async () => {
    if (!ep) return;
    setLoading(true);
    setResponse(null);
    const bodyParam = ep.params.find(p => p._in === "body");
    const start = Date.now();
    try {
      const opts = { method: ep.method, headers: { "Content-Type": "application/json" } };
      if (bodyParam && paramValues[bodyParam.name]) {
        try { opts.body = JSON.stringify(JSON.parse(paramValues[bodyParam.name])); }
        catch { opts.body = paramValues[bodyParam.name]; }
      }
      const res = await fetch(url, opts);
      const dur = Date.now() - start;
      let text;
      try { text = JSON.stringify(await res.json(), null, 2); }
      catch { text = await res.text(); }
      setResponse({ status: res.status, text, ok: res.ok, dur });
      setCallLog(prev => [{ method: ep.method, path: ep.path, status: res.status, dur, ok: res.ok, ts: new Date() }, ...prev].slice(0, 50));
    } catch (e) {
      const dur = Date.now() - start;
      const where = ep.server === "sidecar" ? `the sidecar at ${sidecarHost()}` : "Hub at localhost:8085";
      setResponse({ status: 0, text: `Network error: ${e.message}\n\n(Is ${where} running?)`, ok: false, dur });
      setCallLog(prev => [{ method: ep.method, path: ep.path, status: 0, dur, ok: false, ts: new Date() }, ...prev].slice(0, 50));
    }
    setLoading(false);
  };

  const copyCurl = () => {
    navigator.clipboard?.writeText(curlCmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const filteredEps = (group) => {
    const f = (filter || "").toLowerCase();  // case-insensitive: lowercase the query too
    return endpoints.map((e, i) => ({ ...e, _i: i })).filter(e =>
      e.group === group &&
      (!f || e.path.toLowerCase().includes(f) || e.method.toLowerCase().includes(f) || e.desc.toLowerCase().includes(f))
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* ── sub-topbar ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-inset)", flexShrink: 0 }}>
        <div style={{ fontWeight: 700, fontSize: 13, letterSpacing: .4 }}>Codehome <span style={{ color: "var(--accent)" }}>API Explorer</span></div>
        <TabSwitcher activeTab={tab} onTabChange={setTab} callLogCount={callLog.length} tabs={[
          { id: "explorer", label: "Explorer" },
          { id: "logs", label: "Logs" },
          { id: "calllog", label: `Call Log${callLog.length ? ` (${callLog.length})` : ""}` },
        ]} />
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 14, fontSize: 11, color: "var(--text-dim)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: hubColor }} />
            <span>Hub {hubLabel}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: sidecarColor }} />
            <span>Sidecar {sidecarLabel}</span>
          </div>
        </div>
      </div>

      {/* ── body ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

        {/* LEFT: endpoint list */}
        <div style={{ width: 290, minWidth: 290, borderRight: "1px solid var(--border-soft)", display: "flex", flexDirection: "column", background: "var(--bg-inset)", overflow: "hidden" }}>
          <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: 7 }}>
            <FilterBar value={filter} onChange={setFilter} />
            <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
              <span style={{ fontSize: 10, color: "var(--text-dim)" }}>Collapse:</span>
              <button
                onClick={() => setGroupOpen(Object.fromEntries(groups.map(g => [g, false])))}
                style={{ padding: "2px 8px", fontSize: 10, cursor: "pointer", border: "1px solid var(--border-soft)", borderRadius: 3, background: "none", color: "var(--text-dim)" }}
              >
                All
              </button>
              <button
                onClick={() => setGroupOpen(Object.fromEntries(groups.map(g => [g, true])))}
                style={{ padding: "2px 8px", fontSize: 10, cursor: "pointer", border: "1px solid var(--border-soft)", borderRadius: 3, background: "none", color: "var(--text-dim)" }}
              >
                Expand
              </button>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {groups.map(g => {
              const items = filteredEps(g);
              if (!items.length) return null;
              return (
                <div key={g}>
                  <GroupHeader
                    name={g}
                    isOpen={groupOpen[g]}
                    onToggle={() => setGroupOpen(p => ({ ...p, [g]: !p[g] }))}
                    itemCount={items.length}
                  />
                  {groupOpen[g] && items.map(e => (
                    <EndpointListItem
                      key={e._i}
                      endpoint={e}
                      isSelected={selected === e._i}
                      onSelect={() => selectEndpoint(e._i)}
                    />
                  ))}
                </div>
              );
            })}
          </div>
        </div>

        {/* RIGHT: detail, logs, or call log */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {tab === "logs" ? (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
              <LogsExplorer logs={logs} />
            </div>
          ) : tab === "calllog" ? (
            callLog.length ? (
              <div style={{ padding: 14, flex: 1, overflowY: "auto" }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--text-dim)", marginBottom: 8 }}>Recent calls · {callLog.length} total</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                  {callLog.map((l, i) => (
                    <CallLogEntry key={i} entry={l} />
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>No calls yet — use Explorer to run requests.</div>
            )
          ) : !ep ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-dim)", fontSize: 12 }}>← Select an endpoint to explore</div>
          ) : (
            <>
              <div style={{ padding: "11px 16px", borderBottom: "1px solid var(--border-soft)", background: "var(--bg-panel)", flexShrink: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 5 }}>
                  <MethodBadge method={ep.method} />
                  <span style={{ fontFamily: "var(--mono)", fontSize: 13 }}><PathDisplay path={ep.path} /></span>
                </div>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{ep.desc}</div>
                <div style={{ display: "flex", gap: 8, marginTop: 9, alignItems: "center" }}>
                  <button
                    onClick={tryIt}
                    disabled={loading}
                    style={{ padding: "4px 14px", background: "var(--accent)", color: "#1b1b19", border: "none", borderRadius: 4, fontFamily: "inherit", fontWeight: 700, fontSize: 12, cursor: "pointer" }}
                  >
                    {loading ? "…" : "▶ Run"}
                  </button>
                  <button
                    onClick={copyCurl}
                    style={{ padding: "4px 11px", background: "none", border: "1px solid var(--border-soft)", color: "var(--text-dim)", borderRadius: 4, fontFamily: "inherit", fontSize: 12, cursor: "pointer" }}
                  >
                    {copied ? "Copied!" : "Copy curl"}
                  </button>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-dim)", marginLeft: "auto", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 340 }}>{curlCmd}</span>
                </div>
              </div>

              <div style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
                {ep.params.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "var(--text-dim)", marginBottom: 6 }}>Parameters</div>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr>
                          {["Name", "In", "Type", "Value"].map(h => (
                            <th key={h} style={{ textAlign: "left", padding: "4px 8px", borderBottom: "1px solid var(--border-soft)", color: "var(--text-dim)", fontWeight: 600, fontSize: 11 }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {ep.params.map(p => (
                          <ParamInput
                            key={p.name}
                            param={p}
                            value={paramValues[p.name] || ""}
                            onChange={value => setParamValues(prev => ({ ...prev, [p.name]: value }))}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <ResponseDisplay response={response} loading={loading} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
