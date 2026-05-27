#!/usr/bin/env python3
"""PostToolUse hook for Read. Thin socket client to daemon."""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from daemon.client import call as daemon_call  # noqa: E402

HOME = Path(os.environ.get("HOME", str(Path.home())))
_default_socket = str(HOME / ".config" / "agent-shared" / "run" / "anchored-fs.sock")
SOCKET_PATH = os.environ.get("ANCHORED_FS_SOCKET_PATH", _default_socket)
STATE_DIR = Path(
    os.environ.get(
        "ANCHORED_FS_STATE_DIR", str(HOME / ".config" / "agent-shared" / "state")
    )
)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    request = json.loads(raw)
    if request.get("tool_name") != "Read":
        return 0
    tool_input = request.get("tool_input", {})
    file_path = tool_input.get("file_path")
    if not file_path:
        return 0
    p = Path(file_path)
    try:
        if not p.exists():
            # Failure path: ask daemon for candidates
            response = daemon_call(
                str(SOCKET_PATH),
                {
                    "action": "path_resolver_candidates",
                    "target": file_path,
                    "workspace_root": str(Path.cwd()),
                },
                timeout=2.0,
            )
            if response.get("ok") and response.get("candidates"):
                msg = f"anchored-fs path-resolver candidates for {file_path}:\n"
                for c in response["candidates"]:
                    msg += f"  {c['path']} (similarity {c['similarity']:.2f})\n"
                print(msg, file=sys.stderr)
                sys.exit(2)
            return 0
        # Success path: record state via daemon
        daemon_call(
            str(SOCKET_PATH),
            {"action": "record_read", "path": file_path, "state_dir": str(STATE_DIR)},
            timeout=2.0,
        )
        return 0
    except (FileNotFoundError, OSError, ConnectionRefusedError):
        # Daemon not running — silent pass-through
        return 0


if __name__ == "__main__":
    sys.exit(main())
