"""MCP runtime probe regression tests (v0.8 B2 + Codex fold-in).

Pinned behaviors (each test docstring names the ADR / review finding it
covers):

  ok / hang / error / non-JSON / no-stdout / TOML happy paths.
  Codex review P1: long-running server must classify as ok (not timeout).
  Codex review P2: missing serverInfo must classify as fail.
  Codex review fold-in: PATH-resolved bare commands (npx, docker,
    python3) must probe via shutil.which; absolute managed paths that
    are missing classify as fail; bare PATH commands not on host
    classify as skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make scripts/ importable for any direct module use.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ._helpers import (
    _write_fake_mcp_config,
    _write_fake_mcp_server,
    _write_long_running_fake_server,
)


def test_mcp_runtime_probe_ok_path(tmp_path: Path) -> None:
    """probe_one_server returns status='ok' when the server completes a
    JSON-RPC initialize round-trip (v0.8 B2 baseline)."""
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "ok")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "ok", f"expected ok, got {result.status}: {result.detail}"
    assert "fake-ok" in result.detail


def test_mcp_runtime_probe_hang_times_out(tmp_path: Path) -> None:
    """A server that never responds gets classified as 'timeout' so the
    user can tell "slow" apart from "broken." The probe terminates the
    process so no orphan stays running.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "hang")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=0.5)
    assert result.status == "timeout"


def test_mcp_runtime_probe_classifies_error_response_as_fail(tmp_path: Path) -> None:
    """A server that returns a JSON-RPC error envelope counts as 'fail'."""
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "error")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    assert "simulated failure" in result.detail


def test_mcp_runtime_probe_classifies_non_json_response_as_fail(tmp_path: Path) -> None:
    """Garbage stdout instead of JSON-RPC counts as 'fail' with a clear
    diagnostic so wrappers that accidentally print boot text get caught.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "non_json")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    assert "non-JSON" in result.detail


def test_mcp_runtime_probe_classifies_no_stdout_as_fail(tmp_path: Path) -> None:
    """A server that exits without writing to stdout is 'fail' with the
    stderr tail in the detail so the user sees the crash output.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "no_stdout")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    # Either "stderr" tail or "no stdout" reason should appear.
    assert "stderr" in result.detail or "no stdout" in result.detail


