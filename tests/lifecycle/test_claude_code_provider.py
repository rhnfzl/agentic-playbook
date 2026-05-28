"""ClaudeCodeProvider: live Claude Code trace_provider (Phase 2B Task 1).

Tests mock subprocess.run so no live `claude` CLI is invoked. The
provider's contract is the same as Phase 1's TraceProvider:

  provider(trajectory, phrasing, adapter) -> TraceRecord

A separate test file (test_claude_code_provider_live.py) covers the
real-spawn path gated on PHASE2_LIVE env var.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _trajectory():
    from adapters._protocol import Trajectory

    return Trajectory(
        path=Path("/tmp/x.yaml"),
        skill="trajectory-canary",
        scenario="canary",
        frontmatter={},
        body="",
        input_phrasings=["x"],
        assertions=[],
        llm_judge={},
        adapter_scope=["claude-code"],
        model_pinned="claude-opus-4-7",
    )


def _fake_completed(returncode: int = 0, stderr: str = "", stdout: str = ""):
    """Build a mock subprocess.CompletedProcess."""
    import subprocess

    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr,
    )


def _otel_span_line(operation: str, name: str, **kwargs) -> str:
    """One Claude Code OTel JSON span (the console exporter shape)."""
    span = {
        "name": name,
        "startTimeUnixNano": str(kwargs.get("start", 1000)),
        "endTimeUnixNano": str(kwargs.get("end", 2000)),
        "attributes": [
            {"key": "gen_ai.operation.name", "value": {"stringValue": operation}},
            *[
                {"key": k, "value": {"stringValue": str(v)}}
                for k, v in kwargs.items() if k not in ("start", "end")
            ],
        ],
    }
    return json.dumps(span)


def test_provider_raises_when_claude_not_on_path(tmp_path: Path) -> None:
    """`claude` missing from PATH must surface a clear error the harness
    catches as infra_fail. Don't pretend to run."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    with patch("shutil.which", return_value=None):
        provider = ClaudeCodeProvider()
        import pytest as _pytest
        with _pytest.raises(RuntimeError, match="claude.*PATH"):
            provider(_trajectory(), "hello", "claude-code")


def test_provider_rejects_non_claude_code_adapter(tmp_path: Path) -> None:
    """Phase 2B only ships the Claude Code shim. Other adapters land in
    Phase 3+. Reject explicitly rather than silently fail."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        provider = ClaudeCodeProvider()
        import pytest as _pytest
        with _pytest.raises(ValueError, match="codex"):
            provider(_trajectory(), "hello", "codex")


def test_provider_spawns_claude_with_phrasing_as_prompt(tmp_path: Path) -> None:
    """The trajectory's phrasing is passed to `claude` as the prompt
    (via -p/--print headless mode)."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        captured["env"] = kwargs.get("env", {})
        captured["cwd"] = kwargs.get("cwd")
        return _fake_completed(
            stderr=_otel_span_line(
                "skill_load", "trajectory-canary",
                **{"skill.name": "trajectory-canary"},
            ),
        )

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "run the canary", "claude-code")

    assert "claude" in captured["args"][0]
    # Phrasing must appear in the args (exact flag may vary per Claude Code
    # version; we accept either -p or stdin shape).
    joined = " ".join(captured["args"])
    assert "run the canary" in joined or any(
        "run the canary" == a for a in captured["args"]
    )
    assert record.adapter == "claude-code"
    assert record.prompt == "run the canary"


def test_provider_sets_otel_env_vars(tmp_path: Path) -> None:
    """Console exporter is the simplest capture path: spans go to stderr,
    we parse them. The env vars Claude Code looks at must be set."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["env"] = kwargs.get("env", {}) or {}
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    env = captured["env"]
    assert env.get("OTEL_TRACES_EXPORTER") == "console"
    # Claude Code's docs name this env var as the toggle:
    assert env.get("CLAUDE_CODE_ENABLE_TELEMETRY") == "1"


def test_provider_parses_otel_spans_from_stderr(tmp_path: Path) -> None:
    """OTel spans in stderr feed parse_otel_jsonl. The provider's job is
    to extract them; this test confirms the round-trip."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    spans_stderr = (
        _otel_span_line(
            "skill_load", "trajectory-canary",
            **{"skill.name": "trajectory-canary"},
        ) + "\n" +
        _otel_span_line(
            "tool_call", "Write",
            **{
                "tool.name": "Write",
                "tool.arguments": '{"path": "out.md", "content": "x"}',
            },
        )
    )

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch(
             "subprocess.run",
             return_value=_fake_completed(stderr=spans_stderr),
         ):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "x", "claude-code")

    assert len(record.skill_loads()) == 1
    assert record.skill_loads()[0].name == "trajectory-canary"
    assert len(record.tool_calls()) == 1
    assert record.tool_calls()[0].name == "Write"


