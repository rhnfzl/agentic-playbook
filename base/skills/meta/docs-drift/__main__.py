#!/usr/bin/env python3
"""docs-drift CLI: report documentation-lifecycle non-conformance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the shared package importable without installing it repo-wide.
_SHARED = Path(__file__).resolve().parent.parent / "_shared"
sys.path.insert(0, str(_SHARED))

from docs_lifecycle.path_rules import expected_type_for_path  # noqa: E402
from docs_lifecycle.scan import scan_tree  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Documentation drift report.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--fix-interactive", action="store_true")
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: --root is not a directory: {args.root}", file=sys.stderr)
        return 2

    result = scan_tree(args.root)

    mismatches: list[tuple[str, str, str]] = []
    for entry in result.entries:
        expected = expected_type_for_path(entry.path)
        if expected is not None and entry.type is not expected:
            mismatches.append((entry.path, entry.type.value, expected.value))

    print(f"== docs-drift report for {args.root} ==")
    print(f"scanned entries: {len(result.entries)}")
    print(f"missing frontmatter: {len(result.missing_frontmatter)}")
    for path in result.missing_frontmatter:
        print(f"  - {path}")
    print(f"parse errors: {len(result.parse_errors)}")
    for err in result.parse_errors:
        print(f"  - {err.path}: {err.reason}")
    print(f"read errors: {len(result.read_errors)}")
    for err in result.read_errors:
        print(f"  - {err.path}: {err.reason}")
    print(f"type mismatch: {len(mismatches)}")
    for path, actual, expected in mismatches:
        print(f"  - {path}: declared={actual} expected={expected}")

    if args.fix_interactive:
        print("\n--fix-interactive is stub in v0.1; use manual edits for now.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
