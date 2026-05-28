"""Skill supply-chain security subsystem.

Three external-tool wrappers and one AI-BOM emitter feed a single
aggregator (`scripts/checks/skill_security.py`). Each wrapper returns
`Finding` records or marks itself `skipped` when the underlying tool
is not installed.

Soft-by-default: missing wrappers degrade to a notice, not a CI break.
`STRICT_SECURITY=1` escalates skipped wrappers to errors so a release
branch can gate on full coverage.
"""

from __future__ import annotations

import os
from typing import NamedTuple


class Finding(NamedTuple):
    """Single security finding, one row in the aggregated report."""

    source: str          # "mcp-scan", "agent-skill-evaluator", "ddipe", "pattern-audit"
    severity: str        # "critical" | "high" | "medium" | "low" | "info"
    skill_path: str      # e.g. "base/skills/imported/mattpocock/foo"
    category: str        # short machine-readable label
    message: str         # one-line human-readable description
    raw: str = ""        # tool stdout excerpt for traceability


class WrapperResult(NamedTuple):
    """What every wrapper returns."""

    tool: str
    status: str          # "ok" | "findings" | "skipped" | "error"
    findings: list[Finding]
    note: str = ""       # why skipped, or stderr excerpt on error


def is_strict() -> bool:
    return os.environ.get("STRICT_SECURITY", "").lower() in {"1", "true", "yes", "on"}


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
