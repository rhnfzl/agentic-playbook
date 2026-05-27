#!/usr/bin/env python3
"""Unified check dispatcher (per ADR-0024 sibling pattern).

Replaces the eight sequential script invocations in `make check` with one
Python dispatcher that iterates scripts/checks/CHECKS. Each check returns
a structured CheckResult; the dispatcher aggregates exit code (any fail =
overall fail).

`scripts/eval_runner.py` is intentionally NOT in this dispatcher; it now
runs via `make eval` instead. Evals are slow (LLM-judge driven) and
conceptually closer to integration tests than static analysis.

Usage:

    python3 scripts/check.py [--help]

No flags today; the script always runs every gate in
scripts/checks/CHECKS. `--help` lists each gate so contributors can see
the lineup without grepping the source.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters._loader import PlaybookContent  # noqa: E402
from checks import CHECKS, CheckContext  # noqa: E402


def _print_help() -> None:
    print(
        "scripts/check.py -- unified make-check dispatcher\n"
        "\n"
        "Iterates every gate in scripts/checks/CHECKS and prints a [name] "
        "section plus the gate's stdout details. Exit code is the max "
        "severity across gates (any fail -> 1, any warn -> 0 with warning "
        "summary, all ok -> 0).\n"
        "\n"
        "Registered gates:"
    )
    for check in CHECKS:
        print(f"  - {check.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check.py",
        description="Unified make-check dispatcher. Runs every gate in scripts/checks/.",
        add_help=True,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the registered gate list and exit.",
    )
    args = parser.parse_args()
    if args.list:
        _print_help()
        return 0
    return _run()


def _run() -> int:
    ctx = CheckContext(
        repo_root=REPO_ROOT,
        content=PlaybookContent.load(REPO_ROOT),
    )
    failures: list[str] = []
    warns: list[str] = []
    for check in CHECKS:
        print(f"\n[{check.name}]")
        try:
            result = check.run(ctx)
        except Exception as exc:
            print(f"  x  {check.name} raised {type(exc).__name__}: {exc}")
            failures.append(check.name)
            continue
        # v0.8 (C3): the dispatcher prints CheckResult.details so the
        # legacy-wrapped checks surface their original stdout output.
        # Self-contained checks (hook_source_unification, pyright_zero,
        # human_html_allowlist) populate details directly with the same
        # shape; the dispatcher only adds the [name] header above.
        for line in result.details:
            print(line)
        if result.status == "fail":
            failures.append(check.name)
        elif result.status == "warn":
            warns.append(check.name)
    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed: {', '.join(failures)}")
        return 1
    if warns:
        print(f"OK with {len(warns)} warning(s): {', '.join(warns)}")
    else:
        print(f"OK: {len(CHECKS)} check(s) passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
