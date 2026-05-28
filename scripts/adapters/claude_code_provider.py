"""Live Claude Code trace_provider (Phase 2B, ADR-0045 work).

Spawns the `claude` CLI in headless `-p`/--print mode with OTel
emission enabled (console exporter), parses the emitted spans into a
TraceRecord, and returns it to the harness.

Contract: same as Phase 1's TraceProvider:

    provider(trajectory, phrasing, adapter) -> TraceRecord

CLI invocation:

    claude -p "<phrasing>" --dangerously-skip-permissions

The `--dangerously-skip-permissions` flag auto-approves tool calls so a
headless run does not block on interactive prompts. It is explicit in
the args (not hidden in env vars) so a reader of the source knows the
harness is running in skip-permission mode.

Environment overrides (set by the provider; baseline env is restricted
to a minimal allowlist to avoid leaking parent secrets into the spawned
session):

    CLAUDE_CODE_ENABLE_TELEMETRY=1
    OTEL_TRACES_EXPORTER=console
    OTEL_LOG_USER_PROMPTS=0           # do not log prompt content
    OTEL_LOG_TOOL_DETAILS=1           # need tool.name + tool.arguments
                                      # for the matcher

The agent runs in an isolated temp working directory. Files written
there become `TraceRecord.artifacts` so `final_artifact_path` works
for skills that write rather than edit. Files under hidden
directories (`.claude/`, `.git/`, `.cache/`) are excluded so harness
state does not pollute the agent-output set.

OTel spans land on BOTH stdout and stderr depending on the Claude
Code build (Node ConsoleSpanExporter writes to stdout by default but
some Claude Code builds re-route to stderr). The provider parses both
channels and merges the events.

Errors:

  * `claude` not on PATH       -> RuntimeError (harness -> infra_fail)
  * Non-claude-code adapter    -> ValueError    (harness -> infra_fail)
  * Subprocess timeout         -> TimeoutError  (harness -> infra_fail)
  * Non-zero exit code         -> RuntimeError  (harness -> infra_fail)
                                   -- distinguishes crashed-agent from
                                   clean-exit-but-wrong-output

Tests for the unit behavior live in
`tests/lifecycle/test_claude_code_provider.py` (all paths mocked).
The live-spawn smoke test is gated on PHASE2_LIVE in
`tests/lifecycle/test_claude_code_provider_live.py`.
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

from adapters.claude_code_trace import _attr_value  # noqa: E402  reuse: prevents drift
from adapters.trace_record import TraceEvent, TraceRecord  # noqa: E402


_ALLOWED_ADAPTERS = {"claude-code"}  # Phase 2B only.

_DEFAULT_TIMEOUT_S = 300.0  # 5 minutes per cell; harness can override.

# Minimal env passed to the spawned `claude`. Allowlist documented per
# adversarial review-round-6 finding: a full `dict(os.environ)` was
# leaking AWS_*, GITHUB_TOKEN, etc., into the spawned session. We
# allowlist only the vars Claude Code documents as inputs plus the
# bare minimum a POSIX process needs to run.
_ALLOWED_ENV_KEYS: frozenset[str] = frozenset({
    # Anthropic / Claude Code
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    # OTel
    "OTEL_TRACES_EXPORTER",
    "OTEL_LOG_USER_PROMPTS",
    "OTEL_LOG_TOOL_DETAILS",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    # POSIX minimum
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TERM",
    # Node (Claude Code is Node)
    "NODE_OPTIONS",
    "NVM_DIR",
})


class ClaudeCodeProvider:
    """Live Claude Code trace_provider for the trajectory harness.

    Construction args:
      claude_bin       -- override the binary path; default: shutil.which("claude")
      timeout          -- subprocess timeout in seconds (default: 300).
      keep_workdirs    -- True keeps the per-spawn temp dir for inspection.
                          Default False cleans up after the run.
      extra_env        -- additional env-var keys to forward from the
                          parent process into the spawned session, on
                          top of `_ALLOWED_ENV_KEYS`. Use sparingly.

    Callable: provider(trajectory, phrasing, adapter) -> TraceRecord.
    """

    def __init__(
        self,
        claude_bin: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
        keep_workdirs: bool = False,
        extra_env: frozenset[str] | None = None,
    ) -> None:
        self._claude_bin = claude_bin
        self._timeout = timeout
        self._keep_workdirs = keep_workdirs
        self._extra_env = extra_env or frozenset()

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

        # Per-trajectory tempdir prefix so a debugging session can
        # identify the source from the directory name. Previously every
        # spawn used `trajectory-canary-` regardless of which trajectory
        # was running (adversarial review-round-6 finding).
        prefix = f"traj-{trajectory.skill}-{trajectory.scenario}-"
        workdir = Path(tempfile.mkdtemp(prefix=prefix))
        started_at = datetime.now(timezone.utc)
        try:
            env = self._build_env()
            args = [
                claude_bin,
                "-p", phrasing,
                "--dangerously-skip-permissions",
            ]
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

            # Non-zero exit means the agent crashed mid-task or the CLI
            # rejected the invocation. Distinguish from "agent finished
            # but produced the wrong artifact" by raising; the harness
            # records this as infra_fail (adversarial review-round-6 #5).
            if result.returncode != 0:
                stderr_tail = (result.stderr or "")[-500:]
                raise RuntimeError(
                    f"`claude` exited with code {result.returncode}; "
                    f"stderr tail: {stderr_tail!r}"
                )

            ended_at = datetime.now(timezone.utc)
            # Parse spans from BOTH stdout and stderr; Node Console
            # ExportSpanExporter writes to stdout in some builds and
            # stderr in others. Merging both is defensive and zero-cost.
            events = _parse_otel_lines(result.stdout) + _parse_otel_lines(
                result.stderr,
                start_seq=len(_parse_otel_lines(result.stdout)),
            )
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
        """Return a minimal env: allowlisted parent vars + provider overrides.

        Replaces a `dict(os.environ)` that leaked AWS_*, GITHUB_TOKEN,
        and other parent secrets into the spawned `claude` session
        (adversarial review-round-6 #1).
        """
        allowed = _ALLOWED_ENV_KEYS | self._extra_env
        env = {k: v for k, v in os.environ.items() if k in allowed}
        env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        env["OTEL_TRACES_EXPORTER"] = "console"
        env["OTEL_LOG_USER_PROMPTS"] = "0"
        env["OTEL_LOG_TOOL_DETAILS"] = "1"
        return env


def _parse_otel_lines(text: str, start_seq: int = 0) -> list[TraceEvent]:
    """Pull OTel JSON spans out of mixed text and convert to events.

    Real Claude Code output interleaves spans with startup noise
    (`Loading skills from...`, etc.). Filter non-JSON lines silently.
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
        event = _span_to_event(span, seq=start_seq + len(events))
        if event is not None:
            events.append(event)
    return events


def _span_to_event(span: dict, seq: int) -> TraceEvent | None:
    """Convert one OTel span dict into a TraceEvent.

    Uses `claude_code_trace._attr_value` (imported above) so the
    string/int/double/bool branch list cannot drift from the Phase 1
    shim. Adversarial review-round-6 caught a local copy that silently
    dropped doubleValue and boolValue attributes.
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
    """Flatten OTel attribute list to a dict, reusing the Phase 1
    `_attr_value` so doubleValue / boolValue / intValue / stringValue
    all unwrap consistently."""
    out: dict = {}
    for entry in attrs or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("key")
        if key is None:
            continue
        value = _attr_value(entry)
        if value is not None:
            out[key] = value
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
    """sha256 every NON-HIDDEN file the agent left in its working directory.

    Hidden paths (`.claude/`, `.git/`, `.cache/`) are excluded because
    they're harness state, not agent-produced content. Without this
    exclusion, Claude Code's session-log JSON would land in
    TraceRecord.artifacts and the `final_artifact_path: "*.md"`
    assertion would resolve against the wrong "final" file
    (adversarial review-round-6 #7).
    """
    artifacts: dict[str, str] = {}
    if not workdir.is_dir():
        return artifacts
    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(workdir).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rel = str(path.relative_to(workdir))
        artifacts[rel] = "sha256:" + hashlib.sha256(data).hexdigest()
    return artifacts
