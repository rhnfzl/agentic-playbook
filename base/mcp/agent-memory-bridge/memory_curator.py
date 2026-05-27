#!/usr/bin/env python3
"""Keep MEMORY.md under a hard line cap by demoting lowest-priority entries to
MEMORY_ARCHIVE.md while preserving every underlying memory file on disk.

Subcommands:
    status          Print line count, per-section counts, headroom vs cap.
    audit           Show which entries would be demoted (dry-run, sorted by score).
    apply           Execute demotion: rewrite MEMORY.md and MEMORY_ARCHIVE.md.
    restore <slug>  Move an entry back from archive to MEMORY.md (no-op if cap full).

Priority model (higher = keep in MEMORY.md):
    section weight: User=1000, Reference=600, Project=400, Feedback=200
    pointer penalty: -200 if index line starts with "see workspace AGENTS.md"
                     or "see global AGENTS.md"
    pin override:   +10000 if memory file frontmatter has `pin: true`
    recency bonus:  +80 if mtime within 30d, +30 within 90d, -50 if >365d old

Idempotent. Atomic writes (.tmp then rename). No external deps.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _resolve_memory_dir() -> Path:
    """Resolve the workspace's memory directory at call time so tests and
    multi-workspace installs can override via env. Resolution order:

    1. $MEMORY_INDEX_DIR (explicit override; takes precedence over everything).
    2. $CLAUDE_PROJECT_DIR encoded to the Claude project slug.
    3. $CODEX_WORKSPACE encoded to the Claude project slug.
    4. cwd encoded to the Claude project slug.

    Returns the resolved directory regardless of whether MEMORY.md exists yet;
    the caller decides whether to act on missing files.
    """
    explicit = os.environ.get("MEMORY_INDEX_DIR")
    if explicit:
        return Path(explicit).expanduser()
    workspace = (
        os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("CODEX_WORKSPACE")
        or str(Path.cwd())
    )
    slug = str(Path(workspace).expanduser().resolve()).replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / "memory"


MEMORY_DIR = _resolve_memory_dir()
MEMORY_MD = MEMORY_DIR / "MEMORY.md"
ARCHIVE_MD = MEMORY_DIR / "MEMORY_ARCHIVE.md"
DEFAULT_CAP = 200

SECTION_WEIGHTS = {"User": 1000, "Reference": 600, "Project": 400, "Feedback": 200}
ENTRY_RE = re.compile(
    r"^\s*-\s+\[(?P<title>[^\]]+)\]\((?P<file>[^\)]+)\)\s*[—-]\s*(?P<desc>.*)$"
)
SECTION_RE = re.compile(r"^##\s+(?P<name>\S+)\s*$")


@dataclass
class Entry:
    section: str
    title: str
    file: str
    desc: str
    raw_line: str
    score: float = 0.0
    pinned: bool = False
    reason: str = ""


@dataclass
class Document:
    preamble: list[str] = field(default_factory=list)
    sections: dict[str, list[Entry]] = field(default_factory=dict)
    section_order: list[str] = field(default_factory=list)


def parse_memory(path: Path) -> Document:
    doc = Document()
    if not path.exists():
        return doc
    current = None
    in_preamble = True
    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            sec_match = SECTION_RE.match(line)
            if sec_match:
                in_preamble = False
                current = sec_match.group("name")
                if current not in doc.sections:
                    doc.sections[current] = []
                    doc.section_order.append(current)
                continue
            if in_preamble:
                doc.preamble.append(line)
                continue
            entry_match = ENTRY_RE.match(line)
            if entry_match and current is not None:
                doc.sections[current].append(
                    Entry(
                        section=current,
                        title=entry_match.group("title"),
                        file=entry_match.group("file"),
                        desc=entry_match.group("desc").strip(),
                        raw_line=line,
                    )
                )
    return doc


def read_frontmatter_pin(file_path: Path) -> bool:
    if not file_path.exists():
        return False
    try:
        with file_path.open() as fh:
            head = fh.read(2048)
    except OSError:
        return False
    m = re.search(r"^---\s*\n(?P<body>.*?)\n---\s*\n", head, re.DOTALL | re.MULTILINE)
    if not m:
        return False
    return bool(
        re.search(r"^pin:\s*true\s*$", m.group("body"), re.MULTILINE | re.IGNORECASE)
    )


def score_entry(entry: Entry, memory_dir: Path, now: dt.datetime) -> Entry:
    score = SECTION_WEIGHTS.get(entry.section, 100)
    reasons = [f"section={entry.section}({score})"]

    desc_low = entry.desc.lower()
    if "see workspace agents.md" in desc_low or "see global agents.md" in desc_low:
        score -= 200
        reasons.append("pointer-only(-200)")

    file_path = memory_dir / entry.file
    entry.pinned = read_frontmatter_pin(file_path)
    if entry.pinned:
        score += 10000
        reasons.append("pinned(+10000)")

    if file_path.exists():
        mtime = dt.datetime.fromtimestamp(file_path.stat().st_mtime)
        days_old = (now - mtime).days
        if days_old < 30:
            score += 80
            reasons.append(f"fresh({days_old}d,+80)")
        elif days_old < 90:
            score += 30
            reasons.append(f"recent({days_old}d,+30)")
        elif days_old > 365:
            score -= 50
            reasons.append(f"stale({days_old}d,-50)")
        else:
            reasons.append(f"age={days_old}d")
    else:
        score -= 100
        reasons.append("file-missing(-100)")

    entry.score = score
    entry.reason = " ".join(reasons)
    return entry


def score_document(doc: Document, memory_dir: Path) -> None:
    now = dt.datetime.now()
    for section in doc.section_order:
        for entry in doc.sections[section]:
            score_entry(entry, memory_dir, now)


def total_lines(doc: Document) -> int:
    n = len(doc.preamble)
    for section in doc.section_order:
        n += 2  # blank line + ## header
        n += len(doc.sections[section])
    return n


def select_demotions(doc: Document, cap: int) -> list[Entry]:
    excess = total_lines(doc) - cap
    if excess <= 0:
        return []
    candidates: list[Entry] = []
    for section in doc.section_order:
        for entry in doc.sections[section]:
            if not entry.pinned:
                candidates.append(entry)
    candidates.sort(key=lambda e: e.score)
    return candidates[:excess]


def render_document(doc: Document) -> str:
    lines = list(doc.preamble)
    if lines and lines[-1] != "":
        lines.append("")
    for i, section in enumerate(doc.section_order):
        if i > 0 or lines[-1] != "":
            if lines[-1] != "":
                lines.append("")
        lines.append(f"## {section}")
        for entry in doc.sections[section]:
            lines.append(entry.raw_line)
    return "\n".join(lines).rstrip() + "\n"


def append_to_archive(archive_path: Path, demoted: list[Entry], cap: int) -> None:
    today = dt.date.today().isoformat()
    by_section: dict[str, list[Entry]] = {}
    for entry in demoted:
        by_section.setdefault(entry.section, []).append(entry)
    header_needed = not archive_path.exists()
    with archive_path.open("a") as fh:
        if header_needed:
            fh.write("# Memory Archive\n\n")
            fh.write(
                "Demoted entries from MEMORY.md, preserved here so nothing is lost. "
                "Files remain on disk in the same directory; this index is not "
                "auto-loaded but is grep-discoverable. Restore with "
                "`memory_curator.py restore <slug>`.\n\n"
            )
        fh.write(f"## Demotion {today} (cap={cap})\n\n")
        for section, entries in by_section.items():
            fh.write(f"### {section}\n")
            for entry in entries:
                fh.write(
                    f"{entry.raw_line}  <!-- score={entry.score:.0f} {entry.reason} -->\n"
                )
            fh.write("\n")


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    os.replace(tmp, path)


def cmd_status(args: argparse.Namespace) -> int:
    doc = parse_memory(MEMORY_MD)
    score_document(doc, MEMORY_DIR)
    total = total_lines(doc)
    print(f"MEMORY.md: {total} lines (cap={args.cap}, headroom={args.cap - total})")
    for section in doc.section_order:
        n = len(doc.sections[section])
        print(f"  {section}: {n} entries")
    if ARCHIVE_MD.exists():
        with ARCHIVE_MD.open() as fh:
            archive_lines = sum(1 for _ in fh)
        print(f"MEMORY_ARCHIVE.md: {archive_lines} lines (cold storage)")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    doc = parse_memory(MEMORY_MD)
    score_document(doc, MEMORY_DIR)
    total = total_lines(doc)
    print(f"Current: {total} lines, cap={args.cap}")
    if total <= args.cap:
        print(f"Under cap by {args.cap - total} lines. No demotion needed.")
        if args.show_bottom:
            all_entries = [e for s in doc.section_order for e in doc.sections[s]]
            all_entries.sort(key=lambda e: e.score)
            print(
                f"\nBottom {args.show_bottom} by score (would go first if cap dropped):"
            )
            for entry in all_entries[: args.show_bottom]:
                print(f"  [{entry.score:5.0f}] {entry.section:9s} {entry.title}")
                print(f"           reason: {entry.reason}")
        return 0
    demoted = select_demotions(doc, args.cap)
    print(f"Excess: {total - args.cap} lines. Would demote {len(demoted)} entries:")
    for entry in demoted:
        print(f"  [{entry.score:5.0f}] {entry.section:9s} {entry.title}")
        print(f"           reason: {entry.reason}")
        print(f"           desc:   {entry.desc[:100]}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    doc = parse_memory(MEMORY_MD)
    score_document(doc, MEMORY_DIR)
    total = total_lines(doc)
    if total <= args.cap:
        if not args.quiet:
            print(f"Already under cap ({total} <= {args.cap}). No-op.")
        return 0
    demoted = select_demotions(doc, args.cap)
    if not demoted:
        if not args.quiet:
            print(
                f"No demotion candidates (all pinned?). Total={total}, cap={args.cap}."
            )
        return 1
    demoted_set = {(e.section, e.file) for e in demoted}
    for section in doc.section_order:
        doc.sections[section] = [
            e for e in doc.sections[section] if (e.section, e.file) not in demoted_set
        ]
    if args.dry_run:
        print(
            f"[dry-run] Would demote {len(demoted)} entries, new total={total_lines(doc)}"
        )
        return 0
    atomic_write(MEMORY_MD, render_document(doc))
    append_to_archive(ARCHIVE_MD, demoted, args.cap)
    if not args.quiet:
        print(f"Demoted {len(demoted)} entries. New total={total_lines(doc)} lines.")
        for entry in demoted:
            print(f"  -> archived: {entry.section} {entry.title}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    if not ARCHIVE_MD.exists():
        print("No archive file exists.", file=sys.stderr)
        return 1
    archive_text = ARCHIVE_MD.read_text()
    pattern = re.compile(
        rf"^(\s*-\s+\[[^\]]*\]\((?:{re.escape(args.slug)}\.md|[^\)]*{re.escape(args.slug)}[^\)]*)\)\s*[—-]\s*.*?)(?:\s+<!--.*?-->)?$",
        re.MULTILINE,
    )
    section_pattern = re.compile(r"^### (\S+)\s*$", re.MULTILINE)
    lines = archive_text.split("\n")
    found_line = None
    found_idx = None
    current_section = None
    for i, line in enumerate(lines):
        sec_m = section_pattern.match(line)
        if sec_m:
            current_section = sec_m.group(1)
            continue
        m = pattern.match(line)
        if m:
            found_line = m.group(1)
            found_idx = i
            break
    if found_line is None or found_idx is None:
        print(f"Slug not found in archive: {args.slug}", file=sys.stderr)
        return 1
    doc = parse_memory(MEMORY_MD)
    score_document(doc, MEMORY_DIR)
    if current_section and current_section not in doc.sections:
        doc.sections[current_section] = []
        doc.section_order.append(current_section)
    entry_match = ENTRY_RE.match(found_line)
    if not entry_match:
        print(f"Could not parse archived line: {found_line}", file=sys.stderr)
        return 1
    new_entry = Entry(
        section=current_section or "Project",
        title=entry_match.group("title"),
        file=entry_match.group("file"),
        desc=entry_match.group("desc").strip(),
        raw_line=found_line,
    )
    doc.sections[new_entry.section].append(new_entry)
    if total_lines(doc) > args.cap:
        print(
            f"Restoring would exceed cap ({total_lines(doc)} > {args.cap}). "
            "Pin a high-value entry or raise --cap before restoring.",
            file=sys.stderr,
        )
        return 1
    atomic_write(MEMORY_MD, render_document(doc))
    lines.pop(found_idx)
    atomic_write(ARCHIVE_MD, "\n".join(lines))
    print(f"Restored {new_entry.title} to {new_entry.section}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--cap", type=int, default=DEFAULT_CAP, help="Hard line cap on MEMORY.md"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Print current state")

    audit = sub.add_parser("audit", help="Show what would be demoted")
    audit.add_argument(
        "--show-bottom",
        type=int,
        default=0,
        help="Show N lowest-scored even if under cap",
    )

    apply_p = sub.add_parser("apply", help="Execute demotion")
    apply_p.add_argument("--dry-run", action="store_true")
    apply_p.add_argument("--quiet", action="store_true")

    restore_p = sub.add_parser("restore", help="Restore an archived entry")
    restore_p.add_argument(
        "slug", help="Filename stem (e.g. feedback_html_for_human_review)"
    )

    args = p.parse_args()
    dispatch = {
        "status": cmd_status,
        "audit": cmd_audit,
        "apply": cmd_apply,
        "restore": cmd_restore,
    }
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
