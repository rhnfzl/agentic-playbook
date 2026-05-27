"""Combined scenario covering edit-anchor + path-resolver + stale-read in sequence."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
import pytest


@pytest.fixture
def daemon(tmp_path: Path):
    sock = tmp_path / "d.sock"
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


def test_anchor_resolves_via_pretool_hook(daemon, tmp_path: Path):
    """End-to-end: pretool_edit.py reads payload, calls daemon, returns expanded old_string."""
    f = tmp_path / "z.py"
    f.write_text("def foo():\n    return 1\n")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(f),
            "old_string": "def foo():[upto]    return 1",
            "new_string": "def foo():\n    return 2",
        },
    }
    project_root = Path(__file__).resolve().parents[2]
    home_with_socket = tmp_path
    sock_dir = home_with_socket / ".config" / "agent-shared" / "run"
    sock_dir.mkdir(parents=True, exist_ok=True)
    if not (sock_dir / "anchored-fs.sock").exists():
        (sock_dir / "anchored-fs.sock").symlink_to(daemon)
    env = {
        **os.environ,
        "ANCHORED_FS_STATE_DIR": str(state_dir),
        "HOME": str(home_with_socket),
    }
    result = subprocess.run(
        [sys.executable, "hooks/claude-code/pretool_edit.py"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout) if result.stdout.strip() else {}
    expanded = (
        out.get("hookSpecificOutput", {}).get("updatedInput", {}).get("old_string")
    )
    assert expanded == "def foo():\n    return 1", f"got: {expanded!r}, out: {out}"
