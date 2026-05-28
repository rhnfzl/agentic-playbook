"""Tests for the Snyk skill scanner wrapper.

The wrapper soft-skips when uvx is unavailable or no
SNYK_AGENT_SCAN_CONFIG env var points at a config file. When the
config exists and uvx is available, we mock subprocess to verify
JSON parsing + finding shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from security import mcp_scan_wrapper  # noqa: E402


def test_skips_when_uvx_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SNYK_AGENT_SCAN_CONFIG", raising=False)
    with patch.object(mcp_scan_wrapper, "_have_uvx", return_value=False):
        result = mcp_scan_wrapper.run([tmp_path], tmp_path)
    assert result.status == "skipped"
    assert "uvx" in result.note


def test_skips_when_env_var_unset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SNYK_AGENT_SCAN_CONFIG", raising=False)
    with patch.object(mcp_scan_wrapper, "_have_uvx", return_value=True):
        result = mcp_scan_wrapper.run([tmp_path], tmp_path)
    assert result.status == "skipped"
    assert "SNYK_AGENT_SCAN_CONFIG" in result.note


def test_skips_when_env_var_points_at_missing_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SNYK_AGENT_SCAN_CONFIG", str(tmp_path / "nope.json"))
    with patch.object(mcp_scan_wrapper, "_have_uvx", return_value=True):
        result = mcp_scan_wrapper.run([tmp_path], tmp_path)
    assert result.status == "skipped"
    assert "missing file" in result.note


def test_parses_findings_when_subprocess_succeeds(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "mcp.json"
    config.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SNYK_AGENT_SCAN_CONFIG", str(config))

    class FakeProc:
        returncode = 0
        stdout = json.dumps({
            "findings": [{
                "path": str(tmp_path / "skill"),
                "severity": "HIGH",
                "rule": "CVE-2024-12345",
                "message": "Known-bad pattern X",
            }],
        })
        stderr = ""

    with patch.object(mcp_scan_wrapper, "_have_uvx", return_value=True):
        with patch.object(mcp_scan_wrapper, "_invoke", return_value=FakeProc()):
            result = mcp_scan_wrapper.run([tmp_path / "skill"], tmp_path)

    assert result.status == "findings"
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f.source == "snyk-agent-scan"
    assert f.severity == "high"
    assert f.category == "CVE-2024-12345"
