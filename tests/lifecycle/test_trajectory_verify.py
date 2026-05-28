"""Per-trajectory verify CLI (Phase 1 task 5).

`make verify-trajectory SKILL=<name> SCENARIO=<name>` runs ONE trajectory
against Claude Code (or a fixture trace file) and reports pass/fail
locally before commit. Lighter than the full harness; the inner-loop
authoring tool.

The fixture path lets tests + CI exercise the verify path without
spawning a real LLM session.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _seed(tmp_path: Path) -> None:
    skill_dir = tmp_path / "base" / "skills" / "engineering" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\nversion: 0.1.0\n"
        "owner: t\nlast_reviewed: 2026-05-28\n---\n\n# demo\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / "demo"
    traj_dir.mkdir(parents=True)
    (traj_dir / "happy-path.yaml").write_text(
        "---\n"
        "name: demo/happy-path\n"
        "description: test\n"
        "skill: demo\n"
        "scenario: happy-path\n"
        "version: 0.1.0\n"
        "owner: t\n"
        "last_reviewed: 2026-05-28\n"
        "adapter_scope: [claude-code]\n"
        "model_pinned: claude-opus-4-7\n"
        "---\n\n"
        "input:\n"
        "  phrasings:\n"
        '    - "one"\n'
        '    - "two"\n'
        '    - "three"\n'
        '    - "four"\n'
        '    - "five"\n'
        "\n"
        "assertions:\n"
        "  - first_skill_loaded: demo\n"
        "  - must_invoke_tool: Write\n"
        "\n"
        "llm_judge:\n"
        "  threshold: 0.7\n"
        '  rubric: "x"\n'
        "  model: claude-sonnet-4-6\n",
        encoding="utf-8",
    )


def _write_passing_fixture(tmp_path: Path) -> Path:
    """A trace JSONL that satisfies the demo trajectory's DSL."""
    spans = [
        {
            "name": "skill_load",
            "startTimeUnixNano": "1000",
            "endTimeUnixNano": "1500",
            "attributes": [
                {"key": "gen_ai.operation.name", "value": {"stringValue": "skill_load"}},
                {"key": "skill.name", "value": {"stringValue": "demo"}},
            ],
        },
        {
            "name": "Write",
            "startTimeUnixNano": "2000",
            "endTimeUnixNano": "3000",
            "attributes": [
                {"key": "gen_ai.operation.name", "value": {"stringValue": "tool_call"}},
                {"key": "tool.name", "value": {"stringValue": "Write"}},
                {"key": "tool.arguments", "value": {"stringValue": '{"path": "out.md", "content": "x"}'}},
            ],
        },
    ]
    p = tmp_path / "trace.jsonl"
    p.write_text("\n".join(json.dumps(s) for s in spans), encoding="utf-8")
    return p


def test_verify_passes_against_passing_fixture(tmp_path: Path) -> None:
    import trajectory_verify

    _seed(tmp_path)
    fixture = _write_passing_fixture(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = trajectory_verify.main(
            skill="demo",
            scenario="happy-path",
            fixture=fixture,
            repo_root=tmp_path,
        )
    assert rc == 0, buf.getvalue()
    assert "PASS" in buf.getvalue() or "pass" in buf.getvalue().lower()


def test_verify_fails_when_trajectory_does_not_exist(tmp_path: Path) -> None:
    import trajectory_verify

    _seed(tmp_path)
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = trajectory_verify.main(
            skill="demo",
            scenario="no-such-scenario",
            fixture=None,
            repo_root=tmp_path,
        )
    assert rc == 1
    # Errors go to stderr per scripts/AGENTS.md output-routing rule.
    assert "not found" in err.getvalue().lower()


def test_verify_fails_against_failing_fixture(tmp_path: Path) -> None:
    """Fixture trace missing the Write call should produce a failing run."""
    import trajectory_verify

    _seed(tmp_path)
    spans = [{
        "name": "skill_load",
        "startTimeUnixNano": "1000",
        "endTimeUnixNano": "1500",
        "attributes": [
            {"key": "gen_ai.operation.name", "value": {"stringValue": "skill_load"}},
            {"key": "skill.name", "value": {"stringValue": "demo"}},
        ],
    }]
    failing = tmp_path / "bad.jsonl"
    failing.write_text(json.dumps(spans[0]), encoding="utf-8")

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = trajectory_verify.main(
            skill="demo",
            scenario="happy-path",
            fixture=failing,
            repo_root=tmp_path,
        )
    assert rc == 1
    # Failures route to stderr per output-routing rule; the matcher
    # failure list ("Write was never called") also surfaces on stderr.
    assert "FAIL" in err.getvalue() or "fail" in err.getvalue().lower()
    assert "Write" in err.getvalue()
