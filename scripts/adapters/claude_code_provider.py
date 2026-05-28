"""Live Claude Code trace_provider (Phase 2B, ADR-0045 work).

Spawns the `claude` CLI in headless `-p`/--print mode with OTel
emission enabled (console exporter writes spans to stderr), parses the
emitted spans into a TraceRecord via the Phase 1 shim, and returns it
to the harness.

Contract: same as Phase 1's TraceProvider:

    provider(trajectory, phrasing, adapter) -> TraceRecord

CLI invocation:

    claude -p "<phrasing>"

Environment overrides (set by the provider):

    CLAUDE_CODE_ENABLE_TELEMETRY=1
    OTEL_TRACES_EXPORTER=console
    OTEL_LOG_USER_PROMPTS=0           # do not log prompt content
    OTEL_LOG_TOOL_DETAILS=1           # need tool.name + tool.arguments
                                      # for the matcher

The agent runs in an isolated temp working directory. Files written
there become `TraceRecord.artifacts` so `final_artifact_path` works
for skills that write rather than edit existing files.

Errors:

  * `claude` not on PATH       -> RuntimeError (harness -> infra_fail)
  * Non-claude-code adapter    -> ValueError    (harness -> infra_fail)
  * Subprocess timeout         -> TimeoutError  (harness -> infra_fail)

The provider does NOT swallow these; the harness's try/except in
run_harness produces `infra_fail` cells that an operator can
distinguish from agent-quality regressions.

Tests for the unit behavior live in
`tests/lifecycle/test_claude_code_provider.py` (all paths mocked).
The live-spawn smoke test is gated on PHASE2_LIVE in
`tests/lifecycle/test_claude_code_provider_live.py` (Phase 2B Task 4).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.trace_record import TraceEvent, TraceRecord  # noqa: E402


_ALLOWED_ADAPTERS = {"claude-code"}  # Phase 2B only.

_DEFAULT_TIMEOUT_S = 300.0  # 5 minutes per cell; harness can override.


class ClaudeCodeProvider:
    """Live Claude Code trace_provider for the trajectory harness.

    Construction args:
      claude_bin     -- override the binary path (default: shutil.which("claude"))
      timeout        -- subprocess timeout in seconds (default: 300).
      keep_workdirs  -- True keeps the per-spawn temp dir for inspection.
                        Default False cleans up after the run.

    Callable: provider(trajectory, phrasing, adapter) -> TraceRecord.
    """

    def __init__(
        self,
        claude_bin: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
        keep_workdirs: bool = False,
    ) -> None:
        self._claude_bin = claude_bin
        self._timeout = timeout
        self._keep_workdirs = keep_workdirs

    def __call__(
        self,
        trajectory,  # type: ignore[no-untyped-def]
        phrasing: str,
        adapter: str,
    ) -> TraceRecord:
        if adapter not in _ALLOWED_ADAPTERS:
            raise ValueError(
                f"ClaudeCodeProvider only handles adapter='claude-code' "
                f"in Phase 2B (got {adapter!r}). Codex / Cursor / Windsurf "
                f"shims land in Phase 3+."
            )

        claude_bin = self._claude_bin or shutil.which("claude")
        if not claude_bin:
            raise RuntimeError(
                "`claude` binary not on PATH. Install Claude Code "
                "(https://docs.claude.com/en/docs/claude-code) or pass "
                "claude_bin=... to ClaudeCodeProvider explicitly."
            )

        workdir = Path(tempfile.mkdtemp(prefix="trajectory-canary-"))
        started_at = datetime.now(timezone.utc)
        try:
            env = self._build_env()
            args = [claude_bin, "-p", phrasing]
            try:
                result = subprocess.run(
                    args,
                    cwd=str(workdir),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(
                    f"`claude` did not return within {self._timeout}s "
                    f"({exc.cmd!r})"
                ) from exc

            ended_at = datetime.now(timezone.utc)
            events = _parse_otel_lines(result.stderr)
            artifacts = _scan_workdir_artifacts(workdir)

            return TraceRecord(
                adapter="claude-code",
                model=_detect_model(events) or trajectory.model_pinned or "unknown",
                session_id=f"live-{started_at.isoformat()}",
                prompt=phrasing,
                events=events,
                artifacts=artifacts,
                total_input_tokens=_sum_tokens(events, "input_tokens"),
                total_output_tokens=_sum_tokens(events, "output_tokens"),
                started_at=started_at,
                ended_at=ended_at,
            )
        finally:
            if not self._keep_workdirs:
                shutil.rmtree(workdir, ignore_errors=True)

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        env["OTEL_TRACES_EXPORTER"] = "console"
        # Do not leak prompt text into the OTel pipeline.
        env["OTEL_LOG_USER_PROMPTS"] = "0"
        # Need tool name + arguments for the matcher's must_invoke_tool /
        # final_artifact_path primitives.
        env["OTEL_LOG_TOOL_DETAILS"] = "1"
        return env


def _parse_otel_lines(text: str) -> list[TraceEvent]:
    """Pull OTel JSON spans out of mixed-stderr text and convert to events.

    Real Claude Code stderr interleaves spans with startup noise
    (`Loading skills from...`, etc.). Filter non-JSON lines silently.
    Lines that parse to a JSON object get fed to the Phase 1 OTel
    parsing helpers via in-memory conversion.
    """
    events: list[TraceEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] != "{":
            continue
        try:
            span = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(span, dict):
            continue
        event = _span_to_event(span, seq=len(events))
        if event is not None:
            events.append(event)
    return events


def _span_to_event(span: dict, seq: int) -> TraceEvent | None:
    """Best-effort: convert one OTel span dict into a TraceEvent.

    Mirrors `claude_code_trace._span_to_event` (Phase 1) but is local
    to this module to avoid importing across the adapter boundary.
    Operation name -> kind, name attribute -> name, etc.
    """
    attrs = _attrs_to_dict(span.get("attributes", []))
    op = attrs.get("gen_ai.operation.name")

    start = int(span.get("startTimeUnixNano", "0") or 0)
    end = int(span.get("endTimeUnixNano", "0") or 0)
    duration_ms = max(0, (end - start) // 1_000_000) if end and start else None

    if op == "tool_call":
        name = attrs.get("tool.name") or span.get("name", "unknown")
        arguments_str = attrs.get("tool.arguments")
        arguments: dict | None = None
        if isinstance(arguments_str, str):
            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = {"raw": arguments_str}
        return TraceEvent(
            seq=seq, kind="tool_call", name=str(name),
            arguments=arguments, duration_ms=duration_ms, raw_attrs=attrs,
        )
    if op == "skill_load":
        name = attrs.get("skill.name") or span.get("name", "unknown")
        return TraceEvent(
            seq=seq, kind="skill_load", name=str(name),
            arguments=None, duration_ms=duration_ms, raw_attrs=attrs,
        )
    if op == "chat":
        model = attrs.get("gen_ai.request.model")
        return TraceEvent(
            seq=seq, kind="model_response",
            name=str(model or "chat"),
            arguments=None, duration_ms=duration_ms, raw_attrs=attrs,
        )
    return None


def _attrs_to_dict(attrs):  # type: ignore[no-untyped-def]
    out: dict = {}
    for entry in attrs or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if key is None:
            continue
        value = entry.get("value", {})
        if "stringValue" in value:
            out[key] = value["stringValue"]
        elif "intValue" in value:
            try:
                out[key] = int(value["intValue"])
            except (TypeError, ValueError):
                pass
    return out


def _detect_model(events: list[TraceEvent]) -> str | None:
    for event in events:
        if event.kind == "model_response" and event.name:
            return event.name
    return None


def _sum_tokens(events: list[TraceEvent], key: str) -> int:
    total = 0
    for event in events:
        value = event.raw_attrs.get(f"gen_ai.usage.{key}") or 0
        try:
            total += int(value)
        except (TypeError, ValueError):
            pass
    return total


def _scan_workdir_artifacts(workdir: Path) -> dict[str, str]:
    """sha256 every file the agent left in its working directory.

    Recursive; sorted; relative paths so trajectories' final_artifact_path
    globs match against `out.md` (root) or `subdir/foo.md` consistently
    regardless of where the temp dir lives.
    """
    artifacts: dict[str, str] = {}
    if not workdir.is_dir():
        return artifacts
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rel = str(path.relative_to(workdir))
        artifacts[rel] = "sha256:" + hashlib.sha256(data).hexdigest()
    return artifacts
