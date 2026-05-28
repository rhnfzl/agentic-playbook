#!/usr/bin/env python3
"""Validate every SKILL.md frontmatter `description:` is ≤ 1024 characters.

Codex (and likely other tools that consume MCP-style skill metadata) reject
skills whose `description` field exceeds 1024 characters; the skill is
silently skipped or fails to load. To keep the playbook portable across
every Tier 1/2/3 tool, every SKILL.md description is capped at 1024 chars
regardless of the tool the user installs into.

Multi-line YAML descriptions (indented continuation, no explicit `>` or `|`)
are joined as the parser would and counted as one string. Lines after the
description that introduce another top-level key (`^[a-zA-Z_][\\w-]*\\s*:`)
end the description.

Exit code 0 if every description fits; 1 otherwise, with offending paths
+ lengths printed to stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


MAX_DESCRIPTION_CHARS = 1024

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*", re.DOTALL)
_DESCRIPTION_KEY_RE = re.compile(r"^description\s*:")
_TOP_LEVEL_KEY_RE = re.compile(r"^[a-zA-Z_][\w-]*\s*:")


def _extract_description(text: str) -> str | None:
    """Pull the `description:` value out of YAML frontmatter.

    Handles three shapes:
      description: single line
      description: >
        folded multi-line continuing on indented lines
      description: text starts here
        and continues on indented lines

    Returns None if no description key is found. Returns the raw joined
    string (newlines preserved, leading/trailing whitespace stripped).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    block = m.group(1)
    lines = block.splitlines()
    desc_idx = next(
        (i for i, line in enumerate(lines) if _DESCRIPTION_KEY_RE.match(line)),
        -1,
    )
    if desc_idx < 0:
        return None
    first = re.sub(r"^description\s*:\s*", "", lines[desc_idx])
    pieces: list[str] = [first]
    for nxt in lines[desc_idx + 1 :]:
        if _TOP_LEVEL_KEY_RE.match(nxt):
            break
        pieces.append(nxt)
    return "\n".join(pieces).strip()


def main(repo_root: Path | None = None) -> int:
    repo_root = repo_root or Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): skills moved to base/ + overlays/team/. Walk both.
    skill_roots = [
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ]
    skill_roots = [r for r in skill_roots if r.is_dir()]
    if not skill_roots:
        print(
            "  no skill roots found at base/skills/ or overlays/team/skills/; nothing to check"
        )
        return 0

    failures: list[tuple[Path, int]] = []
    total = 0
    skill_paths: list = []
    for root in skill_roots:
        skill_paths.extend(sorted(root.rglob("SKILL.md")))
    for skill_md in skill_paths:
        total += 1
        text = skill_md.read_text(encoding="utf-8")
        desc = _extract_description(text)
        if desc is None:
            continue
        if len(desc) > MAX_DESCRIPTION_CHARS:
            failures.append((skill_md, len(desc)))

    if failures:
        print(
            f"  FAIL  {len(failures)} skill(s) over {MAX_DESCRIPTION_CHARS} chars "
            f"(Codex rejects these):",
            file=sys.stderr,
        )
        for path, length in failures:
            print(
                f"    {path.relative_to(repo_root)}: {length} chars",
                file=sys.stderr,
            )
        print(
            "  fix: trim the description field in the offending frontmatter. "
            "Keep the actionable trigger language; move long context into the body.",
            file=sys.stderr,
        )
        return 1

    print(
        f"  ok  every SKILL.md description is ≤ {MAX_DESCRIPTION_CHARS} chars "
        f"({total} skill(s) scanned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
