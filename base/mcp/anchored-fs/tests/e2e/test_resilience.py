"""Phase 0 gate: resilience + crash smokes."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def test_update_resilience_smoke(tmp_path: Path):
    """Simulate a CC plugin cache wipe; install.py check must still report ok."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    (home / ".claude" / "plugins" / "cache").mkdir(parents=True)
    (home / ".claude" / "plugins" / "cache" / "dummy.txt").write_text(
        "simulated plugin cache"
    )

    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    project_root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, "install.py", "init"],
        env=env,
        check=True,
        capture_output=True,
        cwd=str(project_root),
    )

    # Simulate Claude Code update wiping its plugins cache:
    shutil.rmtree(home / ".claude" / "plugins" / "cache")

    result = subprocess.run(
        [sys.executable, "install.py", "check"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    assert result.returncode == 0, result.stderr


def test_daemon_crash_restart_smoke(tmp_path: Path):
    """Daemon socket disappears when daemon dies. (Full launchd-managed restart verified post-install, not here.)"""
    sock = tmp_path / "daemon.sock"
    proc = subprocess.Popen(
        [sys.executable, "-m", "daemon.daemon", "--socket", str(sock)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.05)
        assert sock.exists(), "daemon did not create socket"

        from daemon.client import call

        response = call(str(sock), {"action": "ping"})
        assert response.get("pong") is True

        # Kill daemon; subsequent ping should raise connection error.
        proc.terminate()
        proc.wait(timeout=5)

        try:
            call(str(sock), {"action": "ping"}, timeout=0.5)
            assert False, "expected connection failure after daemon terminated"
        except (FileNotFoundError, ConnectionRefusedError, OSError, BrokenPipeError):
            pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
