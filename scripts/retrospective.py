#!/usr/bin/env python3
"""
Backend for the /playbook-retrospective skill.

Locates the current Claude Code session JSONL, lists existing proposals,
and provides a `write_proposal()` helper that the LLM (running the skill)
calls back into to create draft files.

The classification of "what is playbook-worthy" is done by the LLM; this
script is the file-IO surface.

Usage:
  python3 retrospective.py --session-id <id>                  # locate + summarize
  python3 retrospective.py --session-id <id> --list-only      # just list state
  python3 retrospective.py --list-only                        # list proposals only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


def project_slug_from_cwd(cwd: Path) -> str:
    """Compute Claude Code's project-dir slug from the absolute cwd.

    Claude Code stores project state under ~/.claude/projects/<slug>/
    where <slug> is the absolute path with '/' replaced by '-'.
    """
    return str(cwd.resolve()).replace("/", "-")


def find_session_jsonl(session_id: str, cwd: Path) -> Path | None:
    """Locate the session JSONL across Claude Code and Codex CLI storage paths.

    Claude Code:  ~/.claude/projects/<cwd-slug>/<id>.jsonl  (flat)
    Codex CLI:    ~/.codex/sessions/YYYY/MM/DD/*.jsonl     (dated layout, real)
                  ~/.codex/sessions/<id>.jsonl              (flat fallback)
                  ~/.codex/sessions/<cwd-slug>/<id>.jsonl   (per-project variant)
                  ~/.codex/history/<id>.jsonl               (older variant)
                  ~/.codex/archived_sessions/**/<id>.jsonl  (archived; Codex P2 #4 fix)

    Codex P2 #4 fix: the v0.2 first pass only checked flat sessions/ and history/
    paths, missing Codex's actual dated layout (~/.codex/sessions/YYYY/MM/DD/)
    and archived_sessions/. Now uses rglob to find the session by id anywhere
    under the Codex session/archive trees.
    """
    home = Path.home()
    slug = project_slug_from_cwd(cwd)

    # Fast-path: check the well-known flat paths first.
    fast_candidates = [
        home / ".claude" / "projects" / slug / f"{session_id}.jsonl",
        home / ".codex" / "sessions" / f"{session_id}.jsonl",
        home / ".codex" / "sessions" / slug / f"{session_id}.jsonl",
        home / ".codex" / "history" / f"{session_id}.jsonl",
    ]
    for candidate in fast_candidates:
        if candidate.exists():
            return candidate

    # Slow-path: rglob the Codex dated + archived trees by id.
    needle = f"{session_id}.jsonl"
    for tree in (home / ".codex" / "sessions", home / ".codex" / "archived_sessions"):
        if not tree.is_dir():
            continue
        for match in tree.rglob(needle):
            if match.is_file():
                return match

    return None


def get_proposals_dir() -> Path:
    """Resolve where drafts go. Honors $PLAYBOOK_PROPOSALS_DIR."""
    override = os.environ.get("PLAYBOOK_PROPOSALS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".playbook-proposals").resolve()


def list_existing_proposals(proposals_dir: Path) -> list[Path]:
    if not proposals_dir.is_dir():
        return []
    return sorted(proposals_dir.glob("*.md"))


def read_session_messages(jsonl_path: Path) -> list[dict]:
    """Load the session JSONL into a list of message dicts. Tolerates malformed lines."""
    messages: list[dict] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return messages


def write_proposal(
    slug: str,
    proposal_type: str,
    body: str,
    *,
    category: str | None = None,
    sources: list[str] | None = None,
    proposals_dir: Path | None = None,
) -> Path:
    """Write a proposal draft. Returns the path.

    Intentionally permissive: overwrites existing drafts so the LLM can
    re-run the retrospective and refine. Promotion is the gate, not draft creation.
    """
    if proposal_type not in ("skill", "rule", "hook"):
        raise ValueError(
            f"proposal_type must be skill, rule, or hook; got {proposal_type!r}"
        )
    if proposal_type == "skill" and not category:
        raise ValueError("category is required for skill proposals")

    proposals_dir = proposals_dir or get_proposals_dir()
    proposals_dir.mkdir(parents=True, exist_ok=True)

    suffix = proposal_type
    path = proposals_dir / f"{slug}.{suffix}.md"

    today = date.today().isoformat()
    frontmatter_lines = [
        "---",
        f"proposal_type: {proposal_type}",
        f"slug: {slug}",
    ]
    if category:
        frontmatter_lines.append(f"category: {category}")
    if sources:
        frontmatter_lines.append("sources:")
        for src in sources:
            frontmatter_lines.append(f"  - {src}")
    frontmatter_lines.extend(
        [
            f"captured_at: {today}",
            "status: draft",
            "---",
            "",
        ]
    )

    path.write_text("\n".join(frontmatter_lines) + body, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backend for the /playbook-retrospective skill"
    )
    parser.add_argument("--session-id", help="Claude Code session id")
    parser.add_argument(
        "--cwd", default=os.getcwd(), help="Working directory (default: cwd)"
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="List existing proposals + session location; do not analyze",
    )
    args = parser.parse_args()

    cwd = Path(args.cwd)
    proposals_dir = get_proposals_dir()
    existing = list_existing_proposals(proposals_dir)

    print(f"Proposals dir: {proposals_dir}")
    print(f"Existing drafts: {len(existing)}")
    for p in existing:
        print(f"  - {p.name}")

    if not args.session_id:
        print("\nNo --session-id provided; run with one to locate the session JSONL.")
        return 0

    jsonl = find_session_jsonl(args.session_id, cwd)
    print(f"\nSession id:    {args.session_id}")
    print(f"Session JSONL: {jsonl if jsonl else '(not found)'}")
    if not jsonl:
        slug = project_slug_from_cwd(cwd)
        print(f"  Expected at: ~/.claude/projects/{slug}/{args.session_id}.jsonl")
        return 1

    if args.list_only:
        return 0

    messages = read_session_messages(jsonl)
    print(f"Messages:      {len(messages)}")
    print()
    print("This script provides the file-IO surface for the retrospective skill.")
    print("The agent running the skill analyzes the messages and calls")
    print("write_proposal(...) for each candidate learning. To use as a library:")
    print()
    print("  from retrospective import write_proposal")
    print("  write_proposal('my-pattern', 'skill', body='...', category='engineering',")
    print("                 sources=['session abc123 turn 42'])")

    return 0


if __name__ == "__main__":
    sys.exit(main())