def test_mcp_runtime_probe_toml_codex_config(tmp_path: Path) -> None:
    """tomllib is stdlib in Python 3.11+; the helper parses codex's TOML
    format end-to-end with the same probe code path as JSON configs.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "ok")
    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=sys.executable,
        args=[str(server_py)],
        fmt="toml",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "ok"


def test_mcp_runtime_probe_classifies_missing_command(tmp_path: Path) -> None:
    """v0.8 Codex fold-in: a missing command classifies based on whether
    it looks managed or optional:

      * Absolute path containing `/` (managed venv binary): 'fail' with
        "managed MCP runtime missing"
      * Bare PATH command not present on host: 'skipped' with
        "PATH command not present" (handled by a different test)
    """
    from mcp_runtime_probe import probe_one_server

    cfg = _write_fake_mcp_config(
        tmp_path,
        server_name="fake",
        command=str(tmp_path / "does-not-exist"),
        args=[],
        fmt="json",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    assert "managed MCP runtime missing" in result.detail


def test_mcp_runtime_probe_resolves_path_executable(tmp_path: Path) -> None:
    """v0.8 Codex fold-in: bare PATH commands like `python3`, `npx`,
    `docker` must resolve via shutil.which.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_fake_mcp_server(tmp_path, "ok")
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": "python3",  # bare PATH command
                        "args": [str(server_py)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "ok", (
        f"PATH-resolved command must probe successfully, got "
        f"{result.status}: {result.detail}"
    )


def test_mcp_runtime_probe_managed_venv_missing_is_fail(tmp_path: Path) -> None:
    """v0.8 Codex fold-in: managed absolute paths missing on disk = fail."""
    from mcp_runtime_probe import probe_one_server

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": str(tmp_path / "venv" / "bin" / "python"),
                        "args": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    assert "managed MCP runtime missing" in result.detail


def test_mcp_runtime_probe_bare_path_command_not_present_is_skipped(
    tmp_path: Path,
) -> None:
    """v0.8 Codex fold-in: bare PATH command absent on host = skipped."""
    from mcp_runtime_probe import probe_one_server

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": "definitely-not-a-real-cli-tool-xyz",
                        "args": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "skipped"
    assert "PATH command" in result.detail


def test_mcp_runtime_probe_ok_on_long_running_server(tmp_path: Path) -> None:
    """v0.8 Codex P1: a healthy MCP server stays alive after initialize.
    The probe must classify that as 'ok' (not 'timeout'). The original
    cut used subprocess.communicate() which waits for EOF -- every real
    server got misclassified.
    """
    from mcp_runtime_probe import probe_one_server

    server_py = _write_long_running_fake_server(tmp_path)
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": sys.executable,
                        "args": [str(server_py)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "ok", (
        f"long-running server must classify as ok, got {result.status}: "
        f"{result.detail}"
    )
    assert "fake-long-running" in result.detail


def test_mcp_runtime_probe_fails_on_missing_server_info(tmp_path: Path) -> None:
    """v0.8 Codex P2: a JSON-RPC success without serverInfo must fail.
    A non-MCP wrapper that answers `result: {}` should not pass.
    """
    from mcp_runtime_probe import probe_one_server

    script = tmp_path / "fake-no-serverinfo.py"
    script.write_text(
        "import json, sys\n"
        "req = json.loads(sys.stdin.readline())\n"
        "resp = {'jsonrpc': '2.0', 'id': req['id'], 'result': {}}\n"
        "sys.stdout.write(json.dumps(resp) + '\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": sys.executable,
                        "args": [str(script)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=5.0)
    assert result.status == "fail"
    assert "serverInfo" in result.detail


def test_mcp_runtime_probe_skips_disabled_entries(tmp_path: Path) -> None:
    """v0.8 Codex review fix: `enabled: false` entries (VCS, code-
    review-graph, code-quality ship this way) must classify as 'skipped'
    so `make doctor-verify` does not spawn their placeholder commands.
    """
    import json

    from mcp_runtime_probe import probe_one_server

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": sys.executable,
                        "args": ["-c", "import time; time.sleep(60)"],
                        "enabled": False,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=2.0)
    assert result.status == "skipped"
    assert "enabled=false" in result.detail


def test_mcp_runtime_probe_honors_startup_timeout(tmp_path: Path) -> None:
    """v0.8 Codex review fix: when entry.startup_timeout_sec exceeds the
    probe's default, the probe uses the higher value (capped at 300s).
    Tested by giving the probe a 0.2s default + a 2s declared timeout
    against a server that sleeps 1s before responding; the probe must
    wait long enough to see the response.
    """
    import json

    from mcp_runtime_probe import probe_one_server

    server = tmp_path / "slow-server.py"
    server.write_text(
        "import json, sys, time\n"
        "line = sys.stdin.readline()\n"
        "req = json.loads(line)\n"
        "time.sleep(1)\n"
        "resp = {\n"
        "    'jsonrpc': '2.0', 'id': req['id'],\n"
        "    'result': {\n"
        "        'protocolVersion': '2024-11-05',\n"
        "        'serverInfo': {'name': 'slow', 'version': '1.0'},\n"
        "        'capabilities': {},\n"
        "    },\n"
        "}\n"
        "sys.stdout.write(json.dumps(resp) + '\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "slow": {
                        "command": sys.executable,
                        "args": [str(server)],
                        "startup_timeout_sec": 5,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    # Probe default 0.2s; entry overrides to 5s.
    result = probe_one_server("slow", cfg, timeout_sec=0.2)
    assert result.status == "ok", (
        f"probe should honor declared 5s timeout, got {result.status}: "
        f"{result.detail}"
    )


def test_mcp_runtime_probe_skips_placeholder_entries(tmp_path: Path) -> None:
    """v0.8 Codex round-6 fix: entries with unfilled {{...}} placeholders
    in env, args, or command must classify as 'skipped' so doctor-verify
    on a fresh stock-profile install doesn't fail/timeout against
    npx-launched servers (atlassian, slack, error-tracking, tavily) whose
    credentials haven't been filled in yet.
    """
    import json

    from mcp_runtime_probe import probe_one_server

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "@modelcontextprotocol/server-atlassian",
                        ],
                        "env": {
                            "ATLASSIAN_API_TOKEN": "{{REPLACE_WITH_YOUR_TOKEN}}",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    result = probe_one_server("fake", cfg, timeout_sec=2.0)
    assert result.status == "skipped"
    assert "placeholder" in result.detail
