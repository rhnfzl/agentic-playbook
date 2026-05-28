"""Trajectory decay check (60-day window, per ADR-0043).

Phase 0 / Task 4 of the cross-adapter trajectory harness. Trajectories
are model-version-coupled and rot faster than skills (90/180 day bands),
so they get a tighter 60-day window: 30-60 day notice, 60-day warn,
90-day block.
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


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


def _run_decay_in(tmp_path: Path) -> tuple[int, str]:
    """Run decay_check.main() against a fake repo by monkeypatching the
    module-level repo discovery."""
    import decay_check

    original_resolve = Path.resolve

    def fake_resolve(self):
        # The script computes repo_root as Path(__file__).resolve().parent.parent.
        # Redirect that to tmp_path so the test exercises tmp content.
        result = original_resolve(self)
        if "scripts/decay_check" in str(result):
            return tmp_path / "scripts" / "decay_check.py"
        return result

    # The cleanest approach: invoke the script with sys.argv pointing at a
    # CLI flag, but the existing script doesn't take args. Instead we
    # monkeypatch the REPO_ROOT discovery via an env var the new script
    # respects, or just call a refactored entry point. For Phase 0 we'll
    # add an optional repo_root arg in the implementation, then pass it
    # here.
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = decay_check.main(repo_root=tmp_path)
    return rc, buf.getvalue()


def test_fresh_trajectory_passes(tmp_path: Path) -> None:
    repo = _setup_repo(tmp_path, trajectory_last_reviewed="2026-05-25")  # ~3d old
    rc, out = _run_decay_in(repo)
    assert rc == 0, out
    assert "trajectory" in out.lower() or "demo-skill/happy-path" in out


def test_trajectory_in_notice_band_does_not_fail(tmp_path: Path) -> None:
    # 35 days old -> in 30-60d notice band for trajectories.
    repo = _setup_repo(tmp_path, trajectory_last_reviewed="2026-04-23")
    rc, out = _run_decay_in(repo)
    assert rc == 0, out


def test_trajectory_in_warn_band_does_not_fail(tmp_path: Path) -> None:
    # 70 days old -> in 60-90d warn band for trajectories.
    repo = _setup_repo(tmp_path, trajectory_last_reviewed="2026-03-19")
    rc, out = _run_decay_in(repo)
    assert rc == 0, out
    assert (
        "happy-path" in out.lower() or "trajectory" in out.lower()
    ), out


def test_trajectory_past_block_fails(tmp_path: Path) -> None:
    # 100 days old -> beyond trajectory 90d block.
    repo = _setup_repo(tmp_path, trajectory_last_reviewed="2026-02-17")
    rc, out = _run_decay_in(repo)
    assert rc == 1
    assert "happy-path" in out.lower() or "trajectory" in out.lower()


def test_trajectory_missing_last_reviewed_fails(tmp_path: Path) -> None:
    repo = _setup_repo(tmp_path, trajectory_last_reviewed="2026-05-28")
    # Strip last_reviewed entirely.
    traj_path = repo / "base" / "trajectories" / "demo-skill" / "happy-path.yaml"
    content = traj_path.read_text(encoding="utf-8")
    content = content.replace("last_reviewed: 2026-05-28\n", "")
    traj_path.write_text(content, encoding="utf-8")
    rc, out = _run_decay_in(repo)
    assert rc == 1
    assert "last_reviewed" in out
