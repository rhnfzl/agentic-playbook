"""Trajectory recorder (Phase 2C-γ).

The recorder runs Claude Code against a captured prompt, saves the
resulting trace as a JSONL fixture, and drafts a trajectory YAML the
author edits. This file tests:

  * `draft_trajectory_yaml`: pure conversion from TraceRecord to YAML.
  * `save_fixture`: orchestrator that writes the JSONL.
  * `main`: end-to-end CLI flow with mocked provider.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trace(
    tool_calls: list[tuple[str, dict]] | None = None,
    skill: str = "demo-skill",
):
    """Build a TraceRecord with the given tool calls + a skill_load."""
    from adapters.trace_record import TraceEvent, TraceRecord

    events = [
        TraceEvent(
            seq=0, kind="skill_load", name=skill,
            arguments=None, duration_ms=None, raw_attrs={},
        ),
    ]
    for i, (tool, args) in enumerate(tool_calls or [], start=1):
        events.append(TraceEvent(
            seq=i, kind="tool_call", name=tool,
            arguments=args, duration_ms=5, raw_attrs={},
        ))
    return TraceRecord(
        adapter="claude-code",
        model="claude-opus-4-7",
        session_id="record-session",
        prompt="Help me write a PRD",
        events=events,
        artifacts={"spec.md": "sha256:abc"} if tool_calls else {},
        total_input_tokens=100,
        total_output_tokens=200,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )


# --- draft_trajectory_yaml ---


def test_draft_yaml_has_required_frontmatter() -> None:
    """The draft YAML must include all required frontmatter fields so
    the trajectory linter accepts it once TODOs are replaced."""
    from trajectory_record import draft_trajectory_yaml

    trace = _make_trace([("Write", {"path": "spec.md"})])
    yaml_text = draft_trajectory_yaml(
        skill="to-prd",
        scenario="happy-path",
        user_prompt="Help me write a PRD",
        trace=trace,
    )
    for field in (
        "name: to-prd/happy-path",
        "skill: to-prd",
        "scenario: happy-path",
        "model_pinned: claude-opus-4-7",
        "adapter_scope:",
    ):
        assert field in yaml_text, f"missing {field!r}"


def test_draft_yaml_first_phrasing_is_user_prompt(tmp_path: Path) -> None:
    """The user's actual prompt becomes phrasing 1; TODOs are the
    other 4 that the author paraphrases by hand."""
    from trajectory_record import draft_trajectory_yaml

    trace = _make_trace([("Write", {"path": "spec.md"})])
    yaml_text = draft_trajectory_yaml(
        skill="to-prd",
        scenario="happy-path",
        user_prompt="Help me write a PRD",
        trace=trace,
    )
    assert '"Help me write a PRD"' in yaml_text
    # 4 TODO phrasings as paraphrasing placeholders.
    assert yaml_text.count("TODO paraphrase ") >= 4


def test_draft_yaml_infers_must_invoke_tool_for_each_tool_call() -> None:
    """Recorder seeds DSL assertions from the trace so the author has
    a starting list rather than a blank assertions block."""
    from trajectory_record import draft_trajectory_yaml

    trace = _make_trace([
        ("Write", {"path": "spec.md"}),
        ("Read", {"file_path": "old.md"}),
    ])
    yaml_text = draft_trajectory_yaml(
        skill="to-prd",
        scenario="happy-path",
        user_prompt="x",
        trace=trace,
    )
    assert "must_invoke_tool: Write" in yaml_text
    assert "must_invoke_tool: Read" in yaml_text


def test_draft_yaml_seeds_first_skill_loaded_when_skill_present() -> None:
    """A trace with a skill_load event seeds the first_skill_loaded
    DSL primitive."""
    from trajectory_record import draft_trajectory_yaml

    trace = _make_trace(
        [("Write", {"path": "spec.md"})], skill="to-prd",
    )
    yaml_text = draft_trajectory_yaml(
        skill="to-prd",
        scenario="happy-path",
        user_prompt="x",
        trace=trace,
    )
    assert "first_skill_loaded: to-prd" in yaml_text


def test_draft_yaml_includes_judge_rubric_todo() -> None:
    """The llm_judge block is scaffolded with a TODO rubric so the
    author can't accidentally ship a placeholder (the lint gate fails
    on TODO bodies, so this enforces the workflow)."""
    from trajectory_record import draft_trajectory_yaml

    trace = _make_trace([("Write", {"path": "spec.md"})])
    yaml_text = draft_trajectory_yaml(
        skill="to-prd",
        scenario="happy-path",
        user_prompt="x",
        trace=trace,
    )
    assert "llm_judge:" in yaml_text
    assert "TODO" in yaml_text
    assert "rubric:" in yaml_text
    assert "threshold:" in yaml_text


# --- save_fixture ---


def test_save_fixture_writes_jsonl_at_canonical_path(tmp_path: Path) -> None:
    """The fixture is written at base/trajectories/<skill>/fixtures/
    <scenario>-pass.jsonl so trajectory_calibrate.main() can find it."""
    from trajectory_record import save_fixture

    trace = _make_trace([("Write", {"path": "spec.md", "content": "Hello"})])
    path = save_fixture(
        repo_root=tmp_path,
        skill="to-prd",
        scenario="happy-path",
        trace=trace,
    )
    expected = (
        tmp_path / "base" / "trajectories" / "to-prd" / "fixtures"
        / "happy-path-pass.jsonl"
    )
    assert path == expected
    assert path.is_file()


def test_save_fixture_round_trips_through_parse_otel_jsonl(tmp_path: Path) -> None:
    """The JSONL the recorder writes must be parseable by the Phase 1
    `parse_otel_jsonl` shim; otherwise calibrate / verify-trajectory
    would never read it back."""
    from adapters.claude_code_trace import parse_otel_jsonl
    from trajectory_record import save_fixture

    trace = _make_trace([
        ("Write", {"path": "spec.md", "content": "Hello"}),
        ("Read", {"file_path": "old.md"}),
    ])
    path = save_fixture(
        repo_root=tmp_path,
        skill="to-prd",
        scenario="happy-path",
        trace=trace,
    )
    parsed = parse_otel_jsonl(path, session_id="x", prompt="x")
    assert len(parsed.tool_calls()) == 2
    assert {e.name for e in parsed.tool_calls()} == {"Write", "Read"}


# --- main (orchestrator) ---


def test_main_records_fixture_and_writes_draft(tmp_path: Path) -> None:
    """End-to-end: main() spawns the provider, saves the fixture,
    writes the draft YAML, prints next-steps."""
    import io
    from contextlib import redirect_stdout

    skill_dir = tmp_path / "base" / "skills" / "engineering" / "to-prd"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: to-prd\ndescription: x\nversion: 0.1.0\n"
        "owner: t\nlast_reviewed: 2026-05-28\n---\n\n# x\n",
        encoding="utf-8",
    )

    import trajectory_record

    def fake_provider(trajectory_stub, phrasing: str, adapter: str):
        return _make_trace(
            [("Write", {"path": "spec.md", "content": "Hello"})],
            skill="to-prd",
        )

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = trajectory_record.main(
            skill="to-prd",
            scenario="happy-path",
            user_prompt="Help me write a PRD",
            repo_root=tmp_path,
            provider=fake_provider,
        )
    assert rc == 0
    fixture = (
        tmp_path / "base" / "trajectories" / "to-prd" / "fixtures"
        / "happy-path-pass.jsonl"
    )
    draft = (
        tmp_path / "base" / "trajectories" / "to-prd" / "happy-path.yaml.draft"
    )
    assert fixture.is_file()
    assert draft.is_file()
    out = buf.getvalue()
    assert "happy-path.yaml.draft" in out
    assert "make verify-trajectory" in out


def test_main_refuses_to_overwrite_existing_trajectory(tmp_path: Path) -> None:
    """If the trajectory YAML already exists, the recorder writes a
    .draft sibling rather than clobbering. Two consecutive runs both
    succeed; the second's draft is at <scenario>.yaml.draft (not
    .yaml)."""
    import io
    from contextlib import redirect_stderr, redirect_stdout

    skill_dir = tmp_path / "base" / "skills" / "engineering" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: x\nversion: 0.1.0\n"
        "owner: t\nlast_reviewed: 2026-05-28\n---\n\n# x\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / "demo"
    traj_dir.mkdir(parents=True)
    (traj_dir / "happy-path.yaml").write_text(
        "already exists", encoding="utf-8",
    )

    import trajectory_record

    def fake_provider(trajectory_stub, phrasing: str, adapter: str):
        return _make_trace([("Write", {"path": "out.md"})], skill="demo")

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = trajectory_record.main(
            skill="demo",
            scenario="happy-path",
            user_prompt="x",
            repo_root=tmp_path,
            provider=fake_provider,
        )
    assert rc == 0
    # Existing file untouched.
    assert (
        traj_dir / "happy-path.yaml"
    ).read_text(encoding="utf-8") == "already exists"
    # Draft sibling written.
    assert (traj_dir / "happy-path.yaml.draft").is_file()
