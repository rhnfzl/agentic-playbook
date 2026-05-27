#!/usr/bin/env python3
"""
Block playbook-version references in README.md and AGENTS.md files.

READMEs explain HOW to use a thing; they should NOT name which playbook
release a feature landed in. That belongs in CHANGELOG.md and ADRs.

Patterns flagged:
  - Bare version markers in prose: v0.2 / v0.3.0 / v1.x / v0.x
  - "NEW in v...", "added in v...", "introduced in v...", "removed in v..."
  - "Counts (v0.X)" or "Counts (v1.X)" section headers
  - "per Q<num> lock", "Codex P<num>", "Codex PR #<num>", "Cursor audit",
    "v0.2 review" review-ticket scars

Exemptions:
  - Skip files under skills/imported/ and mcp/anchored-fs/ (vendored).
  - Skip CHANGELOG.md, RELEASING.md, VERSION (version-bearing by purpose).
  - Skip docs/adr/ (ADRs are historical artifacts; version mention is fine).
  - Skip lines that name a file with a version segment (e.g. `research-brief-v1.md`),
    those are filename references, not playbook version refs.
  - Skip third-party tool version mentions detected by adjacent vendor name
    (Apache 2.0, Python 3.11, MIT, BSD-, GPL-, March 2026 forum dates).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_NAMES = {"README.md", "AGENTS.md"}

SKIP_PATH_PREFIXES = (
    "skills/imported/",
    "mcp/anchored-fs/",
    "base/skills/imported/",
    "base/mcp/anchored-fs/",
)

SKIP_FILE_NAMES = {
    "CHANGELOG.md",
    "RELEASING.md",
    "VERSION",
}

# Lines that mention a playbook version. Most aggressive: bare "v0.x" / "v1.x".
VERSION_PATTERNS = [
    re.compile(r"\bv\d+\.\d+(?:\.\d+)?\b"),
    re.compile(r"\bv\d+\.x\b", re.I),
]

# Review-tag scars (per Codex P1 fix, per Q13 lock, Cursor audit b6, etc.).
TAG_PATTERNS = [
    re.compile(r"\bper Q\d+\s+(?:lock|fix)", re.I),
    re.compile(r"\bCodex P\d+\b"),
    re.compile(r"\bCodex PR #?\d+\b"),
    re.compile(r"\bCursor audit\b", re.I),
    re.compile(r"\b(?:NEW|added|introduced|removed|fixed)\s+in\s+v\d", re.I),
    re.compile(r"\bsince v\d", re.I),
    re.compile(r"^##\s*Counts\s*\(v", re.M),
]

# Allowlist: skip the line if it looks like a filename reference (`-v1.md` etc.)
# or a third-party tool version that does NOT refer to our playbook.
FILENAME_VERSION = re.compile(r"-v\d+(?:\.\d+)*\.(?:md|json|toml|py|sh|yaml|yml|txt)\b")
THIRD_PARTY_VERSION_CONTEXT = re.compile(
    r"\b(?:Apache|Python|MIT|BSD|GPL|LGPL|MPL|Node|Java|Go|TypeScript|JavaScript|"
    r"Ruby|Rust|FastMCP|antirez|DwarfStar|Pyright|TOML|YAML|"
    r"VS Code|Cursor|Windsurf|Codex|Claude|Pi|JetBrains|"
    r"March \d{4}|April \d{4}|May \d{4}|June \d{4}|July \d{4}|"
    r"August \d{4}|September \d{4}|October \d{4}|November \d{4}|December \d{4}|"
    r"January \d{4}|February \d{4})",
    re.I,
)


def line_is_allowlisted(line: str) -> bool:
    """True if the line should not be flagged even if a version pattern matches."""
    # Filename references like `research-brief-v1.md`
    if FILENAME_VERSION.search(line):
        return True
    # Third-party tool versions adjacent in the same line
    if THIRD_PARTY_VERSION_CONTEXT.search(line):
        return True
    return False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return list of (line_num, pattern_label, line) violations."""
    issues: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues
    for line_num, line in enumerate(text.splitlines(), start=1):
        if line_is_allowlisted(line):
            continue
        for pat in VERSION_PATTERNS:
            if pat.search(line):
                issues.append((line_num, "version-marker", line.strip()))
                break
        for pat in TAG_PATTERNS:
            if pat.search(line):
                issues.append((line_num, "review-tag", line.strip()))
                break
    return issues


def find_targets() -> list[Path]:
    targets: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        rel = path.relative_to(REPO_ROOT)
        rel_str = str(rel)
        if any(
            p.startswith(".") or p in {"node_modules", ".venv", "__pycache__"}
            for p in rel.parts
        ):
            continue
        if any(rel_str.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
            continue
        if not path.is_file():
            continue
        if path.name not in SCAN_NAMES:
            continue
        if path.name in SKIP_FILE_NAMES:
            continue
        targets.append(path)
    return targets


def main() -> int:
    targets = find_targets()
    all_issues: list[tuple[Path, int, str, str]] = []
    for target in targets:
        for line_num, label, line in scan_file(target):
            all_issues.append((target, line_num, label, line))

    if all_issues:
        print(
            f"\nREADME/AGENTS.md version-reference check: {len(all_issues)} violation(s) "
            f"across {len(set(p for p, _, _, _ in all_issues))} file(s)"
        )
        print(
            "Move version-specific content to CHANGELOG.md / docs/adr/ / RELEASING.md."
        )
        print(
            "If a flagged line is a legitimate third-party version mention, expand the"
        )
        print(
            "THIRD_PARTY_VERSION_CONTEXT regex in scripts/check_no_versions_in_readmes.py."
        )
        for path, line_num, label, line in all_issues:
            rel = path.relative_to(REPO_ROOT)
            print(f"  x  {rel}:{line_num} [{label}]: {line[:120]}")
        return 1

    print(
        f"  ok  no playbook version markers in {len(targets)} README/AGENTS.md file(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
