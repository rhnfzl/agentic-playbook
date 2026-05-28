#!/usr/bin/env python3
"""Per-skill telemetry report (CLI).

Reads the local JSONL the collector writes and prints per-skill
trigger count, p50/p95 latency, total tokens, and last-fired
timestamp. Defaults to a 30-day window.

Use cases:
  * see what's actually being used vs what's just sitting in the repo
  * spot decay candidates (no triggers in 60 days)
  * compare adapter coverage per skill

Disabled when TELEMETRY=off (or any of the other disable env vars).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow direct script invocation: ensure scripts/ on path so the
# `telemetry` package resolves.
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from telemetry import is_enabled, storage_path  # noqa: E402
from telemetry.ingest import aggregate, filter_recent, read_jsonl  # noqa: E402


def _format_table(aggregates: list, window_days: int) -> list[str]:
    if not aggregates:
        return [
            f"  i  no skill events recorded in the last {window_days}d",
            f"     storage: {storage_path()}",
        ]
    header = (
        f"  {'SKILL':30}  {'TRIGGERS':>8}  {'p50ms':>8}  {'p95ms':>8}  "
        f"{'IN':>8}  {'OUT':>8}  {'LAST':19}"
    )
    rows = [header]
    for agg in aggregates:
        rows.append(
            f"  {agg.skill[:30]:30}  {agg.trigger_count:>8d}  "
            f"{agg.p50_latency_ms:>8.0f}  {agg.p95_latency_ms:>8.0f}  "
            f"{agg.total_input_tokens:>8d}  {agg.total_output_tokens:>8d}  "
            f"{agg.last_fired_at[:19]:19}"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=30,
        help="window size in days (default 30; 0 = all-time)",
    )
    parser.add_argument(
        "--input", type=Path, default=None,
        help=f"telemetry JSONL path (defaults to {storage_path()})",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON instead of a text table",
    )
    args = parser.parse_args(argv)

    if not is_enabled():
        print("  .  telemetry disabled (TELEMETRY=off); nothing to report")
        return 0

    records = read_jsonl(args.input)
    if args.days > 0:
        records = filter_recent(records, args.days)
    aggregates = aggregate(records)

    if args.json:
        payload = [a._asdict() for a in aggregates]
        print(json.dumps(payload, indent=2))
        return 0

    for line in _format_table(aggregates, args.days):
        print(line)
    print(f"\n  ok  {len(aggregates)} skill(s) reported "
          f"over last {args.days}d (0 = all-time)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
