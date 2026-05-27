"""Integration test: FastMCP server lists all expected tools via MCP stdio protocol."""

import asyncio
import json
import sys
import pytest
from pathlib import Path


@pytest.mark.asyncio
async def test_server_lists_overridden_and_passthrough_tools(tmp_path: Path):
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "server",
        "--allowed-dir",
        str(tmp_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        init_req = (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "0"},
                    },
                }
            )
            + "\n"
        )
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(init_req.encode())
        proc.stdin.write(
            (
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
            ).encode()
        )
        await proc.stdin.drain()
        await proc.stdout.readline()  # init response

        list_req = (
            json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            )
            + "\n"
        )
        proc.stdin.write(list_req.encode())
        await proc.stdin.drain()
        resp_line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
        resp = json.loads(resp_line.decode())
        names = [t["name"] for t in resp["result"]["tools"]]
        # Overridden:
        assert "edit_file" in names
        # Net-new:
        assert "preview_edit_match" in names
        # Passthrough subset (spike finding 2: 14 tools total in stock; we keep all 13 non-overridden):
        for required in [
            "read_text_file",
            "write_file",
            "list_directory",
            "directory_tree",
            "search_files",
            "get_file_info",
            "list_allowed_directories",
        ]:
            assert required in names, f"missing passthrough tool: {required}"
    finally:
        proc.terminate()
        await proc.wait()
