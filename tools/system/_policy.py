"""System-MCP safety policy — Phase 15a (design §4).

Pure decision logic: given a capability + its payload, answer one of
``"allow" | "approve" | "deny"``. The harness (`_harness.py`) turns those
answers into execution / ``ApprovalRequired`` / ``ConstitutionViolation``.

The safety ladder (design §4.1):

  strict mode (start): auto-marked capabilities run; ``macos.run_command``
      runs only if the command matches the terminal allowlist, else halts to
      approval; everything else halts to approval.
  effect mode (target, flipped in 15e): reads run; mutate/irreversible halt
      to approval; run_command still honors the allowlist.

Denylist patterns are ALWAYS deny, in both modes — they are checked before
anything else, and even an ``approved=True`` call can never pass one (the
harness re-checks).

Config comes from ``config/constitution.yaml``'s ``system_mcp`` block via
``core.constitution.Constitution`` (defaults-merged, so pre-15a configs load
unchanged). Pass a ``Constitution`` explicitly for tests.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from core.constitution import Constitution

Decision = str  # "allow" | "approve" | "deny"


# --------------------------------------------------------------------------- #
# Effect classifier for run_command (Phase 15e)
#
# A PURE, fail-closed heuristic (design decision, Tony 2026-07-14): NO model
# call. A static, code-reviewed table of read-only binaries + a conservative
# shell-feature check. It exists so that IN EFFECT MODE a non-allowlisted
# command that is *provably* read-only auto-runs, while anything unknown or
# mutating still gates. Strict mode never consults it.
#
# The bias is deliberate: it is FINE for a read-only command to require
# approval (a miss), and NOT fine for a mutating command to auto-run (a false
# read). Every ambiguity therefore resolves to ``"unknown"`` → gate.
# --------------------------------------------------------------------------- #

#: Binaries whose bare invocation only reads/inspects — no filesystem, network,
#: or process mutation. Code review is the gate here, not a runtime guess.
#: DELIBERATELY EXCLUDED as unsafe: ``sed``/``awk`` (``-i`` / redirection /
#: ``system()`` can write), ``tee`` (writes), ``xargs`` (execs anything),
#: ``ping``/``curl``/``nc`` (network), ``cp``/``mv``/``rm``/``touch``/``mkdir``
#: (mutate). ``git`` is handled separately (subcommand-aware, below).
READ_ONLY_VERBS: frozenset[str] = frozenset({
    "cat", "less", "head", "tail", "grep", "egrep", "fgrep", "rg",
    "find", "ls", "stat", "file", "wc", "sort", "uniq", "cut",
    "echo", "printf", "pwd", "whoami", "id", "hostname", "uname",
    "date", "uptime", "df", "du", "ps", "top", "env", "which", "type",
    "dirname", "basename", "realpath", "readlink", "tree", "diff", "cmp",
    "md5", "md5sum", "shasum", "sha256sum", "jq", "yq", "tr",
    "column", "fold", "nl", "tac", "xxd", "od", "strings", "cal",
})

#: ``git`` subcommands that only read repository state.
_GIT_READ_SUBCMDS: frozenset[str] = frozenset({
    "status", "log", "diff", "show", "rev-parse", "describe",
    "blame", "ls-files", "cat-file", "shortlog", "reflog", "whatchanged",
    "ls-tree", "ls-remote",
})

#: ``find`` primaries that make it a writer/executor.
_FIND_WRITER_FLAGS: frozenset[str] = frozenset({
    "-exec", "-execdir", "-delete", "-ok", "-okdir",
    "-fprint", "-fprintf", "-fls",
})

# Shell metacharacters that mean "not a plain read": command/process
# substitution, and ANY redirection char (``>`` ``>>`` ``2>`` ``&>`` ``<``
# ``<(``). A read verb with a redirect becomes a writer (``cat x > y``), so
# the mere presence of ``<`` or ``>`` anywhere gates — even inside quotes
# (over-gating a quoted ``grep '>'`` to approval is the safe direction).
_CMD_SUBSTITUTION = re.compile(r"\$\(|`")
_REDIRECTION = re.compile(r"[<>]")
_BACKGROUND = re.compile(r"(?<!&)&(?!&)")  # a lone ``&`` (not ``&&``)
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[|;]")  # pipes / and-or / sequencing

#: Shell control / expansion / redirection operators that turn an otherwise
#: allowlisted verb into a vehicle for an arbitrary command — ``ls && rm x``,
#: ``ls; brew install x``, ``ls $(curl …)``, ``ls > /etc/x``, or a newline-
#: smuggled second command (``ls \n rm x``). Their presence DISQUALIFIES the
#: allowlist fast-path: the command must instead face the effect classifier
#: (effect mode) or approval. Closes a prefix-match escape open since 15a —
#: the allowlist prefix ``ls `` used to swallow everything chained after it,
#: auto-running in BOTH modes. Hardened in 15e. (The denylist still only
#: catches specific worst-cases, so it was never a sufficient backstop.)
_SHELL_OPERATORS = re.compile(r"[|&;<>\n`]|\$\(")


def _git_is_read(tokens: list[str]) -> bool:
    """Whether a ``git ...`` invocation only reads (subcommand-aware).

    A bare ``git`` is not enough; an unknown subcommand is not read. The
    genuinely dual-use subcommands (``config``, ``branch``, ``remote``) are
    admitted only in their read shapes.
    """
    args = tokens[1:]
    i = 0
    while i < len(args):  # skip global options: ``-C <path>``, ``-c k=v``, ``--x``
        a = args[i]
        if a in ("-C", "-c"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    if i >= len(args):
        return False  # bare ``git`` / only options
    sub, rest = args[i], args[i + 1:]
    if sub in _GIT_READ_SUBCMDS:
        return True
    if sub == "config":  # read only with an explicit get/list flag
        return any(r in ("--get", "--get-all", "--get-regexp", "--list", "-l")
                   for r in rest)
    if sub == "branch":  # read only when listing (no operand, no write flag)
        write_flags = {"-d", "-D", "-m", "-M", "-c", "-C",
                       "--delete", "--move", "--copy", "--edit-description",
                       "--set-upstream-to", "-u"}
        for r in rest:
            if r in write_flags or not r.startswith("-"):
                return False
        return True
    if sub == "remote":  # bare / show / get-url only
        return not rest or rest[0] in ("show", "get-url", "-v", "--verbose")
    return False


def _verb_is_read(tokens: list[str]) -> bool:
    """Whether one command segment (already tokenized) is provably read-only."""
    verb, rest = tokens[0], tokens[1:]
    if verb == "git":
        return _git_is_read(tokens)
    if verb not in READ_ONLY_VERBS:
        return False
    if verb == "env":
        # Bare ``env`` prints the environment; ``env VAR=v cmd`` EXECUTES cmd.
        return len(rest) == 0
    if verb == "find":
        return not any(t in _FIND_WRITER_FLAGS for t in rest)
    if verb == "sort":  # ``sort -o out`` writes a file
        return not any(t in ("-o", "--output") or t.startswith("--output=")
                       for t in rest)
    return True


def classify_command(command: str) -> str:
    """Classify a shell command as ``"read"`` | ``"mutate"`` | ``"unknown"``.

    Returns ``"read"`` ONLY when every pipeline segment's leading token is a
    confirmed read-only binary (git subcommand-checked) AND no mutating shell
    feature is present. Everything else — writers, unknown binaries, any
    redirection / substitution / chaining-with-a-writer / background — returns
    ``"unknown"`` (treated as a gate). Fail-closed by construction.

    ``"mutate"`` is currently only returned for an empty command (nothing to
    run); the policy treats ``"mutate"`` and ``"unknown"`` identically (gate),
    the distinction is kept for readability / future use.
    """
    cmd = (command or "").strip()
    if not cmd:
        return "mutate"
    # 1. Mutating shell features anywhere in the string → gate. A newline (or
    #    carriage return) is a command separator under ``shell=True`` — and
    #    shlex COLLAPSES it, so ``ls \n rm x`` would otherwise tokenize as
    #    ``ls rm x`` and read as a benign ``ls``. Gate on it explicitly.
    if "\n" in cmd or "\r" in cmd:
        return "unknown"
    if _CMD_SUBSTITUTION.search(cmd) or _REDIRECTION.search(cmd) or _BACKGROUND.search(cmd):
        return "unknown"
    # 2. Every segment's first token must be a confirmed read verb.
    segments = [s.strip() for s in _SEGMENT_SPLIT.split(cmd) if s.strip()]
    if not segments:
        return "unknown"
    for seg in segments:
        try:
            tokens = shlex.split(seg)
        except ValueError:  # unbalanced quotes / ambiguous parse → fail-closed
            return "unknown"
        if not tokens:
            return "unknown"
        if "=" in tokens[0]:  # env-assignment prefix (``FOO=bar cmd``) → gate
            return "unknown"
        if not _verb_is_read(tokens):
            return "unknown"
    return "read"


@dataclass
class PolicyResult:
    """A policy decision plus the human-readable reason behind it."""

    decision: Decision
    reason: str


def _match_denylist(payload: str, patterns: list[str]) -> str | None:
    """Return the first denylist pattern found in ``payload``, or None."""
    for pattern in patterns:
        if pattern and pattern in payload:
            return pattern
    return None


def resolve_path(path: str) -> Path:
    """Expand ``~`` and resolve symlinks — the canonical form roots are checked
    against. A symlink inside an allowed root that points outside it resolves
    outside and is treated as outside (escape-proof by construction)."""
    return Path(path).expanduser().resolve()


def under_any_root(path: str, roots: list[str]) -> bool:
    """Whether ``path`` (symlink-resolved) sits under any of ``roots``."""
    if not path:
        return False
    p = resolve_path(path)
    for root in roots:
        root = (root or "").strip()
        if not root:
            continue
        if p.is_relative_to(resolve_path(root)):
            return True
    return False


def _match_allowlist(command: str, allowlist: list[str]) -> bool:
    """Whether ``command`` is allowlisted (exact match or first-word prefix).

    Prefix rules match on word boundaries so ``ls`` allows ``ls -la ~/Codehome``
    but does NOT allow ``lsof`` (a substring-prefix would). Multi-word entries
    like ``git status`` must match the leading words exactly.

    A command carrying shell control/redirection operators (``&&``, ``;``,
    ``|``, ``$(…)``, ``>``, a smuggled newline, …) can NEVER be allowlisted,
    even if its leading verb matches: ``ls && rm x`` is not ``ls``. Such a
    command falls through to the classifier / approval instead (15e hardening).
    """
    cmd = command.strip()
    if _SHELL_OPERATORS.search(cmd):
        return False
    for entry in allowlist:
        entry = (entry or "").strip()
        if not entry:
            continue
        if cmd == entry or cmd.startswith(entry + " "):
            return True
    return False


def evaluate(
    *,
    name: str,
    effect: str,
    auto: bool,
    payload: str = "",
    constitution: Constitution | None = None,
) -> PolicyResult:
    """Decide what to do with one capability call.

    Args:
        name: Capability name (e.g. ``"macos.run_command"``).
        effect: ``"read" | "mutate" | "irreversible"``.
        auto: Capability-level auto flag (benign reads/mutates the design
            marks "auto" — get_time, system_info, notify, …).
        payload: The side-effect payload (the command string for
            run_command; empty for pure reads).
        constitution: Injected for tests; loaded from YAML if omitted.

    Returns:
        A :class:`PolicyResult` — allow / approve / deny + reason.
    """
    constitution = constitution or Constitution.load()
    cfg = constitution.system_mcp
    mode = cfg.get("mode", "strict")
    terminal = cfg.get("terminal", {})

    # 1. Terminal commands — denylist (always deny; approval can't override)
    #    then the allowlist ladder. Denylist patterns are SHELL fragments
    #    ("rm -rf", "| sh", "> /dev/"), meaningful ONLY for run_command, so
    #    they are scoped here (15c): a message search or file path that merely
    #    contains "sudo" is no longer falsely denied. fs safety comes from
    #    root-scoping (below), never the denylist.
    if name == "macos.run_command":
        hit = _match_denylist(payload, terminal.get("denylist_patterns", []))
        if hit:
            return PolicyResult("deny", f"command contains denylisted pattern '{hit}'")
        if not payload.strip():
            # Nothing can execute — let the capability body return its own
            # clean "empty command" error instead of asking approval for ''.
            return PolicyResult("allow", "empty command (no-op)")
        if _match_allowlist(payload, terminal.get("allowlist", [])):
            return PolicyResult("allow", "command is allowlisted")
        # Effect mode ONLY: a non-allowlisted command that the fail-closed
        # classifier proves read-only auto-runs. Strict mode never gets here
        # for a non-allowlisted command — it always falls to approve below.
        if mode == "effect" and classify_command(payload) == "read":
            return PolicyResult("allow", "read-only command (effect classifier)")
        return PolicyResult("approve", "non-allowlisted terminal command")

    # 3. Filesystem capabilities — root-scoped in BOTH modes (payload = the
    #    primary path). Outside allowed_roots is a hard deny that approval
    #    cannot override; writes inside scratch_root auto-run. fs.move's
    #    destination is enforced in the capability body (same resolver).
    if name.startswith("fs."):
        fs_cfg = cfg.get("fs", {})
        if not payload.strip():
            # Let the capability body return its own clean "path required"
            # error instead of gating an empty string (run_command precedent).
            return PolicyResult("allow", "empty path (no-op)")
        if not under_any_root(payload, fs_cfg.get("allowed_roots", [])):
            return PolicyResult(
                "deny", f"path outside allowed filesystem roots: {payload}"
            )
        if name in ("fs.write_file", "fs.append") and under_any_root(
            payload, [fs_cfg.get("scratch_root", "")]
        ):
            return PolicyResult("allow", "write inside scratch_root")
        # fall through: reads are auto=True (allow below); writes/moves/
        # deletes hit the mode ladder (approve).

    # 4. Everything else by mode.
    if mode == "effect":
        if effect == "read":
            return PolicyResult("allow", "read capability (effect mode)")
        return PolicyResult("approve", f"{effect} capability (effect mode)")

    # strict mode (default): only auto-marked capabilities run.
    if auto:
        return PolicyResult("allow", "auto capability (strict mode)")
    return PolicyResult("approve", "non-auto capability (strict mode)")
