#!/usr/bin/env python3
"""
Interactive installer + lifecycle commands for the coding-agents-playbook.

Detects installed coding agents on this machine, pre-selects them, lets the
user toggle, then materializes content into each agent's native config
location.

Per ADR-0024 (v0.4): adapters self-describe via the Adapter Protocol
(scripts/adapters/_loader.py). The dispatcher iterates adapters.ALL_ADAPTERS
instead of hard-coded detection / destination tables.

Lifecycle commands (per ADR-0016 + ADR-0023):
  --list      Show installed playbook content per adapter
  --status    Compare installed vs lockfile, print drift summary
  --update    Re-materialize playbook content
  --remove    Remove materialized playbook content per lockfile
  --drift     Read lockfile, compare hashes against current state

Lockfile (.playbook-lock.json) is now generated from each Adapter's
install() return value (Iterable[InstalledPath]) rather than scanned from
a hard-coded table; single source of truth.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import ALL_ADAPTERS, _loader  # noqa: E402
from adapters._loader import Adapter, InstalledPath, PlaybookContent  # noqa: E402
from install_lock import install_lock as _install_lock  # noqa: E402
from playbook_profile import (
    dangling_entries,
    filter_content,
    list_profiles,
    load_profiles,
    parse_profile_arg,
    validate_profile_scope,
)  # noqa: E402
from scope_resolution import resolve_scope_arg as _scope_resolve_impl  # noqa: E402


LOCKFILE_NAME = ".playbook-lock.json"


REPO_ROOT = Path(__file__).resolve().parent.parent


def _read_playbook_version() -> str:
    """Read the canonical version from the VERSION file at repo root.

    Per ADR-0040 (v0.11): VERSION file is the single source of truth.
    A previous hardcoded constant drifted to 0.4.0 across multiple
    release cycles (v0.5 through v0.10) without being updated.
    The scripts/checks/playbook_version.py check enforces no return
    to the hardcoded shape.
    """
    version_file = REPO_ROOT / "VERSION"
    return version_file.read_text(encoding="utf-8").strip()


PLAYBOOK_VERSION = _read_playbook_version()


# === Detection ===


def _safe_detect(adapter: Adapter) -> bool:
    try:
        return adapter.detect()
    except (OSError, PermissionError):
        return False


def detected_adapters() -> list[Adapter]:
    return [a for a in ALL_ADAPTERS if _safe_detect(a)]


# === Interactive UX ===


def prompt_selection(detected_names: set[str]) -> list[Adapter]:
    """Show all Adapters with detected ones pre-checked; toggle interactively."""
    selected = {a.name: (a.name in detected_names) for a in ALL_ADAPTERS}
    print()
    print("Detected coding agents:")
    print()
    for adapter in ALL_ADAPTERS:
        marker = "[X]" if selected[adapter.name] else "[ ]"
        print(f"  {marker} {adapter.name:<14} (tier {adapter.tier})")
    print()
    print("  Tier 1 = full adapter (skills + rules + hooks + MCP + agents + commands)")
    print("           hooks ship for claude-code / codex / cursor / windsurf")
    print("  Tier 2 = skills + rules + (hooks for cline, copilot only)")
    print("           gemini-cli / aider / pi: no hook surface today")
    print("  Tier 3 = AGENTS.md only (auto-generated)")
    print()

    while True:
        choice = (
            input(
                "Press Enter to confirm, or type an agent name to toggle (or 'q' to quit): "
            )
            .strip()
            .lower()
        )
        if choice == "q":
            return []
        if not choice:
            break
        if choice in selected:
            selected[choice] = not selected[choice]
            print(f"  Toggled {choice} -> {'ON' if selected[choice] else 'off'}")
        else:
            print(f"  Unknown agent: {choice}")

    return [a for a in ALL_ADAPTERS if selected[a.name]]


# === Adapter dispatch ===


def install_for_adapter(
    adapter: Adapter,
    content: PlaybookContent,
    target: Path | None,
    prior_managed_keys: dict | None = None,
) -> list[InstalledPath]:
    print(f"\n  -> {adapter.name} (tier {adapter.tier})")
    try:
        manifest = list(adapter.install(content, target, prior_managed_keys))
        print(f"  done ({len(manifest)} path(s) recorded)")
        return manifest
    except Exception as exc:
        print(f"  failed: {exc}")
        raise


# Adapters that register MCP servers inside shared JSON/TOML config files.
# Used to compute managed_keys for the lockfile so a later narrower install
# can remove the playbook-owned entries that fall out of the new profile.
_MCP_REGISTERING_ADAPTERS = {"claude-code", "codex", "cursor", "windsurf"}


# Adapters that copy hook scripts + register them in a native config file.
# Each maps to (hooks_dir_factory) where the factory returns the absolute
# directory the adapter writes hooks into. Cursor and Copilot honor a target
# argument because their hook surface is project-scoped (Cursor also writes
# user-level; v0.5 reconciles only the project-level set, mirroring what
# the adapter actually writes when target == $HOME).
_HOOK_REGISTERING_ADAPTERS: dict = {
    "claude-code": lambda target: Path.home() / ".claude" / "hooks",
    "codex": lambda target: Path.home() / ".codex" / "hooks",
    "cursor": lambda target: Path.home() / ".cursor" / "hooks",
    "cline": lambda target: Path.home() / ".cline" / "hooks",
    "copilot": (
        lambda target: (
            (target if target is not None else Path.home()) / ".github" / "hooks"
        )
    ),
    # v0.6: Windsurf project-level hooks; lockfile tracks under
    # windsurf_hooks (a flat name set, not event-keyed, because the
    # Cascade reconciler matches command-substring rather than full path).
    "windsurf": lambda target: (
        (target if target is not None else Path.home()) / ".windsurf" / "hooks"
    ),
}


def _new_managed_keys_for(
    adapter_name: str,
    content: PlaybookContent,
    target: Path | None = None,
    *,
    pre_install_per_config: dict[tuple[str, str], set[str]] | None = None,
    prior_entries: list | None = None,
) -> dict:
    """Compute the managed_keys dict for one adapter AFTER install.

    v0.9 round-3 (Cursor #1): MCP ownership policy is implemented in
    scripts/install_managed_keys.py. This shim forwards to that module
    while keeping the install.py-local hook directory factory and the
    windsurf hooks namer (both depend on _HOOK_REGISTERING_ADAPTERS
    which is install.py-local).

    See install_managed_keys.compute_managed_keys_for for the rule.
    """
    from install_managed_keys import compute_managed_keys_for

    def _hook_factory(name: str, ctx, tgt):
        hook_dir_factory = _HOOK_REGISTERING_ADAPTERS.get(name)
        if hook_dir_factory is None:
            return {}
        return _hook_command_keys(
            ctx, hook_dir_factory(tgt), adapter_name=name
        )

    return compute_managed_keys_for(
        adapter_name,
        content,
        target,
        pre_install_per_config=pre_install_per_config,
        prior_entries=prior_entries,
        hook_keys_factory=_hook_factory,
        windsurf_keys_factory=_windsurf_hook_names,
    )


def _hook_command_keys(
    content: PlaybookContent,
    hooks_dir: Path,
    *,
    adapter_name: str,
) -> dict[str, list[str]]:
    """Compute {event: [absolute_command_path, ...]} the adapter will own.

    Resolution is adapter-aware so plan-time matches write-time:
      claude-code / cursor / cline / copilot: PLAYBOOK-HOOK-EVENT verbatim.
      codex: auto-promote PreToolUse + non-Bash matcher -> PostToolUse.

    Cursor-only hooks (PLAYBOOK-HOOK-CURSOR-ONLY: true) are excluded for
    every non-cursor adapter, mirroring what the adapters themselves do.
    Cursor-wrapped cores (a parent hook whose PLAYBOOK-HOOK-CURSOR-WRAPPER
    points at a sibling) are excluded from CURSOR's keyspace because the
    Cursor adapter registers only the wrapper, not the core. This keeps
    the lockfile aligned with the actual hooks.json registrations and
    prevents reconcile from misclassifying a core path as managed.
    """
    from hook_registration import (
        codex_event_for,
        is_hook_for_adapter,
        is_wrapped_core,
        resolve_hook_event,
    )

    event_resolver = codex_event_for if adapter_name == "codex" else resolve_hook_event
    by_event: dict[str, set[str]] = {}
    for hook in content.hooks:
        # v0.8 (ADR-0037): is_hook_for_adapter combines cursor-only and the
        # new PLAYBOOK-HOOK-ADAPTERS scoping. Plan-time keyspace must match
        # write-time exactly: if an adapter wouldn't install the hook,
        # the lockfile shouldn't either, or orphan-cleanup will mis-classify.
        if not is_hook_for_adapter(hook, adapter_name):
            continue
        if adapter_name == "cursor" and is_wrapped_core(hook):
            continue
        event = event_resolver(hook)
        by_event.setdefault(event, set()).add(str(hooks_dir / f"{hook.name}.sh"))
    return {event: sorted(paths) for event, paths in by_event.items()}


def _windsurf_hook_names(content: PlaybookContent) -> dict[str, bool]:
    """Return the flat {hook_name: True} dict for Windsurf Cascade
    reconciliation. Only hooks that resolve to at least one Cascade event
    are tracked (others are skipped at install time anyway).
    """
    from hook_registration import is_hook_for_adapter, resolve_windsurf_events

    names: dict[str, bool] = {}
    for hook in content.hooks:
        # v0.8 (ADR-0037): windsurf adapter only installs hooks whose
        # PLAYBOOK-HOOK-ADAPTERS allows windsurf (default = all hook-capable
        # adapters). Anchored-fs hooks pinned to claude-code drop out here.
        if not is_hook_for_adapter(hook, "windsurf"):
            continue
        if not resolve_windsurf_events(hook):
            continue
        names[hook.name] = True
    return names


# === Bundle health (v0.8 / ADR-0026 follow-through) ===
#
# Helpers live in scripts/install_bundles.py per the C1 decomposition.
# Underscore aliases preserved here so existing call sites + lifecycle
# tests that imported the private names keep working.

from install_bundles import (  # noqa: E402
    bundle_health_scripts as _bundle_health_scripts,
    run_bundle_bootstraps as _run_bundle_bootstraps,
    run_bundle_health as _run_bundle_health,
)


# === Lockfile + lifecycle ===


# Lockfile helpers live in scripts/install_lockfile.py per the C1
# decomposition. Underscore-prefixed aliases preserved here for the
# existing call sites and the lifecycle tests.

from install_lockfile import (  # noqa: E402
    generate_lockfile as _generate_lockfile_impl,
    hash_dir as _hash_dir,
    load_lockfile as _load_lockfile,
)

# v0.8 Cursor review fix: re-export facade removed. The lockfile helpers
# live in install_lockfile.py; callers (tests, install_orphans,
# install_verify) import directly from there. install.py keeps thin
# aliases as local function-scope shims (used inside cmd_status and
# cmd_remove) so refactoring the orchestration shell does not require
# touching every call site at once.


def generate_lockfile(
    target: Path | None,
    repo_root: Path,
    per_adapter_manifests: dict[str, list[InstalledPath]],
    profile_names: list[str] | None = None,
    content_scope: list[str] | None = None,
    carry_forward_sections: dict[str, dict] | None = None,
    managed_keys: dict[str, dict] | None = None,
) -> Path:
    """Back-compat wrapper around install_lockfile.generate_lockfile.

    Pinned positional + keyword shape preserves the existing call site in
    `_run_install_locked`; the implementation pulls PLAYBOOK_VERSION from
    this module so the version-bumped header stays in sync without making
    install_lockfile depend on install.py.

    v0.11: forwards `content_scope` so the lockfile records which overlays
    were active at install time (so `make update` restores the same
    composition without re-running auto-detect).
    """
    return _generate_lockfile_impl(
        target,
        repo_root,
        per_adapter_manifests,
        playbook_version=PLAYBOOK_VERSION,
        profile_names=profile_names,
        content_scope=content_scope,
        carry_forward_sections=carry_forward_sections,
        managed_keys=managed_keys,
    )


from install_lockfile import resolve_locked_path as _resolve_locked_path  # noqa: E402
from install_orphans import cleanup_orphans as _cleanup_orphans  # noqa: E402

# Lifecycle command bodies live in scripts/install_lifecycle.py; install.py
# wraps each so the CLI surface still routes through this module while the
# per-command logic stays decomposed.

from install_lifecycle import (  # noqa: E402
    cmd_list as _cmd_list_impl,
    cmd_remove as _cmd_remove_impl,
    cmd_status as _cmd_status_impl,
)


def cmd_list(target: Path | None) -> int:
    return _cmd_list_impl(target, repo_root=REPO_ROOT)


def cmd_status(target: Path | None) -> int:
    return _cmd_status_impl(
        target, repo_root=REPO_ROOT, lockfile_name=LOCKFILE_NAME
    )


def cmd_remove(target: Path | None) -> int:
    return _cmd_remove_impl(
        target, repo_root=REPO_ROOT, lockfile_name=LOCKFILE_NAME
    )


# cmd_verify + _verify_adapter live in scripts/install_verify.py per the
# v0.7 post-review decomposition. install.py wires the CLI flag; the
# verify module owns the per-adapter check and the native-config shape
# knowledge lives in scripts/hook_native_config.py.


def cmd_verify(target: Path | None) -> int:
    """ADR-0036 layer-3 runtime verification (thin wrapper).

    Delegates to install_verify.cmd_verify with the lockfile loader,
    adapter detector, and path resolver from this module injected in.
    """
    from install_verify import cmd_verify as _cmd_verify

    return _cmd_verify(
        target,
        load_lockfile=_load_lockfile,
        detected_adapters=detected_adapters,
        resolve_locked_path=_resolve_locked_path,
        repo_root=REPO_ROOT,
        # v0.8 (B4): the Windows-copy drift check needs a tree-hasher; pass
        # the existing _hash_dir so verify_adapter can compare the lockfile
        # tree_sha256 against the on-disk state.
        hash_dir=_hash_dir,
    )


def _run_install(
    target: Path | None,
    selected: list[Adapter],
    profile_names: list[str] | None = None,
    scope_names: list[str] | None = None,
) -> int:
    # v0.9 round-12 regular review P2 fix: incompatible-lockfile check
    # MUST run before the empty-selection short-circuit. Earlier code
    # returned 0 ("nothing to install") on a clean machine with no
    # detected agents, even when a v0.8 lockfile sat in the target.
    # Users running `--non-interactive` on a fresh checkout could then
    # miss the exit-3 cleanup-required signal entirely.
    #
    # v0.9 adversarial-round-2 HIGH-1 fix: refuse to overwrite a v0.8
    # lockfile in place. ADR-0039 declares a hard schema cut; if we
    # proceed with empty prior state, v0.8 MCP entries get classified
    # as user-authored and stale entries from a wider prior profile
    # never get reconciled. Direct the user at the v0.8 cleanup
    # workflow.
    from install_lockfile import (
        incompatible_lockfile_path,
        print_incompatible_lockfile_error,
    )

    bad_lock = incompatible_lockfile_path(target, REPO_ROOT)
    if bad_lock is not None:
        print_incompatible_lockfile_error(bad_lock)
        return 3

    if not selected:
        print("No agents selected; nothing to install.")
        return 0

    lock_dir = target if target is not None else REPO_ROOT
    with _install_lock(lock_dir):
        return _run_install_locked(target, selected, profile_names, scope_names)


def _run_install_locked(
    target: Path | None,
    selected: list[Adapter],
    profile_names: list[str] | None,
    scope_names: list[str] | None = None,
) -> int:
    content = PlaybookContent.load(REPO_ROOT, scope=scope_names)

    if profile_names:
        profile = load_profiles(REPO_ROOT, profile_names)
        # v0.11 (ADR-0040): validate profile's requires_overlays against the
        # active scope. Failing here surfaces the missing overlay clearly
        # instead of silently producing a thin install where the profile's
        # overlay-specific skills get filtered out.
        try:
            validate_profile_scope(profile, scope_names or [])
        except ValueError as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 4
        # Surface profile drift: any include-list entry that does not match a
        # real content slug is silently dropped by filter_content. profiles/
        # README.md says referenced items MUST exist; warn loudly if not so
        # the user spots renames or deletions instead of getting a thinner
        # install than they asked for.
        dangling = dangling_entries(content, profile)
        if dangling:
            print(
                f"\nWARNING: profile '{profile.name}' lists entries that no longer exist:"
            )
            for kind, slugs in dangling.items():
                for slug in slugs:
                    print(f"  - {kind}: {slug}")
            print(
                "  These are silently dropped by the filter. Fix profiles/"
                f"{profile.name}.toml to remove or rename them."
            )
        before = (
            len(content.skills),
            len(content.rules),
            len(content.hooks),
            len(content.mcp_configs),
        )
        content = filter_content(content, profile)
        after = (
            len(content.skills),
            len(content.rules),
            len(content.hooks),
            len(content.mcp_configs),
        )
        print(
            f"\nProfile filter ({profile.name}): "
            f"skills {before[0]}->{after[0]}, "
            f"rules {before[1]}->{after[1]}, "
            f"hooks {before[2]}->{after[2]}, "
            f"mcp {before[3]}->{after[3]}"
        )

    bundled = [m for m in content.mcp_configs if m.source_dir is not None]
    bundle_manifest: list[InstalledPath] = []
    if bundled:
        # Collect prior-install bundle paths so materialize_mcp_sources can
        # distinguish its own Windows-fallback copies (replace) from
        # user-authored real files at the same path (skip). Without this,
        # a Windows install would lose track of its own copies on rerun:
        # the first install copies (no symlink privilege), the second
        # install sees a real file and reclassifies it as foreign.
        prior_bundles_lock = _load_lockfile(target, REPO_ROOT) or {}
        prior_bundle_entries = (
            prior_bundles_lock.get("adapters", {}).get("_bundles", {}) or {}
        )
        prior_owned_bundle_paths: set[Path] = {
            _resolve_locked_path(rel) for rel in prior_bundle_entries
        }
        actions = _loader.materialize_mcp_sources(
            content.mcp_configs, prior_owned_paths=prior_owned_bundle_paths
        )
        created = sum(1 for _, _, a in actions if a == "created")
        updated = sum(1 for _, _, a in actions if a == "updated")
        unchanged = sum(1 for _, _, a in actions if a == "unchanged")
        skipped = [
            (name, path) for name, path, a in actions if a == "skipped-real-file"
        ]
        print(
            f"\nMCP sources symlinked to {_loader.AGENT_SHARED_MCP_DIR}: "
            f"{created} created, {updated} updated, {unchanged} unchanged"
            f"{f', {len(skipped)} skipped (real file in the way)' if skipped else ''}"
        )
        for name, path in skipped:
            print(
                f"  WARN: {name}: {path} exists as a real file; cleanup needed for symlink"
            )

        # Record the symlinks in a synthetic _bundles section so cmd_status
        # and cmd_remove can see them. Without this, make remove leaves
        # ~/.config/agent-shared/mcp_servers/ symlinks behind after uninstall.
        # ownership="owned": the playbook fully owns each symlink (we made it,
        # we can unlink it).
        for action_tuple in actions:
            link_path = action_tuple[1]
            action = action_tuple[2]
            if action == "skipped-real-file":
                continue
            bundle_manifest.append(InstalledPath(link_path, "owned"))

        # Per ADR-0026: bundles MAY ship a bootstrap.sh for idempotent setup
        # (e.g. venv creation). The playbook runs it AFTER source symlink and
        # BEFORE adapter MCP registration so adapters can shell out to a
        # working server if needed. Bundles without bootstrap.sh are no-ops.
        _run_bundle_bootstraps(bundled)

    print(f"\nInstalling for: {', '.join(a.name for a in selected)}")
    per_adapter_manifests: dict[str, list[InstalledPath]] = {}
    if bundle_manifest:
        # Record bundle symlinks as a synthetic adapter section so the lockfile
        # captures them. cmd_remove handles the _bundles section the same way
        # as any other adapter's owned files.
        per_adapter_manifests["_bundles"] = bundle_manifest
    failures: list[str] = []
    prior_lock_early = _load_lockfile(target, REPO_ROOT) or {}
    prior_managed_all = prior_lock_early.get("managed_keys", {}) or {}
    new_managed_keys: dict[str, dict] = {}

    # v0.9 (ADR-0039 / round-3 Cursor #1): pre-install snapshot lives in
    # install_managed_keys.snapshot_pre_install_mcp. After adapter.install(),
    # _new_managed_keys_for builds list[ManagedMcpEntry] per-config:
    #
    #   * (post - pre) at this path => freshly_inserted -> new entries
    #     with fresh uuid + ISO8601 timestamp.
    #   * (prior_entries at this path INTERSECT post INTERSECT configured)
    #     => carry-forward (preserve prior id + installed_at).
    #
    # Per-config ownership closes the v0.8 Cursor multi-config orphan
    # risk that the round-5/6 UNION/INTERSECT fallbacks worked around.
    from install_managed_keys import snapshot_pre_install_mcp

    pre_install_per_config = snapshot_pre_install_mcp(selected, target)

    for adapter in selected:
        try:
            adapter_prior = prior_managed_all.get(adapter.name)
            manifest = install_for_adapter(adapter, content, target, adapter_prior)
            per_adapter_manifests[adapter.name] = manifest
            prior_entries_list = (adapter_prior or {}).get("mcp_servers", [])
            adapter_new = _new_managed_keys_for(
                adapter.name,
                content,
                target,
                pre_install_per_config=pre_install_per_config,
                prior_entries=prior_entries_list,
            )
            if adapter_new:
                new_managed_keys[adapter.name] = adapter_new
        except Exception:
            failures.append(adapter.name)

    if failures:
        print(
            f"\nFAIL: {len(failures)} of {len(selected)} agent(s) did not install: "
            f"{', '.join(failures)}"
        )
        return 1

    # Cleanup orphans from a prior wider install. When the user narrows from
    # the full playbook to --profile qa, the adapter just writes the qa subset
    # and is otherwise a no-op; old skills/hooks/MCP files would stay behind
    # and the regenerated lockfile would drop them from view, leaving `make
    # remove` unable to clean them later. Diff prior vs new PER ADAPTER and
    # unlink the difference (owned-only; hash-mismatch guard from ADR-0023).
    #
    # Adapters that ran this turn get reconciled; adapters that didn't run
    # (user toggled them off, or detection missed them) are CARRIED FORWARD
    # in the new lockfile so their files stay tracked. Otherwise an
    # unrelated install for one adapter could orphan-delete another
    # adapter's installed content.
    prior_lock = _load_lockfile(target, REPO_ROOT)
    carry_forward: dict[str, dict] = {}
    if prior_lock:
        _cleanup_orphans(prior_lock, per_adapter_manifests)
        for prior_name, prior_entries in prior_lock.get("adapters", {}).items():
            if prior_name not in per_adapter_manifests:
                carry_forward[prior_name] = prior_entries

    # Preserve managed_keys for adapters we didn't run this turn so a future
    # narrower install can still reconcile against their original registrations.
    merged_managed_keys = dict(prior_managed_all)
    merged_managed_keys.update(new_managed_keys)
    lock_path = generate_lockfile(
        target,
        REPO_ROOT,
        per_adapter_manifests,
        profile_names=profile_names,
        content_scope=scope_names,
        carry_forward_sections=carry_forward,
        managed_keys=merged_managed_keys,
    )
    if carry_forward:
        carried = ", ".join(sorted(carry_forward.keys()))
        print(
            f"\nCarried forward {len(carry_forward)} prior adapter section(s) "
            f"not selected this run: {carried}"
        )
    print(f"\nLockfile: {lock_path}")
    print("Done. Re-run `make install` anytime to sync updates.")
    return 0


# === Main ===


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install + lifecycle for coding-agents-playbook"
    )
    parser.add_argument(
        "--diagnose", action="store_true", help="Diagnose setup; do not install"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Use detected agents without prompting",
    )
    parser.add_argument("--target", default=None, help="Target project directory")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List installed playbook content per adapter",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show drift between lockfile and current state",
    )
    parser.add_argument(
        "--update", action="store_true", help="Re-materialize playbook content"
    )
    parser.add_argument(
        "--remove", action="store_true", help="Remove materialized files per lockfile"
    )
    parser.add_argument(
        "--drift", action="store_true", help="Show drift report (alias of --status)"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="ADR-0036 layer-3 verification: lockfile vs native config vs on-disk",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Narrow content to one or more profiles (profiles/<name>.toml "
        "basename, e.g. backend-developer). Pass multiple profiles as a "
        "comma-separated list, e.g. --profile product-manager,research,"
        "backend-developer (the installer unions their includes). Omit to "
        "install everything.",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="Content scope: which overlays layer onto base/. Pass overlay "
        "names comma-separated (e.g. --scope team). Special: 'none' or "
        "'base' for base-only install. Omit to auto-detect from the "
        "target project's git remote URL (per ADR-0040).",
    )
    args = parser.parse_args()

    requested_profiles = parse_profile_arg(args.profile)
    if requested_profiles:
        available = list_profiles(REPO_ROOT)
        unknown = [name for name in requested_profiles if name not in available]
        if unknown:
            print(
                f"Unknown profile(s): {', '.join(unknown)}", file=sys.stderr
            )
            print(f"Available: {', '.join(available)}", file=sys.stderr)
            sys.exit(2)

    target_arg = Path(args.target).expanduser() if args.target else None

    if args.list:
        sys.exit(cmd_list(target_arg))
    if args.status or args.drift:
        sys.exit(cmd_status(target_arg))
    if args.verify:
        sys.exit(cmd_verify(target_arg))
    if args.remove:
        sys.exit(cmd_remove(target_arg))

    print("Coding Agents Playbook installer")
    print(f"Repo root: {REPO_ROOT}")

    detected = detected_adapters()
    detected_names = {a.name for a in detected}
    summary = ", ".join(sorted(detected_names)) if detected_names else "none"
    print(f"\nDetected {len(detected_names)} agent(s): {summary}")

    if args.diagnose:
        print("\nFull detection report:")
        for a in ALL_ADAPTERS:
            print(
                f"  {a.name:<14} (tier {a.tier}): {'detected' if a.name in detected_names else 'not detected'}"
            )

        # v0.8 (ADR-0026 follow-through): aggregate bundle health.sh exit
        # codes so `make doctor` surfaces runtime readiness, not just
        # detection state. Bundles without a health.sh contribute nothing
        # (the file is conventional, not required).
        health_scripts = _bundle_health_scripts(REPO_ROOT)
        if health_scripts:
            print("\nBundle health checks:")
            unhealthy: list[tuple[str, int, str]] = []
            for script in health_scripts:
                bundle_name = script.parent.parent.name
                rc, stderr_tail = _run_bundle_health(script)
                status = "ok" if rc == 0 else ("TIMED OUT" if rc == 124 else "FAILED")
                print(f"  {bundle_name:<14} {status} (exit {rc})")
                if rc != 0:
                    unhealthy.append((bundle_name, rc, stderr_tail))
            if unhealthy:
                print("\nUnhealthy bundle diagnostics:")
                for name, rc, stderr_tail in unhealthy:
                    print(f"  --- {name} (exit {rc}) ---")
                    for line in stderr_tail.rstrip().splitlines() or ["<no stderr>"]:
                        print(f"    {line}")
        return

    if args.non_interactive or args.update:
        selected = [a for a in ALL_ADAPTERS if a.name in detected_names]
    else:
        selected = prompt_selection(detected_names)

    # v0.9 round-13 adversarial HIGH fix: the incompatible-lockfile
    # check must run in main() BEFORE the empty-selection return.
    # Round-13-r2 regular review P2 fix: but it must NOT call
    # resolve_target() on the cancel path, because resolve_target
    # prompts the user (interactive) or fails with the playbook-root
    # guard.
    # Round-14 adversarial HIGH fix: when --non-interactive runs
    # without --target, resolve_target uses cwd as the implicit
    # target. The lockfile check has to mirror that path-resolution
    # rule (cwd for non-interactive without --target; explicit
    # --target value otherwise) so a v0.8 .playbook-lock.json sitting
    # in cwd still triggers exit 3. Interactive runs are left to the
    # _run_install internal check (it fires after resolve_target
    # prompts the user).
    target_for_lockfile_check: Path | None
    if args.target:
        try:
            target_for_lockfile_check = Path(args.target).expanduser().resolve()
        except (OSError, RuntimeError):
            target_for_lockfile_check = None
    elif args.non_interactive or args.update:
        # Mirror resolve_target: cwd is the implicit target, unless
        # cwd is the playbook repo (no install would happen there
        # anyway, so the guard is a no-op).
        try:
            cwd_resolved = Path.cwd().resolve()
        except OSError:
            cwd_resolved = None
        target_for_lockfile_check = (
            cwd_resolved
            if cwd_resolved is not None and cwd_resolved != REPO_ROOT.resolve()
            else None
        )
    else:
        # Interactive without --target: defer to the internal check
        # in _run_install (which runs AFTER resolve_target prompts).
        target_for_lockfile_check = None

    from install_lockfile import (
        incompatible_lockfile_path,
        print_incompatible_lockfile_error,
    )

    bad_lock = incompatible_lockfile_path(target_for_lockfile_check, REPO_ROOT)
    if bad_lock is not None:
        print_incompatible_lockfile_error(bad_lock)
        sys.exit(3)

    if not selected:
        print("\nNo agents selected. Nothing to install.")
        return

    # Now we know we're installing, resolve the target (may prompt).
    target = _loader.resolve_target(
        REPO_ROOT,
        cli_target=args.target,
        non_interactive=args.non_interactive or args.update,
    )
    print(f"\nTarget project: {target}")

    # Restore the last-installed profile(s) on --update if the user didn't pass
    # any explicitly. Without this, `make install --profile qa` followed by
    # `make update` silently widens back to the full playbook because the
    # update path has no implicit profile memory.
    #
    # v0.10: the lockfile may contain either a single profile string (v0.9
    # writers) or a list of profile names (v0.10 multi-profile writers).
    # Tolerate both shapes so an in-place upgrade keeps the narrower
    # selection.
    effective_profiles = requested_profiles
    if args.update and not effective_profiles:
        prior = _load_lockfile(target, REPO_ROOT)
        prior_profile = prior.get("profile") if prior else None
        if isinstance(prior_profile, str):
            effective_profiles = [prior_profile]
        elif isinstance(prior_profile, list):
            effective_profiles = [str(name) for name in prior_profile if name]
        if effective_profiles:
            print(
                f"\nUpdate: restoring profile(s) "
                f"{', '.join(effective_profiles)} from prior lockfile "
                f"(pass --profile to override)."
            )

    # Restore content_scope from the prior lockfile on --update (mirrors the
    # profile restore above). Without this, an explicit --scope team install
    # in a project with no recognizable remote silently re-detects to [] on
    # update, then validate_profile_scope rejects with "missing team overlay".
    # Per ADR-0040 L149: update reads lockfile first, falls back to auto-detect.
    scope_names: list[str]
    if args.scope is not None:
        scope_names = _scope_resolve_impl(args.scope, target, REPO_ROOT)
    elif args.update:
        prior = _load_lockfile(target, REPO_ROOT)
        prior_scope = prior.get("content_scope") if prior else None
        if isinstance(prior_scope, list) and prior_scope:
            scope_names = [str(s) for s in prior_scope]
            print(
                f"\nUpdate: restoring content_scope "
                f"{', '.join(scope_names)} from prior lockfile "
                f"(pass --scope to override)."
            )
        else:
            scope_names = _scope_resolve_impl(None, target, REPO_ROOT)
    else:
        scope_names = _scope_resolve_impl(None, target, REPO_ROOT)
    if scope_names:
        print(f"Content scope: {', '.join(scope_names)}")
    elif args.scope is None:
        # Per ADR-0040 auto-detect matrix: silent base-only is the default
        # for unknown remotes / missing remotes, but warn so the user notices
        # before validate_profile_scope rejects a profile that needs an overlay.
        print(
            "Content scope: base only (no recognized remote detected). "
            "Pass --scope <overlay> explicitly if a profile needs an overlay."
        )

    sys.exit(
        _run_install(
            target,
            selected,
            profile_names=effective_profiles or None,
            scope_names=scope_names,
        )
    )


if __name__ == "__main__":
    main()
