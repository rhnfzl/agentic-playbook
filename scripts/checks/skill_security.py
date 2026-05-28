"""Supply-chain security audit (delegates to scripts/audit_security.py)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main(
        "audit_security", summary="supply-chain security audit"
    )
