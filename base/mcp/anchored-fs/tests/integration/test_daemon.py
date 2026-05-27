import asyncio
import sys
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_daemon_handles_resolve_request(tmp_path: Path):
    sock = tmp_path / "daemon.sock"
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "daemon.daemon",
        "--socket",
        str(sock),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        for _ in range(50):
            if sock.exists():
                break
            await asyncio.sleep(0.05)
        assert sock.exists(), "daemon did not create socket"

        target_file = tmp_path / "x.py"
        target_file.write_text("def foo():\n    return 1\n")

        from daemon.client import call

        response = call(
            str(sock),
            {
                "action": "resolve_upto",
                "path": str(target_file),
                "pattern": "def foo():[upto]    return 1",
            },
        )
        assert response["ok"] is True
        assert "def foo():" in response["span_text"]
    finally:
        proc.terminate()
        await proc.wait()
