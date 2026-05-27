#!/usr/bin/env python3
"""
Per-project update: re-apply playbook content to a target initialized by
playbook_init.py.

Reads target/.playbook-config.yaml (naive parse, no PyYAML dep) and:
  1. Refreshes the AGENTS.md pointer header to the current playbook root
  2. Bumps the last_reviewed frontmatter line to today
  3. Per ADR-0028 (v0.5): if install_mode is symlink or copy, runs the
     TargetMaterializer to populate target/.agents/ with the profile's
     content + projects per-tool symlinks + generates target/AGENTS.md
     managed block. install_mode=pointer keeps the v0.4 pointer-only
     behavior.

Usage:
  python3 scripts/playbook_update.py --target /path/to/project
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from adapters._loader import PlaybookContent  # noqa: E402
from agents_md import AgentsMd  # noqa: E402
from playbook_profile import (  # noqa: E402
    filter_content,
    load_profiles,
    parse_profile_arg,
    validate_profile_scope,
)
from target_materializer import (  # noqa: E402
    TargetMaterializer,
    prune_orphans,
    write_lockfile,
)


def parse_config(text: str) -> dict[str, str]:
    """Naive parser for .playbook-config.yaml top-level scalar fields."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = re.match(r"^([a-z_]+):\s*\"?([^\"]*)\"?\s*$", stripped)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def refresh_pointer(target: Path) -> int:
    """Refresh AGENTS.md pointer + last_reviewed via the AgentsMd document type.

    Used by every install_mode (pointer / symlink / copy). The
    TargetMaterializer also rewrites target/AGENTS.md via a managed block,
    but that block respects whatever pointer the file already has, so the
    refresh happens before materialization.
    """
    agents_md_path = target / "AGENTS.md"
    if not agents_md_path.exists():
        print(
            f"ERROR: {agents_md_path} not found; run playbook_init.py first",
            file=sys.stderr,
        )
        return 1

    doc = AgentsMd.load(agents_md_path)
    refreshed = doc.with_refreshed_pointer(REPO_ROOT)
    if refreshed is not doc:
        refreshed.save_to(agents_md_path)
        print(f"Pointer refreshed in {agents_md_path}")
    else:
        print(f"Pointer already current in {agents_md_path}")

    today = date.today().isoformat()
    bumped = refreshed.with_last_reviewed(today)
    if bumped is not refreshed:
        bumped.save_to(agents_md_path)
        print(f"last_reviewed bumped to {today}")
    return 0


def materialize_content(
    target: Path,
    profile_name: str,
    install_mode: str,
    scope: str | None = None,
) -> int:
    """Run the TargetMaterializer and prune orphans regardless of mode.

    v0.7 (ADR-0036 layer-2 fix): a prior install in symlink/copy mode that is
    now being re-run in pointer mode used to short-circuit out of materialize
    + prune. That left the .agents/ tree from the prior install on disk as
    silent orphans. Now we always go through TargetMaterializer.materialize,
    which routes pointer mode to _materialize_pointer (AGENTS.md only); the
    subsequent prune_orphans treats every .agents/ entry from the prior
    lockfile as an orphan and removes it. The lockfile is rewritten to
    reflect the new pointer-only state.
    """
    if install_mode not in ("pointer", "symlink", "copy"):
        print(
            f"ERROR: unknown install_mode {install_mode!r} in .playbook-config.yaml; "
            f"expected pointer|symlink|copy",
            file=sys.stderr,
        )
        return 1

    # v0.11 (ADR-0040): content_scope from .playbook-config.yaml (or empty)
    # is passed through to PlaybookContent.load so overlays/<scope>/ layer
    # onto base/ for the materialize pass.
    scope_names = parse_profile_arg(scope) if scope else []
    content = PlaybookContent.load(REPO_ROOT, scope=scope_names)
    # v0.10 (criterion-B fold of cursor + codex review): .playbook-config.yaml
    # stores `profile:` as a comma-separated string when init recorded
    # multiple profiles. parse_profile_arg + load_profiles handle both the
    # legacy single-name form and the v0.10 multi-profile form so an init
    # via `--profile pm,research` round-trips through update.
    profile_names = parse_profile_arg(profile_name) or ["tech-lead"]
    try:
        profile = load_profiles(REPO_ROOT, profile_names)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    # v0.11 (ADR-0040): validate the profile's requires_overlays against the
    # active scope. Without this, an update against a base-only scope can
    # silently materialize a thin target by filtering out overlay-only
    # skills/rules/hooks instead of failing loud.
    try:
        validate_profile_scope(profile, scope_names)
    except ValueError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 4
    filtered = filter_content(content, profile)

    materializer = TargetMaterializer(target, REPO_ROOT, install_mode)
    result = materializer.materialize(filtered)
    removed = prune_orphans(target, result.entries)
    write_lockfile(target, result)

    print()
    print(f"Materialized into {target} (install_mode={install_mode}):")
    for kind, count in result.counts.items():
        print(f"  {kind:12s} {count}")
    if removed:
        print(f"  pruned       {removed} orphan(s) from prior install")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Target project directory")
    args = parser.parse_args()
    target = Path(args.target).expanduser().resolve()

    config_path = target / ".playbook-config.yaml"
    if not config_path.exists():
        print(
            f"ERROR: {config_path} not found; run playbook_init.py first",
            file=sys.stderr,
        )
        return 1

    config = parse_config(config_path.read_text(encoding="utf-8"))
    profile = config.get("profile", "tech-lead")
    install_mode = config.get("install_mode", "pointer")
    # v0.11 (ADR-0040): read content_scope from config first; fall back to
    # the lockfile so pre-v0.11 targets that initialized without --scope
    # but installed with explicit --scope team get their overlay back
    # on the next playbook_update.py run. Final fallback: auto-detect
    # from the target project's git remote so a fresh init (no config
    # scope, no lockfile yet) still installs the right overlay rather
    # than dropping into base-only and failing validate_profile_scope.
    scope = config.get("content_scope", "")
    if not scope:
        lockfile_path = target / ".playbook-lock.json"
        if lockfile_path.is_file():
            try:
                import json as _json
                lockdata = _json.loads(lockfile_path.read_text(encoding="utf-8"))
                lock_scope = lockdata.get("content_scope")
                if isinstance(lock_scope, list) and lock_scope:
                    scope = ",".join(str(s) for s in lock_scope)
                    print(
                        f"Content scope: {scope} (restored from .playbook-lock.json)"
                    )
            except (OSError, ValueError):
                pass
    if not scope:
        from scope_resolution import detect_scope_from_remote
        detected = detect_scope_from_remote(target, REPO_ROOT)
        if detected:
            scope = ",".join(detected)
            print(
                f"Content scope: {scope} (auto-detected from target remote)"
            )
    print(f"Target: {target}")
    print(f"Profile: {profile}")
    if scope and "(restored" not in str(scope) and "(auto-detected" not in str(scope):
        print(f"Content scope: {scope}")
    print(f"Install mode: {install_mode}")
    print()

    rc = refresh_pointer(target)
    if rc != 0:
        return rc

    rc = materialize_content(target, profile, install_mode, scope=scope or None)
    if rc != 0:
        return rc

    # v0.8 (ADR-0038): refresh the registry entry so last_updated_at moves
    # forward and a renamed profile (per-project edit to .playbook-
    # config.yaml) propagates into the machine-wide view.
    try:
        from target_registry import record_target

        record_target(target, profile=profile, install_mode=install_mode)
    except Exception as exc:  # pragma: no cover - defensive log only
        print(
            f"WARNING: failed to refresh target in multi-target registry: {exc}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
