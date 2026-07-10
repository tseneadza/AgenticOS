---
name: update-glossary
description: |
  Keep AgenticOS's GLOSSARY.md current. Use this skill whenever a change introduces a new acronym, project-specific term, or non-obvious technical concept to the docs or codebase — the glossary rule in CLAUDE.md requires the entry to land in the SAME change (same policy as CHANGELOG.md / roadmap.md). Also use it for a periodic sweep ("update the glossary", "add the new terms", "glossary pass") to harvest in-repo terms that were missed. Covers: where terms live (docs/GLOSSARY.md is authoritative, mirrored to Brain2), the eight sections, the entry style, and the CHANGELOG + Brain2 sync that must accompany every edit.
compatibility: AgenticOS repo, docs/GLOSSARY.md (authoritative) + ~/Brain2/08 - Systems/Agentic OS/GLOSSARY.md (mirror)
---

# Update Glossary (keep GLOSSARY.md current)

## Overview

`docs/GLOSSARY.md` is the **living, authoritative** dictionary for every
acronym, project term, and non-obvious technical concept in AgenticOS. A copy
is mirrored at `~/Brain2/08 - Systems/Agentic OS/GLOSSARY.md`. Per `CLAUDE.md`
(Glossary rule): **any change that introduces a new term to the docs or code
must add its glossary entry in the same change.** Missing/outdated entries are
a bug.

## When to use

- You added a new acronym, coined term, or non-obvious concept in code/docs
  (e.g. this session added VAD, energy gate/`min_rms`, headless voice test,
  resting state, presence greeting, orb states).
- Tony says "update the glossary", "add the new terms", "glossary pass".
- You spot an in-repo term that isn't defined here.

## The eight sections

1. Core project vocabulary — coined/AgenticOS-specific
2. Phases, planning, and process — FR/TR/PRD/phase language
3. Architecture and runtime — sidecar internals, LangGraph, MCP
4. Persistence and data — MySQL, SQLAlchemy, checkpointer
5. Frontend, desktop, and GUI — React/Tauri/orb/theme
6. Voice, LLM, and OSA — voice pipeline, models, persona
7. Unix, macOS, and system ops — signals, launchd, venv
8. Web, protocols, and general tech — HTTP/JSON/WS/REST

Put a term in the **most specific** section; cross-reference from others only
if it truly spans. Entries are ordered **alphabetically** within a section.

## Entry style (match exactly)

```
**term** — one-line definition. Then optional context: where it lives
(`path/to/file.py`), why it matters, a design-doc §ref, or a date for a
behavior change. Keep it tight; wrap ~76 cols like the rest of the file.
```

Bold the term with `**…**`, em-dash separator, plain prose after. Use
backticks for file paths, config keys, and code identifiers.

## Procedure

1. **Find the new terms.** Diff the change (or grep the touched files) for
   acronyms and coined identifiers a newcomer wouldn't know. When doing a
   sweep, grep the repo for `\b[A-Z]{2,}\b` and scan recent CHANGELOG entries.
2. **Dedupe.** Grep GLOSSARY.md first (`grep -n '\*\*Term' docs/GLOSSARY.md`)
   so you don't re-add an existing entry.
3. **Insert** each entry in the right section, alphabetically, in the style
   above.
4. **CHANGELOG.** Add a one-line note to `docs/CHANGELOG.md`
   (`glossary: added VAD, energy gate, presence greeting, …`).
5. **Sync the mirror.** Copy the updated file to
   `~/Brain2/08 - Systems/Agentic OS/GLOSSARY.md` (docs/ is authoritative):
   `cp docs/GLOSSARY.md "$HOME/Brain2/08 - Systems/Agentic OS/GLOSSARY.md"`.
6. If it was a full sweep, bump the **"Last full pass"** date in the header.

## Gotchas

- **Same-change rule:** don't defer the entry to "later" — later means never.
  Add it in the commit that introduced the term.
- **Authoritative vs mirror:** only edit `docs/GLOSSARY.md` by hand; the Brain2
  copy is a `cp` target, never edited independently (they must not diverge).
- **Alphabetical, not append:** new terms slot into position, they don't pile
  up at the bottom of a section.
