"""Trajectory linter (scripts/checks/trajectory.py) gate behavior.

Phase 0 / Task 3 of the cross-adapter trajectory harness. The linter
enforces ADR-0044 + ADR-0046 frontmatter and shape rules. The reader
(test_load_trajectories.py) is permissive; this gate is strict.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


VALID_FRONTMATTER = """---
name: demo-skill/happy-path
description: Demo trajectory used for tests.
skill: demo-skill
scenario: happy-path
version: 0.1.0
owner: test
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:
  phrasings:
    - "first phrasing"
    - "second phrasing"
    - "third phrasing"
    - "fourth phrasing"
    - "fifth phrasing"

assertions:
  - first_skill_loaded: demo-skill

llm_judge:
  threshold: 0.7
  rubric: "Score it."
  model: claude-sonnet-4-6
"""


ONE_PHRASING_FRONTMATTER = """---
name: demo-skill/happy-path
description: Demo trajectory used for tests.
skill: demo-skill
scenario: happy-path
version: 0.1.0
owner: test
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:
  phrasings:
    - "only one phrasing"

assertions:
  - first_skill_loaded: demo-skill

llm_judge:
  threshold: 0.7
  rubric: "Score it."
  model: claude-sonnet-4-6
"""


def _setup_repo(
    tmp_path: Path,
    *,
    trajectory_yaml: str = VALID_FRONTMATTER,
    skill_dir_present: bool = True,
    trajectory_skill: str = "demo-skill",
    trajectory_scenario: str = "happy-path",
) -> Path:
    """Build a tmp repo with one optional skill + one trajectory file."""
    if skill_dir_present:
        skill_dir = tmp_path / "base" / "skills" / "engineering" / trajectory_skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: demo\nversion: 0.1.0\n"
            "owner: test\nlast_reviewed: 2026-05-28\n---\n\n# Demo Skill\n",
            encoding="utf-8",
        )
    traj_dir = tmp_path / "base" / "trajectories" / trajectory_skill
    traj_dir.mkdir(parents=True)
    (traj_dir / f"{trajectory_scenario}.yaml").write_text(
        trajectory_yaml, encoding="utf-8"
    )
    return tmp_path


def _run_check(repo_root: Path):
    from adapters._loader import PlaybookContent
    from checks import CheckContext
    from checks import trajectory as trajectory_check

    ctx = CheckContext(
        repo_root=repo_root,
        content=PlaybookContent.load(repo_root),
    )
    return trajectory_check.run(ctx)


def test_lint_passes_for_valid_trajectory(tmp_path: Path) -> None:
    repo = _setup_repo(tmp_path)
    result = _run_check(repo)
    assert result.status == "ok", "\n".join(result.details)


def test_lint_fails_when_skill_directory_missing(tmp_path: Path) -> None:
    repo = _setup_repo(tmp_path, skill_dir_present=False)
    result = _run_check(repo)
    assert result.status == "fail"
    joined = "\n".join(result.details)
    assert "demo-skill" in joined
    assert "does not resolve" in joined or "missing" in joined.lower()


def test_lint_fails_when_scenario_does_not_match_filename(tmp_path: Path) -> None:
    yaml_with_wrong_scenario = VALID_FRONTMATTER.replace(
        "scenario: happy-path", "scenario: edge-case"
    )
    repo = _setup_repo(
        tmp_path,
        trajectory_yaml=yaml_with_wrong_scenario,
    )
    result = _run_check(repo)
    assert result.status == "fail"
    assert "scenario" in "\n".join(result.details).lower()


def test_lint_fails_when_adapter_scope_contains_unknown_adapter(
    tmp_path: Path,
) -> None:
    yaml_bad_adapter = VALID_FRONTMATTER.replace(
        "adapter_scope: [claude-code]",
        "adapter_scope: [claude-code, banana-cli]",
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml_bad_adapter)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "banana-cli" in "\n".join(result.details)


def test_lint_fails_when_required_field_missing(tmp_path: Path) -> None:
    yaml_missing_model = VALID_FRONTMATTER.replace(
        "model_pinned: claude-opus-4-7\n", ""
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml_missing_model)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "model_pinned" in "\n".join(result.details)


def test_lint_fails_when_judge_threshold_out_of_range(tmp_path: Path) -> None:
    yaml_bad_threshold = VALID_FRONTMATTER.replace(
        "threshold: 0.7", "threshold: 1.5"
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml_bad_threshold)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "threshold" in "\n".join(result.details).lower()


def test_lint_fails_when_input_phrasings_empty(tmp_path: Path) -> None:
    yaml_no_phrasings = """---
name: demo-skill/happy-path
description: Demo trajectory used for tests.
skill: demo-skill
scenario: happy-path
version: 0.1.0
owner: test
last_reviewed: 2026-05-28
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:

assertions:
  - first_skill_loaded: demo-skill

llm_judge:
  threshold: 0.7
  rubric: "Score it."
  model: claude-sonnet-4-6
