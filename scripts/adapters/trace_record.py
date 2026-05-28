"""TraceRecord: normalized cross-adapter trace data (ADR-0045).

Every adapter trace shim (Claude Code, Codex, Cursor, Windsurf) takes
its tool's native trace stream and produces a TraceRecord. The matcher
(scripts/trajectory_matcher.py) reads TraceRecord only; it does not
import any per-adapter module.

This module is pure data + light accessor helpers. No I/O, no LLM, no
filesystem access. Adding a new trace shim does not require editing
this module unless the event taxonomy itself changes (which is an
ADR amendment).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NamedTuple


TRACE_EVENT_KINDS: frozenset[str] = frozenset(
    {"skill_load", "tool_call", "tool_result", "model_response"}
)


KNOWN_TRACE_ADAPTERS: frozenset[str] = frozenset(
    {"claude-code", "codex", "cursor", "windsurf"}
)


class TraceEvent(NamedTuple):
    """One event in a TraceRecord's events list.

    Field semantics:
      seq           -- monotonic order within the trajectory; 0-based.
      kind          -- one of TRACE_EVENT_KINDS.
      name          -- skill slug, tool name, etc., context-dependent on kind.
      arguments     -- tool-call argument dict (kind=tool_call only) or None.
      duration_ms   -- wall-clock duration (kind=tool_call) or None.
      raw_attrs     -- un-normalized adapter-native attrs preserved for
                       debugging when the matcher hits an unexpected case.
    """

    seq: int
    kind: Literal["skill_load", "tool_call", "tool_result", "model_response"]
    name: str
    arguments: dict | None
    duration_ms: int | None
    raw_attrs: dict


class TraceRecord(NamedTuple):
    """One end-to-end trace for one (trajectory phrasing, adapter) execution.

    Field semantics:
      adapter              -- which trace shim produced this record; one of
                              KNOWN_TRACE_ADAPTERS.
      model                -- the model the adapter actually ran (may differ
                              from trajectory's model_pinned; matcher reports).
      session_id           -- adapter-specific session identifier; opaque to
                              the matcher, used only in the human report.
      prompt               -- the user message that triggered this run; one
                              of the trajectory's phrasings, verbatim.
      events               -- ordered list of TraceEvents. Monotonic by seq.
      artifacts            -- {relative_path: "sha256:<hex>"} for every file
                              written during the run. Lets the DSL assert
                              file-content fingerprints without re-reading.
      total_input_tokens   -- usage counter, used for cost-mode reporting.
      total_output_tokens  -- usage counter.
      started_at / ended_at -- wall-clock bracket.
    """

    adapter: str
    model: str
    session_id: str
    prompt: str
    events: list[TraceEvent]
    artifacts: dict[str, str]
    total_input_tokens: int
    total_output_tokens: int
    started_at: datetime
    ended_at: datetime

    def tool_calls(self) -> list[TraceEvent]:
        """Return only the tool_call events, in trace order."""
        return [e for e in self.events if e.kind == "tool_call"]

    def skill_loads(self) -> list[TraceEvent]:
        """Return only the skill_load events, in trace order."""
        return [e for e in self.events if e.kind == "skill_load"]
