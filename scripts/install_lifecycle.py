"""Lifecycle commands: list / status / remove.

Decomposed out of install.py so the orchestration entry points
(install.main, _run_install_locked) can stay readable. Each function
takes the install target plus REPO_ROOT and LOCKFILE_NAME from
install.py so this module stays free of install-side constants while
still owning the full command body.

Per ADR-0023:
  - ownership="owned"  : verify current hash matches lockfile; unlink if so,
                         else skip with warning (user has edited the file).
  - ownership="managed": never unlink (file mixes playbook + user content).

cmd_verify lives in scripts/install_verify.py; install.py still wires
the CLI flag because the verify module already accepts injected helpers
(matching the v0.7 decomposition pattern).
"""

from __future__ import annotations

from pathlib import Path

from install_lockfile import (
    copied_dir_drift,
    entry_hash,
    entry_is_copied_dir,
    entry_is_symlink,
    entry_ownership,
    hash_dir,
    hash_file,
    load_lockfile,
    relative_to_home,
    resolve_locked_path,
)


def scan_orphans_for_adapter(
    entries: dict,
    known_paths: set[Path],
    *,
    lockfile_name: str,
) -> list[Path]:
    """Find files in the parent dirs of `entries` that aren't in known_paths.

    Used by cmd_status to surface drift the lockfile alone can't see (files
    left behind by a previous wider install, or hand-dropped by the user).
    Scans the IMMEDIATE parent of each tracked file plus one level up so we
    catch orphan siblings without descending into every adapter home.
    """
    if not entries:
        return []
    parents: set[Path] = set()
    for rel in entries:
        full = resolve_locked_path(rel)
        parents.add(full.parent)
        # Also scan one level up (the adapter's "skills root", "hooks root", etc.)
        # so renamed-or-deleted-then-replaced dirs surface as orphans.
        if full.parent.parent != Path("/"):
            parents.add(full.parent.parent)
    orphans: list[Path] = []
    for parent in parents:
        if not parent.is_dir():
            continue
        try:
            for child in parent.iterdir():
                if not child.is_file():
                    continue
                if child in known_paths:
                    continue
                # Skip dotfiles + the lockfile itself.
                if child.name.startswith("."):
                    continue
                if child.name == lockfile_name:
                    continue
                orphans.append(child)
        except (OSError, PermissionError):
            continue
    return sorted(orphans)


def cmd_list(target: Path | None, *, repo_root: Path) -> int:
    lock = load_lockfile(target, repo_root)
    if not lock:
        print("No .playbook-lock.json found. Run `make install` to generate one.")
        return 0
    print(f"Lockfile: {lock['generated_at']} (version {lock['version']})")
    if lock.get("target"):
        print(f"Target: {lock['target']}")
    print()
    for adapter_name, entries in lock.get("adapters", {}).items():
        print(f"  {adapter_name} ({len(entries)} files)")
        for rel in sorted(entries.keys())[:10]:
            print(f"    {rel}")
        if len(entries) > 10:
            print(f"    ... +{len(entries) - 10} more")
        print()
    return 0


