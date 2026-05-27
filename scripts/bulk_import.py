#!/usr/bin/env python3
"""
Bulk import skills + subagents from user's machine into the playbook repo.

Per Q10 v0.2 lock: literal everything from ~/.agents/skills/ + 6 markdown
subagents from ~/.claude/agents/ + 3 TOML subagents from ~/.codex/agents/.

Discipline:
- Skip items whose name already exists in the playbook (avoid dupes).
- Best-effort categorize via name heuristic; unknown -> 'imported'.
- Normalize frontmatter: ensure owner: rehan-8v and last_reviewed: 2026-05-24.
- For TOML subagents from Codex, convert TOML back to canonical markdown
  per ADR-0009 (developer_instructions -> body, other fields -> frontmatter).
- Idempotent: safe to re-run.

Usage:
  python3 scripts/bulk_import.py             # dry-run (lists what would import)
  python3 scripts/bulk_import.py --apply     # actually copy
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tomllib
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TODAY = date.today().isoformat()
OWNER = "rehan-8v"

# Skills already in playbook (will be skipped on import).
EXISTING_SKILLS_BY_NAME = {
    p.parent.name for p in (REPO_ROOT / "skills").rglob("SKILL.md")
}

# Heuristic name -> category mapping. Items not in any list go to 'imported'.
NAME_TO_CATEGORY: dict[str, str] = {}
_BUCKETS = {
    "engineering": [
        "diagnose",
        "lint-guard",
        "prototype",
        "tdd",
        "improve-codebase-architecture",
        "sync-team-repos",
        "supacode-cli",
        "triage",
        "to-issues",
        "to-prd",
        "synthteam-code-context",
    ],
    "productivity": [
        "team-presentation",
        "frontend-slides",
        "spreadsheet",
        "meeting-brief",
        "ask-colleague",
        "ask-team",
        "distill-slack-persona",
        "grill-with-docs",
        "promote-ticket",
        "caveman",
    ],
    "observability": [
        "ha-alert-triage",
        "market-audit-deployed-stack",
    ],
    "meta": [
        "anchored-edit",
        "audit-docs",
        "docs-drift",
        "docs-index",
        "find-skills",
        "graphify",
        "human-html",
        "setup-matt-pocock-skills",
        "zoom-out",
    ],
}
for cat, names in _BUCKETS.items():
    for n in names:
        NAME_TO_CATEGORY[n] = cat


def _has_frontmatter(text: str) -> bool:
    return text.startswith("---\n") and "\n---\n" in text


def _ensure_frontmatter(text: str, name: str) -> str:
    """Ensure SKILL.md has owner + last_reviewed. Adds missing fields without clobbering."""
    if not _has_frontmatter(text):
        # Inject minimal frontmatter at top.
        return (
            "---\n"
            f"name: {name}\n"
            f"description: Imported from personal collection (~/.agents/skills/{name}/).\n"
            f"version: 1.0.0\n"
            f"owner: {OWNER}\n"
            f"last_reviewed: {TODAY}\n"
            f"tags: [imported]\n"
            f"scope: imported\n"
            "---\n\n"
        ) + text

    # Parse and update existing frontmatter.
    end_idx = text.index("\n---\n", 4)
    fm_block = text[4:end_idx]
    body = text[end_idx + 5 :]
    fm_lines = fm_block.splitlines()

    have_owner = any(re.match(r"^owner\s*:", line) for line in fm_lines)
    have_last_reviewed = any(re.match(r"^last_reviewed\s*:", line) for line in fm_lines)
    have_version = any(re.match(r"^version\s*:", line) for line in fm_lines)
    have_name = any(re.match(r"^name\s*:", line) for line in fm_lines)

    extras: list[str] = []
    if not have_name:
        extras.append(f"name: {name}")
    if not have_version:
        extras.append("version: 1.0.0")
    if not have_owner:
        extras.append(f"owner: {OWNER}")
    if not have_last_reviewed:
        extras.append(f"last_reviewed: {TODAY}")

    if not extras:
        return text  # already complete

    new_fm = "\n".join(fm_lines + extras)
    return f"---\n{new_fm}\n---\n{body}"


def _strip_em_dashes(text: str) -> str:
    """Per rules/no-em-dashes.md. Replace `, ` / `, ` / `,` / `,` and en-dash variants."""
    text = (
        text.replace(", ", ", ").replace(", ", ", ").replace(",", ",").replace(",", ",")
    )
    text = (
        text.replace(", ", ", ").replace(", ", ", ").replace(",", ",").replace("-", "-")
    )
    return text


def import_skills(apply: bool) -> int:
    src_root = Path.home() / ".agents" / "skills"
    if not src_root.is_dir():
        print(f"  warn  source missing: {src_root}")
        return 0

    imported = skipped_dup = skipped_no_skill_md = 0
    for entry in sorted(src_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "_shared":
            continue
        name = entry.name
        if name in EXISTING_SKILLS_BY_NAME:
            print(f"  skip  {name} (already in playbook)")
            skipped_dup += 1
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            print(f"  skip  {name} (no SKILL.md)")
            skipped_no_skill_md += 1
            continue

        category = NAME_TO_CATEGORY.get(name, "imported")
        dest_dir = REPO_ROOT / "skills" / category / name
        dest_skill = dest_dir / "SKILL.md"
        if dest_skill.exists():
            print(f"  skip  {name} (already imported)")
            skipped_dup += 1
            continue

        text = skill_md.read_text(encoding="utf-8")
        text = _ensure_frontmatter(text, name)
        text = _strip_em_dashes(text)

        if apply:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_skill.write_text(text, encoding="utf-8")
            # Copy any additional assets in the source dir (scripts, references, etc.).
            # SKIP .git (Codex P1 #1: source skills that are git checkouts created
            # 160000 gitlink entries in the playbook, breaking fresh clones).
            # SKIP node_modules (bundled vendor deps; not part of the skill).
            excluded_names = {"SKILL.md", ".git", "node_modules", ".DS_Store"}
            for asset in entry.iterdir():
                if asset.name in excluded_names:
                    continue
                dest_asset = dest_dir / asset.name
                if asset.is_dir():
                    if not dest_asset.exists():
                        # Use ignore to be doubly safe against nested .git / node_modules.
                        shutil.copytree(
                            asset,
                            dest_asset,
                            ignore=shutil.ignore_patterns(
                                ".git", "node_modules", ".DS_Store"
                            ),
                        )
                else:
                    if not dest_asset.exists():
                        shutil.copy2(asset, dest_asset)
        print(
            f"  {'IMPORT' if apply else 'would import'}  {name} -> skills/{category}/"
        )
        imported += 1

    print(
        f"\n  Skills: {imported} {'imported' if apply else 'would be imported'}, "
        f"{skipped_dup} skipped (dupe), {skipped_no_skill_md} skipped (no SKILL.md)"
    )
    return imported


def import_md_agents(apply: bool) -> int:
    src_root = Path.home() / ".claude" / "agents"
    if not src_root.is_dir():
        print(f"  warn  source missing: {src_root}")
        return 0

    dest_root = REPO_ROOT / "agents"
    imported = skipped = 0
    for src in sorted(src_root.glob("*.md")):
        dest = dest_root / src.name
        if dest.exists():
            print(f"  skip  {src.name} (already in agents/)")
            skipped += 1
            continue
        text = src.read_text(encoding="utf-8")
        text = _strip_em_dashes(text)
        if apply:
            dest_root.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
        print(f"  {'IMPORT' if apply else 'would import'}  agents/{src.name}")
        imported += 1
    print(
        f"\n  Agents (md): {imported} {'imported' if apply else 'would be imported'}, "
        f"{skipped} skipped"
    )
    return imported


def import_toml_agents(apply: bool) -> int:
    """Convert Codex TOML subagents back to canonical markdown per ADR-0009."""
    src_root = Path.home() / ".codex"
    if not src_root.is_dir():
        print(f"  warn  source missing: {src_root}")
        return 0

    # Codex subagents live in ~/.codex/agents/ per the official subagent spec
    # (developers.openai.com/codex/subagents). Older configs may have them
    # directly under ~/.codex/; check both.
    tomls = (
        list((src_root / "agents").glob("*.toml"))
        if (src_root / "agents").is_dir()
        else []
    )
    tomls += [p for p in src_root.glob("*.toml") if p.name != "config.toml"]

    dest_root = REPO_ROOT / "agents"
    imported = skipped = 0
    for toml_path in sorted(tomls):
        # Skip config.toml itself
        if toml_path.name == "config.toml":
            continue
        name = toml_path.stem
        dest = dest_root / f"{name}.md"
        if dest.exists():
            print(f"  skip  {name} (already in agents/)")
            skipped += 1
            continue
        try:
            data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            print(f"  fail  {toml_path}: {exc}")
            continue

        body = data.pop("developer_instructions", "").rstrip()
        body = _strip_em_dashes(body)
        # Remaining keys become frontmatter.
        fm_lines = ["---"]
        for key, value in data.items():
            if isinstance(value, str):
                fm_lines.append(f"{key}: {value}")
            elif isinstance(value, list):
                fm_lines.append(f"{key}: [{', '.join(repr(v) for v in value)}]")
            elif isinstance(value, dict):
                continue  # skip nested tables; rare for subagents
            else:
                fm_lines.append(f"{key}: {value}")
        fm_lines.append("---")
        md_text = "\n".join(fm_lines) + "\n\n" + body + "\n"

        if apply:
            dest_root.mkdir(parents=True, exist_ok=True)
            dest.write_text(md_text, encoding="utf-8")
        print(
            f"  {'IMPORT' if apply else 'would import'}  agents/{name}.md (from TOML)"
        )
        imported += 1
    print(
        f"\n  Agents (toml): {imported} {'imported' if apply else 'would be imported'}, "
        f"{skipped} skipped"
    )
    return imported


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-import skills + subagents from user's machine"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Actually copy (default is dry-run)"
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Bulk import [{mode}] ===\n")

    print("[1/3] Skills from ~/.agents/skills/")
    skills_imported = import_skills(args.apply)

    print("\n[2/3] Markdown subagents from ~/.claude/agents/")
    md_imported = import_md_agents(args.apply)

    print("\n[3/3] TOML subagents from ~/.codex/")
    toml_imported = import_toml_agents(args.apply)

    total = skills_imported + md_imported + toml_imported
    print(f"\nTotal {'imported' if args.apply else 'would be imported'}: {total}")

    if not args.apply:
        print("\nRe-run with --apply to actually copy files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
