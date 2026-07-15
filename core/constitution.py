"""Agent constitution enforcement.

Every side-effectful operation (file write, file delete, HTTP call, shell
command) must pass through guard() before executing. This is the runtime
boundary described in the PRD (TR-07): violations halt execution, they are
not advisory.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Phase 14e — defaults for the optional ``notifications:`` block (OSA proactive
# policy knobs). Merged under any values present in the YAML so configs written
# before 14e keep loading unchanged.
DEFAULT_NOTIFICATIONS: dict = {
    "quiet_hours_start": "22:00",   # local time, HH:MM
    "quiet_hours_end": "08:00",     # overnight wrap supported (start > end)
    "rate_limit_seconds": 300,       # max 1 announced message per app per window
    "activity_idle_minutes": 10,     # HID idle < this => Tony is active
    "chat_activity_minutes": 30,     # fallback: last OSA chat within this => active
    "briefing_time": "08:30",       # daily briefing, local time
    "briefing_enabled": True,
}


# Phase 14d — defaults for the optional ``voice:`` block (OSA voice-pipeline
# knobs). Merged under any values present in the YAML so configs written
# before 14d keep loading unchanged. ``enabled`` is a HARD default of False:
# the voice service never runs unless Tony opts in on-device.
DEFAULT_VOICE: dict = {
    "enabled": False,            # hard default — opt-in on-device only
    "wake_word": "osa",         # openWakeWord phrase (custom model TBD)
    "stt_model": "small",       # faster-whisper size (latency/quality knob)
    # Piper voice model (2026-07-08, voice-OUT pass): a bare voice NAME
    # resolved under ``voice_dir``, or an absolute .onnx path. Default is the
    # auditioned calm British male (JARVIS register).
    "piper_voice": "en_GB-alan-medium",
    "voice_dir": "~/.agentic-os/voices",  # where Piper .onnx models live
    # Voice-OUT toggle (2026-07-08): speak OSA's chat replies + announced
    # proactive messages aloud. Independent of voice-IN (wake word / STT):
    # TTS needs no mic permission, so it can run before the full loop lands.
    "speak_replies": True,
    # Speech cadence (2026-07-08, Tony's live feedback): Piper's length_scale
    # — 1.0 = the model's trained pace, LOWER = faster. Alan-medium's default
    # is deliberate/slow; ~0.85 sounds like natural conversation.
    "length_scale": 0.85,
    # §9 Q3 RESOLVED (2026-07-08): always-listening is a RUNTIME opt-in
    # (POST /api/osa/voice/wake) — this YAML default stays true so every
    # sidecar start comes up push-to-talk only. Guarded by the safety test.
    "push_to_talk_only": True,
    "wake_stt_model": "tiny",    # fast whisper size for wake-burst checks
    "wake_ack": "Yes?",          # spoken ack for a bare "Osa"
    "wake_aliases": [],          # extra whisper renderings of the wake word
    # Conversation mode (2026-07-08): after a reply finishes playing, the
    # next utterance within this window needs no wake word (0 disables).
    "followup_window_s": 8.0,
    # Half-duplex echo guard (2026-07-14): discard any captured utterance
    # whose recording overlapped OSA's own TTS playback, or that started
    # within this cooldown after playback ended (swallows the echo tail so
    # OSA never answers — or re-wakes — itself). 0 effectively disables it.
    "echo_cooldown_s": 1.0,
    "min_rms": 0.02,             # energy gate for speech frames (0 disables)
    "mute": False,               # global output mute (runtime-flippable)
}


# Phase 15a — defaults for the optional ``system_mcp:`` block (OSA System MCP
# safety policy). Merged under any values present in the YAML so configs
# written before 15a keep loading unchanged. ``mode: strict`` is the hard
# default: only allowlisted terminal commands auto-run; everything else halts
# to human approval. Denylist patterns deny in BOTH modes.
DEFAULT_SYSTEM_MCP: dict = {
    "mode": "strict",              # strict | effect (effect migration = 15e)
    "terminal": {
        "allowlist": [              # auto-run in strict mode (prefix or exact)
            "date",
            "uptime",
            "whoami",
            "pwd",
            "ls",
            "df",
            "git status",
            "git log",
        ],
        "denylist_patterns": [      # ALWAYS deny (both modes)
            "rm -rf",
            "sudo",
            "dd ",
            "mkfs",
            "curl | sh",
            "| sh",
            "> /dev/",
            ":(){",
            "chmod 777 /",
        ],
    },
    # Phase 15b — filesystem capability scoping (design §4.2 / §5.2).
    # Reads/writes are confined to allowed_roots (symlink-resolved); writes
    # inside scratch_root auto-run even in strict mode.
    "fs": {
        "allowed_roots": [
            "~/Codehome",
            "~/Brain2",
        ],
        "scratch_root": "~/Codehome/AgenticOS/data/osa_scratch",
    },
    # Phase 15c — iMessage read (chat.db). db_path is CONFIG, never a caller
    # arg, so an MCP client can't repoint the reader at another SQLite file.
    "messages": {
        "db_path": "~/Library/Messages/chat.db",
        "max_limit": 200,
    },
    # Phase 15d — Mail (AppleScript → Mail.app; transport locked 2026-07-13).
    # The account is CONFIG, never a caller arg (db_path precedent). Body
    # fetch runs behind its own short timeout — see tools/system/mail_mcp.py.
    "mail": {
        "account": "iCloud",
        "default_mailbox": "INBOX",
        "max_limit": 100,
        "body_timeout_s": 10,
        # Phase 15e — on-disk .emlx body fallback root (FDA-dependent). Config,
        # never a caller arg (db_path precedent). Faster than the AppleScript
        # ``content of <msg>`` fetch that hung 40s+ in the 15d spike.
        "emlx_root": "~/Library/Mail",
    },
}


def _merge_system_mcp(raw_block: dict | None) -> dict:
    """Two-level defaults merge for the ``system_mcp`` block.

    A partial block only overrides the keys it names — including inside the
    nested ``terminal`` dict — so adding one allowlist entry in YAML doesn't
    silently drop the default denylist.
    """
    raw_block = raw_block or {}
    merged = {**DEFAULT_SYSTEM_MCP, **raw_block}
    merged["terminal"] = {
        **DEFAULT_SYSTEM_MCP["terminal"],
        **(raw_block.get("terminal") or {}),
    }
    merged["fs"] = {
        **DEFAULT_SYSTEM_MCP["fs"],
        **(raw_block.get("fs") or {}),
    }
    merged["messages"] = {
        **DEFAULT_SYSTEM_MCP["messages"],
        **(raw_block.get("messages") or {}),
    }
    merged["mail"] = {
        **DEFAULT_SYSTEM_MCP["mail"],
        **(raw_block.get("mail") or {}),
    }
    return merged


class ConstitutionViolation(Exception):
    """Raised when a tool call violates a hard constraint. Halts the run."""


class ApprovalRequired(Exception):
    """Raised when an action type needs human approval before executing."""

    def __init__(self, action: str, description: str):
        """Initialize with the action name and a human-readable description.

        Args:
            action: The action type requiring approval (e.g. "file_delete").
            description: Explanation of why approval is needed.
        """
        self.action = action
        self.description = description
        super().__init__(f"Approval required for '{action}': {description}")


@dataclass
class Constitution:
    """Runtime enforcement of agent safety constraints and resource budgets.

    Attributes:
        approval_required: Map of action types to descriptions requiring human sign-off.
        limits: Resource limits (max tokens, cost cap, file-write cap).
        blocked: List of payload patterns that are unconditionally forbidden.
        write_allowlist: List of directory roots the agent is allowed to write into.
    """

    approval_required: dict[str, str] = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    blocked: list[str] = field(default_factory=list)
    write_allowlist: list[str] = field(default_factory=list)
    notifications: dict = field(
        default_factory=lambda: dict(DEFAULT_NOTIFICATIONS)
    )
    voice: dict = field(
        default_factory=lambda: dict(DEFAULT_VOICE)
    )
    system_mcp: dict = field(
        default_factory=lambda: _merge_system_mcp(None)
    )

    @classmethod
    def load(cls, path: Path | None = None) -> "Constitution":
        """Load a Constitution from a YAML file.

        Args:
            path: Path to the constitution YAML. Defaults to
                config/constitution.yaml.

        Returns:
            A populated Constitution instance.
        """
        path = path or CONFIG_DIR / "constitution.yaml"
        raw = yaml.safe_load(path.read_text())["constitution"]
        return cls(
            approval_required={
                item["action"]: item.get("description", "")
                for item in raw.get("approval_required", [])
            },
            limits=raw.get("limits", {}),
            blocked=raw.get("blocked", []),
            write_allowlist=raw.get("write_allowlist", []),
            # 14e: absent block (pre-14e configs) => pure defaults; a partial
            # block only overrides the keys it names.
            notifications={
                **DEFAULT_NOTIFICATIONS,
                **(raw.get("notifications") or {}),
            },
            # 14d: absent block (pre-14d configs) => pure defaults; a partial
            # block only overrides the keys it names.
            voice={
                **DEFAULT_VOICE,
                **(raw.get("voice") or {}),
            },
            # 15a: absent block (pre-15a configs) => pure defaults; a partial
            # block only overrides the keys it names (two-level merge).
            system_mcp=_merge_system_mcp(raw.get("system_mcp")),
        )

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------
    def guard(self, action_type: str, payload: str = "", *, approved: bool = False) -> None:
        """Evaluate a tool call before execution.

        Raises ConstitutionViolation for blocked operations and
        ApprovalRequired for actions needing human sign-off (unless the
        caller passes approved=True after obtaining it).
        """
        for pattern in self.blocked:
            if pattern in payload:
                raise ConstitutionViolation(
                    f"Blocked operation: payload contains '{pattern}'"
                )

        if action_type in self.approval_required and not approved:
            raise ApprovalRequired(action_type, self.approval_required[action_type])

    def guard_write_path(self, target: str | os.PathLike) -> None:
        """Ensure the target path is inside an allowlisted root directory.

        Args:
            target: Filesystem path the agent intends to write to.

        Raises:
            ConstitutionViolation: If the path is outside all allowlisted roots.
        """
        resolved = Path(target).resolve()
        for root in self.write_allowlist:
            try:
                resolved.relative_to(Path(root).resolve())
                return
            except ValueError:
                continue
        raise ConstitutionViolation(
            f"Write outside allowlisted roots: {resolved}"
        )

    def check_token_budget(self, tokens_used: int) -> None:
        """Raise ConstitutionViolation if tokens_used exceeds the per-workflow cap.

        Args:
            tokens_used: Total tokens consumed so far in the workflow.
        """
        budget = self.limits.get("max_tokens_per_workflow")
        if budget and tokens_used > budget:
            raise ConstitutionViolation(
                f"Token budget exceeded: {tokens_used} > {budget}"
            )

    def check_cost_budget(self, cost_today_usd: float) -> None:
        """Raise ConstitutionViolation if daily cost exceeds the configured cap.

        Args:
            cost_today_usd: Cumulative USD cost for the current day.
        """
        cap = self.limits.get("max_cost_per_day_usd")
        if cap and cost_today_usd > cap:
            raise ConstitutionViolation(
                f"Daily cost cap exceeded: ${cost_today_usd:.2f} > ${cap:.2f}"
            )

    def check_files_written(self, count: int) -> None:
        """Raise ConstitutionViolation if file-write count exceeds the per-run cap.

        Args:
            count: Number of files written so far in the current run.
        """
        cap = self.limits.get("max_files_written_per_run")
        if cap and count > cap:
            raise ConstitutionViolation(
                f"File-write cap exceeded: {count} > {cap}"
            )
