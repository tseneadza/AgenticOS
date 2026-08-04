# OSA Attention Model — learning what concerns Tony

> **Status: DESIGNED 2026-07-24** (Cowork session with Tony). Phase 0 testbed is
> LIVE as the Cowork artifact `today-attention`. Phases A–C are AgenticOS dev
> work — not started. Ledger this as 🟧 IN PROGRESS when a dev session picks it up.

## Decisions locked with Tony (2026-07-24)

- **Signals:** explicit + implicit. OSA learns both from deliberate teaching and
  from observed behavior.
- **Model form:** an **editable profile document** — human-readable prose that
  OSA rewrites as it learns and Tony can read/correct at any time. Fits the
  CONTINUATION.md doc culture: the model IS a doc, never a black box.
- **Powers:** rank & summarize + **proactive interrupts** when something crosses
  a learned "always matters" threshold. **NOT** acting on items (auto-archive,
  auto-decline) — deliberately parked; revisit only after trust is established.

## 1. Concept

OSA maintains an **attention profile**: one versioned document describing what
concerns Tony, what doesn't, and what OSA is currently guessing. Every brief,
ranking, and interrupt decision is made by an LLM pass that reads this profile
plus the day's raw items. Learning = rewriting the profile from an event log.
Trust comes from three properties: the profile is **readable**, **correctable**,
and **every change is announced**.

## 2. Signal taxonomy

**Explicit (Tony teaches):**
- Mute a sender/source ("never care") — hard rule.
- Thumbs up/down on a brief, with optional free-text ("job alerts are noise").
- Direct edits to the profile document.
- Chat instructions to OSA ("always flag billing emails").

**Implicit (OSA observes) — Phase C:**
- Opened/clicked items from a brief vs ignored ones.
- Gmail behavior: replied-to vs left-unread-for-days (read state via mail tools).
- Topics Tony raises with OSA in chat (what he asks about = what he cares about).
- Calendar behavior: which events he actually keeps vs declines.

Every signal becomes an **event**: `{ts, source, kind, item_summary, direction,
weight}`. Explicit events weigh heavily; implicit events are hints that need
repetition before they become profile text.

## 3. Profile document spec

One markdown document, sectioned:

```
# Tony's Attention Profile (vN, updated <ts>)
## Hard rules            ← deterministic, applied pre-LLM, never decay
- MUTE sender: editor@members.wayfair.com
- ALWAYS FLAG: security incidents, API key exposure, billing/credit issues
## Standing concerns     ← stable prose, Tony-authored or Tony-confirmed
## Current focus         ← project-bound, expires with the project
## Learned hunches       ← OSA's guesses: each with confidence, evidence count,
                           last-reinforced date. Promote to Standing on confirm;
                           decay out after ~3 weeks unreinforced.
```

- **Storage (AgenticOS):** MySQL — `osa_attention_profile` (versioned rows:
  `id, version, body, created_at, trigger_event_ids`) and
  `osa_attention_events` (append-only log). Versioning gives audit + rollback.
- Hard rules live INSIDE the document (single source of truth) but are parsed
  out for cheap pre-filtering — honors "profile document" without paying LLM
  cost to drop known junk.

## 4. Learning loop (consolidation)

1. Events append continuously.
2. Consolidation pass triggers on: explicit feedback (immediate), or N≥10 new
   implicit events, or weekly timer.
3. LLM receives: current profile + new events → returns rewritten profile.
   Prompt contract: preserve Hard rules verbatim unless an event explicitly
   changes them; only promote a hunch with ≥3 reinforcing events; date-stamp
   hunches; keep the document under ~150 lines.
4. Diff is announced ("OSA learned: job-alert emails demoted to noise") via the
   announcement path → orb alert (OSAORB #1 mechanism). Tony can revert by
   editing the profile — that edit is itself a heavyweight event.
5. **Routing:** consolidation is judgment work → cloud model. Pre-filtering by
   hard rules is menial → local (fits 2026-07-23 local-first routing).

## 5. What OSA does with the profile

- **Brief (rank & summarize):** on demand or scheduled. Sources: Gmail unread,
  today's calendar, AgenticOS dev state (CONTINUATION.md top session,
  IDEA_LEDGER 🟧/🅿 rows). Hard-rule filter → LLM ranks remainder against
  profile → short prioritized brief, "what I'd tackle first" line at the end.
- **Proactive interrupts:** a scanner checks new items against ALWAYS FLAG
  rules. On match: orb alert + optional voice line. Guardrails: quiet hours,
  interrupt budget (max ~3/day), every interrupt logged as an event so a thumbs-
  down on an interrupt teaches OSA to raise the bar. Interrupts earn their
  existence by being rare and right.
- **Explicitly out of scope:** touching the underlying items. No auto-archive,
  no auto-decline. Parked with reason: trust first. (Ledger it 🅿 when filed.)

## 6. Phasing

