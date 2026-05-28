"""Trajectory NamedTuple shape + PlaybookContent integration.

Phase 0 / Task 1 of the cross-adapter trajectory harness. The Trajectory type
is the typed surface every downstream consumer reads (reader, frontmatter
linter, decay check, harness). Locking its shape early lets the rest of
Phase 0 reference exact field names.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_trajectory_namedtuple_has_required_fields() -> None:
    from adapters._protocol import Trajectory

    fields = Trajectory._fields
    assert "path" in fields
    assert "skill" in fields
    assert "scenario" in fields
    assert "frontmatter" in fields
    assert "body" in fields
    assert "input_phrasings" in fields
    assert "assertions" in fields
    assert "llm_judge" in fields
    assert "adapter_scope" in fields
    assert "model_pinned" in fields


def test_trajectory_can_be_constructed() -> None:
    from adapters._protocol import Trajectory

    traj = Trajectory(
        path=Path("/tmp/example.yaml"),
        skill="to-prd",
        scenario="happy-path",
        frontmatter={"name": "to-prd/happy-path", "skill": "to-prd"},
        body="",
        input_phrasings=["help me", "write a prd"],
        assertions=[{"first_skill_loaded": "to-prd"}],
        llm_judge={"threshold": 0.7, "rubric": "score it"},
        adapter_scope=["claude-code", "codex"],
        model_pinned="claude-opus-4-7",
    )
    assert traj.skill == "to-prd"
    assert traj.scenario == "happy-path"
    assert len(traj.input_phrasings) == 2
    assert traj.adapter_scope == ["claude-code", "codex"]


def test_playbook_content_carries_trajectories_field() -> None:
    from adapters._protocol import PlaybookContent

    fields = PlaybookContent._fields
    assert "trajectories" in fields, (
        "PlaybookContent must expose trajectories so adapters, "
        "checks, and the harness all see the same loaded set."
    )


def test_trajectory_reexported_from_loader_shim() -> None:
    """ADR-0031: _loader.py re-exports every public protocol name."""
    from adapters._loader import Trajectory as LoaderTrajectory
    from adapters._protocol import Trajectory as ProtocolTrajectory

    assert LoaderTrajectory is ProtocolTrajectory
