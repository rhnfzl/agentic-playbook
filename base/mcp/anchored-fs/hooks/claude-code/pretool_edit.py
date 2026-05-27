#!/usr/bin/env python3
"""PreToolUse hook for Edit / MultiEdit / Write.

Responsibilities (as of 2026-05-24):
  - Adoption telemetry: records every Edit via daemon (fail-soft).
  - Stale-read guard: warns when file changed since last Read.

NOT handled here (see mcp__anchored_fs__edit_file / mcp__filesystem__edit_file):
  - [upto] anchor resolution. Native Edit validates old_string against file
    content BEFORE hooks fire, so [upto] syntax is rejected before this hook
    can transform it. Bug #15897 would also drop updatedInput in multi-hook
    setups. Route all [upto] usage to the MCP tools.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from daemon.client import call as daemon_call  # noqa: E402

HOME = Path(os.environ.get("HOME", str(Path.home())))
SOCKET_PATH = Path(
    os.environ.get(
        "ANCHORED_FS_SOCKET_PATH",
        str(HOME / ".config" / "agent-shared" / "run" / "anchored-fs.sock"),
    )
)


def _emit(payload: dict) -> NoReturn:
    print(json.dumps(payload))
    sys.exit(0)


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        _emit({})
    request = json.loads(raw)
    tool_name = request.get("tool_name")
    tool_input = request.get("tool_input", {})

    if tool_name not in {"Edit", "MultiEdit", "Write"}:
        _emit({})
    if tool_name == "Write":
        _emit({})

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits", [])
    else:
        edits = [
            {
                "old_string": tool_input.get("old_string", ""),
                "new_string": tool_input.get("new_string", ""),
            }
        ]
    file_path = tool_input.get("file_path", "")

    state_dir = Path(
        os.environ.get(
            "ANCHORED_FS_STATE_DIR",
            str(HOME / ".config" / "agent-shared" / "state"),
        )
    )

    for edit in edits:
        old = edit.get("old_string", "")
        # Log adoption for every edit via daemon (fail-soft).
        # [upto] usage is recorded as used_upto=True for telemetry even though
        # resolution does not happen here; it signals a misconfigured caller.
        used_upto = "[upto]" in old
        try:
            daemon_call(
                str(SOCKET_PATH),
                {
                    "action": "record_adoption",
                    "agent": "claude-code-hook",
                    "session": "unknown",
                    "used_upto": used_upto,
                    "old_lines": len(old.splitlines()),
                    "rescued": False,
                    "file_extension": Path(file_path).suffix,
                    "state_dir": str(state_dir),
                },
                timeout=1.0,
            )
        except (FileNotFoundError, OSError, ConnectionRefusedError):
            pass

    if tool_name in {"Edit", "MultiEdit"} and file_path:
        try:
            stale_response = daemon_call(
                str(SOCKET_PATH),
                {
                    "action": "check_stale",
                    "path": file_path,
                    "state_dir": str(state_dir),
                    "allow_no_prior": True,
                },
                timeout=1.0,
            )
            if stale_response.get("ok") and stale_response.get("stale"):
                _emit(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": f"anchored-fs WARN: {file_path} changed since your last Read. Consider re-reading before editing.",
                        }
                    }
                )
        except (FileNotFoundError, OSError, ConnectionRefusedError):
            pass

    _emit({})


if __name__ == "__main__":
    sys.exit(main())
