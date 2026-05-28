"""Canonical skill identity + frontmatter helpers.

Before this module the playbook had three independent answers to
"which skill is this?":

  decay_check._usage_decay_findings   used skill_md.parent.name
  build_atlas._render_skill           used frontmatter `name`
  telemetry JSONL                     used OTLP skill.name attribute

The split was structurally unreliable: as soon as a directory slug
diverged from the frontmatter `name` (common when a skill gets
renamed without moving the directory), usage-decay false-flagged
and atlas telemetry rendered against the wrong key. The canonical
join key is the frontmatter `name`, falling back to the directory
basename when frontmatter is missing.

Three independent frontmatter parsers (`_reader._parse_frontmatter`,
`atlas.graph_builder._frontmatter`, `security.ai_bom`'s inline
helper) also drifted. This module exposes one parser; the others
delegate.
"""

from __future__ import annotations

import re
from pathlib import Path


_FRONTMATTER_FIELD_RE = re.compile(r"^(\w+)\s*:\s*(.*?)\s*$")


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Return `(frontmatter_dict, body)` or `({}, full_content)` if no
    frontmatter. Matches the semantics of the existing
    `adapters._reader._parse_frontmatter` so consumers can migrate
    without behavioral surprises."""
    if not content.startswith("---"):
        return {}, content
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}, content
    block = content[3:end]
    body = content[end + 3 :].lstrip("\n")
    fm: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _FRONTMATTER_FIELD_RE.match(line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm, body


def frontmatter_field(content: str, key: str) -> str | None:
    """Convenience for callers that need a single field. Returns None
    when the field is missing or empty."""
    fm, _ = parse_frontmatter(content)
    value = fm.get(key)
    return value if value else None


def skill_identity(skill_md: Path) -> str:
    """Canonical join key for everything that wants to ask
    "which skill is this?".

    Order of precedence:
      1. SKILL.md frontmatter `name:` field
      2. Directory basename of `skill_md.parent`

    Telemetry JSONL writers should set OTLP `skill.name` to the
    same value (matches the live trajectory shim's behavior).
    Atlas + decay + future consumers MUST all call this helper
    so they cannot drift.
    """
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return skill_md.parent.name
    name = frontmatter_field(text, "name")
    if name:
        return name
    return skill_md.parent.name