**Phase 0 — Cowork artifact testbed ✅ LIVE (2026-07-24).**
`today-attention` artifact: mutes (✕ per sender), editable concerns note,
thumbs feedback with free-text teaching, event log, and askClaude-driven
profile rewrite — all in `localStorage`. Purpose: validate the loop cheaply and
accumulate seed data. Its localStorage keys (`osa.concerns`, `osa.mutedSenders`,
`osa.events`) are the export format for seeding Phase A.

**Phase A — Profile in AgenticOS.** MySQL tables above; OSA tools
`get_attention_profile`, `log_attention_event`, `consolidate_attention_profile`
(read/log are menial/local-safe; consolidate is cloud). Seed from artifact
export + Tony interview.

**Phase B — OSA owns the brief.** Brief generation inside OSA using its own
mail/calendar/docs tools; artifact becomes a thin viewer (or retires).
CONTINUATION/ledger parsing reuses the artifact's section/table parsing logic.

**Phase C — Implicit signals + interrupts.** Read-state sampling, brief-click
capture, chat-topic mining; ALWAYS-FLAG scanner wired to the announcement path.

## 7. Open questions (for next dev session with Tony)

- Consolidation cadence: is "immediate on explicit + weekly otherwise" right?
- Should the profile also live as a rendered doc in `docs/` (generated artifact,
  like PORT_ASSIGNMENTS.md was) for greppability, with MySQL as truth?
- Interrupt channels: orb only, or also macOS notification when GUI is closed?
- Does Phase B fold into the existing morning-brief ambitions, or stay separate?

## 8. Provisions for human weakness — "debauchery clause" (added 2026-08-04)

Decisions locked with Tony. An attention model that only serves the
disciplined version of its owner will be ignored by the real one.

**8.1 Guilty-pleasure lane.** Vices are NOT noise. The profile keeps a
`Vices (protected)` list (show premieres, hobbies, deals on things he actually
likes). Briefs end with a short **"🍸 For your vices"** section (≤2–3 items) —
surfaced without moralizing, never buried by noise filtering. Muting junk must
never silently swallow a vice category; only an explicit statement from Tony
demotes something from vice to noise.

**8.2 NSFW discretion, not censorship.** Questionable/racy content is
**flagged ("NSFW:") and phrased discreetly** — briefs may be glanced at in
public — but is never dismissed, filtered, or down-ranked on propriety alone.
Flag-and-phrase, never suppress.

**8.3 Vice guardrails (nudges, not nagging).** OSA may notice weakness
patterns (impulse-promo clicks, doomscroll senders, late-night activity) and
offer AT MOST one gentle, observational nudge per brief — wry, never preachy.
A thumbs-down on a nudge raises the nudge threshold; repeated thumbs-downs
mean stop nudging that pattern. Nudges earn their place the same way
interrupts do: rare and right.

**8.4 Forgiveness by design.** The model must not over-learn from Tony at his
weakest:
- Events carry a `weak_hour` flag (midnight–5am local). Weak-hour signals are
  discounted in consolidation; at most they become "(weak-hour hunch)" entries
  needing daytime reinforcement.
- A rapid burst of similar mutes = possible rage-mute → low-confidence hunch,
  not a hard generalization.
- Ignoring briefs for a few days is NOT a negative signal on the items in them.
- Binge behavior doesn't rewrite standing concerns; it feeds 8.3 at most.

Phase mapping: all of §8 is prompt + event-schema work — live in Phase 0 (the
artifact) as of 2026-08-04; Phases A–C inherit it via the same prompts and the
`weak_hour` column on `osa_attention_events`.

## 9. Flexibility guarantees (added 2026-08-04)

Tony's requirement: this must stay flexible. Insured five ways:

**9.1 Defaults in code, decisions in data.** Everything in §5–§8 (vices lane,
nudge caps, NSFW phrasing, interrupt budgets, forgiveness weights) is a
DEFAULT, not law. The profile document may contain a **"Behavior overrides"**
section, and **the profile always wins** over defaults. Changing OSA's behavior
= editing a doc (or giving feedback), never a code change.

**9.2 Meta-feedback is first-class.** Feedback about the rules themselves
("drop the vices section", "nudge me harder", "interrupt me for X") flows
through the SAME learning loop and lands in Behavior overrides. The system
that learns what concerns Tony also learns how Tony wants to be told.

**9.3 Everything versioned, everything revertible.** Profile rewrites are
versioned rows (rollback = restore version N); this doc lives in git; the
artifact keeps profile versions in localStorage. No change is a one-way door.

**9.4 Conventions, not schemas.** Profile sections are conventions the LLM
maintains — adding a section costs nothing. The event log is append-only JSON
tolerant of new fields (`weak_hour` was added exactly this way). No migrations
to fear.

**9.5 The design itself is provisional.** Each phase gate (A, B, C) starts
with a review of this doc against reality + a Tony interview. Anything here
can be renegotiated; verdicts go to IDEA_LEDGER per house rules. The only
fixed points are the trust properties in §1: readable, correctable, announced.
