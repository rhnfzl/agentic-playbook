#!/usr/bin/env python3
"""Supply-chain security aggregator (standalone CLI).

Runs three independent wrappers (mcp-scan, agent-skill-evaluator,
DDIPE) plus emits an AI-BOM. Soft-by-default per ADR-0047: missing
upstream tools degrade to a notice. `STRICT_SECURITY=1` flips
skipped wrappers to errors.

This script is invoked both:
  * Directly by `make audit-security`
  * Wrapped as a check by `scripts/checks/skill_security.py`

Exit codes:
  0  no findings at >= medium severity, no strict skips
  1  blocking findings or strict-mode skips
  2  AI-BOM IO error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from security import Finding, SEVERITY_ORDER, WrapperResult, is_strict
from security import agent_skill_evaluator_wrapper, ai_bom
from security import ddipe_detector, mcp_scan_wrapper


def _gather_skill_dirs(repo_root: Path) -> list[Path]:
    imported = repo_root / "base" / "skills" / "imported"
    if not imported.is_dir():
        return []
    return sorted(p.parent for p in imported.rglob("SKILL.md"))


def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        return
    findings_sorted = sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.skill_path),
    )
    for f in findings_sorted:
        prefix = {
            "critical": "X",
            "high": "X",
            "medium": "!",
            "low": ".",
            "info": ".",
        }.get(f.severity, "?")
        print(
            f"  {prefix}  [{f.severity}] {f.source}: {f.skill_path}: "
            f"{f.category}: {f.message}"
        )


def _summary_line(results: list[WrapperResult], findings: list[Finding]) -> str:
    by_status: dict[str, list[str]] = {}
    for r in results:
        by_status.setdefault(r.status, []).append(r.tool)
    by_sev: dict[str, int] = {}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    parts: list[str] = []
    for status in ("ok", "findings", "skipped", "error"):
        if status in by_status:
            parts.append(f"{status}={','.join(by_status[status])}")
    if by_sev:
        sev_str = " ".join(f"{k}={v}" for k, v in by_sev.items())
        parts.append(f"severities[{sev_str}]")
    return " ".join(parts) or "no wrappers ran"


def run_security_audit(repo_root: Path) -> int:
    skill_dirs = _gather_skill_dirs(repo_root)

    results: list[WrapperResult] = []
    results.append(mcp_scan_wrapper.run(skill_dirs, repo_root))
    results.append(agent_skill_evaluator_wrapper.run(skill_dirs, repo_root))

    ddipe_findings = ddipe_detector.scan_skill_dirs(skill_dirs, repo_root)
    results.append(
        WrapperResult(
            tool="ddipe",
            status="findings" if ddipe_findings else "ok",
            findings=ddipe_findings,
        )
    )

    try:
        rc = ai_bom.main(["--repo-root", str(repo_root)])
    except Exception as exc:  # noqa: BLE001 (surface IO errors)
        print(f"  X  AI-BOM emission failed: {type(exc).__name__}: {exc}")
        return 2
    if rc != 0:
        return rc

    all_findings: list[Finding] = []
    for r in results:
        all_findings.extend(r.findings)
        if r.status == "skipped":
            print(f"  .  {r.tool}: skipped ({r.note})")
        elif r.status == "error":
            print(f"  X  {r.tool}: error ({r.note})")

    _print_findings(all_findings)

    print(f"\nSecurity audit: {_summary_line(results, all_findings)}")

    strict = is_strict()
    skipped_count = sum(1 for r in results if r.status == "skipped")
    error_results = [r for r in results if r.status == "error"]
    blocking_findings = [
        f
        for f in all_findings
        if SEVERITY_ORDER.get(f.severity, 99) <= SEVERITY_ORDER["medium"]
    ]

    if blocking_findings:
        return 1
    if error_results:
        # ADR-0047: a wrapper exiting unexpectedly is a gate failure, not
        # a soft-skip. We do not know what the wrapper would have flagged,
        # so we cannot let the build through.
        print(
            f"  {len(error_results)} wrapper(s) errored unexpectedly; "
            "ADR-0047 treats this as a blocking failure"
        )
        return 1
    if strict and skipped_count > 0:
        print(
            f"  STRICT_SECURITY=1: {skipped_count} wrapper(s) skipped, treating as failure"
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate supply-chain security wrappers (mcp-scan, "
            "agent-skill-evaluator, DDIPE) and emit an AI-BOM. "
            "Soft-by-default; STRICT_SECURITY=1 escalates skipped "
            "wrappers to errors. See ADR-0047."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="defaults to the parent of this script (the playbook checkout)",
    )
    args = parser.parse_args(argv)
    return run_security_audit(args.repo_root.resolve())


if __name__ == "__main__":
    sys.exit(main())
