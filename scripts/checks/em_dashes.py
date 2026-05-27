"""Em-dash lint (delegates to scripts/check_em_dashes.py via run_legacy_main)."""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main("check_em_dashes", summary="em-dash lint")
