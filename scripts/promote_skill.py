#!/usr/bin/env python3
"""
Backend for the /playbook-promote skill.

Reads a draft from $PLAYBOOK_PROPOSALS_DIR and prepares the skill/rule/hook
for inclusion in the playbook repo. The interview (clarifying questions,
2nd-source grounding, when-NOT-to-use) is driven by the skill (LLM); this
script handles the file-IO and git-branch mechanics.

Usage:
  python3 promote_skill.py --slug <slug>
  python3 promote_skill.py --slug <slug> --no-branch    # write to current branch
  python3 promote_skill.py --slug <slug> --playbook-home /path/to/playbook
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PLAYBOOK_LOCATIONS = (
    Path.home() / "team" / "coding-agents-playbook",
    Path.home() / "coding-agents-playbook",
    Path.home() / "projects" / "coding-agents-playbook",
    Path.home() / "src" / "coding-agents-playbook",
    Path.home() / "work" / "coding-agents-playbook",
)


def find_playbook_home() -> Path | None:
    """Locate the playbook checkout. Honors $PLAYBOOK_HOME, else searches common paths."""
    override = os.environ.get("PLAYBOOK_HOME")
    if override:
        candidate = Path(override).expanduser().resolve()
        if (candidate / "scripts" / "new_skill.py").exists():
            return candidate
        return None

    for candidate in DEFAULT_PLAYBOOK_LOCATIONS:
        if (candidate / "scripts" / "new_skill.py").exists():
            return candidate.resolve()
    return None


def get_proposals_dir() -> Path:
    override = os.environ.get("PLAYBOOK_PROPOSALS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".playbook-proposals").resolve()


def find_draft(slug: str, proposals_dir: Path) -> Path | None:
    """Find the draft file for slug; checks .skill.md, .rule.md, .hook.md suffixes."""
    for suffix in ("skill", "rule", "hook"):
        candidate = proposals_dir / f"{slug}.{suffix}.md"
        if candidate.exists():
            return candidate
    return None


def parse_proposal_frontmatter(draft_path: Path) -> tuple[dict, str]:
    """Naive frontmatter parser. Returns (frontmatter_dict, body)."""
    content = draft_path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}, content
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}, content
    block = content[3:end]
    body = content[end + 3 :].lstrip("\n")
    fm: dict = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\w+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm, body


def create_feature_branch(playbook_home: Path, slug: str) -> str:
    """Create and checkout feat/playbook-add-<slug>. If it exists, switch to it."""
    branch = f"feat/playbook-add-{slug}"
    result = subprocess.run(
        ["git", "checkout", "-b", branch],
        cwd=playbook_home,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        subprocess.run(["git", "checkout", branch], cwd=playbook_home, check=True)
    return branch


def _scope_subdir(scope: str) -> str:
    """Map scope=base|team to its subtree prefix per ADR-0040."""
    if scope == "team":
        return "overlays/<name>"
    return "base"


def scaffold_skill(
    playbook_home: Path,
    slug: str,
    category: str,
    owner: str,
    scope: str = "base",
) -> Path:
    """Use the existing new_skill.py to scaffold a new skill folder + SKILL.md.

    v0.11 (ADR-0040): new_skill.py now scaffolds under base/skills/ or
    overlays/<name>/skills/. Forward the scope so promotion lands in the
    same tree the loader walks.
    """
    new_skill_py = playbook_home / "scripts" / "new_skill.py"
    subprocess.run(
        [
            "python3",
            str(new_skill_py),
            "--name",
            slug,
            "--category",
            category,
            "--owner",
            owner,
            "--scope",
            scope,
        ],
        check=True,
    )
    return (
        playbook_home / _scope_subdir(scope) / "skills" / category / slug / "SKILL.md"
    )


def write_rule(
    playbook_home: Path, slug: str, body: str, scope: str = "base"
) -> Path:
    """Write a new rule. Refuses to overwrite an existing rule.

    v0.11 (ADR-0040): rules moved to base/rules/ + overlays/<name>/rules/.
    Scope decides which subtree the new rule lands in. Mirrors new_skill.py's
    refusal-on-collision discipline.
    """
    rules_dir = playbook_home / _scope_subdir(scope) / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"{slug}.md"
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing rule at {path}. "
            f"Pick a different slug, edit in place, or delete first."
        )
    path.write_text(body, encoding="utf-8")
    return path


def write_hook(
    playbook_home: Path, slug: str, body: str, scope: str = "base"
) -> Path:
    """Write a new hook. Refuses to overwrite.

    v0.11 (ADR-0040): hooks moved to base/hooks/ + overlays/<name>/hooks/.
    """
    hooks_dir = playbook_home / _scope_subdir(scope) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / f"{slug}.sh"
    if path.exists():
        raise FileExistsError(
            f"refusing to overwrite existing hook at {path}. "
            f"Pick a different slug, edit in place, or delete first."
        )
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backend for the /playbook-promote skill"
    )
    parser.add_argument(
        "--slug",
        required=True,
        help="Draft slug (basename without .skill/.rule/.hook.md)",
    )
    parser.add_argument("--playbook-home", help="Override playbook checkout path")
    parser.add_argument(
        "--owner",
        default=os.environ.get("USER", "unknown"),
        help="Skill owner (default: $USER)",
    )
    parser.add_argument(
        "--no-branch",
        action="store_true",
        help="Skip creating a feature branch; write to current branch",
    )
    parser.add_argument(
        "--scope",
        default="base",
        choices=("base", "team"),
        help=(
            "v0.11 (ADR-0040): which tree to promote into. 'base' (default) "
            "lands the draft in base/<type>/. 'team' lands in "
            "overlays/<name>/<type>/."
        ),
    )
    args = parser.parse_args()

    if args.playbook_home:
        playbook_home: Path | None = Path(args.playbook_home).expanduser().resolve()
        if not (playbook_home / "scripts" / "new_skill.py").exists():
            print(
                f"error: --playbook-home {playbook_home} does not look like the playbook checkout "
                f"(missing scripts/new_skill.py).",
                file=sys.stderr,
            )
            return 1
    else:
        playbook_home = find_playbook_home()
    if not playbook_home:
        print(
            "error: could not find the coding-agents-playbook checkout.",
            file=sys.stderr,
        )
        print("Searched: $PLAYBOOK_HOME, then:", file=sys.stderr)
        for loc in DEFAULT_PLAYBOOK_LOCATIONS:
            print(f"  - {loc}", file=sys.stderr)
        print(
            "Set $PLAYBOOK_HOME or pass --playbook-home /path/to/playbook.",
            file=sys.stderr,
        )
        return 1

    proposals_dir = get_proposals_dir()
    draft = find_draft(args.slug, proposals_dir)
    if not draft:
        print(
            f"error: no draft found for slug '{args.slug}' in {proposals_dir}",
            file=sys.stderr,
        )
        return 1

    fm, body = parse_proposal_frontmatter(draft)
    proposal_type = fm.get("proposal_type", "skill")

    print(f"playbook home: {playbook_home}")
    print(f"draft:         {draft}")
    print(f"proposal type: {proposal_type}")

    if not args.no_branch:
        branch = create_feature_branch(playbook_home, args.slug)
        print(f"branch:        {branch}")
    else:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=playbook_home,
            capture_output=True,
            text=True,
        ).stdout.strip()

    scope = args.scope
    scope_subdir = _scope_subdir(scope)

    if proposal_type == "skill":
        category = fm.get("category", "engineering")
        scaffold_path = scaffold_skill(
            playbook_home, args.slug, category, args.owner, scope=scope
        )
        print(f"scaffolded:    {scaffold_path}")
        print()
        print("Next steps (skill):")
        print(
            f"  1. Edit {scaffold_path}: merge the draft body, add 'When NOT to use this skill'"
        )
        print(f"  2. cd {playbook_home} && make check")
        print(f"  3. git add . && git commit -m 'feat(skills): add {args.slug}'")
        print(f"  4. git push -u origin {branch}")
        print("  5. Open PR in VCS targeting develop")
    elif proposal_type == "rule":
        path = write_rule(playbook_home, args.slug, body, scope=scope)
        print(f"wrote rule:    {path}")
        print()
        print("Next steps (rule):")
        print(f"  1. Review {path}")
        print(f"  2. cd {playbook_home} && make check")
        print(
            f"  3. git add {scope_subdir}/rules/ && "
            f"git commit -m 'feat(rules): add {args.slug}'"
        )
        print(f"  4. git push -u origin {branch}")
        print("  5. Open PR in VCS targeting develop")
    elif proposal_type == "hook":
        path = write_hook(playbook_home, args.slug, body, scope=scope)
        print(f"wrote hook:    {path}")
        print()
        print("Next steps (hook):")
        print(f"  1. Review {path} and test it")
        print(f"  2. cd {playbook_home} && make check")
        print(
            f"  3. git add {scope_subdir}/hooks/ && "
            f"git commit -m 'feat(hooks): add {args.slug}'"
        )
        print(f"  4. git push -u origin {branch}")
        print("  5. Open PR in VCS targeting develop")
    else:
        print(
            f"error: unknown proposal_type '{proposal_type}' in {draft}",
            file=sys.stderr,
        )
        return 1

    print()
    print(f"Reminder: do NOT delete {draft} until the PR merges.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
