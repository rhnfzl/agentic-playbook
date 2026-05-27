#!/usr/bin/env python3
"""Em-dash linter for the playbook's own authored files.

Enforces rules/no-em-dashes.md on the playbook itself. Addresses Codex finding
P3 #8: the rule was installed for downstream teams but not enforced on the
playbook's own committed prose.

Scope:
- Top-level *.md
- rules/, docs/adr/, docs/research/, prompts/, skills/<cat>/<name>/SKILL.md

Allowlist (files that may legitimately mention the character):
- rules/no-em-dashes.md (the rule itself)
- skills/engineering/code-review/SKILL.md (review checklist references the char)

Exit code: 0 if clean (or only allowlisted files have hits), 1 if drift detected.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters._loader import find_em_dashes

REPO_ROOT = Path(__file__).resolve().parent.parent

ALLOWLIST = {
    # Rules + skill bodies that legitimately reference the character.
    # Post-v0.11 paths under base/ + overlays/<name>/ (ADR-0040).
    "base/rules/no-em-dashes.md",
    "overlays/<name>/skills/engineering/code-review/SKILL.md",
    # MCP source with the character inside a regex character class that parses
    # MEMORY.md entry rows where the user used an em-dash separator. Functional,
    # not authored prose.
    "base/mcp/agent-memory-bridge/memory_curator.py",
}

# Vendored content (per ADR-0018, ADR-0019) ships verbatim from upstream and is
# not subject to our prose rules. Exclude entire subtrees.
VENDORED_PREFIXES = (
    "base/mcp/anchored-fs/",
    "base/skills/imported/",
)

# Patterns enumerate the post-v0.11 base/ + overlays/<name>/ layout
# (ADR-0040 mass git mv landed). Each pattern uses .glob from REPO_ROOT.
PATTERNS = [
    # Top-level docs
    "*.md",
    # ADRs + research evidence
    "docs/adr/*.md",
    "docs/research/*.md",
    "docs/human-html/*.md",
    # base/ content (all 7 content types moved here in v0.11)
    "base/rules/*.md",
    "base/prompts/*.md",
    "base/skills/**/*.md",
    "base/agents/*.md",
    "base/commands/*.md",
    "base/hooks/*.sh",
    "base/mcp/**/*.py",
    "base/mcp/**/*.md",
    "base/hooks/templates/*",
    # overlays/<name>/ content (5 content types currently present)
    "overlays/<name>/rules/*.md",
    "overlays/<name>/prompts/*.md",
    "overlays/<name>/skills/**/*.md",
    "overlays/<name>/agents/*.md",
    "overlays/<name>/hooks/*.sh",
    "overlays/<name>/mcp/**/*.json",
    # Scripts (Codex P3 #5: rules/no-em-dashes.md bans em dashes in
    # code comments and docstrings too, not just docs)
    "scripts/*.py",
    # Profile bundle config + the per-profile README/AGENTS docs
    # (devops.README.md, profiles/README.md, profiles/AGENTS.md, etc.).
    # The TOML scan was the original gate; READMEs were a gap until v0.10
    # caught a shipped em dash in profiles/devops.README.md.
    "profiles/*.toml",
    "profiles/*.md",
    # Template bundles (workspace-IP scaffolds the user customizes locally;
    # we lint the templates themselves so they ship clean, even though the
    # customized output lives outside the playbook).
    "scripts/templates/*",
    "profiles/templates/**/*",
]


def main() -> int:
    violations: list[tuple[str, int, str]] = []
    for pattern in PATTERNS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = str(path.relative_to(REPO_ROOT))
            if rel in ALLOWLIST:
                continue
            if any(rel.startswith(prefix) for prefix in VENDORED_PREFIXES):
                continue
            hits = find_em_dashes(path.read_text(encoding="utf-8"))
            for line_num, line in hits:
                violations.append((rel, line_num, line.strip()))

    if not violations:
        print(
            f"  ok  no em/en dashes outside allowlisted files "
            f"({len(ALLOWLIST)} files allowlisted)"
        )
        return 0

    print(f"  FAIL  {len(violations)} em/en dash(es) found in authored prose")
    print(
        "  Per rules/no-em-dashes.md, use commas, parentheses, or separate sentences instead."
    )
    for rel, line_num, line in violations:
        print(f"    {rel}:{line_num}: {line[:100]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
