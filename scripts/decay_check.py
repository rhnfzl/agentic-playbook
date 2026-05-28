#!/usr/bin/env python3
"""
Warn on content with stale last_reviewed dates; block at hard cutoff.

Two content classes share the same date-based decay bands today
(ADR-0044 added trajectories):

  Skills (base/skills/<cat>/<name>/SKILL.md):
    - 60-day notice band
    - 90-day warn
    - 180-day block

  Trajectories (base/trajectories/<skill>/<scenario>.yaml):
    - 60-day notice (matches skills)
    - 90-day warn
    - 180-day block

The design intuition is that trajectories rot faster than skills because
they're tied to a specific model version (`model_pinned` frontmatter).
The first cut keeps trajectory bands identical to skills until the Phase
1 harness produces actual drift data; tightening before then would
generate noise the team is likely to stop reading. ADR-0044 lists this
failure mode in its reject-if criteria.

v0.14 (ADR-0048) added a usage-based layer. When the local telemetry
JSONL is present AND `TELEMETRY` is not set to off, the check also flags
skills that have not fired in 60+ days regardless of their
`last_reviewed` date. This catches "I reviewed it last week but no one
uses it" decay that the date-based bands miss. Disabled cleanly when
`TELEMETRY=off`.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple


class _DecayBands(NamedTuple):
    notice: int
    warn: int
    block: int


SKILL_BANDS = _DecayBands(notice=60, warn=90, block=180)
TRAJECTORY_BANDS = _DecayBands(notice=60, warn=90, block=180)

USAGE_DECAY_DAYS = 60   # no triggers in this many days = decaying

# Back-compat aliases for any consumer that imports these constants directly.
NOTICE_DAYS = SKILL_BANDS.notice
WARN_DAYS = SKILL_BANDS.warn
BLOCK_DAYS = SKILL_BANDS.block


def _check_files(
    paths: list[Path],
    repo_root: Path,
    bands: _DecayBands,
    today: date,
    label: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (notices, warnings, errors, info_lines) for the path set."""
    notices: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    info: list[str] = []

    for p in paths:
        rel = p.relative_to(repo_root)
        try:
            content = p.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: cannot read ({exc})")
            continue

        match = re.search(r"last_reviewed:\s*(\d{4}-\d{2}-\d{2})", content)
        if not match:
            errors.append(f"{rel}: no last_reviewed field")
            continue

        try:
            last = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{rel}: invalid last_reviewed date format")
            continue

        age = (today - last).days

        if age >= bands.block:
            errors.append(
                f"{rel}: last_reviewed {age}d ago (>={bands.block}d, BLOCKING for {label})"
            )
        elif age >= bands.warn:
            warnings.append(
                f"{rel}: last_reviewed {age}d ago (>={bands.warn}d, {label})"
            )
        elif age >= bands.notice:
            notices.append(
                f"{rel}: last_reviewed {age}d ago "
                f"({bands.notice}-{bands.warn}d band for {label}, refresh soon)"
            )
        else:
            info.append(f"{rel}: ok ({age}d)")

    return notices, warnings, errors, info


def _usage_decay_findings(
    skill_paths: list[Path],
    repo_root: Path,
    today: date,
) -> list[str]:
    """Telemetry-aware decay: flag skills with no triggers in 60d.

    Silent no-op if `TELEMETRY=off`, telemetry deps unavailable, or
    no JSONL recorded yet. Returns notice strings (advisory band,
    not blocking) so the date-based decay stays the single source
    of truth for build pass/fail.
    """
    try:
        from telemetry import is_enabled, storage_path
        from telemetry.ingest import aggregate, read_jsonl
    except ImportError:
        return []
    if not is_enabled():
        return []
    if not storage_path().is_file():
        return []
    records = read_jsonl()
    aggregates = aggregate(records)
    fired_by_skill: dict[str, str] = {a.skill: a.last_fired_at for a in aggregates}

    notices: list[str] = []
    for skill_md in skill_paths:
        skill_name = skill_md.parent.name
        rel = skill_md.relative_to(repo_root)
        last = fired_by_skill.get(skill_name)
        if last is None:
            notices.append(
                f"{rel}: no telemetry events recorded (no usage signal)"
            )
            continue
        try:
            last_date = datetime.strptime(last[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        idle = (today - last_date).days
        if idle >= USAGE_DECAY_DAYS:
            notices.append(
                f"{rel}: last fired {idle}d ago "
                f"(>={USAGE_DECAY_DAYS}d, usage-decay band)"
            )
    return notices


def _gather_skill_files(repo_root: Path) -> list[Path]:
    skill_roots = [
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ]
    skill_paths: list[Path] = []
    for root in skill_roots:
        if not root.is_dir():
            continue
        skill_paths.extend(sorted(root.rglob("SKILL.md")))
    return skill_paths


def _gather_trajectory_files(repo_root: Path) -> list[Path]:
    trajectory_roots = [
        repo_root / "base" / "trajectories",
        repo_root / "overlays" / "team" / "trajectories",
    ]
    paths: list[Path] = []
    for root in trajectory_roots:
        if not root.is_dir():
            continue
        for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            paths.extend(sorted(skill_dir.glob("*.yaml")))
    return paths


def main(
    repo_root: Path | None = None,
    today: date | None = None,
) -> int:
    """Entry point.

    `repo_root` lets tests aim the check at a tmp tree; CLI invocation
    discovers the playbook checkout automatically.

    `today` lets tests fix the reference date so band-boundary assertions
    do not rot as the calendar advances. CLI use leaves it None.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent
    if today is None:
        today = date.today()
    skill_paths = _gather_skill_files(repo_root)
    trajectory_paths = _gather_trajectory_files(repo_root)

    if not skill_paths and not trajectory_paths:
        print("  no skill or trajectory roots found; nothing to check")
        return 0

    all_notices: list[str] = []
    all_warnings: list[str] = []
    all_errors: list[str] = []

    if skill_paths:
        n, w, e, _ = _check_files(skill_paths, repo_root, SKILL_BANDS, today, "skill")
        all_notices.extend(n)
        all_warnings.extend(w)
        all_errors.extend(e)
    if trajectory_paths:
        n, w, e, _ = _check_files(
            trajectory_paths, repo_root, TRAJECTORY_BANDS, today, "trajectory"
        )
        all_notices.extend(n)
        all_warnings.extend(w)
        all_errors.extend(e)
    all_notices.extend(_usage_decay_findings(skill_paths, repo_root, today))

    if all_notices:
        print(f"\nDecay check: {len(all_notices)} notice(s)")
        for n in all_notices:
            print(f"  .  {n}")

    if all_warnings:
        print(f"\nDecay check: {len(all_warnings)} warning(s)")
        for w in all_warnings:
            print(f"  !  {w}")

    if all_errors:
        print(f"\nDecay check: {len(all_errors)} error(s)")
        for e in all_errors:
            print(f"  x  {e}")
        return 1

    total = len(skill_paths) + len(trajectory_paths)
    if not all_warnings and not all_notices:
        print(
            f"  ok  all {total} content file(s) reviewed within their notice band "
            f"(skill: {SKILL_BANDS.notice}d, trajectory: {TRAJECTORY_BANDS.notice}d)"
        )
    elif not all_warnings:
        print(
            f"  ok  all {total} content file(s) reviewed within warn band "
            f"({len(all_notices)} approaching the warn line)"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
