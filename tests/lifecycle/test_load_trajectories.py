"""load_trajectories: reader for base/trajectories/<skill>/<scenario>.yaml.

Phase 0 / Task 2 of the cross-adapter trajectory harness. The reader walks
each content root (per ADR-0040 base/overlay layering), parses YAML
trajectory files with a permissive shape (missing optional fields default
sensibly), and returns Trajectory NamedTuples.

The lint pass (Task 3) enforces stricter rules. The reader only fails on
unparseable YAML or missing top-level frontmatter; everything else is the
linter's job.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_trajectory_yaml(
    skill: str = "demo-skill",
    scenario: str = "happy-path",
    extra_frontmatter: str = "",
    body: str = "",
) -> str:
    return f"""---
name: {skill}/{scenario}
description: One-line description for the trajectory.
skill: {skill}
scenario: {scenario}
version: 0.1.0
owner: test
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
{extra_frontmatter}---

{body}
"""


def test_load_trajectories_returns_empty_when_no_dir(tmp_path: Path) -> None:
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    (tmp_path / "base").mkdir()
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    assert result == []


def test_load_trajectories_walks_skill_subdirs(tmp_path: Path) -> None:
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    (tmp_path / "base" / "trajectories" / "demo-skill").mkdir(parents=True)
    (tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml").write_text(
        _make_trajectory_yaml(),
        encoding="utf-8",
    )
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    assert len(result) == 1
    traj = result[0]
    assert traj.skill == "demo-skill"
    assert traj.scenario == "happy-path"
    assert traj.model_pinned == "claude-opus-4-7"
    assert "claude-code" in traj.adapter_scope


def test_load_trajectories_parses_input_phrasings_from_body(tmp_path: Path) -> None:
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    body = """input:
  phrasings:
    - "Help me write a PRD"
    - "Convert this brainstorm to a doc"
    - "Turn this into a PRD"
    - "Write a product doc"
    - "/to-prd I want a dashboard spec"

assertions:
  - first_skill_loaded: demo-skill
  - must_invoke_tool: Write

llm_judge:
  threshold: 0.7
  rubric: "Score the trajectory."
  model: claude-sonnet-4-6
"""
    (tmp_path / "base" / "trajectories" / "demo-skill").mkdir(parents=True)
    (tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml").write_text(
        _make_trajectory_yaml(body=body),
        encoding="utf-8",
    )
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    assert len(result) == 1
    traj = result[0]
    assert len(traj.input_phrasings) == 5
    assert traj.input_phrasings[0] == "Help me write a PRD"
    assert traj.assertions == [
        {"first_skill_loaded": "demo-skill"},
        {"must_invoke_tool": "Write"},
    ]
    assert traj.llm_judge["threshold"] == 0.7
    assert traj.llm_judge["model"] == "claude-sonnet-4-6"


def test_load_trajectories_handles_multiple_scenarios(tmp_path: Path) -> None:
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    skill_dir = tmp_path / "base" / "trajectories" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "happy-path.yaml").write_text(
        _make_trajectory_yaml(scenario="happy-path"),
        encoding="utf-8",
    )
    (skill_dir / "edge-empty.yaml").write_text(
        _make_trajectory_yaml(scenario="edge-empty"),
        encoding="utf-8",
    )
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    scenarios = sorted(t.scenario for t in result)
    assert scenarios == ["edge-empty", "happy-path"]


def test_load_trajectories_overlay_wins_on_collision(tmp_path: Path) -> None:
    """ADR-0040: later content roots override earlier ones for the same key."""
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    base = tmp_path / "base" / "trajectories" / "demo-skill"
    base.mkdir(parents=True)
    (base / "happy-path.yaml").write_text(
        _make_trajectory_yaml(extra_frontmatter="version: 0.1.0\n"),
        encoding="utf-8",
    )

    overlay = tmp_path / "overlays" / "team" / "trajectories" / "demo-skill"
    overlay.mkdir(parents=True)
    (overlay / "happy-path.yaml").write_text(
        _make_trajectory_yaml(extra_frontmatter="version: 9.9.9\n"),
        encoding="utf-8",
    )

    result = load_trajectories(resolve_content_paths(["team"], tmp_path))
    assert len(result) == 1
    # Overlay frontmatter wins.
    assert result[0].frontmatter.get("version") == "9.9.9"


def test_load_trajectories_skips_files_without_frontmatter(tmp_path: Path) -> None:
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    (tmp_path / "base" / "trajectories" / "demo-skill").mkdir(parents=True)
    (tmp_path / "base" / "trajectories" / "demo-skill" / "broken.yaml").write_text(
        "this is not a valid trajectory at all\n",
        encoding="utf-8",
    )
    # Reader is permissive; broken files are surfaced by the linter, not silently dropped.
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    # Reader still returns a Trajectory with empty frontmatter so the linter
    # can attribute the failure to a specific path.
    assert len(result) == 1
    assert result[0].frontmatter == {}


def test_load_trajectories_parses_call_order_assertion(tmp_path: Path) -> None:
    """Codex review finding: `call_order: [{tool: X, before: Y}]` must load
    correctly from YAML, not get shredded by comma-splitting inside the dict."""
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories

    body = """input:
  phrasings:
    - "x"

