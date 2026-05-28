"""Live Claude Code trace_provider (Phase 2B, ADR-0045).

Spawns the `claude` CLI in headless `-p`/--print mode with OTel
emission enabled (console exporter), parses the emitted spans into a
TraceRecord via the shared `claude_code_trace.events_from_text`, and
returns it to the harness.

Contract: TraceProvider callable:

    provider(trajectory, phrasing, adapter) -> TraceRecord

CLI invocation (default; least-privilege per the security review):

    claude -p "<phrasing>" --allowedTools Edit,Glob,Grep,NotebookEdit,Read,Write

The default tool allowlist explicitly excludes Bash, WebFetch, WebSearch,
SendMessage, and Task because a malicious or careless trajectory
phrasing could otherwise instruct the agent to do arbitrary things
with the host user's permissions. Trajectories that legitimately need
those tools opt in via `extra_allowed_tools=` on the provider.

Dangerous-skip opt-in (CI sandbox only):

    claude -p "<phrasing>" --dangerously-skip-permissions

Enabled when `PHASE2_LIVE_DANGEROUS=1` is set OR when the provider is
constructed with `dangerous_skip_perms=True`. Auto-approves every tool
call. Use ONLY inside an already-sandboxed environment (rootless
container with no host mounts, gVisor, etc.). The provider emits one
line to stderr per spawn in this mode so the escalation is visible.

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
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.claude_code_trace import events_from_text  # noqa: E402  shared OTel parser
from adapters.trace_record import TraceEvent, TraceRecord  # noqa: E402


_ALLOWED_ADAPTERS = {"claude-code"}  # Phase 2B only.

_DEFAULT_TIMEOUT_S = 300.0  # 5 minutes per cell; harness can override.

# Default tool allowlist for the spawned `claude -p` session.
#
# Security-review (HIGH finding, 2026-05-28): the previous default was
# `--dangerously-skip-permissions`, which auto-approved EVERY tool call.
# A malicious or accidentally-misspelled trajectory phrasing (e.g.
# "delete every file under ~") would have run unimpeded with the user's
# permissions. The trajectory harness is a TEST surface, not a trusted
# automation surface; we apply least-privilege by default.
#
# The default allowlist below lets the agent:
#   - Read existing files inside its workdir (no exfil of the parent fs
#     beyond what the env-allowlist already permits).
#   - Write/Edit/NotebookEdit inside the workdir to produce the
#     artifacts trajectories assert on.
#   - Glob/Grep to navigate the workdir.
#
# Tools deliberately EXCLUDED from the default:
#   - Bash             (arbitrary shell command execution)
#   - WebFetch         (egress to attacker-controlled URLs)
#   - WebSearch        (egress + content injection from search results)
#   - SendMessage      (cross-agent escalation)
#   - Task             (subagent spawn, recursive risk)
#
# Trajectories that legitimately need Bash etc. must opt-in via
# `ClaudeCodeProvider(extra_allowed_tools=frozenset({"Bash"}))` or via
# a future per-trajectory `allowed_tools:` frontmatter field. Doing it
# explicitly keeps the threat model visible in the trajectory file.
_DEFAULT_ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "NotebookEdit",
        "Glob",
        "Grep",
    }
)

# Opt-in env var that switches back to the legacy
# `--dangerously-skip-permissions` behavior. Only honored when set to
# exactly "1"; any other value is ignored. The provider emits a stderr
# warning on every spawn in this mode so a CI operator sees the
# escalation in their logs.
_DANGEROUS_OPT_IN_VAR = "PHASE2_LIVE_DANGEROUS"

# Minimal env passed to the spawned `claude`. Allowlist documented per
# adversarial review-round-6 finding: a full `dict(os.environ)` was
# leaking AWS_*, GITHUB_TOKEN, etc., into the spawned session. We
# allowlist only the vars Claude Code documents as inputs plus the
# bare minimum a POSIX process needs to run.
_ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {
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
    }
)


class ClaudeCodeProvider:
    """Live Claude Code trace_provider for the trajectory harness.

    Construction args:
      claude_bin             -- override the binary path; default:
                                shutil.which("claude").
      timeout                -- subprocess timeout in seconds (default: 300).
      keep_workdirs          -- True keeps the per-spawn temp dir for
                                inspection. Default False cleans up after
                                the run.
      extra_env              -- additional env-var keys to forward from
                                the parent process into the spawned
                                session, on top of `_ALLOWED_ENV_KEYS`.
                                Use sparingly.
      extra_allowed_tools    -- additional Claude Code tool names to
                                add to the default `--allowedTools` list.
                                For example, frozenset({"Bash"}) when a
                                trajectory needs shell execution. The
                                addition is opt-in per provider instance.
      dangerous_skip_perms   -- True passes `--dangerously-skip-permissions`
                                INSTEAD of the allowlist. Equivalent to
                                setting `PHASE2_LIVE_DANGEROUS=1`; the
                                env var is checked at construction time
                                if this arg is False. Both code paths
                                emit a loud stderr warning per spawn.

    Callable: provider(trajectory, phrasing, adapter) -> TraceRecord.

    Security:

    The default mode constrains the spawned `claude -p` session to a
    narrow tool allowlist (`Read,Write,Edit,NotebookEdit,Glob,Grep`).
    Bash, WebFetch, WebSearch, SendMessage, and Task are NOT in the
    default allowlist, because a malicious or careless trajectory
    phrasing could otherwise instruct the agent to do arbitrary
    things with the host user's permissions.

    The dangerous-skip mode (env or arg) is a deliberate escape hatch
    for environments that already provide a real sandbox
    (e.g. a CI runner inside an ephemeral container). When enabled the
    provider emits one line to stderr per spawn so the escalation is
    visible in operational logs.
    """

    def __init__(
        self,
        claude_bin: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT_S,
        keep_workdirs: bool = False,
        extra_env: frozenset[str] | None = None,
        extra_allowed_tools: frozenset[str] | None = None,
        dangerous_skip_perms: bool = False,
    ) -> None:
        self._claude_bin = claude_bin
        self._timeout = timeout
        self._keep_workdirs = keep_workdirs
        self._extra_env = extra_env or frozenset()
        self._allowed_tools = _DEFAULT_ALLOWED_TOOLS | (
            extra_allowed_tools or frozenset()
        )
        env_opt_in = os.environ.get(_DANGEROUS_OPT_IN_VAR) == "1"
        self._dangerous_skip_perms = dangerous_skip_perms or env_opt_in

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
            args = self._build_args(claude_bin, phrasing)
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
                    f"`claude` did not return within {self._timeout}s ({exc.cmd!r})"
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
            # Parse spans from BOTH stdout and stderr (Node Console
            # SpanExporter writes to stdout in some builds and stderr in
            # others) using the shared `events_from_text`. That helper
            # flattens OTLP envelopes and sorts spans by
            # `startTimeUnixNano` so seq numbers reflect time order, not
            # pipe order. Without that sort a span emitted to stderr
            # before a stdout span would have a larger seq, flipping
            # `first_skill_loaded` / `call_order` assertions on mixed
            # channels.
            events = events_from_text(
                (result.stdout or "") + "\n" + (result.stderr or "")
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

    def _build_args(self, claude_bin: str, phrasing: str) -> list[str]:
        """Return the argv passed to subprocess.run.

        Default: `-p <phrasing> --allowedTools Read,Write,Edit,...`
        Dangerous opt-in: `-p <phrasing> --dangerously-skip-permissions`

        The dangerous mode emits one line to stderr per spawn so the
        escalation is visible in operational logs even when output is
        captured by CI (security-review HIGH finding, 2026-05-28).
        """
        if self._dangerous_skip_perms:
            print(
                f"  warn  ClaudeCodeProvider spawning with "
                f"--dangerously-skip-permissions ({_DANGEROUS_OPT_IN_VAR} "
                f"or dangerous_skip_perms=True). The agent can run any "
                f"tool unsupervised; only enable inside a real sandbox.",
                file=sys.stderr,
            )
            return [
                claude_bin,
                "-p",
                phrasing,
                "--dangerously-skip-permissions",
            ]
        # Sorted for deterministic args across runs; aids reproducibility
        # of the trajectory harness output.
        allowlist_csv = ",".join(sorted(self._allowed_tools))
        return [
            claude_bin,
            "-p",
            phrasing,
            "--allowedTools",
            allowlist_csv,
        ]


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
