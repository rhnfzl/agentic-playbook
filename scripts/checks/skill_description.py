"""SKILL.md description <= 1024 char check.

Delegates to scripts/check_skill_description.py. Codex rejects skills
whose frontmatter description exceeds 1024 chars; the same constraint is
assumed for any Tier 1/2/3 tool that round-trips skill metadata through
the same schema.
"""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main(
        "check_skill_description",
        summary="SKILL.md description length cap (Codex 1024-char limit)",
    )
