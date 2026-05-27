#!/usr/bin/env python3
"""docs-index CLI: regenerate DOCS_INDEX.md from frontmatter."""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent / "_shared"
sys.path.insert(0, str(_SHARED))

from docs_lifecycle.scan import scan_tree  # noqa: E402
from docs_lifecycle.types import DocEntry, DocType  # noqa: E402


def _first_diff_line(a: str, b: str) -> int | None:
    """Return the 1-indexed line number where a and b first differ, or None if identical."""
    for i, (line_a, line_b) in enumerate(
        zip(a.splitlines(keepends=True), b.splitlines(keepends=True)), start=1
    ):
        if line_a != line_b:
            return i
    # If we got here, one is a prefix of the other.
    if a != b:
        shorter = min(len(a.splitlines()), len(b.splitlines()))
        return shorter + 1
    return None


GROUP_ORDER = [
    DocType.PERMANENT,
    DocType.REFERENCE,
    DocType.TRANSIENT,
    DocType.DESIGN_SPEC,
    DocType.DESIGN_DRAFT,
    DocType.REPORT_SNAPSHOT,
    DocType.MEETING,
]

GROUP_TITLES = {
    DocType.PERMANENT: "Permanent (architecture)",
    DocType.REFERENCE: "Reference (living)",
    DocType.TRANSIENT: "Transient (active tickets)",
    DocType.DESIGN_SPEC: "Design Specs",
    DocType.DESIGN_DRAFT: "Design Drafts",
    DocType.REPORT_SNAPSHOT: "Report Snapshots",
    DocType.MEETING: "Meetings",
}


# v0.12: subproject mapping moved out of the script body into an optional
# per-workspace config file. The script no longer hardcodes any workspace-
# specific subproject names; each workspace provides its own mapping via
# `.docs-index.toml`. If no config is found, every doc is grouped under a
# single "workspace" subproject (the prior fallback behavior).
#
# Config schema:
#
#     # .docs-index.toml at the workspace root
#     [subprojects]
#     "frontend/" = "frontend"
#     "api-service/" = "api"
#
# Keys are path prefixes; values are the subproject display name used in
# the DOCS_INDEX.md grouping. The script falls back to "workspace" for any
# path not matched by a prefix.


def _load_subproject_map(root: Path) -> dict[str, str]:
    """Load `[subprojects]` mapping from `<root>/.docs-index.toml`.

    Returns an empty dict if the config file is absent, malformed, or
    lacks a `[subprojects]` table. Empty dict means "all paths group
    under 'workspace'", which matches the pre-config fallback.
    """
    config_path = root / ".docs-index.toml"
    if not config_path.is_file():
        return {}
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return {}
    raw = data.get("subprojects", {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(prefix): str(name)
        for prefix, name in raw.items()
        if isinstance(prefix, str) and isinstance(name, str)
    }


def _subproject(path: str, mapping: dict[str, str]) -> str:
    """Map `path` to a subproject display name via the workspace config."""
    for prefix, name in mapping.items():
        if path.startswith(prefix):
            return name
    return "workspace"


def render(entries: list[DocEntry], subproject_map: dict[str, str]) -> str:
    lines = ["# Docs Index", ""]
    lines.append(f"Generated from {len(entries)} frontmattered files.")
    lines.append("")
    for group in GROUP_ORDER:
        bucket = [e for e in entries if e.type is group]
        if not bucket:
            continue
        lines.append(f"## {GROUP_TITLES[group]}")
        by_sub: dict[str, list[DocEntry]] = {}
        for e in bucket:
            by_sub.setdefault(_subproject(e.path, subproject_map), []).append(e)
        for subproj in sorted(by_sub):
            lines.append(f"### {subproj}")
            items = sorted(
                by_sub[subproj],
                key=lambda e: e.last_reviewed,
                reverse=True,
            )
            for e in items:
                stale = " STALE" if e.status.value == "superseded" else ""
                lines.append(
                    f"- **[{e.summary}]({e.path})** · tags: {', '.join(e.tags) or '-'} "
                    f"· reviewed {e.last_reviewed.isoformat()}{stale}"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not args.root.is_dir():
        print(f"error: --root is not a directory: {args.root}", file=sys.stderr)
        return 2

    result = scan_tree(args.root)
    subproject_map = _load_subproject_map(args.root)
    generated = render(result.entries, subproject_map)
    index_path = args.root / "DOCS_INDEX.md"

    if args.check:
        try:
            current = (
                index_path.read_text(encoding="utf-8") if index_path.exists() else ""
            )
        except OSError as exc:
            print(f"error: cannot read {index_path}: {exc}", file=sys.stderr)
            return 3
        if current != generated:
            print(f"DOCS_INDEX.md is stale at {index_path}")
            diff_line = _first_diff_line(current, generated)
            if diff_line is not None:
                print(f"  first divergence at line {diff_line}")
            return 1
        print("DOCS_INDEX.md is up to date.")
        return 0

    try:
        index_path.write_text(generated, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {index_path}: {exc}", file=sys.stderr)
        return 3
    print(f"wrote {index_path} ({len(result.entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