assertions:
  - first_skill_loaded: demo-skill
  - call_order: [{tool: AskUserQuestion, before: Write}, {tool: Read, before: Write}]

llm_judge:
  threshold: 0.7
  rubric: "x"
  model: claude-sonnet-4-6
"""
    (tmp_path / "base" / "trajectories" / "demo-skill").mkdir(parents=True)
    (tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml").write_text(
        _make_trajectory_yaml(body=body),
        encoding="utf-8",
    )
    result = load_trajectories(resolve_content_paths(None, tmp_path))
    assert len(result) == 1
    traj = result[0]
    # Find the call_order assertion (must be a list of dicts, not garbled strings).
    call_order_assertions = [a for a in traj.assertions if "call_order" in a]
    assert len(call_order_assertions) == 1
    value = call_order_assertions[0]["call_order"]
    assert isinstance(value, list)
    assert len(value) == 2
    assert value[0] == {"tool": "AskUserQuestion", "before": "Write"}
    assert value[1] == {"tool": "Read", "before": "Write"}


def test_loaded_call_order_passes_matcher_end_to_end(tmp_path: Path) -> None:
    """The full pipeline: YAML -> reader -> matcher. Verifies the codex
    finding that call_order was DOA from YAML is fixed."""
    from adapters._protocol import resolve_content_paths
    from adapters._reader import load_trajectories
    from adapters.trace_record import TraceEvent, TraceRecord
    from datetime import datetime, timezone
    from trajectory_matcher import evaluate_assertions

    body = """input:
  phrasings:
    - "x"

assertions:
  - call_order: [{tool: AskUserQuestion, before: Write}]

llm_judge:
  threshold: 0.7
  rubric: "x"
  model: claude-sonnet-4-6
"""
    (tmp_path / "base" / "trajectories" / "demo-skill").mkdir(parents=True)
    (tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml").write_text(
        _make_trajectory_yaml(body=body),
        encoding="utf-8",
    )
    traj = load_trajectories(resolve_content_paths(None, tmp_path))[0]

    trace = TraceRecord(
        adapter="claude-code",
        model="x",
        session_id="s",
        prompt="x",
        events=[
            TraceEvent(seq=0, kind="tool_call", name="AskUserQuestion",
                       arguments=None, duration_ms=None, raw_attrs={}),
            TraceEvent(seq=1, kind="tool_call", name="Write",
                       arguments={"path": "out.md"}, duration_ms=None, raw_attrs={}),
        ],
        artifacts={"out.md": "sha256:x"},
        total_input_tokens=0,
        total_output_tokens=0,
        started_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
    )
    result = evaluate_assertions(traj.assertions, trace)
    assert result.passed, "\n".join(result.failures)
