"""Hook metadata header check (delegates to scripts/check_hook_metadata.py).

Per ADR-0029: every hook ships PLAYBOOK-HOOK-EVENT and PLAYBOOK-HOOK-MATCHER
headers so the installer can register it across Claude / Codex / Cursor /
Cline / Copilot consistently. This check fails fast if a hook lacks either
header.
"""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main(
        "check_hook_metadata",
        summary="hook metadata headers (PLAYBOOK-HOOK-EVENT / PLAYBOOK-HOOK-MATCHER)",
    )
