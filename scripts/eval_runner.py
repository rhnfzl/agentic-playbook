#!/usr/bin/env python3
"""
Eval harness for high-risk skills (v0.3, ADR-0017).

Reads evals/<skill>/cases.yaml. For each case, applies a small set of
assertions against the skill's SKILL.md, frontmatter, and reference
files. Prints pass/fail per case + per-skill summary.

v0.3 mode: STATIC assertions (no LLM call). Each assertion is a small,
deterministic check the skill body must satisfy. The judge.md alongside
documents the scoring rubric in human-readable form.

Assertion types:
  - section_present: assert SKILL.md has a heading matching the pattern
  - section_absent:  assert SKILL.md does NOT have a heading matching
  - body_contains:   assert SKILL.md body contains a regex pattern
  - body_absent:     assert SKILL.md body does NOT contain a regex pattern
  - frontmatter_has: assert frontmatter contains a key=value pair
  - reference_exists: assert <skill-dir>/references/<file> exists

Future v0.4+ mode: DYNAMIC: spawn a subagent with each case input,
capture output, judge via the per-suite judge.md.

Usage:
  python3 scripts/eval_runner.py                   # run all eval suites
  python3 scripts/eval_runner.py <suite-name>      # run one suite
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "evals"

# Simple YAML-ish parser. We use a strict subset:
#   - top-level "cases:" key only
#   - list of mappings, each with "name", "skill", "assertions"
#   - assertions is a list of mappings with "type" and "args" (or inline)
# Avoids the PyYAML dependency consistent with frontmatter_lint.


def _parse_cases_yaml(text: str) -> list[dict]:
    """Naive parser tuned to the cases.yaml shape we control."""
    cases: list[dict] = []
    current_case: dict | None = None
    current_assertion: dict | None = None
    in_cases = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("cases:"):
            in_cases = True
            continue
        if not in_cases:
            continue
        # New case: line is "- name: ..."
        if line.startswith("  - name:"):
            if current_case:
                cases.append(current_case)
            current_case = {
                "name": line.split(":", 1)[1].strip().strip('"').strip("'"),
                "assertions": [],
            }
            current_assertion = None
            continue
        if current_case is None:
            continue
        if line.startswith("    skill:"):
            current_case["skill"] = line.split(":", 1)[1].strip().strip('"').strip("'")
            continue
        # v0.11 (ADR-0040): required_scope is an optional per-case YAML key
        # listing overlay names the case depends on. eval_runner filters
        # cases whose required_scope is not satisfied by the active scope.
        if line.startswith("    required_scope:"):
            raw_val = line.split(":", 1)[1].strip()
            # Accept "[a, b]" inline shape (simple).
            if raw_val.startswith("[") and raw_val.endswith("]"):
                inner = raw_val[1:-1].strip()
                items = [
                    s.strip().strip('"').strip("'")
                    for s in inner.split(",")
                    if s.strip()
                ]
                current_case["required_scope"] = items
            continue
        if line.startswith("    assertions:"):
            continue
        # Each assertion is "      - type: ..." with optional "        pattern: ..." / "        value: ..."
        if line.startswith("      - type:"):
            if current_assertion:
                current_case["assertions"].append(current_assertion)
            current_assertion = {
                "type": line.split(":", 1)[1].strip().strip('"').strip("'")
            }
            continue
        if line.startswith("        ") and current_assertion is not None:
            key, _, val = line.strip().partition(":")
            current_assertion[key.strip()] = val.strip().strip('"').strip("'")
    if current_assertion and current_case:
        current_case["assertions"].append(current_assertion)
    if current_case:
        cases.append(current_case)
    return cases


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    try:
        end = text.index("---", 3)
    except ValueError:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^(\w[\w\-]*)\s*:\s*(.*)$", line.strip())
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def _section_pattern_matches(text: str, pattern: str) -> bool:
    rx = re.compile(rf"^##\s+.*{pattern}.*$", re.M | re.I)
    return bool(rx.search(text))


def _run_assertion(assertion: dict, skill_md: Path) -> tuple[bool, str]:
    a_type = assertion.get("type", "")
    text = skill_md.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)
    body = text.split("---", 2)[-1] if text.startswith("---") else text

    if a_type == "section_present":
        pat = assertion.get("pattern", "")
        ok = _section_pattern_matches(body, pat)
        return ok, f"section matching '{pat}' {'present' if ok else 'missing'}"

    if a_type == "section_absent":
        pat = assertion.get("pattern", "")
        ok = not _section_pattern_matches(body, pat)
        return (
            ok,
            f"section matching '{pat}' {'absent' if ok else 'PRESENT (must be absent)'}",
        )

    if a_type == "body_contains":
        pat = assertion.get("pattern", "")
        ok = bool(re.search(pat, body, re.I))
        return ok, f"body {'contains' if ok else 'MISSING'} '{pat}'"

    if a_type == "body_absent":
        pat = assertion.get("pattern", "")
        ok = not re.search(pat, body, re.I)
        return ok, f"body {'cleanly absent' if ok else 'CONTAINS forbidden'} '{pat}'"

    if a_type == "frontmatter_has":
        key = assertion.get("key", "")
        value = assertion.get("value", "")
        actual = fm.get(key, "")
        ok = value.lower() in actual.lower() if value else bool(actual)
        return (
            ok,
            f"frontmatter[{key}] = '{actual}' {'matches' if ok else 'MISMATCH'} '{value}'",
        )

    if a_type == "reference_exists":
        ref = assertion.get("path", "")
        ok = (skill_md.parent / ref).exists()
        return ok, f"reference '{ref}' {'exists' if ok else 'MISSING'}"

    return False, f"unknown assertion type: {a_type}"


def run_suite(suite_dir: Path, active_scope: set[str] | None = None) -> tuple[int, int]:
    """Return (pass_count, fail_count) for one eval suite.

    v0.11 (ADR-0040): when `active_scope` is provided, cases whose
    `required_scope` is not a subset of the active scope are SKIPPED
    (counted as neither pass nor fail).
    """
    cases_path = suite_dir / "cases.yaml"
    if not cases_path.exists():
        print(f"  SKIP {suite_dir.name}: no cases.yaml")
        return 0, 0

    cases = _parse_cases_yaml(cases_path.read_text(encoding="utf-8"))
    if not cases:
        print(f"  SKIP {suite_dir.name}: cases.yaml empty")
        return 0, 0

    pass_count = 0
    fail_count = 0
    print(f"\n  {suite_dir.name}:")
    for case in cases:
        name = case.get("name", "(unnamed)")
        required_scope = set(case.get("required_scope", []))
        if active_scope is not None and required_scope and not required_scope.issubset(active_scope):
            print(
                f"    [SKIP] {name}: required_scope "
                f"{sorted(required_scope)} not in active scope "
                f"{sorted(active_scope)}"
            )
            continue
        skill_path = case.get("skill", "")
        if not skill_path:
            print(f"    [FAIL] {name}: missing skill: path")
            fail_count += 1
            continue
        skill_md = REPO_ROOT / skill_path
        if not skill_md.exists():
            print(f"    [FAIL] {name}: skill file {skill_path} not found")
            fail_count += 1
            continue
        all_passed = True
        failures: list[str] = []
        for assertion in case.get("assertions", []):
            ok, msg = _run_assertion(assertion, skill_md)
            if not ok:
                all_passed = False
                failures.append(msg)
        if all_passed:
            pass_count += 1
            print(f"    [PASS] {name}")
        else:
            fail_count += 1
            print(f"    [FAIL] {name}")
            for f in failures:
                print(f"           - {f}")
    return pass_count, fail_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval harness for high-risk skills")
    parser.add_argument("suite", nargs="?", help="Run only this suite (directory name)")
    parser.add_argument(
        "--scope",
        default=None,
        help=(
            "v0.11 (ADR-0040): active content scope (comma-separated overlay "
            "names, e.g. 'team'). Cases whose required_scope is not satisfied "
            "by the active scope are SKIPPED. Omit to run all cases (no scope "
            "filter)."
        ),
    )
    args = parser.parse_args()

    active_scope: set[str] = set()
    if args.scope:
        active_scope = {s.strip() for s in args.scope.split(",") if s.strip()}

    if not EVALS_DIR.exists():
        print("no evals/ dir; nothing to run")
        return 0

    suites: list[Path] = []
    if args.suite:
        target = EVALS_DIR / args.suite
        if not target.is_dir():
            print(f"suite not found: evals/{args.suite}")
            return 1
        suites = [target]
    else:
        suites = sorted(p for p in EVALS_DIR.iterdir() if p.is_dir())

    total_pass = 0
    total_fail = 0
    print(f"Running {len(suites)} eval suite(s)")
    for suite in suites:
        p, f = run_suite(suite, active_scope if active_scope else None)
        total_pass += p
        total_fail += f
    print()
    print(f"  {total_pass} passed, {total_fail} failed")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
