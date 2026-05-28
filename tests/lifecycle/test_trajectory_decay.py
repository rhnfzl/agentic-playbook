"""Trajectory decay check (60/90/180-day bands, per ADR-0044).

Phase 0 / Task 4 of the cross-adapter trajectory harness. Trajectory bands
match skill bands until the Phase 1 harness produces actual drift data;
the ADR explains the rationale.

These tests inject a fixed `today` so the assertions stay stable as the
calendar advances. Each band boundary (60d / 90d / 180d) gets its own
exact-day test.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


FIXED_TODAY = date(2026, 5, 28)

SKILL_MD = """---
name: demo-skill
description: demo
version: 0.1.0
owner: test
last_reviewed: 2026-05-28
---

# Demo Skill
"""


def _trajectory_yaml(last_reviewed: str) -> str:
    return f"""---
name: demo-skill/happy-path
description: Demo
skill: demo-skill
scenario: happy-path
version: 0.1.0
owner: test
last_reviewed: {last_reviewed}
adapter_scope: [claude-code]
model_pinned: claude-opus-4-7
---

input:
  phrasings:
    - "x"
"""


def _days_ago(n: int) -> str:
    """Return YYYY-MM-DD for n days before FIXED_TODAY."""
    return (FIXED_TODAY - timedelta(days=n)).isoformat()


def _setup_repo(tmp_path: Path, trajectory_last_reviewed: str) -> Path:
    """Build a tmp repo with one skill + one trajectory file."""
    skill_dir = tmp_path / "base" / "skills" / "engineering" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    traj_dir = tmp_path / "base" / "trajectories" / "demo-skill"
    traj_dir.mkdir(parents=True)
    (traj_dir / "happy-path.yaml").write_text(
        _trajectory_yaml(trajectory_last_reviewed),
        encoding="utf-8",
    )
    return tmp_path


def _run_decay(tmp_path: Path) -> tuple[int, str]:
    """Run decay_check.main() against the tmp repo with a fixed reference date."""
    import decay_check

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = decay_check.main(repo_root=tmp_path, today=FIXED_TODAY)
    return rc, buf.getvalue()


def test_fresh_trajectory_passes(tmp_path: Path) -> None:
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(3))
    rc, out = _run_decay(repo)
    assert rc == 0, out


def test_trajectory_one_day_below_notice_boundary_passes(tmp_path: Path) -> None:
    """59 days ago is below the 60d notice band; should be silent ok."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(59))
    rc, out = _run_decay(repo)
    assert rc == 0, out
    assert "ok" in out.lower()


def test_trajectory_at_notice_boundary_emits_notice(tmp_path: Path) -> None:
    """60 days ago is exactly on the boundary; emits a notice but does not fail."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(60))
    rc, out = _run_decay(repo)
    assert rc == 0, out
    assert "notice" in out.lower()
    assert "demo-skill/happy-path" in out or "happy-path" in out


def test_trajectory_one_day_below_warn_boundary_only_notices(tmp_path: Path) -> None:
    """89 days ago is below the 90d warn boundary; notice only."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(89))
    rc, out = _run_decay(repo)
    assert rc == 0
    assert "warning" not in out.lower()


def test_trajectory_at_warn_boundary_emits_warn(tmp_path: Path) -> None:
    """90 days ago crosses the warn boundary; warns but does not fail."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(90))
    rc, out = _run_decay(repo)
    assert rc == 0, out
    assert "warning" in out.lower()
    assert "demo-skill/happy-path" in out or "happy-path" in out


def test_trajectory_one_day_below_block_boundary_only_warns(tmp_path: Path) -> None:
    """179 days ago is one short of the block; warn but exit 0."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(179))
    rc, out = _run_decay(repo)
    assert rc == 0
    assert "warning" in out.lower()
    assert "BLOCKING" not in out


def test_trajectory_at_block_boundary_fails(tmp_path: Path) -> None:
    """180 days ago crosses the block boundary; non-zero exit."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(180))
    rc, out = _run_decay(repo)
    assert rc == 1
    assert "BLOCKING" in out


def test_trajectory_missing_last_reviewed_fails(tmp_path: Path) -> None:
    """Trajectory without last_reviewed always fails (frontmatter lint also catches)."""
    repo = _setup_repo(tmp_path, trajectory_last_reviewed=_days_ago(1))
    traj_path = repo / "base" / "trajectories" / "demo-skill" / "happy-path.yaml"
    content = traj_path.read_text(encoding="utf-8")
    content = content.replace(f"last_reviewed: {_days_ago(1)}\n", "")
    traj_path.write_text(content, encoding="utf-8")
    rc, out = _run_decay(repo)
    assert rc == 1
    assert "last_reviewed" in out


def test_skill_and_trajectory_use_same_bands_today() -> None:
    """v0.2 simplification: trajectories share skill bands. The ADR
    explains the reasoning; this test makes the contract explicit so a
    future change to TRAJECTORY_BANDS triggers a deliberate review."""
    import decay_check

    assert decay_check.SKILL_BANDS == decay_check.TRAJECTORY_BANDS
