#!/usr/bin/env python3
"""
Lint SKILL.md frontmatter for required fields + Agent Skills spec compliance.

Required fields: name, description, version, owner, last_reviewed.
Optional: tags, scope, allowed-tools, license.

Spec checks (v0.3, per Agent Skills spec at agentskills.io):
  - name: kebab-case, matches parent directory name
  - description: <= 250 chars, starts with "Use when" (recommended)
  - version: semver-ish (MAJOR.MINOR.PATCH)
  - allowed-tools: if present, must be a YAML list of known tool names
  - license: if present, must be a known SPDX identifier
  - referenced files (in body): paths under skill-dir must exist

Naive parser (no PyYAML dependency) by design.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ["name", "description", "version", "owner", "last_reviewed"]

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[A-Za-z0-9\.\-]+)?$")
DESC_MAX = (
    1024  # Generous upper bound; spec encourages concision but doesn't strictly cap
)
DESC_WARN = 250  # Encourage shorter descriptions for new content

KNOWN_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "GPL-3.0",
    "LGPL-3.0",
    "MPL-2.0",
    "ISC",
    "Unlicense",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "proprietary",
    "internal-only",
}

KNOWN_TOOLS = {
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "NotebookEdit",
    "ExitPlanMode",
    "EnterPlanMode",
    "SendMessage",
    "ScheduleWakeup",
    "AskUserQuestion",
}

# Vendored content (per ADR-0019) keeps its upstream directory layout and naming.
# We do not enforce parent-dir-match against vendored skills.
# v0.11 (ADR-0040): skills moved into base/skills/ + overlays/team/skills/.
# Vendored imports live under base/skills/imported/.
VENDORED_PREFIX = "base/skills/imported/"

REFERENCED_FILE_RE = re.compile(r"<skill-dir>/([a-zA-Z0-9_\-./]+)")


def parse_frontmatter(content: str) -> tuple[dict[str, str] | None, str]:
    """Return (fields dict, body text). Body excludes the frontmatter block."""
    if not content.startswith("---"):
        return None, content
    try:
        end = content.index("---", 3)
    except ValueError:
        return None, content

    block = content[3:end]
    body = content[end + 3 :]
    fields: dict[str, str] = {}
    current_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        m = re.match(r"^(\w[\w\-]*)\s*:\s*(.*)$", line)
        if m:
            key_name: str = m.group(1)
            current_key = key_name
            value = m.group(2).strip()
            fields[key_name] = value
        elif current_key is not None and raw_line.startswith((" ", "\t", "-")):
            key: str = current_key
            fields[key] = (fields.get(key, "") + " " + line.strip()).strip()
    return fields, body


def lint_skill(skill_md: Path, repo_root: Path) -> list[str]:
    rel = skill_md.relative_to(repo_root)
    text = skill_md.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    issues: list[str] = []

    if fm is None:
        return [f"{rel}: missing or malformed frontmatter"]

    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            issues.append(f"{rel}: missing or empty field '{field}'")

    name = fm.get("name", "").strip().strip('"').strip("'")
    is_vendored = str(rel).startswith(VENDORED_PREFIX)
    if name and not NAME_RE.match(name):
        issues.append(
            f"{rel}: name '{name}' not kebab-case (a-z0-9 with hyphens, no leading/trailing hyphen)"
        )
    if name and name != skill_md.parent.name and not is_vendored:
        issues.append(
            f"{rel}: name '{name}' does not match directory '{skill_md.parent.name}'"
        )

    desc = fm.get("description", "").strip().strip('"').strip("'")
    if desc and len(desc) > DESC_MAX:
        issues.append(f"{rel}: description {len(desc)} chars (>{DESC_MAX})")

    version = fm.get("version", "").strip()
    if version and not VERSION_RE.match(version):
        issues.append(f"{rel}: version '{version}' not semver MAJOR.MINOR.PATCH")

    # Vendored content can carry upstream-shaped license + allowed-tools strings
    # that do not match our regex/SPDX assumptions. Provenance is captured in
    # docs/research/external-skill-sources.md; skip these two checks for them.
    if not is_vendored:
        license_val = fm.get("license", "").strip()
        if license_val and license_val not in KNOWN_LICENSES:
            issues.append(f"{rel}: license '{license_val}' not in known SPDX list")

        allowed_tools = (
            fm.get("allowed-tools", "").strip() or fm.get("allowed_tools", "").strip()
        )
        if allowed_tools:
            cleaned = allowed_tools.strip("[]")
            tool_names = [
                t.strip().strip('"').strip("'") for t in cleaned.split(",") if t.strip()
            ]
            unknown = [t for t in tool_names if t not in KNOWN_TOOLS and t]
            if unknown:
                issues.append(
                    f"{rel}: allowed-tools includes unknown tool(s): {', '.join(unknown)}"
                )

    # Referenced file existence: <skill-dir>/foo.md must exist
    skill_dir = skill_md.parent
    for m in REFERENCED_FILE_RE.finditer(body):
        ref = skill_dir / m.group(1)
        if not ref.exists():
            issues.append(f"{rel}: references missing file: {m.group(1)}")

    return issues


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): skills moved to base/ + overlays/team/. Walk both.
    skill_roots = [
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ]
    skill_roots = [r for r in skill_roots if r.is_dir()]
    if not skill_roots:
        print("  no skill roots found at base/skills/ or overlays/team/skills/; nothing to lint")
        return 0

    issues: list[str] = []
    checked = 0
    skill_paths: list = []
    for root in skill_roots:
        skill_paths.extend(sorted(root.rglob("SKILL.md")))
    for skill_md in skill_paths:
        checked += 1
        issues.extend(lint_skill(skill_md, repo_root))

    if issues:
        print(f"\nFrontmatter lint: {len(issues)} issue(s) in {checked} skill(s)")
        for issue in issues:
            print(f"  x  {issue}")
        return 1

    print(f"  ok  frontmatter valid in {checked} skill(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
