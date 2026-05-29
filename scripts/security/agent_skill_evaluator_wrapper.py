"""Wraps the `agent-skill-evaluator` PyPI package.

agent-skill-evaluator is positioned as "npm audit for SKILL.md": it
checks frontmatter shape, links, and a small set of risky-instruction
heuristics. We import its public function if available; otherwise
fall back to invoking it as a module so we tolerate either install
path (pip install vs uvx run).

Soft-skip if neither path is available.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from pathlib import Path

from . import Finding, WrapperResult


def _try_import():
    try:
        return importlib.import_module("agent_skill_evaluator")
    except ImportError:
        return None


def _have_uvx() -> bool:
    return shutil.which("uvx") is not None


def _normalize_severity(value: str) -> str:
    return {
        "error": "high",
        "warning": "medium",
        "info": "info",
    }.get((value or "").lower(), "medium")


def _to_findings(payload: dict, repo_root: Path) -> list[Finding]:
    out: list[Finding] = []
    for row in payload.get("issues", []):
        skill_path = row.get("file", "")
        try:
            rel = str(Path(skill_path).resolve().relative_to(repo_root))
        except (ValueError, OSError):
            rel = skill_path
        out.append(
            Finding(
                source="agent-skill-evaluator",
                severity=_normalize_severity(row.get("level", "")),
                skill_path=rel,
                category=row.get("rule", "unspecified"),
                message=row.get("message", "")[:200],
                raw=json.dumps(row)[:500],
            )
        )
    return out


def _run_via_import(mod, skill_dirs: list[Path], repo_root: Path) -> WrapperResult:
    evaluate = getattr(mod, "evaluate_paths", None)
    if not callable(evaluate):
        return WrapperResult(
            tool="agent-skill-evaluator",
            status="skipped",
            findings=[],
            note="agent_skill_evaluator.evaluate_paths missing; binding drift",
        )
    try:
        raw = evaluate([str(d) for d in skill_dirs])
    except Exception as exc:  # noqa: BLE001 (vendor surface)
        return WrapperResult(
            tool="agent-skill-evaluator",
            status="error",
            findings=[],
            note=f"{type(exc).__name__}: {exc}",
        )
    payload: dict = raw if isinstance(raw, dict) else {}
    findings = _to_findings(payload, repo_root)
    return WrapperResult(
        tool="agent-skill-evaluator",
        status="findings" if findings else "ok",
        findings=findings,
    )


def _run_via_uvx(skill_dirs: list[Path], repo_root: Path) -> WrapperResult:
    cmd = ["uvx", "agent-skill-evaluator", "--format", "json"]
    cmd.extend(str(d) for d in skill_dirs)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return WrapperResult(
            tool="agent-skill-evaluator",
            status="error",
            findings=[],
            note=f"{type(exc).__name__}: {exc}",
        )
    if proc.returncode not in (0, 1):
        return WrapperResult(
            tool="agent-skill-evaluator",
            status="error",
            findings=[],
            note=f"exit={proc.returncode}: {proc.stderr.strip()[:200]}",
        )
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        return WrapperResult(
            tool="agent-skill-evaluator",
            status="error",
            findings=[],
            note=f"non-JSON stdout: {exc}",
        )
    findings = _to_findings(payload, repo_root)
    return WrapperResult(
        tool="agent-skill-evaluator",
        status="findings" if findings else "ok",
        findings=findings,
    )


def run(skill_dirs: list[Path], repo_root: Path) -> WrapperResult:
    if not skill_dirs:
        return WrapperResult(tool="agent-skill-evaluator", status="ok", findings=[])
    mod = _try_import()
    if mod is not None:
        return _run_via_import(mod, skill_dirs, repo_root)
    if _have_uvx():
        return _run_via_uvx(skill_dirs, repo_root)
    return WrapperResult(
        tool="agent-skill-evaluator",
        status="skipped",
        findings=[],
        note="neither `agent_skill_evaluator` import nor `uvx` available",
    )
