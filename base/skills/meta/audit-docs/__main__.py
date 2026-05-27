#!/usr/bin/env python3
"""audit-docs CLI: quarterly staleness sweep."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent / "_shared"
sys.path.insert(0, str(_SHARED))

from docs_lifecycle.frontmatter import emit_frontmatter  # noqa: E402
from docs_lifecycle.scan import scan_tree  # noqa: E402
from docs_lifecycle.types import (  # noqa: E402
    Audience,
    DocEntry,
    DocStatus,
    DocType,
    ReviewCadence,
)


STALE_DAYS = 90  # default / on-code-change threshold
SUPERSEDED_DAYS = 365
CADENCE_STALE_THRESHOLD: dict[ReviewCadence, int | None] = {
    ReviewCadence.NEVER: None,  # never flags as stale
    ReviewCadence.ON_CODE_CHANGE: STALE_DAYS,  # 90 days
    ReviewCadence.QUARTERLY: 100,  # quarter + ~10d slack
    ReviewCadence.ON_TICKET_CLOSE: None,  # flagged via needs_promote, not stale
}


def run_audit(root: Path, today: date | None = None) -> tuple[str, Path]:
    today = today or date.today()
    result = scan_tree(root)

    stale = []
    archive_candidates = []
    needs_promote = []
    for e in result.entries:
        age = (today - e.last_reviewed).days
        threshold = CADENCE_STALE_THRESHOLD.get(e.review_cadence)
        if threshold is not None and age > threshold:
            stale.append(e)
        if e.status is DocStatus.SUPERSEDED and age > SUPERSEDED_DAYS:
            archive_candidates.append(e)
        if (
            e.type is DocType.TRANSIENT
            and e.delete_after == "ticket-closed"
            and age
            > STALE_DAYS  # only flag if also stale - prevents re-listing every transient forever
        ):
            needs_promote.append(e)

    lines = [
        f"# Docs Audit - {today.isoformat()}",
        "",
        f"Scanned {len(result.entries)} entries. Thresholds: stale > {STALE_DAYS} days, superseded > {SUPERSEDED_DAYS} days.",
        "",
        f"## Stale ({len(stale)})",
        *[f"- {e.path} (last_reviewed={e.last_reviewed})" for e in stale],
        "",
        f"## Superseded > 12 months ({len(archive_candidates)})",
        *[f"- {e.path}" for e in archive_candidates],
        "",
        f"## Transient - ticket-status check needed ({len(needs_promote)})",
        *[f"- {e.path} (jira={e.jira})" for e in needs_promote],
        "",
    ]
    body = "\n".join(lines) + "\n"

    out_path = root / "docs" / "reports" / "snapshots" / f"audit_{today.isoformat()}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    entry = DocEntry(
        path=str(out_path.relative_to(root)),
        type=DocType.REPORT_SNAPSHOT,
        status=DocStatus.FROZEN,
        jira=None,
        owner=f"{os.environ.get('USER', 'unknown')}@audit-docs",
        last_reviewed=today,
        review_cadence=ReviewCadence.NEVER,
        supersedes=None,
        delete_after=None,
        tags=["audit", "docs-lifecycle"],
        audience=Audience.BOTH,
        summary=f"Quarterly docs audit for {today.isoformat()}",
    )
    out_path.write_text(emit_frontmatter(entry) + "\n" + body, encoding="utf-8")
    return (body, out_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: --root is not a directory: {args.root}", file=sys.stderr)
        return 2

    try:
        _body, out = run_audit(args.root)
    except OSError as exc:
        print(f"error: audit report write failed: {exc}", file=sys.stderr)
        return 3
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
