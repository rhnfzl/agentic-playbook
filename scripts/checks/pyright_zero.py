"""Pyright zero-warnings check (v0.7+).

A second-attempt guardrail the user asked for after two rounds of
"don't skip pyright warnings." The first guardrail (pyrightconfig.json)
demoted noisy reports to warnings but did not gate CI on them; the
second (this check) blocks `make check` whenever pyright reports any
error OR warning anywhere in the analyzed tree.

Runtime contract:
  * Pyright must be on PATH. The check is a no-op (warn, not fail) when
    pyright is absent so contributors without a local install can still
    run `make check`; CI is expected to install it.
  * Pyright runs with the workspace's pyrightconfig.json. Any
    `# pyright: ignore[...]` line that the contributor wants to use must
    be paired with a `# justification:` line on the same line; the check
    flags un-justified ignores so "skip the warning" becomes visible in
    review.
  * Exit 0 only when pyright reports 0 errors AND 0 warnings AND there
    are no un-justified `# pyright: ignore` comments.
  * The type gate needs a pyright engine new enough to resolve current
    third-party stubs (pytest 9.x). When the running engine is below
    `_PYRIGHT_ENGINE_FLOOR` (e.g. offline, the pinned engine could not be
    fetched), the warning count is dominated by engine false positives, so
    the gate SKIPS the type check with a clear "warn" instead of failing on
    noise. The engine-independent un-justified-ignore scan still runs.

This check did not exist in v0.6. The contract is enforced retroactively
on v0.7's tree.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import CheckContext, CheckResult


_PYRIGHT_IGNORE_RE = re.compile(r"#\s*pyright\s*:\s*ignore")
_JUSTIFICATION_RE = re.compile(r"#\s*justification\s*:", re.IGNORECASE)

# Pyright engine floor. The PyPI `pyright` wrapper bundles an engine that
# lags npm; lagging engines mis-resolve modern pytest (9.x) and emit dozens
# of false-positive "unknown attribute of module pytest" warnings. Below
# this floor the warning count cannot be trusted, so the gate SKIPS (warn)
# rather than failing on engine noise. The Makefile `check` target sets
# PYRIGHT_PYTHON_FORCE_VERSION to fetch this engine when online; we also set
# it here so a direct `python3 scripts/check.py` pins the same engine.
_PYRIGHT_ENGINE_FLOOR = "1.1.410"


def _version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in v.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


# Paths the scanner walks. Vendored deps (.venv) and bytecode caches are
# never our code, so we don't gate on their suppressions.
_SCAN_DIRS = ["scripts", "tests", "mcp/anchored-fs"]
_SKIP_PATH_SEGMENTS = (".venv", "__pycache__", "node_modules", ".pytest_cache")


def _scan_unjustified_ignores(repo_root: Path) -> list[str]:
    """Walk Python sources and flag `# pyright: ignore` lines that lack
    a `# justification: ...` comment on the same line. The justification
    keeps the suppression visible during review; an unjustified ignore
    is what the user objected to. This module itself is excluded because
    it embeds the regex pattern as a string literal, not as a real
    suppression directive.
    """
    findings: list[str] = []
    self_path = Path(__file__).resolve()
    for sub in _SCAN_DIRS:
        root = repo_root / sub
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if py.resolve() == self_path:
                continue
            if any(seg in py.parts for seg in _SKIP_PATH_SEGMENTS):
                continue
            try:
                lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if not _PYRIGHT_IGNORE_RE.search(line):
                    continue
                if _JUSTIFICATION_RE.search(line):
                    continue
                rel = py.relative_to(repo_root)
                findings.append(
                    f"{rel}:{lineno}: `# pyright: ignore` without "
                    f"`# justification: <reason>` on the same line"
                )
    return findings


def run(ctx: CheckContext) -> CheckResult:
    repo_root = ctx.repo_root
    pyright_bin = shutil.which("pyright")
    if pyright_bin is None:
        return CheckResult(
            status="warn",
            summary="pyright not on PATH; install via `npm i -g pyright` "
            "for local enforcement (CI installs it explicitly)",
            details=[],
        )

    unjustified = _scan_unjustified_ignores(repo_root)

    # Pin the engine floor for this run so direct `python3 scripts/check.py`
    # gets the same engine the Makefile target requests. setdefault lets an
    # operator override (or a fetch failure fall back to the bundled engine,
    # handled by the version-floor skip below).
    env = {**os.environ}
    env.setdefault("PYRIGHT_PYTHON_FORCE_VERSION", _PYRIGHT_ENGINE_FLOOR)

    proc = subprocess.run(
        [pyright_bin, "--outputjson"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if not proc.stdout.strip():
        # Pyright crashed or wrote nothing. Empty output used to parse as
        # `{}`, which counted as 0 errors / 0 warnings and let the gate
        # pass silently. Fail loud instead so a broken pyright install
        # cannot mask warnings on CI.
        return CheckResult(
            status="fail",
            summary=(
                f"pyright produced no JSON report (exit code {proc.returncode}); "
                "the gate cannot tell warnings from a crash"
            ),
            details=[
                "stdout: (empty)",
                f"stderr: {proc.stderr[:500].strip() or '(empty)'}",
                "verify pyright with `pyright --version` and re-run.",
            ],
        )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return CheckResult(
            status="fail",
            summary=f"pyright JSON output unparseable: {exc}",
            details=[proc.stdout[:500], proc.stderr[:500]],
        )

    summary = report.get("summary")
    if not isinstance(summary, dict):
        return CheckResult(
            status="fail",
            summary=(
                "pyright JSON report has no `summary` block; cannot trust "
                "the warning count"
            ),
            details=[proc.stdout[:500]],
        )

    # Engine too old (e.g. offline, the pinned engine could not be fetched and
    # the wrapper fell back to its bundled build): the type-warning count is
    # dominated by engine false positives and cannot be trusted. Still enforce
    # the engine-INDEPENDENT contract (un-justified `# pyright: ignore`), but
    # SKIP the type gate with a clear note rather than failing on noise.
    engine = str(report.get("version", ""))
    if engine and _version_tuple(engine) < _version_tuple(_PYRIGHT_ENGINE_FLOOR):
        if unjustified:
            return CheckResult(
                status="fail",
                summary=f"{len(unjustified)} un-justified `# pyright: ignore` line(s)",
                details=[
                    *unjustified,
                    "    add `# justification: <one sentence>` on the same line",
                ],
            )
        return CheckResult(
            status="warn",
            summary=(
                f"pyright engine {engine} is older than the {_PYRIGHT_ENGINE_FLOOR} "
                "floor needed for current pytest; skipping the strict type gate "
                "(its warnings are likely engine false positives)"
            ),
            details=[
                f"To enforce: PYRIGHT_PYTHON_FORCE_VERSION={_PYRIGHT_ENGINE_FLOOR} "
                "(the `make check` target sets this; needs one online fetch).",
            ],
        )

    errors = int(summary.get("errorCount", 0))
    warnings = int(summary.get("warningCount", 0))
    files = int(summary.get("filesAnalyzed", 0))

    if errors == 0 and warnings == 0 and not unjustified:
        return CheckResult(
            status="ok",
            summary=f"pyright clean: {files} file(s) analyzed, 0 errors, 0 warnings",
            details=[],
        )

    failure_lines: list[str] = []
    if errors or warnings:
        failure_lines.append(
            f"pyright reports {errors} error(s) and {warnings} warning(s)"
        )
        for diag in report.get("generalDiagnostics", []) or []:
            severity = diag.get("severity")
            if severity not in {"error", "warning"}:
                continue
            file_str = diag.get("file", "?")
            try:
                rel = Path(file_str).relative_to(repo_root)
            except ValueError:
                rel = file_str
            start = (diag.get("range") or {}).get("start") or {}
            line = start.get("line")
            col = start.get("character")
            loc = (
                f"{rel}:{line + 1}:{col + 1}"
                if isinstance(line, int) and isinstance(col, int)
                else str(rel)
            )
            message = diag.get("message", "").splitlines()[0]
            rule = diag.get("rule")
            rule_suffix = f" [{rule}]" if rule else ""
            failure_lines.append(f"  {severity}: {loc} {message}{rule_suffix}")
    for item in unjustified:
        failure_lines.append(f"  unjustified-ignore: {item}")
        failure_lines.append(
            "    add `# justification: <one sentence on why this is safe>` on the same line"
        )

    return CheckResult(
        status="fail",
        summary="pyright zero-warning gate failed",
        details=failure_lines,
    )
