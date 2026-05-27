"""Integration tests: fuzzy_path and check_stale actions wired into daemon."""

import json
import subprocess
import sys
import time
from pathlib import Path
import pytest


@pytest.fixture
def daemon_running(tmp_path: Path):
    sock = tmp_path / "daemon.sock"
    proc = subprocess.Popen(
        [sys.executable, "-m", "daemon.daemon", "--socket", str(sock)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        if sock.exists():
            break
        time.sleep(0.05)
    yield sock
    proc.terminate()
    proc.wait(timeout=5)


def test_daemon_fuzzy_path_action(daemon_running, tmp_path: Path):
    (tmp_path / "format.py").write_text("x")
    from daemon.client import call

    response = call(
        str(daemon_running),
        {
            "action": "fuzzy_path",
            "target": "fromat.py",
            "workspace_root": str(tmp_path),
        },
    )
    assert response["ok"] is True
    assert any("format.py" in c["path"] for c in response["candidates"])


def test_daemon_check_stale_action(daemon_running, tmp_path: Path):
    f = tmp_path / "y.py"
    f.write_text("hello")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    from daemon.client import call

    response = call(
        str(daemon_running),
        {
            "action": "check_stale",
            "path": str(f),
            "state_dir": str(state_dir),
            "allow_no_prior": True,
        },
    )
    assert response["stale"] is False


def _write_graduation_state(state_dir: Path, last_check: float) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "graduation-state.json").write_text(
        json.dumps(
            {
                "last_check": last_check,
                "edit_anchor_mode": "auto_rescue",
                "stale_read_guard_mode": "warn",
            }
        )
    )


def _write_adoption_records(
    state_dir: Path, count: int, used_upto: bool = False
) -> None:
    """Write `count` adoption records with old_lines >= 25 to trigger graduation."""
    state_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for i in range(count):
        lines.append(
            json.dumps(
                {
                    "ts": time.time() - i,
                    "agent": "test",
                    "session": "s",
                    "used_upto": used_upto,
                    "old_lines": 30,
                    "rescued": False,
                    "file_extension": ".py",
                }
            )
        )
    (state_dir / "adoption.jsonl").write_text("\n".join(lines) + "\n")


def test_daemon_graduation_runs_lazy_after_6h(daemon_running, tmp_path: Path):
    """Graduation runs when last_check is 7h ago and updates graduation-state.json."""
    state_dir = tmp_path / "state"
    # Seed: 7h old check + 100 records with used_upto=False (0% adoption) -> force_reject
    _write_graduation_state(state_dir, last_check=time.time() - 7 * 3600)
    _write_adoption_records(state_dir, count=100, used_upto=False)

    from daemon.client import call

    response = call(
        str(daemon_running),
        {"action": "ping", "state_dir": str(state_dir)},
    )
    assert response["ok"] is True

    # Allow async graduation to complete
    time.sleep(0.2)

    grad_state = json.loads((state_dir / "graduation-state.json").read_text())
    assert grad_state["edit_anchor_mode"] == "force_reject"
    assert grad_state["last_check"] > time.time() - 5  # was updated recently


def test_daemon_graduation_skips_when_recent(daemon_running, tmp_path: Path):
    """Graduation is skipped when last_check was 1h ago."""
    state_dir = tmp_path / "state"
    recent_check = time.time() - 1 * 3600
    _write_graduation_state(state_dir, last_check=recent_check)
    _write_adoption_records(state_dir, count=100, used_upto=False)

    from daemon.client import call

    response = call(
        str(daemon_running),
        {"action": "ping", "state_dir": str(state_dir)},
    )
    assert response["ok"] is True

    time.sleep(0.2)

    grad_state = json.loads((state_dir / "graduation-state.json").read_text())
    # Mode should be unchanged (graduation skipped)
    assert grad_state["edit_anchor_mode"] == "auto_rescue"
    # last_check should NOT have been updated (still matches what we set)
    assert abs(grad_state["last_check"] - recent_check) < 5


def test_daemon_record_adoption_action(daemon_running, tmp_path: Path):
    """record_adoption action writes a record to adoption.jsonl in state_dir."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    from daemon.client import call

    response = call(
        str(daemon_running),
        {
            "action": "record_adoption",
            "agent": "test-agent",
            "session": "sess-abc",
            "used_upto": True,
            "old_lines": 10,
            "rescued": False,
            "file_extension": ".py",
            "state_dir": str(state_dir),
        },
    )
    assert response["ok"] is True
    adoption_log = state_dir / "adoption.jsonl"
    assert adoption_log.exists()
    record = json.loads(adoption_log.read_text().strip())
    assert record["agent"] == "test-agent"
    assert record["session"] == "sess-abc"
    assert record["used_upto"] is True
    assert record["old_lines"] == 10
    assert record["rescued"] is False
    assert record["file_extension"] == ".py"
    assert "ts" in record
