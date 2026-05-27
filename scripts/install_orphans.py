"""Orphan-cleanup helper (v0.8 C1 decomposition).

The lockfile records every file the playbook materialized in the previous
install. When a later install ships a narrower set (`make install
--profile qa` after `make install --profile backend-developer`), the
prior set contains entries that fell out of scope. cleanup_orphans
unlinks those, respecting:

  * **Ownership**: only entries marked `owned` are eligible; `managed`
    entries (managed-block files, AGENTS.md) are never removed because
    they mix playbook + user content.
  * **Edit guard (ADR-0023)**: an `owned` file whose on-disk hash no
    longer matches the lockfile hash is skipped with a warning. The
    user has edited it; the playbook must not silently destroy that
    edit.
  * **Per-adapter scoping (v0.5 review fixup)**: only adapters that
    actually ran this turn are reconciled. An adapter the user toggled
    off this run is NOT treated as orphan; its sections carry forward
    in the new lockfile so `make remove` can still clean them later.
  * **Symlink-through guard (v0.6 P1)**: when the new manifest replaces
    a directory with a symlink that points into a canonical-owned tree,
    the prior per-file paths now resolve THROUGH the symlink into the
    canonical tree. `full.unlink()` on those paths would destroy
    canonical content. cleanup_orphans refuses to unlink any path
    whose resolve() lands inside the new manifest's owned tree.
  * **Copied-dir drift**: an orphan entry recorded as `copied_dir`
    (Windows symlink-fallback) is unlinked via `shutil.rmtree` only if
    its current tree hash still matches the recorded `tree_sha256`.

Extracted from `scripts/install.py` per the C1 decomposition; the
private `_cleanup_orphans` alias is re-exported there for the existing
call sites.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from adapters._protocol import InstalledPath
from install_lockfile import (
    copied_dir_drift,
    entry_hash,
    entry_is_copied_dir,
    entry_is_symlink,
    entry_ownership,
    hash_file,
    relative_to_home,
    resolve_locked_path,
)


def cleanup_orphans(
    prior_lock: dict,
    new_manifests: dict[str, list[InstalledPath]],
) -> None:
    """Unlink prior-lockfile files NOT in this install's manifests, SCOPED
    PER ADAPTER. Owned-only; respects the hash-mismatch guard (per ADR-0023).

    Behavior summary lives in the module docstring; see also ADR-0023 +
    the v0.5 review fixup commit + the v0.6 P1 finding.
    """
    removed = skipped_managed = skipped_edited = skipped_via_symlink = 0
    prior_adapters = prior_lock.get("adapters", {})
    for adapter_name, manifest in new_manifests.items():
        prior_entries = prior_adapters.get(adapter_name)
        if not prior_entries:
            continue
        new_paths_for_adapter = {relative_to_home(ip.path) for ip in manifest}
        # v0.6 (P1 fix): the SET of absolute paths the new manifest owns,
        # used to detect orphan paths that now resolve through a new
        # symlink into a canonical-owned directory.
        new_owned_real_paths: set[Path] = set()
        for ip in manifest:
            try:
                new_owned_real_paths.add(ip.path.resolve())
            except OSError:
                continue
        for rel, entry in prior_entries.items():
            if rel in new_paths_for_adapter:
                continue
            ownership = entry_ownership(entry)
            full = resolve_locked_path(rel)
            if not (full.exists() or full.is_symlink()):
                continue
            if ownership == "managed":
                skipped_managed += 1
                continue
            # v0.6 P1 fix: refuse to unlink files that now resolve INTO
            # the new manifest's owned tree (the prior install's per-file
            # paths chained through a newly-created symlink). Without
            # this guard, replacing ~/.cursor/skills/<n>/ with a symlink
            # to ~/.agents/skills/<n>/ would cause `full.unlink()` on the
            # prior per-file paths to delete the canonical files.
            crosses_into_new = False
            try:
                resolved = full.resolve()
                if resolved in new_owned_real_paths:
                    crosses_into_new = True
                else:
                    for owned in new_owned_real_paths:
                        try:
                            resolved.relative_to(owned)
                            crosses_into_new = True
                            break
                        except ValueError:
                            continue
            except OSError:
                pass
            if crosses_into_new:
                skipped_via_symlink += 1
                continue
            if entry_is_symlink(entry):
                try:
                    full.unlink()
                    removed += 1
                except OSError as exc:
                    print(f"  warn: could not unlink orphan symlink {full}: {exc}")
                continue
            if entry_is_copied_dir(entry):
                # v0.8 (C3-cleanup): shared drift predicate avoids the
                # third copy of "hash tree, compare to recorded".
                drift = copied_dir_drift(full, entry)
                if drift == "missing":
                    continue
                if drift in {"drift", "unreadable"}:
                    skipped_edited += 1
                    print(f"  skip orphan dir (edited): {full}")
                    continue
                # drift is None -> pristine -> safe to remove
                try:
                    shutil.rmtree(full)
                    removed += 1
                except OSError as exc:
                    print(f"  warn: could not unlink orphan dir {full}: {exc}")
                continue
            expected_hash = entry_hash(entry)
            try:
                current_hash = hash_file(full)
            except (OSError, PermissionError):
                continue
            if current_hash != expected_hash:
                skipped_edited += 1
                print(f"  skip orphan (edited): {full}")
                continue
            try:
                full.unlink()
                removed += 1
            except OSError as exc:
                print(f"  warn: could not unlink orphan {full}: {exc}")
    if removed or skipped_managed or skipped_edited or skipped_via_symlink:
        msg = f"\nCleanup: removed {removed} orphan file(s)"
        if skipped_managed:
            msg += f", skipped {skipped_managed} managed"
        if skipped_edited:
            msg += f", skipped {skipped_edited} edited"
        if skipped_via_symlink:
            msg += f", skipped {skipped_via_symlink} via-new-symlink (v0.6 P1 guard)"
        print(msg + ".")


__all__ = ["cleanup_orphans"]
