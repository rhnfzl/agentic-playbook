"""Detect duplicate ADR numbers in docs/adr/.

ADRs use a 4-digit prefix (0001, 0002, ...). A duplicate prefix means an
author picked a number without checking the existing list, usually because
an `ls docs/adr/ | head -N` was truncated. The collision can persist for
months because no existing check looks for it, and the failure modes
(broken cross-references, brittle parsing of "the latest ADR") surface
far from the cause.

This check fails when any 4-digit prefix appears in more than one file
under docs/adr/. The check is cheap (one directory walk + one dict).

The check accepts the pattern `<4digits>-<slug>.md`; non-conforming files
(README.md, .gitkeep, drafts under a `wip/` subdirectory) are ignored.
"""

from __future__ import annotations

from collections import defaultdict

from . import CheckContext, CheckResult


name = "adr-number-unique"


def run(ctx: CheckContext) -> CheckResult:
    adr_dir = ctx.repo_root / "docs" / "adr"
    if not adr_dir.is_dir():
        return CheckResult(
            status="ok",
            summary="no docs/adr/ directory",
            details=[],
        )

    by_number: dict[str, list[str]] = defaultdict(list)
    scanned = 0
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        scanned += 1
        number = path.name[:4]
        by_number[number].append(path.name)

    duplicates = {n: files for n, files in by_number.items() if len(files) > 1}
    if duplicates:
        details = [
            f"{number}: {', '.join(sorted(files))}"
            for number, files in sorted(duplicates.items())
        ]
        return CheckResult(
            status="fail",
            summary=(
                f"{len(duplicates)} duplicate ADR number(s) across "
                f"{scanned} ADR(s)"
            ),
            details=details,
        )

    return CheckResult(
        status="ok",
        summary=f"ADR numbers unique across {scanned} ADR(s)",
        details=[],
    )
