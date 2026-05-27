"""No-playbook-version-in-READMEs check.

Delegates to scripts/check_no_versions_in_readmes.py.
"""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main(
        "check_no_versions_in_readmes",
        summary="no playbook-version markers in READMEs",
    )