def test_provider_filters_non_json_lines_from_stderr(tmp_path: Path) -> None:
    """Real Claude Code stderr interleaves OTel spans with startup noise
    (`Loading skills...`, etc.). Provider must skip non-JSON lines, not
    crash."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    mixed = (
        "Loading skills from ~/.claude/skills/\n"
        + _otel_span_line(
            "tool_call", "Write",
            **{"tool.name": "Write"},
        ) + "\n"
        + "Session ended (cost: $0.01)\n"
    )

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch(
             "subprocess.run",
             return_value=_fake_completed(stderr=mixed),
         ):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "x", "claude-code")
    assert len(record.tool_calls()) == 1


def test_provider_surfaces_timeout(tmp_path: Path) -> None:
    """A subprocess.TimeoutExpired must surface as a clear error so the
    harness records `infra_fail: timeout`."""
    import subprocess

    from adapters.claude_code_provider import ClaudeCodeProvider

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=10)

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider(timeout=10)
        import pytest as _pytest
        with _pytest.raises(TimeoutError, match="10"):
            provider(_trajectory(), "x", "claude-code")


def test_provider_runs_in_isolated_cwd(tmp_path: Path) -> None:
    """The agent might write files; isolate so it doesn't touch the
    playbook checkout. The CWD passed to subprocess.run must be a temp
    dir, not the playbook root."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured_cwds: list = []

    def fake_run(args, **kwargs):
        captured_cwds.append(kwargs.get("cwd"))
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    assert captured_cwds[0] is not None
    # CWD must be the provider's per-spawn temp dir, NOT the playbook
    # checkout. The provider cleans up after the run; we check the path
    # is a temp-style location (tempfile prefix or /tmp or /var/folders).
    cwd_str = str(captured_cwds[0]).lower()
    assert any(
        marker in cwd_str
        for marker in ("trajectory-canary-", "/tmp/", "/var/folders/", "appdata")
    ), f"CWD does not look like a tempdir: {cwd_str}"


def test_provider_default_uses_allowed_tools_allowlist(tmp_path: Path) -> None:
    """Security-review HIGH finding (2026-05-28): default headless mode
    must use a tool allowlist, NOT --dangerously-skip-permissions. The
    allowlist excludes Bash, WebFetch, WebSearch, SendMessage, Task by
    default — a malicious trajectory phrasing should not be able to
    instruct the agent to run arbitrary shell commands."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    assert "--dangerously-skip-permissions" not in captured["args"]
    assert "--allowedTools" in captured["args"]
    allowlist_idx = captured["args"].index("--allowedTools") + 1
    allowlist = captured["args"][allowlist_idx]
    # Default tools that MUST be present:
    for tool in ("Read", "Write", "Edit", "NotebookEdit", "Glob", "Grep"):
        assert tool in allowlist, f"expected {tool!r} in default allowlist"
    # Dangerous tools that MUST NOT be present:
    for tool in ("Bash", "WebFetch", "WebSearch", "Task"):
        assert tool not in allowlist, f"{tool!r} must NOT be in default allowlist"


def test_provider_extra_allowed_tools_extends_default(tmp_path: Path) -> None:
    """Trajectories that legitimately need Bash etc. opt in via the
    provider's extra_allowed_tools constructor arg. The default tools
    remain present; the extra ones are added."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider(
            extra_allowed_tools=frozenset({"Bash"}),
        )
        provider(_trajectory(), "x", "claude-code")

    allowlist_idx = captured["args"].index("--allowedTools") + 1
    allowlist = captured["args"][allowlist_idx]
    assert "Bash" in allowlist
    assert "Read" in allowlist  # default still in


def test_provider_dangerous_arg_switches_to_skip_permissions(tmp_path: Path) -> None:
    """Explicit dangerous_skip_perms=True opts back into the legacy
    behavior. Use only inside a real sandbox (rootless container, gVisor)."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider(dangerous_skip_perms=True)
        provider(_trajectory(), "x", "claude-code")

    assert "--dangerously-skip-permissions" in captured["args"]
    assert "--allowedTools" not in captured["args"]


def test_provider_dangerous_env_var_switches_to_skip_permissions(
    tmp_path: Path, monkeypatch,
) -> None:
    """`PHASE2_LIVE_DANGEROUS=1` opts in via env (for CI runners)."""
    monkeypatch.setenv("PHASE2_LIVE_DANGEROUS", "1")
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    assert "--dangerously-skip-permissions" in captured["args"]


def test_provider_dangerous_mode_warns_on_stderr(tmp_path: Path, capsys) -> None:
    """When dangerous mode is active, every spawn must emit a warning
    on stderr so a CI operator sees the escalation in their logs."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", return_value=_fake_completed()):
        provider = ClaudeCodeProvider(dangerous_skip_perms=True)
        provider(_trajectory(), "x", "claude-code")

    captured = capsys.readouterr()
    assert "dangerously-skip-permissions" in captured.err.lower()
    assert "PHASE2_LIVE_DANGEROUS" in captured.err