"""
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml_no_phrasings)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "phrasing" in "\n".join(result.details).lower()


def test_lint_warns_when_phrasing_count_below_five(tmp_path: Path) -> None:
    """Anthropic guidance: 5 phrasings minimum. Below 5 is a warn, not fail,
    so projects can adopt incrementally without blocking CI on day one."""
    repo = _setup_repo(tmp_path, trajectory_yaml=ONE_PHRASING_FRONTMATTER)
    result = _run_check(repo)
    assert result.status == "warn"
    assert "phrasing" in "\n".join(result.details).lower()


def test_lint_with_no_trajectories_is_ok(tmp_path: Path) -> None:
    """Empty trajectories tree = ok (the gate only fires on present files)."""
    (tmp_path / "base").mkdir()
    from adapters._loader import PlaybookContent
    from checks import CheckContext
    from checks import trajectory as trajectory_check

    ctx = CheckContext(
        repo_root=tmp_path,
        content=PlaybookContent.load(tmp_path),
    )
    result = trajectory_check.run(ctx)
    assert result.status == "ok"


# --- Review-fix regressions: review findings codified as gate tests ---


def test_lint_fails_when_adapter_scope_is_empty(tmp_path: Path) -> None:
    """Empty inline list adapter_scope = trajectory will never run. Hard fail."""
    yaml = VALID_FRONTMATTER.replace(
        "adapter_scope: [claude-code]",
        "adapter_scope: []",
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "empty" in "\n".join(result.details).lower()
    assert "adapter_scope" in "\n".join(result.details)


def test_lint_fails_when_assertions_block_is_empty(tmp_path: Path) -> None:
    """A trajectory with no assertions has nothing for the harness to check."""
    yaml = VALID_FRONTMATTER.replace(
        "assertions:\n  - first_skill_loaded: demo-skill",
        "assertions:",
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "assertions" in "\n".join(result.details).lower()


def test_lint_fails_when_llm_judge_threshold_missing(tmp_path: Path) -> None:
    yaml = VALID_FRONTMATTER.replace("  threshold: 0.7\n", "")
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "threshold" in "\n".join(result.details).lower()


def test_lint_fails_when_llm_judge_rubric_missing(tmp_path: Path) -> None:
    yaml = VALID_FRONTMATTER.replace('  rubric: "Score it."\n', "")
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "rubric" in "\n".join(result.details).lower()


def test_lint_fails_when_llm_judge_model_missing(tmp_path: Path) -> None:
    yaml = VALID_FRONTMATTER.replace("  model: claude-sonnet-4-6\n", "")
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    assert "model" in "\n".join(result.details).lower()


def test_lint_fails_when_frontmatter_field_is_TODO_placeholder(
    tmp_path: Path,
) -> None:
    """The scaffolder leaves `model_pinned: TODO-model-id`. The linter must
    refuse to accept a placeholder."""
    yaml = VALID_FRONTMATTER.replace(
        "model_pinned: claude-opus-4-7",
        "model_pinned: TODO-model-id",
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    joined = "\n".join(result.details).lower()
    assert "todo" in joined
    assert "model_pinned" in joined


def test_lint_accepts_quoted_frontmatter_values(tmp_path: Path) -> None:
    """Quoted scalars like `skill: "demo-skill"` must not break slug comparisons."""
    yaml = VALID_FRONTMATTER.replace(
        "skill: demo-skill", 'skill: "demo-skill"'
    ).replace(
        "scenario: happy-path", "scenario: 'happy-path'"
    ).replace(
        "name: demo-skill/happy-path", 'name: "demo-skill/happy-path"'
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "ok", "\n".join(result.details)


def test_lint_fails_when_phrasing_starts_with_TODO(tmp_path: Path) -> None:
    """Third-review P2: scaffolder writes `TODO first phrasing` etc.; the
    linter must catch body-level TODOs, not just frontmatter."""
    yaml = VALID_FRONTMATTER.replace(
        '"first phrasing"', '"TODO first phrasing"'
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    joined = "\n".join(result.details).lower()
    assert "todo" in joined and "phrasing" in joined


def test_lint_fails_when_rubric_starts_with_TODO(tmp_path: Path) -> None:
    """Third-review P2: the scaffolder leaves a TODO rubric scaffold."""
    yaml = VALID_FRONTMATTER.replace(
        '  rubric: "Score it."',
        '  rubric: "TODO Score the trajectory on:"',
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    joined = "\n".join(result.details).lower()
    assert "rubric" in joined and "todo" in joined


def test_lint_fails_when_call_order_uses_block_style(tmp_path: Path) -> None:
    """Third-review P2: block-style call_order parses as an empty string
    (the naive reader does not handle indented block sequences). The
    linter must fail loud rather than let an unrunnable trajectory pass."""
    yaml = VALID_FRONTMATTER.replace(
        "  - first_skill_loaded: demo-skill",
        "  - first_skill_loaded: demo-skill\n"
        "  - call_order:\n"
        "      - tool: AskUserQuestion\n"
        "        before: Write",
    )
    repo = _setup_repo(tmp_path, trajectory_yaml=yaml)
    result = _run_check(repo)
    assert result.status == "fail"
    joined = "\n".join(result.details).lower()
    assert "call_order" in joined
    assert "inline" in joined or "block" in joined


def test_lint_resolves_imported_skill(tmp_path: Path) -> None:
    """Trajectories may target imported skills at base/skills/imported/<source>/<name>/."""
    yaml = VALID_FRONTMATTER.replace(
        "demo-skill/happy-path", "imported-skill/happy-path"
    ).replace(
        "skill: demo-skill", "skill: imported-skill"
    ).replace(
        "first_skill_loaded: demo-skill", "first_skill_loaded: imported-skill"
    )
    # Build the imported-skill layout instead of first-party.
    imported_dir = (
        tmp_path / "base" / "skills" / "imported" / "demo-source" / "imported-skill"
    )
    imported_dir.mkdir(parents=True)
    (imported_dir / "SKILL.md").write_text(
        "---\nname: imported-skill\ndescription: imported demo\nversion: 0.1.0\n"
        "owner: test\nlast_reviewed: 2026-05-28\n---\n\n# Imported Skill\n",
        encoding="utf-8",
    )
    traj_dir = tmp_path / "base" / "trajectories" / "imported-skill"
    traj_dir.mkdir(parents=True)
    (traj_dir / "happy-path.yaml").write_text(yaml, encoding="utf-8")

    result = _run_check(tmp_path)
    assert result.status == "ok", "\n".join(result.details)
