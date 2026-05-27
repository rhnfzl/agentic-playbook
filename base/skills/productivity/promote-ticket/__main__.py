#!/usr/bin/env python3
"""promote-ticket v0.1: locate transient docs, prompt user for distillation."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent / "_shared"
sys.path.insert(0, str(_SHARED))

from docs_lifecycle.changelog import append_changelog_entry  # noqa: E402
from docs_lifecycle.frontmatter import FrontmatterError, parse_frontmatter  # noqa: E402


def find_transients(root: Path, ticket_id: str) -> list[Path]:
    matches: list[Path] = []
    for md in root.rglob("*.md"):
        rel = md.relative_to(root).as_posix()
        if "/tickets/active/" not in rel and not rel.startswith("tickets/active/"):
            continue
        if not rel.split("/")[-1].startswith(f"{ticket_id}-"):
            continue
        matches.append(md)
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticket_id")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--delete",
        action="store_true",
        help="After manual distillation, delete the transient doc.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip the interactive confirmation (for non-TTY agent use).",
    )
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: --root is not a directory: {args.root}", file=sys.stderr)
        return 2

    transients = find_transients(args.root, args.ticket_id)
    if not transients:
        print(f"No transient docs found for ticket {args.ticket_id}.")
        return 0

    print(f"Found {len(transients)} transient doc(s) for {args.ticket_id}:")
    for path in transients:
        rel = path.relative_to(args.root)
        print(f"  - {rel}")
        try:
            entry, _ = parse_frontmatter(str(rel), path.read_text(encoding="utf-8"))
            print(f"      summary: {entry.summary}")
        except FrontmatterError as exc:
            print(f"      [warn] frontmatter error: {exc}")

    if not args.delete:
        print()
        print(
            "v0.1: distill manually into the relevant subproject's docs/architecture/"
        )
        print(
            "or docs/references/, then re-run with --delete to remove the transient(s)."
        )
        return 0

    if args.yes:
        answer = "yes"
    else:
        try:
            answer = input(
                "Confirm ticket is closed and distillation is complete? (yes/NO): "
            )
        except EOFError:
            print(
                "error: no TTY and --yes not provided; refusing to delete.",
                file=sys.stderr,
            )
            return 2
    if answer.strip().lower() != "yes":
        print("Aborted.")
        return 1

    deleted: list[Path] = []
    for path in transients:
        try:
            path.unlink()
        except OSError as exc:
            print(
                f"  [warn] could not delete {path.relative_to(args.root)}: {exc}",
                file=sys.stderr,
            )
            continue
        deleted.append(path)
        print(f"  deleted {path.relative_to(args.root)}")

    if deleted:
        append_changelog_entry(
            args.root / "CHANGELOG.md",
            author="promote-ticket",
            on=date.today(),
            lines=[
                f"promoted and deleted {args.ticket_id} transient doc(s): "
                + ", ".join(str(p.relative_to(args.root)) for p in deleted),
            ],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