def cmd_status(target: Path | None, *, repo_root: Path, lockfile_name: str) -> int:
    lock = load_lockfile(target, repo_root)
    if not lock:
        print("No .playbook-lock.json found. Run `make install` to generate one.")
        return 1
    print(f"Lockfile: {lock['generated_at']} (version {lock['version']})")
    if lock.get("target"):
        print(f"Target: {lock['target']}")
    if lock.get("profile"):
        print(f"Profile: {lock['profile']}")
    print()
    any_drift = False
    # Collect every known path so the orphan scan can ignore them.
    known_paths: set[Path] = set()
    for entries in lock.get("adapters", {}).values():
        for rel in entries:
            known_paths.add(resolve_locked_path(rel))

    for adapter_name, entries in lock.get("adapters", {}).items():
        agent_drift: list[tuple[str, str]] = []
        for rel, locked_entry in entries.items():
            full = resolve_locked_path(rel)
            if entry_is_symlink(locked_entry):
                # Symlinks: REMOVED iff the link no longer exists; CHANGED iff
                # the target moved. Don't hash; symlinks have no byte content.
                if not full.is_symlink() and not full.exists():
                    agent_drift.append(("REMOVED", rel))
                    continue
                try:
                    current_target = str(full.readlink()) if full.is_symlink() else ""
                except OSError:
                    continue
                if current_target != locked_entry.get("symlink_target", ""):
                    agent_drift.append(("CHANGED", rel))
                continue
            if entry_is_copied_dir(locked_entry):
                # v0.8 (C3-cleanup): the shared drift predicate lives in
                # install_lockfile.copied_dir_drift so cmd_status,
                # cleanup_orphans, and verify_adapter agree on the rule.
                drift = copied_dir_drift(full, locked_entry)
                if drift == "missing":
                    agent_drift.append(("REMOVED", rel))
                elif drift == "drift":
                    agent_drift.append(("CHANGED", rel))
                continue
            if not full.exists():
                agent_drift.append(("REMOVED", rel))
                continue
            try:
                current_hash = hash_file(full)
            except (OSError, PermissionError):
                continue
            if current_hash != entry_hash(locked_entry):
                agent_drift.append(("CHANGED", rel))
        # Orphan detection: scan the parent directories of every tracked file
        # for files that AREN'T in the lockfile. Catches drift the manifest
        # doesn't know about (e.g. files left behind by a wider prior install).
        orphans = scan_orphans_for_adapter(
            entries, known_paths, lockfile_name=lockfile_name
        )
        for orphan in orphans:
            agent_drift.append(("ADDED", relative_to_home(orphan)))

        if agent_drift:
            any_drift = True
            print(f"  {adapter_name}: drift detected")
            for tag, rel in agent_drift:
                print(f"    {tag}: {rel}")
        else:
            print(f"  {adapter_name}: clean ({len(entries)} files)")
    if any_drift:
        print(
            "\nDrift detected. Run `make update` to re-materialize, or `make remove` to roll back."
        )
    else:
        print("\nAll adapters in sync with lockfile.")
    return 0


