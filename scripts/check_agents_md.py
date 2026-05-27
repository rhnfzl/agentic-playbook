#!/usr/bin/env python3
"""
AGENTS.md governance harness.

Enforces v0.3 contract from docs/adr/0013-agents-md-governance.md (when written)
and the locked decisions from the v0.3 plan artifact. Blocking checks fail with
exit code 1; warnings print but exit 0.

Checks:
  - Coverage: every first-class top-level dir has AGENTS.md
  - Subtree: dirs with package markers (pyproject.toml / Makefile / Dockerfile /
    SKILL.md / package.json) warn if no nearby AGENTS.md
  - Length: root target 80-140, warn >200, BLOCK >300
            sub  target 25-80,  warn >120, BLOCK >180
  - Required sections (sub-AGENTS.md only): 8 headings present, even if body
    of a section is "None"
  - Locality: sub-AGENTS.md must not have >40% line-overlap with root
  - Freshness: 90d for active code dirs, 180d for docs/template dirs
  - Conflict control: direct contradictions between root and sub flagged unless
    sub has a <!-- conflict-with-root: justified --> marker

.agents-md-ignore at repo root lists relative paths to skip (one per line).
v0.3 ships this file EMPTY (the locked decision: full coverage authored).
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

# Locked thresholds from v0.3 plan
ROOT_LEN_WARN = 200
ROOT_LEN_BLOCK = 300
SUB_LEN_WARN = 120
SUB_LEN_BLOCK = 180
LOCALITY_OVERLAP_PCT = 40
FRESHNESS_ACTIVE_DAYS = 90
FRESHNESS_DOCS_DAYS = 180

REQUIRED_SECTIONS = [
    "Purpose",
    "What Lives Here",
    "Local Commands",
    "Edit Rules",
    "Required Checks",
    "Required Skills",
    "Do Not",
    "Owner",  # tolerant: "Owner And Freshness" or "Owner" both match
]

# Content types that live under base/ and overlays/<name>/ per ADR-0040.
# Order is the canonical content-type ordering used across the playbook.
CONTENT_TYPES = [
    "agents",
    "commands",
    "hooks",
    "mcp",
    "prompts",
    "rules",
    "skills",
]

# Dirs that must carry AGENTS.md regardless of scope (these stay at the
# repo root through the base/overlay split).
AT_ROOT_DIRS = ["docs", "profiles", "scripts"]


def get_first_class_dirs(repo_root: Path) -> list[str]:
    """Discover the first-class dirs that MUST carry AGENTS.md.

    v0.12 (post-v0.11): replaces the hand-maintained dual-prefix list
    (which carried both 'rules' and 'base/rules' through the v0.11
    migration window) with a layout-driven discovery. The function walks
    repo_root's content-root layout per ADR-0040:

      - AT_ROOT_DIRS unconditionally (docs / profiles / scripts).
      - `base/<content_type>` for every CONTENT_TYPES entry that exists.

    Overlays (`overlays/<name>/<type>/`) are NOT first-class dirs for
    governance: each overlay layers on top of base, so the base/<type>/
    AGENTS.md is the authoritative governance point. Overlays inherit
    that policy. This matches the pre-v0.11 behavior (the original list
    enumerated only base/<type>/ via the old root paths). Future-proof
    against another overlay by treating overlay AGENTS.md as opt-in
    (still picked up by the broader AGENTS.md walk for length /
    freshness / sections / locality if present).

    Result: adding a new content type or removing a stale pre-v0.11 path
    no longer requires editing this list. The is_dir() filter at the
    call site (main()) still skips missing dirs.
    """
    dirs = list(AT_ROOT_DIRS)

    base_dir = repo_root / "base"
    if not base_dir.is_dir():
        return dirs

    for content_type in CONTENT_TYPES:
        if (base_dir / content_type).is_dir():
            dirs.append(f"base/{content_type}")

    return dirs

# Dir name segments treated as "docs / template" for freshness purposes
# (180d budget). v0.12: match by ANY part of the path so post-v0.11 nested
# paths like `base/prompts/AGENTS.md` still classify correctly.
DOCS_LIKE = {"docs", "prompts", "profiles"}

PACKAGE_MARKERS = {
    "pyproject.toml",
    "package.json",
    "Makefile",
    "Dockerfile",
    "SKILL.md",
}

# Conflict-control: simple keyword pairs we flag when present in both root and sub
# with contradictory values. Heuristic; sub can override with marker.
CONFLICT_PATTERNS = [
    (
        re.compile(r"no\s+em[\s\-]?dash", re.I),
        re.compile(r"em[\s\-]?dash\s+(ok|allowed|permitted)", re.I),
    ),
    (
        re.compile(r"never push to develop", re.I),
        re.compile(r"push to develop\s+(ok|allowed)", re.I),
    ),
    (
        re.compile(r"VCS(?:\s+not\s+github)?", re.I),
        re.compile(r"use\s+gh\s+cli\s+for\s+team", re.I),
    ),
]

CONFLICT_MARKER = "conflict-with-root: justified"


def load_ignore(repo_root: Path) -> set[str]:
    ignore = repo_root / ".agents-md-ignore"
    if not ignore.exists():
        return set()
    return {
        line.strip()
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def find_agents_md_files(repo_root: Path) -> list[Path]:
    found = []
    for path in repo_root.rglob("AGENTS.md"):
        rel = path.relative_to(repo_root)
        parts = rel.parts
        if any(
            p.startswith(".") or p in {"node_modules", ".venv", "__pycache__"}
            for p in parts
        ):
            continue
        found.append(path)
    return sorted(found)


def parse_freshness(text: str) -> date | None:
    m = re.search(r"last[_\s]reviewed[:\s]+(\d{4}-\d{2}-\d{2})", text, re.I)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def section_headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+)$", text, re.M)]


def line_overlap_pct(a_lines: list[str], b_lines: list[str]) -> int:
    a_set = {
        line.strip() for line in a_lines if line.strip() and not line.startswith("#")
    }
    b_set = {
        line.strip() for line in b_lines if line.strip() and not line.startswith("#")
    }
    if not b_set:
        return 0
    overlap = a_set & b_set
    return int(100 * len(overlap) / len(b_set))


def detect_conflicts(root_text: str, sub_text: str) -> list[str]:
    if CONFLICT_MARKER in sub_text:
        return []
    conflicts = []
    for root_pat, sub_pat in CONFLICT_PATTERNS:
        if root_pat.search(root_text) and sub_pat.search(sub_text):
            conflicts.append(f"sub contradicts root on: {root_pat.pattern}")
    return conflicts


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    ignore = load_ignore(repo_root)

    errors: list[str] = []
    warnings: list[str] = []

    # Coverage check
    for d in get_first_class_dirs(repo_root):
        if d in ignore:
            continue
        target = repo_root / d
        if not target.is_dir():
            continue
        agents_md = target / "AGENTS.md"
        if not agents_md.exists():
            errors.append(f"COVERAGE: {d}/ missing AGENTS.md")

    # Root file
    root_md = repo_root / "AGENTS.md"
    root_text = root_md.read_text(encoding="utf-8") if root_md.exists() else ""
    if not root_text:
        errors.append("COVERAGE: root AGENTS.md missing")

    root_lines = root_text.splitlines()
    root_len = len(root_lines)
    if root_len > ROOT_LEN_BLOCK:
        errors.append(
            f"LENGTH: root AGENTS.md is {root_len} lines (BLOCK >{ROOT_LEN_BLOCK})"
        )
    elif root_len > ROOT_LEN_WARN:
        warnings.append(
            f"LENGTH: root AGENTS.md is {root_len} lines (warn >{ROOT_LEN_WARN})"
        )

    # All AGENTS.md files (root + nested) get section + freshness + size + locality + conflict checks
    for path in find_agents_md_files(repo_root):
        rel = path.relative_to(repo_root)
        rel_str = str(rel)
        if rel_str in ignore:
            continue

        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        is_root = path == root_md
        is_docs_like = any(part in DOCS_LIKE for part in rel.parts)

        # Length (sub only)
        if not is_root:
            n = len(lines)
            if n > SUB_LEN_BLOCK:
                errors.append(f"LENGTH: {rel} is {n} lines (BLOCK >{SUB_LEN_BLOCK})")
            elif n > SUB_LEN_WARN:
                warnings.append(f"LENGTH: {rel} is {n} lines (warn >{SUB_LEN_WARN})")

        # Required sections (sub only)
        if not is_root:
            headings = section_headings(text)
            heading_blob = " | ".join(headings).lower()
            missing = [s for s in REQUIRED_SECTIONS if s.lower() not in heading_blob]
            if missing:
                errors.append(
                    f"SECTIONS: {rel} missing required headings: {', '.join(missing)}"
                )

        # Locality (sub only)
        if not is_root and root_text:
            pct = line_overlap_pct(root_lines, lines)
            if pct > LOCALITY_OVERLAP_PCT:
                errors.append(
                    f"LOCALITY: {rel} has {pct}% line-overlap with root (>{LOCALITY_OVERLAP_PCT}%)"
                )

        # Freshness
        last = parse_freshness(text)
        budget = FRESHNESS_DOCS_DAYS if is_docs_like else FRESHNESS_ACTIVE_DAYS
        if last is None:
            errors.append(f"FRESHNESS: {rel} missing last_reviewed line")
        else:
            age = (date.today() - last).days
            if age > budget:
                errors.append(
                    f"FRESHNESS: {rel} last_reviewed {age}d ago (budget {budget}d)"
                )

        # Conflict control (sub only)
        if not is_root and root_text:
            for conflict in detect_conflicts(root_text, text):
                errors.append(f"CONFLICT: {rel}: {conflict}")

    # Subtree coverage hint (warn-only)
    for marker in PACKAGE_MARKERS:
        for marker_path in repo_root.rglob(marker):
            rel = marker_path.relative_to(repo_root)
            if any(
                p.startswith(".") or p in {"node_modules", ".venv", "__pycache__"}
                for p in rel.parts
            ):
                continue
            dir_path = marker_path.parent
            nearby = dir_path / "AGENTS.md"
            walk = dir_path
            while walk != repo_root and not (walk / "AGENTS.md").exists():
                walk = walk.parent
            if not nearby.exists() and walk == repo_root:
                # No AGENTS.md anywhere between marker and root
                warnings.append(f"SUBTREE: {rel} has no nearby AGENTS.md (warn)")

    # Output
    if warnings:
        print(f"\nAGENTS.md governance: {len(warnings)} warning(s)")
        for w in warnings:
            print(f"  !  {w}")

    if errors:
        print(f"\nAGENTS.md governance: {len(errors)} error(s)")
        for e in errors:
            print(f"  x  {e}")
        return 1

    print(
        f"  ok  AGENTS.md governance passed ({len(find_agents_md_files(repo_root))} files checked)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
