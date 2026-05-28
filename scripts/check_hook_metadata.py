#!/usr/bin/env python3
"""Validate every hook script ships the v0.5 PLAYBOOK-HOOK-* headers.

Per ADR-0029 + ADR-0033 sibling work: each hook script under `hooks/`
must declare its event and matcher inline so the installer can register
it consistently across Claude / Codex / Cursor / Cline / Copilot.

  # PLAYBOOK-HOOK-EVENT: <PascalCase event>          required
  # PLAYBOOK-HOOK-MATCHER: <regex-OR string OR `*`>  required

Missing either header is a check failure. The optional
PLAYBOOK-HOOK-CURSOR-MATCHER header is NOT required (auto-derived from
the Claude matcher by hook_registration.py when absent).

v0.6: underscore-prefixed files (e.g. hooks/_cascade-translate.sh) are
adapter-internal helpers, not registered hooks. The loader
(scripts/adapters/_reader.py::load_hooks) skips them, so this checker
mirrors that convention and does not require PLAYBOOK-HOOK-* headers
on them. Per ADR-0035.

Exit 0 if every registered hook has both headers; 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


_EVENT_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-EVENT:\s*(\w+)\s*$")
_MATCHER_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-MATCHER:\s*(.+?)\s*$")
_ADAPTERS_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-ADAPTERS:\s*(.+?)\s*$")

# Must mirror hook_registration._HOOK_CAPABLE_ADAPTERS.
_VALID_ADAPTERS = frozenset(
    {"claude-code", "codex", "cursor", "cline", "copilot", "windsurf"}
)


def _scan(hook_path: Path) -> tuple[bool, bool, set[str] | None]:
    """Return (has_event_header, has_matcher_header, declared_adapters_or_None).

    declared_adapters is None when the header is absent (= apply to every
    hook-capable adapter, valid). It's a set when the header is present;
    callers validate the set is non-empty AND all entries are known
    adapter slugs. v0.8 Codex round-9 fix: an empty or all-typo
    ADAPTERS list would otherwise silently disable the hook for every
    adapter while still passing make check.
    """
    has_event = False
    has_matcher = False
    declared: set[str] | None = None
    try:
        body = hook_path.read_text(encoding="utf-8")
    except OSError:
        return False, False, None
    for line in body.splitlines()[:20]:
        stripped = line.strip()
        if _EVENT_RE.match(stripped):
            has_event = True
        if _MATCHER_RE.match(stripped):
            has_matcher = True
        m = _ADAPTERS_RE.match(stripped)
        if m:
            raw = m.group(1).strip()
            declared = {tok.strip() for tok in raw.split(",") if tok.strip()}
    return has_event, has_matcher, declared


def main(repo_root: Path | None = None) -> int:
    repo_root = repo_root or Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): hooks moved to base/ + overlays/team/. Walk both.
    hook_roots = [
        repo_root / "base" / "hooks",
        repo_root / "overlays" / "team" / "hooks",
    ]
    hook_roots = [r for r in hook_roots if r.is_dir()]
    if not hook_roots:
        print(
            "  no hooks dirs at base/hooks/ or overlays/team/hooks/; nothing to check"
        )
        return 0

    missing_event: list[Path] = []
    missing_matcher: list[Path] = []
    bad_adapters: list[tuple[Path, str]] = []
    total = 0
    hook_paths: list = []
    for root in hook_roots:
        hook_paths.extend(sorted(root.glob("*.sh")))
    for hook in hook_paths:
        # Skip underscore-prefixed helper scripts (v0.6 / ADR-0035): they
        # are adapter-internal wrappers, not registered hooks. The loader
        # in scripts/adapters/_reader.py::load_hooks applies the same
        # filter.
        if hook.name.startswith("_"):
            continue
        total += 1
        has_event, has_matcher, declared_adapters = _scan(hook)
        if not has_event:
            missing_event.append(hook)
        if not has_matcher:
            missing_matcher.append(hook)
        # v0.8 Codex round-9 fix: an empty or all-typo ADAPTERS list
        # silently disables the hook for every adapter while otherwise
        # passing make check. Fail loudly so typos are caught at gate
        # time, not runtime.
        if declared_adapters is not None:
            unknown = declared_adapters - _VALID_ADAPTERS
            valid = declared_adapters & _VALID_ADAPTERS
            if unknown:
                bad_adapters.append((hook, f"unknown slug(s): {sorted(unknown)}"))
            elif not valid:
                bad_adapters.append((hook, "empty after parse"))

    if missing_event or missing_matcher or bad_adapters:
        if missing_event:
            print(
                f"  FAIL  {len(missing_event)} hook(s) missing # PLAYBOOK-HOOK-EVENT:",
                file=sys.stderr,
            )
            for h in missing_event:
                print(f"    {h.relative_to(repo_root)}", file=sys.stderr)
        if missing_matcher:
            print(
                f"  FAIL  {len(missing_matcher)} hook(s) missing # PLAYBOOK-HOOK-MATCHER:",
                file=sys.stderr,
            )
            for h in missing_matcher:
                print(f"    {h.relative_to(repo_root)}", file=sys.stderr)
        if bad_adapters:
            print(
                f"  FAIL  {len(bad_adapters)} hook(s) with bad PLAYBOOK-HOOK-ADAPTERS:",
                file=sys.stderr,
            )
            for hook, why in bad_adapters:
                print(
                    f"    {hook.relative_to(repo_root)}: {why}",
                    file=sys.stderr,
                )
            print(
                "  valid slugs: claude-code, codex, cursor, cline, copilot, windsurf",
                file=sys.stderr,
            )
        print(
            "  fix: add the two header lines after the shebang. See hooks/README.md "
            "and ADR-0029 for the convention.",
            file=sys.stderr,
        )
        return 1

    roots_str = ", ".join(str(r) for r in hook_roots)
    print(
        f"  ok  every hook in {roots_str} declares both PLAYBOOK-HOOK-EVENT and "
        f"PLAYBOOK-HOOK-MATCHER ({total} hook(s) scanned)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