def cmd_remove(target: Path | None, *, repo_root: Path, lockfile_name: str) -> int:
    """Remove materialized files per lockfile, respecting ownership + hash.

    Per ADR-0023:
      - ownership="owned"  : verify current hash matches lockfile; unlink if so,
                             else skip with warning (user has edited the file).
      - ownership="managed": never unlink (file mixes playbook + user content).
    """
    lock = load_lockfile(target, repo_root)
    if not lock:
        print("No .playbook-lock.json found; cannot determine what to remove.")
        return 1
    removed = skipped_managed = skipped_edited = 0
    skipped_managed_paths: list[str] = []
    for entries in lock.get("adapters", {}).values():
        for rel, entry in entries.items():
            ownership = entry_ownership(entry)
            full = resolve_locked_path(rel)
            if ownership == "managed":
                if full.exists() or full.is_symlink():
                    skipped_managed += 1
                    skipped_managed_paths.append(str(full))
                continue
            # Symlinks (file or directory): unlink unconditionally. The
            # playbook placed every symlink in ~/.config/agent-shared/mcp_servers/,
            # so there's no "user edited the file" hazard like there is for
            # owned regular files.
            if entry_is_symlink(entry):
                if not (full.exists() or full.is_symlink()):
                    continue
                try:
                    full.unlink()
                    removed += 1
                except OSError as exc:
                    print(f"  WARN: could not remove symlink {full}: {exc}")
                continue
            if entry_is_copied_dir(entry):
                if not full.is_dir():
                    continue
                expected_tree = (
                    entry.get("tree_sha256", "") if isinstance(entry, dict) else ""
                )
                try:
                    current_tree = hash_dir(full)
                except (OSError, PermissionError) as exc:
                    print(f"  WARN: could not hash dir {full}: {exc}")
                    continue
                if expected_tree and current_tree != expected_tree:
                    skipped_edited += 1
                    print(f"  SKIP edited dir (hash mismatch): {full}")
                    continue
                try:
                    import shutil

                    shutil.rmtree(full)
                    removed += 1
                except OSError as exc:
                    print(f"  WARN: could not remove dir {full}: {exc}")
                continue
            if not full.exists():
                continue
            expected_hash = entry_hash(entry)
            try:
                current_hash = hash_file(full)
            except (OSError, PermissionError) as exc:
                print(f"  WARN: could not hash {full}: {exc}")
                continue
            if current_hash != expected_hash:
                skipped_edited += 1
                print(f"  SKIP edited (hash mismatch): {full}")
                continue
            try:
                full.unlink()
                removed += 1
            except OSError as exc:
                print(f"  WARN: could not remove {full}: {exc}")
    # v0.9 round-17 adversarial HIGH fix: before deleting the lockfile,
    # reconcile native MCP registrations using managed_keys. Earlier
    # cmd_remove skipped "managed" ownership files (which includes the
    # native MCP config files like ~/.cursor/mcp.json) and then unlinked
    # the lockfile. Result: callable MCP entries left in native configs
    # with no remaining ownership record. ADR-0039's per-(adapter,
    # config_path) schema gives us exact reconcile targets; use them.
    lock_path = (target / lockfile_name) if target else (repo_root / lockfile_name)
    if lock_path.exists():
        managed_keys_full = lock.get("managed_keys", {}) or {}
        if managed_keys_full:
            from adapters._protocol import reconcile_managed_json_mcp
            from adapters._writer import remove_managed_block

            entries_by_config: dict[str, set[str]] = {}
            for adapter_managed in managed_keys_full.values():
                if not isinstance(adapter_managed, dict):
                    continue
                for entry in adapter_managed.get("mcp_servers", []) or []:
                    if not isinstance(entry, dict):
                        continue
                    name = entry.get("name")
                    cfg = entry.get("config_path")
                    if isinstance(name, str) and isinstance(cfg, str):
                        entries_by_config.setdefault(cfg, set()).add(name)
            mcp_removed = 0
            toml_blocks_removed = 0
            for cfg_str, names in entries_by_config.items():
                cfg_path = Path(cfg_str)
                if not cfg_path.is_file():
                    continue
                # v0.9 round-17 regular review P2 fix: Codex uses TOML
                # with a managed-block marker, not the JSON
                # mcpServers shape. Dispatch on suffix so the right
                # cleanup mechanism fires for each adapter.
                if cfg_path.suffix == ".toml":
                    removal = remove_managed_block(
                        cfg_path,
                        comment_prefix="#",
                        comment_suffix="",
                    )
                    if removal == "removed":
                        toml_blocks_removed += 1
                else:
                    mcp_removed += reconcile_managed_json_mcp(
                        cfg_path,
                        "mcpServers",
                        set(),  # new = empty (uninstalling everything)
                        names,  # prior = managed names at this path
                    )
            if mcp_removed:
                print(
                    f"  Removed {mcp_removed} managed MCP entr(ies) from "
                    f"native JSON config files."
                )
            if toml_blocks_removed:
                print(
                    f"  Removed {toml_blocks_removed} managed MCP block(s) "
                    f"from Codex TOML config file(s)."
                )
        lock_path.unlink()
    msg = f"Removed {removed} file(s)."
    if skipped_managed:
        msg += (
            f" Skipped {skipped_managed} managed-block file(s) "
            f"(use the adapter's own remove flow for those: "
            f"{', '.join(skipped_managed_paths[:3])}"
            f"{'...' if len(skipped_managed_paths) > 3 else ''})."
        )
    if skipped_edited:
        msg += (
            f" Skipped {skipped_edited} user-edited file(s) "
            "(hash mismatch; delete manually if you want them gone)."
        )
    msg += " Lockfile deleted."
    print(msg)
    return 0
