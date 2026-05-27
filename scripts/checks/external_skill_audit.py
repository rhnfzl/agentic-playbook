"""External skill security audit (delegates to scripts/audit_external_skill.py)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main(
        "audit_external_skill", summary="external skill audit"
    )
