"""Wraps the Snyk skill scanner for the supply-chain gate.

`snyk-agent-scan` (formerly `mcp-scan`) targets installed MCP server
configurations, not raw skill directories. The playbook ships MCP
*bundles* under `base/mcp/`, not installed configs, so by default
this wrapper is inert: it returns `skipped` with a note pointing at
the env var that opts in.

Opt-in:

  SNYK_AGENT_SCAN_CONFIG=/path/to/config.json make audit-security

The wrapper still tries both package names (new + legacy) so older
contributor installs keep working until they upgrade. If neither
resolves we return `skipped`.

Why subprocess and not a Python API: the scanner publishes a CLI as
its stable contract.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import Finding, WrapperResult


TOOL_CANDIDATES = ("snyk-agent-scan", "mcp-scan")

SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFORMATIONAL": "info",
    "INFO": "info",
}


def _have_uvx() -> bool:
    return shutil.which("uvx") is not None


def _normalize_severity(value: str) -> str:
    return SEVERITY_MAP.get((value or "").upper(), "medium")


def _invoke(tool_pkg: str, config_path: Path) -> subprocess.CompletedProcess[str] | None:
    cmd = [
        "uvx", f"{tool_pkg}@latest", "scan",
        "--json", "--skills", "--ci", str(config_path),
    ]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None


def _parse_findings(payload: dict, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for row in payload.get("findings", payload.get("issues", [])):
        skill_path = row.get("path", row.get("file", ""))
        try:
            rel = str(Path(skill_path).resolve().relative_to(repo_root))
        except (ValueError, OSError):
            rel = skill_path
        findings.append(Finding(
            source="snyk-agent-scan",
            severity=_normalize_severity(row.get("severity", row.get("level", ""))),
            skill_path=rel,
            category=row.get("rule", row.get("code", "unspecified")),
            message=row.get("message", "")[:200],
            raw=json.dumps(row)[:500],
        ))
    return findings


def run(skill_dirs: list[Path], repo_root: Path) -> WrapperResult:
    """Run the Snyk skill scanner.

    Soft-skip if uvx is not on PATH, or if no SNYK_AGENT_SCAN_CONFIG
    env var points at an MCP config file. The `skill_dirs` argument
    is accepted for aggregator-shape parity but unused: the scanner
    operates on configs, not raw skill dirs.
    """
    del skill_dirs  # interface-shape only; scanner reads config files
    tool = "snyk-agent-scan"

    if not _have_uvx():
        return WrapperResult(
            tool=tool, status="skipped", findings=[],
            note="uvx not on PATH; install uv to enable the Snyk skill scanner",
        )

    config_env = os.environ.get("SNYK_AGENT_SCAN_CONFIG", "").strip()
    if not config_env:
        return WrapperResult(
            tool=tool, status="skipped", findings=[],
            note="set SNYK_AGENT_SCAN_CONFIG=<path-to-mcp-config> to opt in",
        )

    config_path = Path(config_env).expanduser().resolve()
    if not config_path.is_file():
        return WrapperResult(
            tool=tool, status="skipped", findings=[],
            note=f"SNYK_AGENT_SCAN_CONFIG points at missing file: {config_path}",
        )

    last_error = ""
    for candidate in TOOL_CANDIDATES:
        proc = _invoke(candidate, config_path)
        if proc is None:
            last_error = f"{candidate} subprocess timed out or failed to spawn"
            continue
        if proc.returncode not in (0, 1):
            last_error = (
                f"{candidate} exit={proc.returncode}: "
                f"{proc.stderr.strip()[:200]}"
            )
            continue
        try:
            payload = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            last_error = f"{candidate} non-JSON stdout: {exc}"
            continue
        findings = _parse_findings(payload, repo_root)
        return WrapperResult(
            tool=tool,
            status="findings" if findings else "ok",
            findings=findings,
            note=f"resolved via {candidate}" if candidate != tool else "",
        )

    return WrapperResult(
        tool=tool, status="skipped", findings=[],
        note=f"no candidate scanner resolved; last error: {last_error}",
    )
