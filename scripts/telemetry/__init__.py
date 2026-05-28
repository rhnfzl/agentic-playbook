"""Skill telemetry subsystem.

Captures skill_load + skill_complete events from Claude Code's
`gen_ai.*` OTel emission, normalizes to a privacy-bounded record
shape, and surfaces per-skill usage stats.

Off by default. Two opt-in toggles:

  1. The collector (docker or pure-python) only runs when the user
     explicitly invokes `make telemetry-init`.
  2. Every consumer (report CLI, decay-by-usage, Atlas badges)
     checks `is_enabled()` and degrades cleanly when telemetry is
     marked off via `TELEMETRY=off` or `TELEMETRY_ENABLED=0`.

Privacy: only metadata is recorded. Prompt and response bodies are
stripped at the collector. The default storage location is XDG-style
under `~/.coding-agents-playbook/telemetry/`; nothing is sent
upstream.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple


DEFAULT_TELEMETRY_DIR = Path.home() / ".coding-agents-playbook" / "telemetry"
JSONL_FILENAME = "skills.jsonl"

_DISABLED_VALUES = {"off", "0", "false", "no", "disabled"}


def is_enabled() -> bool:
    """Return False if the user has explicitly disabled telemetry.

    Telemetry is disabled when ANY of these env vars is set to a
    falsy value (off, 0, false, no, disabled):

      TELEMETRY
      TELEMETRY_ENABLED
      PLAYBOOK_TELEMETRY

    Otherwise telemetry is "available" (consumers still need to find
    a JSONL file to read from; the env var only governs whether they
    are allowed to try).
    """
    for var in ("TELEMETRY", "TELEMETRY_ENABLED", "PLAYBOOK_TELEMETRY"):
        raw = os.environ.get(var, "").strip().lower()
        if raw in _DISABLED_VALUES:
            return False
    return True


def storage_path() -> Path:
    """Resolve the JSONL storage path.

    Env var `TELEMETRY_DIR` overrides the default if the user wants
    to keep telemetry in a different XDG-style directory.
    """
    override = os.environ.get("TELEMETRY_DIR", "").strip()
    if override:
        return Path(override).expanduser() / JSONL_FILENAME
    return DEFAULT_TELEMETRY_DIR / JSONL_FILENAME


class TelemetryRecord(NamedTuple):
    """Privacy-bounded record. Only metadata, never bodies."""

    skill: str               # e.g. "to-prd"
    adapter: str             # e.g. "claude-code"
    model: str               # e.g. "claude-opus-4-7"
    fired_at: str            # ISO 8601 with TZ
    latency_ms: float        # end-to-end skill duration
    input_tokens: int
    output_tokens: int
    session_id: str = ""     # optional, may be redacted
