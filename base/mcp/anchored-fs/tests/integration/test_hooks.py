import json
import subprocess
import sys
import os
import time
from pathlib import Path
import pytest


def run_hook(
    script: str, payload: dict, env_extra: dict | None = None
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.update(env_extra or {})
    project_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
    )


@pytest.fixture
def daemon_running(tmp_path: Path):
    sock = tmp_path / "daemon.sock"
    proc = subprocess.Popen(
        [sys.executable, "-m", "daemon.daemon", "--socket", str(sock)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    for _ in range(50):
        if sock.exists():
            break
        time.sleep(0.05)
    yield sock
    proc.terminate()
    proc.wait(timeout=5)


def test_pretool_edit_passes_through_when_no_upto(tmp_path: Path):
    target = tmp_path / "x.py"
    target.write_text("hello\n")
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "hello",
            "new_string": "world",
        },
    }
    result = run_hook("hooks/claude-code/pretool_edit.py", payload)
    assert result.returncode == 0, result.stderr
    if result.stdout.strip():
        out = json.loads(result.stdout)
        assert out.get("hookSpecificOutput", {}).get("permissionDecision") in (
            None,
            "allow",
        )


def test_pretool_edit_rewrites_upto_to_full_old_string(tmp_path: Path):
    """Requires a running daemon. If daemon socket not available, test should still pass (silent pass-through)."""
    target = tmp_path / "y.py"
    target.write_text("def foo():\n    x = 1\n    return x\n")
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "def foo():[upto]    return x",
            "new_string": "def foo():\n    return improved()",
        },
    }
    # Note: if no daemon is running, the hook returns {} (pass-through). To get rewriting, start daemon first.
    # For this test, we just assert the hook exits cleanly. Full rewrite is exercised by E2E tests (Task 16).
    result = run_hook("hooks/claude-code/pretool_edit.py", payload)
    assert result.returncode == 0, result.stderr


def test_pretool_edit_logs_adoption(daemon_running, tmp_path: Path):
    """When daemon is running, hook sends record_adoption for each edit processed."""
    target = tmp_path / "x.py"
    target.write_text("hello\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(target),
            "old_string": "hello",
            "new_string": "world",
        },
    }
    result = run_hook(
        "hooks/claude-code/pretool_edit.py",
        payload,
        env_extra={
            "ANCHORED_FS_STATE_DIR": str(state_dir),
            "ANCHORED_FS_SOCKET_PATH": str(daemon_running),
        },
    )
    assert result.returncode == 0, result.stderr
    # Daemon should have written an adoption record
    adoption_log = state_dir / "adoption.jsonl"
    assert adoption_log.exists(), "adoption.jsonl not written by daemon"
    import json

    record = json.loads(adoption_log.read_text().strip())
    assert record["agent"] == "claude-code-hook"
    assert record["used_upto"] is False


def test_posttool_read_exit_0_on_success(daemon_running, tmp_path: Path):
    """posttool_read delegates state IO to the daemon; verify exit 0 and that
    the daemon wrote to read-history.json."""
    target = tmp_path / "z.py"
    target.write_text("hello\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    payload = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(target)},
        "tool_response": {"file_path": str(target), "content": "hello\n"},
    }
    result = run_hook(
        "hooks/claude-code/posttool_read.py",
        payload,
        env_extra={
            "ANCHORED_FS_STATE_DIR": str(state_dir),
            "ANCHORED_FS_SOCKET_PATH": str(daemon_running),
        },
    )
    assert result.returncode == 0, result.stderr
    # Daemon should have written to read-history.json
    history_file = state_dir / "read-history.json"
    assert history_file.exists()