def test_provider_env_is_minimal_allowlist(tmp_path: Path, monkeypatch) -> None:
    """Adversarial review-round-6 #1: a full os.environ passthrough leaked
    AWS_*, GITHUB_TOKEN, etc., into the spawned claude session. The
    provider now uses an allowlist; verify AWS_ACCESS_KEY_ID is NOT
    forwarded while ANTHROPIC_API_KEY IS."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "secret-should-not-leak")
    monkeypatch.setenv("GITHUB_TOKEN", "secret-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-leak-ok")

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    env = captured["env"]
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "GITHUB_TOKEN" not in env
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test-leak-ok"


def test_provider_raises_on_nonzero_exit_code(tmp_path: Path) -> None:
    """Adversarial review-round-6 #5: a crashed agent must surface as
    infra_fail, NOT as a quality regression. Non-zero exit code raises
    RuntimeError so the harness records the crash distinctly."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch(
             "subprocess.run",
             return_value=_fake_completed(
                 returncode=2,
                 stderr="Error: authentication failed",
             ),
         ):
        provider = ClaudeCodeProvider()
        import pytest as _pytest
        with _pytest.raises(RuntimeError, match="code 2"):
            provider(_trajectory(), "x", "claude-code")


def test_provider_parses_spans_from_stdout_too(tmp_path: Path) -> None:
    """Adversarial review-round-6 #3 (verdict-blocker): Node's
    ConsoleSpanExporter writes to stdout by default, not stderr. The
    provider now parses both channels. Spans on stdout must produce
    events the same as spans on stderr."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    span_on_stdout = _otel_span_line(
        "tool_call", "Write",
        **{"tool.name": "Write"},
    )

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch(
             "subprocess.run",
             return_value=_fake_completed(stdout=span_on_stdout, stderr=""),
         ):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "x", "claude-code")

    assert len(record.tool_calls()) == 1
    assert record.tool_calls()[0].name == "Write"


def test_provider_excludes_hidden_dirs_from_artifacts(tmp_path: Path) -> None:
    """Adversarial review-round-6 #7: Claude Code creates `.claude/`
    session state in the workdir. Without exclusion, those files
    pollute TraceRecord.artifacts and `final_artifact_path` matches
    the wrong file. Hidden parts (`.claude`, `.git`, `.cache`) are
    excluded; visible files are kept."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    def fake_run(args, **kwargs):
        cwd = Path(kwargs["cwd"])
        # Visible agent output:
        (cwd / "report.md").write_text("real output", encoding="utf-8")
        # Hidden harness state:
        (cwd / ".claude").mkdir()
        (cwd / ".claude" / "session.json").write_text(
            '{"...": "..."}', encoding="utf-8",
        )
        (cwd / ".cache").mkdir()
        (cwd / ".cache" / "x.bin").write_text("blob", encoding="utf-8")
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "x", "claude-code")

    assert "report.md" in record.artifacts
    assert not any(k.startswith(".") for k in record.artifacts)


def test_provider_temp_dir_prefix_names_the_trajectory(tmp_path: Path) -> None:
    """Adversarial review-round-6 #8: a tempdir prefix of
    `trajectory-canary-` regardless of trajectory was misleading.
    Per-trajectory prefix now identifies the source."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        provider(_trajectory(), "x", "claude-code")

    assert "traj-trajectory-canary-canary-" in captured["cwd"]


def test_provider_captures_workdir_artifacts(tmp_path: Path) -> None:
    """Files written by the agent in its CWD become record.artifacts so
    `final_artifact_path` works for skills that write rather than Edit."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    def fake_run(args, **kwargs):
        # Simulate the agent writing a file in its cwd before returning.
        cwd = Path(kwargs["cwd"])
        (cwd / "agent-output.md").write_text("canary chirped\n", encoding="utf-8")
        return _fake_completed()

    with patch("shutil.which", return_value="/usr/local/bin/claude"), \
         patch("subprocess.run", side_effect=fake_run):
        provider = ClaudeCodeProvider()
        record = provider(_trajectory(), "x", "claude-code")

    assert "agent-output.md" in record.artifacts
    assert record.artifacts["agent-output.md"].startswith("sha256:")
