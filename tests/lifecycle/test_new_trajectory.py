"""scripts/new_trajectory.py scaffold writes a valid trajectory YAML.

Phase 0 / Task 5. Authors invoke `make new TRAJECTORY=<skill>:<scenario>`,
which routes to new_trajectory.py and produces a starter YAML the linter
accepts.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _seed_skill(repo_root: Path, skill: str, category: str = "engineering") -> None:
    skill_dir = repo_root / "base" / "skills" / category / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: " + skill + "\ndescription: stub\nversion: 0.1.0\n"
        "owner: test\nlast_reviewed: 2026-05-28\n---\n\n# " + skill + "\n",
        encoding="utf-8",
    )


def _invoke(repo_root: Path, skill: str, scenario: str) -> tuple[int, str]:
    import new_trajectory

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = new_trajectory.main(
            skill=skill,
            scenario=scenario,
            owner="test",
            repo_root=repo_root,
        )
    return rc, buf.getvalue()


def test_scaffold_creates_yaml_at_canonical_path(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "demo-skill")
    rc, _ = _invoke(tmp_path, "demo-skill", "happy-path")
    assert rc == 0
    target = tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml"
    assert target.is_file()


def test_scaffold_fails_when_skill_does_not_exist(tmp_path: Path) -> None:
    (tmp_path / "base").mkdir()
    rc, out = _invoke(tmp_path, "no-such-skill", "happy-path")
    assert rc == 1
    assert "no-such-skill" in out
    assert "not found" in out.lower() or "does not" in out.lower()


def test_scaffold_refuses_to_overwrite_existing(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "demo-skill")
    rc1, _ = _invoke(tmp_path, "demo-skill", "happy-path")
    assert rc1 == 0
    rc2, out = _invoke(tmp_path, "demo-skill", "happy-path")
    assert rc2 == 1
    assert "exists" in out.lower()


def test_scaffolded_yaml_fails_lint_until_TODOs_are_replaced(tmp_path: Path) -> None:
    """End-to-end: scaffold a trajectory, run the lint check.

    The scaffolder intentionally writes `TODO-model-id` and TODO-prefixed
    phrasings. The linter must REJECT this until the author fills them
    in. This is the contract between scaffolder and linter; if it
    silently passes, authors will commit unfilled placeholders.
    """
    from adapters._loader import PlaybookContent
    from checks import CheckContext
    from checks import trajectory as trajectory_check

    _seed_skill(tmp_path, "demo-skill")
    _invoke(tmp_path, "demo-skill", "happy-path")

    ctx = CheckContext(
        repo_root=tmp_path,
        content=PlaybookContent.load(tmp_path),
    )
    result = trajectory_check.run(ctx)
    assert result.status == "fail", "\n".join(result.details)
    joined = "\n".join(result.details).lower()
    assert "todo" in joined or "model_pinned" in joined


def test_scaffolded_yaml_passes_lint_after_TODOs_replaced(tmp_path: Path) -> None:
    """Same end-to-end, with the TODO markers replaced. Demonstrates the
    expected author workflow: scaffold, fill in, commit."""
    from adapters._loader import PlaybookContent
    from checks import CheckContext
    from checks import trajectory as trajectory_check

    _seed_skill(tmp_path, "demo-skill")
    _invoke(tmp_path, "demo-skill", "happy-path")

    traj_path = (
        tmp_path / "base" / "trajectories" / "demo-skill" / "happy-path.yaml"
    )
    content = traj_path.read_text(encoding="utf-8")
    content = content.replace("TODO-model-id", "claude-opus-4-7")
    content = content.replace(
        "TODO one-line description of what this trajectory verifies.",
        "Verifies the demo-skill happy path.",
    )
    for i, label in enumerate(["first", "second", "third", "fourth", "fifth"]):
        content = content.replace(
            f'    - "TODO {label} phrasing"',
            f'    - "phrasing variant {i + 1}"',
        )
    content = content.replace(
        "    TODO Score the trajectory on:",
        "    Score the trajectory on:",
    )
    traj_path.write_text(content, encoding="utf-8")

    ctx = CheckContext(
        repo_root=tmp_path,
        content=PlaybookContent.load(tmp_path),
    )
    result = trajectory_check.run(ctx)
    assert result.status == "ok", "\n".join(result.details)
