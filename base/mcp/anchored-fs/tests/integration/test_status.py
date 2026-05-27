import json
import os
import subprocess
import sys
import time
from pathlib import Path


def test_status_reports_validator_modes_and_telemetry(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    project_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "install.py", "init"],
        env=env,
        check=True,
        capture_output=True,
        cwd=str(project_root),
    )

    state_dir = home / ".config" / "agent-shared" / "state"
    adoption_path = state_dir / "adoption.jsonl"
    adoption_path.write_text(
        json.dumps(
            {"ts": time.time(), "used_upto": True, "old_lines": 30, "rescued": False}
        )
        + "\n"
    )

    result = subprocess.run(
        [sys.executable, "install.py", "status"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, result.stderr
    assert "edit_anchor" in result.stdout
    assert "adoption" in result.stdout.lower()
