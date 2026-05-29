"""Lockfile read/write/entries (ADR-0024 / v0.8 C1 decomposition).

The lockfile helpers were extracted from `scripts/install.py` per the
ADR-0016 size threshold and the C1 decomposition plan. install.py is
now the dispatcher; this module owns the lockfile data model.

Public surface:

  hash_file / hash_dir            -- sha256 of a file / tree.
  entry_for(path, ownership)      -- build a lockfile entry from a path.
  entry_is_symlink / entry_is_copied_dir
                                  -- classify an entry.
  entry_hash / entry_ownership    -- read fields tolerant of legacy
                                     str-only entries (pre-v0.4).
  generate_lockfile(...)          -- write the per-adapter manifests
                                     plus managed_keys + carry-forward.
  load_lockfile(target, repo_root)
                                  -- read either target/.playbook-lock.json
                                     or repo_root/.playbook-lock.json.
  relative_to_home(path)          -- canonicalize a path for the
                                     lockfile key space.
  LOCKFILE_NAME                   -- the literal filename.

install.py re-exports the underscore-prefixed aliases so existing call
sites keep working without churn.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

# Importing InstalledPath from adapters._protocol creates an explicit
# typed contract for the manifests this module consumes. The import
# happens at module load (cheap) and matches what install.py does.
from adapters._protocol import InstalledPath


LOCKFILE_NAME = ".playbook-lock.json"

# Lockfile schema version (ADR-0039).
#
# v0.9 hard cut: managed_keys.mcp_servers shape changes from
# `dict[adapter, list[str]]` to `dict[adapter, list[ManagedMcpEntry]]`.
# Readers MUST require lockfile_version == LOCKFILE_VERSION; mismatched
# versions are not supported (build phase, no migration path).
LOCKFILE_VERSION = 3


class ManagedMcpEntry(TypedDict):
    """One managed MCP server entry (v0.9 / ADR-0039).

    Keyed per (adapter, config_path) so the same server name installed
    into different mcp config files (Cursor global vs project, Claude
    Code user vs project) is tracked separately and uninstall can
    target the exact file the playbook wrote.

    Fields:
        id: uuid4 generated at install time; stable identity that
            survives renames or duplicate names across configs.
        name: Human MCP server name; not authoritative for identity
            (collisions across scopes are expected).
        config_path: Absolute path to the native MCP config file the
            entry was written into.
        scope: "global" for user-home configs, "project" for workspace
            configs. Records the agent's precedence position.
        installed_at: ISO8601 UTC timestamp; audit trail.
    """

    id: str
    name: str
    config_path: str
    scope: str
    installed_at: str


def make_managed_mcp_entry(
    name: str, config_path: Path | str, scope: str
) -> ManagedMcpEntry:
    """Build a ManagedMcpEntry with a fresh uuid and current timestamp.

    Callers pass name (MCP server name from McpConfig), config_path
    (the native config file the entry was just written to), and scope
    ("global" or "project"). The id is uuid4 and installed_at is
    datetime.now(timezone.utc) in ISO8601 with second precision.
    """
    return ManagedMcpEntry(
        id=str(uuid.uuid4()),
        name=name,
        config_path=str(config_path),
        scope=scope,
        installed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def managed_entries_for_config(
    entries: list[ManagedMcpEntry] | None, config_path: Path | str
) -> set[str]:
    """Filter a list of ManagedMcpEntry to the names installed at config_path.

    Used by the adapter reconcile path: each adapter writes to one or
    more native mcp config files, and the per-config managed-name set
    is what reconcile_managed_json_mcp needs to know which entries to
    delete from THAT file when the new install no longer ships them.
    """
    if not entries:
        return set()
    target = str(config_path)
    return {e["name"] for e in entries if e.get("config_path") == target}


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def hash_dir(path: Path) -> str:
    """Stable content hash of a directory tree.

    Used for paths that the Windows symlink fallback copied as a real
    directory rather than the intended symlink. The hash visits every
    file in sorted order so the same tree produces the same digest on
    every machine, and a manual edit inside the tree shows up as drift
    in `make status` exactly like a single-file edit would.
    """
    h = hashlib.sha256()
    for sub in sorted(path.rglob("*")):
        if not sub.is_file():
            continue
        try:
            rel = str(sub.relative_to(path))
        except ValueError:
            rel = str(sub)
        h.update(rel.encode("utf-8"))
        try:
            h.update(sub.read_bytes())
        except (OSError, PermissionError):
            continue
    return h.hexdigest()


def relative_to_home(path: Path) -> str:
    """Render a path relative to $HOME when possible; else absolute."""
    home = Path.home()
    try:
        return str(path.relative_to(home))
    except ValueError:
        return str(path)


def entry_for(path: Path, ownership: str) -> dict | None:
    """Build a lockfile entry for one path.

    Files get a sha256 entry; symlinks (file or directory) get a
    symlink_target so cmd_remove can unlink them without needing a content
    hash; real directories get a tree_sha256 (used only on the Windows
    symlink-fallback path, where what should be a directory symlink became
    a real copied tree). Returns None when the path is unreadable.
    """
    try:
        if path.is_symlink():
            try:
                target_str = str(path.readlink())
            except OSError:
                target_str = ""
            return {"symlink_target": target_str, "ownership": ownership}
        if path.is_dir():
            return {
                "tree_sha256": hash_dir(path),
                "kind": "copied_dir",
                "ownership": ownership,
            }
        return {"sha256": hash_file(path), "ownership": ownership}
    except (OSError, PermissionError):
        return None


def entry_is_symlink(entry: object) -> bool:
    return isinstance(entry, dict) and "symlink_target" in entry


def entry_is_copied_dir(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("kind") == "copied_dir"


def entry_hash(entry: object) -> str:
    if isinstance(entry, dict):
        return entry.get("sha256", "")
    return str(entry)


def entry_ownership(entry: object) -> str:
    if isinstance(entry, dict):
        return entry.get("ownership", "owned")
    return "owned"


def generate_lockfile(
    target: Path | None,
    repo_root: Path,
    per_adapter_manifests: dict[str, list[InstalledPath]],
    *,
    playbook_version: str,
    profile_names: list[str] | None = None,
    content_scope: list[str] | None = None,
    carry_forward_sections: dict[str, dict] | None = None,
    managed_keys: dict[str, dict] | None = None,
) -> Path:
    """Write .playbook-lock.json from per-Adapter manifests (ADR-0024).

    The `profile` field is persisted so a later `make update` (without an
    explicit --profile) restores the same narrowed content instead of
    silently widening back to the full playbook.

    v0.10 (per the profile-separation principle): the `profile` field is
    a list of profile names. `make install --profile pm,research,developer`
    records `["pm", "research", "developer"]` so the update path re-runs
    the same union. Reads tolerate the v0.9 single-string form by wrapping
    it into a one-element list before reuse.

    `carry_forward_sections` preserves adapter sections from a prior lockfile
    that weren't re-installed this run (e.g. user toggled an adapter off
    without explicitly running `make remove` for it). Without this, the new
    lockfile would forget those installs and `make remove` could no longer
    clean them up.

    `managed_keys` records the registration names each adapter manages inside
    shared config files (MCP server names in ~/.claude.json, hook commands in
    ~/.claude/settings.json, etc.) so a later narrower install can remove
    playbook-managed entries that drop out of the profile while leaving
    user-authored entries intact.
    """
    lock: dict = {
        "lockfile_version": LOCKFILE_VERSION,
        "version": playbook_version,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": str(target) if target else None,
        "profile": list(profile_names) if profile_names else None,
        # v0.11 (ADR-0040): content_scope (NOT just `scope` - avoids collision
        # with ManagedMcpEntry.scope which means "global"|"project").
        # Persists which overlays were active so `make update` restores the
        # same composition without re-running auto-detect.
        "content_scope": list(content_scope) if content_scope else None,
        "adapters": {},
        "managed_keys": managed_keys or {},
    }
    if carry_forward_sections:
        # Seed with prior sections first; per-adapter manifest entries below
        # overwrite any that we just (re)installed.
        for name, prior_entries in carry_forward_sections.items():
            lock["adapters"][name] = dict(prior_entries)
    for adapter_name, manifest in per_adapter_manifests.items():
        entries: dict[str, dict] = {}
        for ip in manifest:
            # We accept symlinks even when the target is missing, because
            # is_symlink() succeeds on a dangling link.
            if not (ip.path.exists() or ip.path.is_symlink()):
                continue
            entry = entry_for(ip.path, ip.ownership)
            if entry is None:
                continue
            entries[relative_to_home(ip.path)] = entry
        lock["adapters"][adapter_name] = entries
    lock_path = (target / LOCKFILE_NAME) if target else (repo_root / LOCKFILE_NAME)
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    return lock_path


def load_lockfile(target: Path | None, repo_root: Path) -> dict | None:
    """Load `.playbook-lock.json` from target or repo_root.

    v0.9 hard cut (ADR-0039): returns the dict only when
    lockfile_version == LOCKFILE_VERSION. Non-v3 lockfiles return None
    with a stderr warning. The install path must additionally call
    ``incompatible_lockfile_path()`` to detect "incompatible lockfile
    present, must clean up before proceeding" -- v0.8 list[str]
    managed_keys would otherwise be silently dropped by v3 readers
    (the adversarial-round-2 HIGH-1 finding).
    """
    import sys as _sys

    candidates = []
    if target is not None:
        candidates.append(target / LOCKFILE_NAME)
    candidates.append(repo_root / LOCKFILE_NAME)
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        version = data.get("lockfile_version")
        if version == LOCKFILE_VERSION:
            return data
        print(
            f"WARN: {candidate} has lockfile_version={version!r}, "
            f"v0.9 requires {LOCKFILE_VERSION}. Treating as no lockfile.",
            file=_sys.stderr,
        )
        return None
    return None


def incompatible_lockfile_path(target: Path | None, repo_root: Path) -> Path | None:
    """Return the path to a non-v3 lockfile that would be USED, else None.

    v0.9 install/update writes call this BEFORE materializing any
    content. A v0.8 lockfile present at the active read site means an
    upgrade in progress; the install path must abort and direct the
    user at the v0.8 cleanup workflow.

    Round-3 adversarial fix: mirror ``load_lockfile`` precedence (first
    hit wins). The earlier implementation walked both target and
    repo_root and returned ANY incompatible candidate, so a user with
    a valid v3 target lockfile could get exit 3 because of an unrelated
    stale lockfile at repo_root. Now we only inspect the lockfile that
    would actually be loaded.
    """
    # Round-4 round-2 fix (regular review P3): mirror load_lockfile's
    # full semantics. Parse failures (corrupt file, unreadable, wrong
    # JSON shape) at the FIRST candidate must NOT cause us to skip the
    # FALLBACK candidate. load_lockfile() skips parse failures via
    # `continue`; this helper now does the same so a corrupt target
    # lockfile cannot mask a v0.8 repo_root lockfile that would still
    # be loaded by the install dispatcher.
    candidates = []
    if target is not None:
        candidates.append(target / LOCKFILE_NAME)
    candidates.append(repo_root / LOCKFILE_NAME)
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("lockfile_version") == LOCKFILE_VERSION:
            return None
        return candidate
    return None


def resolve_locked_path(rel_or_abs: str) -> Path:
    """Resolve a lockfile-recorded path string back to an absolute Path.

    Lockfile keys are stored relative to $HOME when possible and absolute
    otherwise; this is the inverse of `relative_to_home`.
    """
    p = Path(rel_or_abs)
    return p if p.is_absolute() else Path.home() / rel_or_abs


def print_incompatible_lockfile_error(bad_lock: Path) -> None:
    """Print the v0.8-lockfile-detected stderr message. Same body used by
    install.main() and _run_install() so the wording does not drift.

    Direct the user at manual cleanup or a v0.8 checkout so the worst case
    is "skills/hooks left behind" rather than "tracking record silently
    deleted" (the current install --remove flow rejects a v0.8 lockfile
    too, so it would no-op while users believe cleanup happened).
    """
    print(
        f"\nERROR: incompatible lockfile detected at {bad_lock}",
        file=sys.stderr,
    )
    print(
        "  v0.9 introduced a hard schema cut (ADR-0039); the playbook will\n"
        "  not safely upgrade a v0.8 install in place. The current\n"
        "  scripts/install.py --remove cannot clean a v0.8 lockfile either.\n\n"
        "  To proceed (build-phase machines only; no users yet):\n"
        "    1. (Optional) Check out the last v0.8 commit and run that\n"
        "       version's `make remove` to clean up tracked files + native\n"
        "       config entries from the v0.8 install:\n"
        "         git checkout <last-v0.8-sha>\n"
        "         make remove\n"
        "         git checkout -\n"
        "    2. Delete the v0.8 lockfile by hand:\n"
        f"         rm {bad_lock}\n"
        "    3. Re-run `make install` with v0.9.\n\n"
        "  If you skip step 1, any skills/hooks/MCP entries the v0.8\n"
        "  install wrote will remain on disk. The v0.9 install will not\n"
        "  delete them; only the v0.8 lockfile-aware remove can.",
        file=sys.stderr,
    )


def copied_dir_drift(full: Path, locked_entry: object) -> str | None:
    """Return a drift description if a copied_dir lockfile entry differs
    from on-disk, or None if pristine / not applicable.

    v0.8 deduplication: cmd_status (install.py), cmd_remove via
    cleanup_orphans (install_orphans.py), and cmd_verify via
    verify_adapter (install_verify.py) all need to ask "does this
    copied directory still match its recorded tree_sha256?" Inlining
    that branch three times produced three subtly-different copies; the
    Cursor review flagged the duplication. This function is the single
    source of truth.

    Returns:
        None if the entry is not a copied_dir, the path is missing, the
        tree is unreadable, or the recorded hash matches the on-disk
        tree.
        "missing" if the directory itself is gone (caller may classify
        differently per command).
        "drift" if the recorded tree_sha256 differs from on-disk.
        "unreadable" if the hash could not be computed.
    """
    if not entry_is_copied_dir(locked_entry):
        return None
    if not full.is_dir():
        return "missing"
    expected = (
        locked_entry.get("tree_sha256", "") if isinstance(locked_entry, dict) else ""
    )
    if not expected:
        return None
    try:
        actual = hash_dir(full)
    except (OSError, PermissionError):
        return "unreadable"
    return "drift" if actual != expected else None


__all__ = [
    "LOCKFILE_NAME",
    "LOCKFILE_VERSION",
    "ManagedMcpEntry",
    "entry_for",
    "entry_hash",
    "entry_is_copied_dir",
    "entry_is_symlink",
    "entry_ownership",
    "generate_lockfile",
    "hash_dir",
    "hash_file",
    "incompatible_lockfile_path",
    "load_lockfile",
    "make_managed_mcp_entry",
    "managed_entries_for_config",
    "relative_to_home",
    "resolve_locked_path",
]
