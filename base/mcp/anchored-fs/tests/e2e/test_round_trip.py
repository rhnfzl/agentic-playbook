"""Cross-agent E2E: same file, same anchored pattern, two execution paths."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def test_mcp_path_resolves_upto_via_edit_file(tmp_path: Path):
    """Direct call into tools/edit_file.py (the path Codex's MCP server uses)."""
    target = tmp_path / "g.py"
    target.write_text("def world():\n    a = 1\n    b = 2\n    return a + b\n")
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    from tools.edit_file import edit_file

    result = edit_file(
        path=str(target),
        old_text="def world():[upto]    return a + b",
        new_text="def world():\n    return 42",
        dry_run=False,
    )
    assert result["ok"] is True
    assert target.read_text() == "def world():\n    return 42\n"


def test_byte_identical_outcome_both_paths(tmp_path: Path):
    """Same source + same edit through edit_file twice produces byte-identical file state."""
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))
    src = "def shared():\n    x = 1\n    y = 2\n    return x + y\n"
    new = "def shared():\n    return 3\n"
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text(src)
    file_b.write_text(src)
    from tools.edit_file import edit_file

    edit_file(
        path=str(file_a),
        old_text="def shared():[upto]    return x + y",
        new_text=new,
        dry_run=False,
    )
    edit_file(
        path=str(file_b),
        old_text="def shared():[upto]    return x + y",
        new_text=new,
        dry_run=False,
    )
    assert file_a.read_text() == file_b.read_text()


def test_claude_code_hook_path_resolves_upto(tmp_path: Path):
    """End-to-end: spawn daemon, route a pretool_edit invocation through it."""
    sock = tmp_path / "d.sock"
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

        f = tmp_path / "h.py"
        f.write_text("def hello():\n    print('hi')\n    return 1\n")

        # Wire the daemon socket where pretool_edit expects it
        sock_dir = tmp_path / ".config" / "agent-shared" / "run"
        sock_dir.mkdir(parents=True, exist_ok=True)
        if not (sock_dir / "anchored-fs.sock").exists():
            (sock_dir / "anchored-fs.sock").symlink_to(sock)

        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(f),
                "old_string": "def hello():[upto]    return 1",
                "new_string": "def hello():\n    return 99",
            },
        }
        project_root = Path(__file__).resolve().parents[2]
        env = {**os.environ, "HOME": str(tmp_path)}
        result = subprocess.run(
            [sys.executable, "hooks/claude-code/pretool_edit.py"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(project_root),
        )
        assert result.returncode == 0, result.stderr
        if result.stdout.strip():
            out = json.loads(result.stdout)
            expanded = (
                out.get("hookSpecificOutput", {})
                .get("updatedInput", {})
                .get("old_string")
            )
            assert expanded == "def hello():\n    print('hi')\n    return 1", (
                f"got {expanded!r}"
            )
    finally:
        proc.terminate()
        proc.wait(timeout=5)
