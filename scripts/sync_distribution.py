#!/usr/bin/env python3
"""Playbook content distribution sync.

Per ADR-0042: reads a manifest, scrubs peripheral references, and copies
allowlisted paths from this playbook into an external destination repo.
Never auto-commits, never auto-pushes. The destination's working tree is
updated; the operator reviews via `git diff` and commits manually.

Usage:
  python3 scripts/sync_distribution.py --manifest /path/to/manifest.toml
  python3 scripts/sync_distribution.py --manifest /path/to/manifest.toml --dry-run
  python3 scripts/sync_distribution.py memory --manifest /path/to/manifest.toml

Exit codes:
  0  success
  1  validation error (clean tree, schema, etc.)
  2  another sync run is active (lock file present and fresh)
  3  source / destination IO error
  4  user-rejected direction (--direction reverse not implemented)
  5  marketplace emit safety failure (reserved catalog name, slug,
     path-safety, or materialize failure; per ADR-0043). Raised by the
     [marketplace] integration so the cron wrapper can distinguish a
     safety failure from a generic IO error (3).
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Iterator


LOCK_PATH = Path("/tmp/playbook-distribution-sync.lock")
LOCK_STALE_AFTER_SECONDS = 3600  # 1 hour
LOG_PATH = (
    Path(os.environ.get("PLAYBOOK_SYNC_LOG", ""))
    if os.environ.get("PLAYBOOK_SYNC_LOG")
    else Path.home() / "Library" / "Logs" / "playbook-distribution-sync.log"
)
TOOL_VERSION = "sync_distribution.py v1.1"

# Files we will read+scrub+write as text. Binary files would mangle if
# scrubbed; the conservative play is to copy them as bytes without
# touching content. The list is intentionally explicit so an unknown
# extension errs on the safe side (bytes copy, no scrub).
TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".py",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".sh",
        ".jinja",
        ".jinja2",
        ".j2",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".txt",
        ".cfg",
        ".ini",
        ".conf",
        ".env",
        ".example",
    }
)

# Files whose name (not suffix) marks them as text. Dotfiles + extension-
# less files don't get caught by Path.suffix (".gitattributes" → suffix
# ""); they're handled here explicitly. Without this, root dotfiles in
# the allowlist take the binary copy path and bypass scrub even when the
# operator clearly intended for their contents to be scrubbed.
TEXT_FILENAMES = frozenset(
    {
        "Makefile",
        "Dockerfile",
        "LICENSE",
        "VERSION",
        "README",
        ".gitignore",
        ".gitattributes",
        ".agents-md-ignore",
        ".editorconfig",
        ".dockerignore",
    }
)

# Default exclusions baked into the allowlist walker. These are caches
# and metadata dirs that should never flow to a destination repo
# regardless of operator manifest content. Public-facing destinations
# would otherwise receive .pyc bytes when scripts/ or tests/ are
# allowlisted whole.
DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        ".venv",
        "venv",
        ".DS_Store",
    }
)

AUDIT_FILENAME = ".sync-manifest.json"


@dataclass
class ScrubPattern:
    """One regex substitution applied to text content."""

    pattern: re.Pattern[str]
    replacement: str

    def apply(self, text: str) -> str:
        return self.pattern.sub(self.replacement, text)


@dataclass
class Manifest:
    """Parsed manifest contents (in-memory)."""

    destination_path: Path
    require_clean_git: bool
    allowlist: list[str]
    denylist: list[str]
    scrubs: list[ScrubPattern]
    memory_source_dir: Path | None = None
    memory_destination_dir: Path | None = None
    memory_allowlist: list[str] = field(default_factory=list)
    memory_denylist: list[str] = field(default_factory=list)
    marketplace_catalog_name: str | None = None
    marketplace_author_name: str | None = None
    marketplace_author_email: str | None = None
    marketplace_profiles_dir: str | None = None
    marketplace_default_profile_version: str | None = None

    def scrub_rules_hash(self) -> str:
        # Include compiled flags so case_insensitive flips trigger drift
        # warnings on the next sync. Without `p.pattern.flags` in the
        # payload, switching `case_insensitive = false` -> true (or vice
        # versa) produced an identical hash and drift detection stayed
        # silent. (Second-eye review 2026-05-27.)
        payload = "\n".join(
            f"{p.pattern.pattern}::flags={p.pattern.flags}::{p.replacement}"
            for p in self.scrubs
        )
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def allowlist_hash(self) -> str:
        payload = "\n".join(self.allowlist) + "\n--\n" + "\n".join(self.denylist)
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stderr(*parts: object) -> None:
    print(*parts, file=sys.stderr)


def _load_manifest(manifest_path: Path) -> Manifest:
    """Read + validate the manifest TOML. Raises SystemExit on schema errors."""
    if not manifest_path.is_file():
        raise SystemExit(f"manifest not found: {manifest_path}")
    try:
        with manifest_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"manifest parse error: {exc}") from exc

    dest = data.get("destination", {})
    dest_path_str = dest.get("path")
    if not isinstance(dest_path_str, str) or not dest_path_str:
        raise SystemExit("manifest: [destination].path is required (string)")
    require_clean_git = bool(dest.get("require_clean_git", True))

    sources = data.get("sources", {})
    allowlist_raw = sources.get("allowlist", [])
    denylist_raw = sources.get("denylist", [])
    if not isinstance(allowlist_raw, list):
        raise SystemExit("manifest: [sources].allowlist must be a list")
    if not isinstance(denylist_raw, list):
        raise SystemExit("manifest: [sources].denylist must be a list")
    allowlist = [str(p) for p in allowlist_raw if isinstance(p, str)]
    denylist = [str(p) for p in denylist_raw if isinstance(p, str)]
    if not allowlist:
        raise SystemExit("manifest: [sources].allowlist cannot be empty")

    scrubs: list[ScrubPattern] = []
    scrub_block = data.get("scrubs", {})
    patterns_raw = scrub_block.get("patterns", [])
    if not isinstance(patterns_raw, list):
        raise SystemExit("manifest: [scrubs].patterns must be a list")
    for idx, entry in enumerate(patterns_raw):
        if not isinstance(entry, dict):
            raise SystemExit(f"manifest: scrubs.patterns[{idx}] must be a table")
        match = entry.get("match")
        replace = entry.get("replace", "")
        if not isinstance(match, str) or not match:
            raise SystemExit(
                f"manifest: scrubs.patterns[{idx}].match is required (string)"
            )
        if not isinstance(replace, str):
            raise SystemExit(
                f"manifest: scrubs.patterns[{idx}].replace must be a string"
            )
        # Default is case-insensitive matching. Set
        # `case_insensitive = false` per-pattern to force case-sensitive.
        # The default catches misformatted casing in source content
        # (team vs team vs team), which would otherwise leak.
        flags = 0 if entry.get("case_insensitive") is False else re.IGNORECASE
        try:
            compiled = re.compile(match, flags)
        except re.error as exc:
            raise SystemExit(
                f"manifest: scrubs.patterns[{idx}].match is not a valid regex: {exc}"
            ) from exc
        scrubs.append(ScrubPattern(pattern=compiled, replacement=replace))

    memory_block = data.get("memory", {})
    msrc = memory_block.get("source_dir")
    mdst = memory_block.get("destination_dir")
    memory_allowlist_raw = memory_block.get("allowlist", [])
    memory_denylist_raw = memory_block.get("denylist", [])
    memory_source_dir = Path(msrc).expanduser() if isinstance(msrc, str) else None
    memory_destination_dir = Path(mdst).expanduser() if isinstance(mdst, str) else None
    if isinstance(memory_allowlist_raw, list):
        memory_allowlist = [str(s) for s in memory_allowlist_raw if isinstance(s, str)]
    else:
        memory_allowlist = []
    if isinstance(memory_denylist_raw, list):
        memory_denylist = [str(s) for s in memory_denylist_raw if isinstance(s, str)]
    else:
        memory_denylist = []

    marketplace_block = data.get("marketplace", {})
    if not isinstance(marketplace_block, dict):
        raise SystemExit("manifest: [marketplace] must be a table")
    marketplace_catalog_name = marketplace_block.get("catalog_name")
    marketplace_author_name = marketplace_block.get("author_name")
    marketplace_author_email = marketplace_block.get("author_email")
    marketplace_profiles_dir = marketplace_block.get("profiles_dir")
    marketplace_default_profile_version = marketplace_block.get(
        "default_profile_version"
    )
    for name, value in (
        ("catalog_name", marketplace_catalog_name),
        ("author_name", marketplace_author_name),
        ("profiles_dir", marketplace_profiles_dir),
    ):
        if value is not None and not isinstance(value, str):
            raise SystemExit(f"manifest: [marketplace].{name} must be a string")
    if marketplace_author_email is not None and not isinstance(
        marketplace_author_email, str
    ):
        raise SystemExit("manifest: [marketplace].author_email must be a string")
    if marketplace_default_profile_version is not None and not isinstance(
        marketplace_default_profile_version, str
    ):
        raise SystemExit(
            "manifest: [marketplace].default_profile_version must be a string"
        )
    # All-or-none: a partial [marketplace] block must fail loud at load time
    # rather than silently skipping the emit step at run time. The three
    # required keys are catalog_name + author_name + profiles_dir.
    _required_marketplace = {
        "catalog_name": marketplace_catalog_name,
        "author_name": marketplace_author_name,
        "profiles_dir": marketplace_profiles_dir,
    }
    _present = [k for k, v in _required_marketplace.items() if v]
    if _present and len(_present) != len(_required_marketplace):
        _missing = sorted(set(_required_marketplace) - set(_present))
        raise SystemExit(
            "manifest: [marketplace] is partially configured; it requires "
            f"all of catalog_name + author_name + profiles_dir (missing: "
            f"{', '.join(_missing)}). Remove the block to disable marketplace "
            "emit, or fill in every required key."
        )

    return Manifest(
        destination_path=Path(dest_path_str).expanduser().resolve(),
        require_clean_git=require_clean_git,
        allowlist=allowlist,
        denylist=denylist,
        scrubs=scrubs,
        memory_source_dir=memory_source_dir,
        memory_destination_dir=memory_destination_dir,
        memory_allowlist=memory_allowlist,
        memory_denylist=memory_denylist,
        marketplace_catalog_name=marketplace_catalog_name,
        marketplace_author_name=marketplace_author_name,
        marketplace_author_email=marketplace_author_email,
        marketplace_profiles_dir=marketplace_profiles_dir,
        marketplace_default_profile_version=marketplace_default_profile_version,
    )


def _acquire_lock() -> None:
    """Create the lock file or abort if a fresh lock is held."""
    if LOCK_PATH.exists():
        age = datetime.now(UTC).timestamp() - LOCK_PATH.stat().st_mtime
        if age < LOCK_STALE_AFTER_SECONDS:
            _stderr(
                f"another sync is in progress (lock at {LOCK_PATH}, "
                f"age {int(age)}s); aborting cleanly"
            )
            raise SystemExit(2)
        _stderr(
            f"stale lock at {LOCK_PATH} (age {int(age)}s > "
            f"{LOCK_STALE_AFTER_SECONDS}s); reclaiming"
        )
    LOCK_PATH.write_text(
        f"{datetime.now(UTC).isoformat()}\npid={os.getpid()}\n",
        encoding="utf-8",
    )


def _release_lock() -> None:
    """Best-effort lock removal."""
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def _validate_clean_git(repo: Path) -> bool:
    """Return True if `repo` is a clean git working tree, False otherwise."""
    if not (repo / ".git").exists():
        _stderr(f"destination is not a git repo: {repo}")
        return False
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _stderr(f"git status failed in {repo}: {result.stderr.strip()}")
        return False
    return result.stdout.strip() == ""


def _validate_clean_source(repo: Path) -> tuple[bool, str]:
    """Return (clean, detail). source dirty = reproducibility hazard.

    The audit records `source_commit` from `git rev-parse HEAD`, but if
    the working tree has uncommitted edits, the synced content reflects
    those edits while the audit claims it came from HEAD. A future
    operator who tries to reproduce the destination from `source_commit`
    will see different content. Second-eye review (2026-05-27) caught
    this as a HIGH reproducibility hole.

    Returns (True, "") for a clean source, (False, "<detail>") otherwise.
    """
    if not (repo / ".git").exists():
        # Source might be a non-git checkout (extracted tarball, vendored).
        # In that case the audit's source_commit is "unknown" anyway and
        # the reproducibility risk is operator-acknowledged.
        return (True, "")
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return (False, f"git status failed: {result.stderr.strip()}")
    if result.stdout.strip() != "":
        # Trim the porcelain to two lines so the stderr message stays
        # operator-readable; the full diff is one `git status` away.
        sample = "\n".join(result.stdout.strip().splitlines()[:2])
        return (False, f"uncommitted changes:\n  {sample}")
    return (True, "")


def _source_commit(repo: Path) -> tuple[str, str]:
    """Return (sha, branch) for the source repo's current HEAD."""
    sha_result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    branch_result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return (sha_result.stdout.strip(), branch_result.stdout.strip())


def _is_text_file(path: Path) -> bool:
    """Whether the file is treated as text (scrubbed) vs binary (raw bytes).

    Checks the file's suffix first (covers `.md`, `.py`, etc.), then falls
    back to the filename (`Makefile`, `LICENSE`, dotfiles like
    `.gitattributes`). Dotfiles have an empty `Path.suffix`, so without
    the filename fallback they take the binary copy path and bypass scrub
    even when their content clearly contains scrubbable tokens.
    """
    if path.suffix in TEXT_EXTENSIONS:
        return True
    if path.name in TEXT_FILENAMES:
        return True
    return False


def _is_path_under(path: str, prefix: str) -> bool:
    """Return True if `path` is under `prefix` (where prefix may end with /)."""
    prefix_norm = prefix.rstrip("/")
    if path == prefix_norm:
        return True
    return path.startswith(prefix_norm + "/")


def _within(path: Path, root: Path) -> bool:
    """Return True if path resolves to a location inside root.

    Used to reject manifest entries that escape source_root (e.g. a
    `..` traversal). Resolves both sides via realpath so symlinks can't
    smuggle paths outside the boundary.
    """
    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def _walk_with_default_excludes(root: Path) -> Iterator[Path]:
    """Iterator over files under root, skipping DEFAULT_EXCLUDED_DIR_NAMES.

    Cheaper + safer than `root.rglob("*")` followed by post-filtering:
    pruning at the directory level avoids walking large cache trees and
    avoids any chance of yielding a file inside a denylisted dir that
    later misses the substring check.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                if entry.name in DEFAULT_EXCLUDED_DIR_NAMES:
                    continue
                stack.append(entry)
                continue
            # Files (including symlinks) yield. iterdir() also returns
            # symlinks pointing at directories; treat those as files
            # (they'll be preserved as symlinks by _copy_file).
            if entry.is_file() or entry.is_symlink():
                yield entry


def _resolve_sources(
    source_root: Path, allowlist: list[str], denylist: list[str]
) -> list[Path]:
    """Expand allowlist entries into a concrete list of source files.

    Files relative to source_root that match an allowlist entry (file or
    directory prefix) and do NOT match any denylist entry are returned.

    Entries that escape source_root via traversal (e.g. `../notes.md`)
    are rejected with a stderr warning rather than silently writing
    outside the destination repo.

    Default-excluded dir names (`__pycache__`, `.git`, `.pytest_cache`,
    etc.) are rejected even when explicitly named in the allowlist. The
    walker already prunes them as children, but a top-level allowlist
    entry like `"scripts/__pycache__/"` would otherwise bypass the
    prune by starting the walk INSIDE the excluded dir. Second-eye
    review (2026-05-27) caught this gap. The default-exclude policy is
    firm: cache and metadata dirs should never flow to a destination
    regardless of operator manifest.
    """
    result: list[Path] = []
    seen: set[Path] = set()
    source_root_resolved = source_root.resolve()
    for entry in allowlist:
        candidate = source_root / entry.rstrip("/")
        if not _within(candidate, source_root_resolved):
            _stderr(
                f"WARN: allowlist entry escapes source_root and will be "
                f"ignored: {entry}"
            )
            continue
        # Reject explicit allowlist of a default-excluded dir. We check
        # by name (not the resolved location) so the policy is operator-
        # visible in the manifest entry itself.
        if candidate.name in DEFAULT_EXCLUDED_DIR_NAMES:
            _stderr(
                f"WARN: allowlist entry {entry!r} names a default-excluded "
                f"dir; refusing to ship cache / metadata content"
            )
            continue
        if candidate.is_file():
            if candidate not in seen:
                result.append(candidate)
                seen.add(candidate)
            continue
        if candidate.is_dir():
            for file_path in _walk_with_default_excludes(candidate):
                if file_path not in seen:
                    result.append(file_path)
                    seen.add(file_path)
            continue
        # Allowlist entry that does not exist on disk is a manifest warning,
        # not a fatal error. The operator may have referenced a file that
        # got removed since the manifest was written.
        _stderr(f"WARN: allowlist entry not found in source: {entry}")

    if not denylist:
        return sorted(result)

    def _denied(rel: str) -> bool:
        return any(_is_path_under(rel, d) for d in denylist)

    filtered: list[Path] = []
    for file_path in result:
        rel = str(file_path.relative_to(source_root))
        if _denied(rel):
            continue
        filtered.append(file_path)
    return sorted(filtered)


def _scrub_text(text: str, scrubs: list[ScrubPattern]) -> str:
    for s in scrubs:
        text = s.apply(text)
    return text


def _copy_file(
    src: Path,
    dst: Path,
    scrubs: list[ScrubPattern],
    dry_run: bool,
    source_root: Path | None = None,
) -> tuple[bool, str | None]:
    """Copy `src` to `dst` with optional scrub.

    Returns (changed, error_message). `changed` is True if dst would be
    modified or created. In dry_run mode no writes happen.

    Symlinks are preserved as symlinks; the link target is copied verbatim
    (no scrub, since scrubbing a path string would break the symlink).
    Without this, materializing a symlink as a plain copy of its target's
    bytes produces a duplicate-content file at the destination, which the
    hook-source-unification check correctly flags as drift.

    Safety (adversarial review 2026-05-27): a symlink inside an
    allowlisted directory could point outside `source_root` and, when
    preserved verbatim, leak the path string + create an attacker-
    controlled link at the destination. When `source_root` is provided
    the resolved target is checked against it; symlinks escaping the
    source tree are rejected with an error.
    """
    try:
        if src.is_symlink():
            target = os.readlink(src)
            if source_root is not None:
                # Resolve the symlink target relative to the symlink's
                # parent (per POSIX symlink semantics). If the resolved
                # path leaves source_root, reject.
                target_path = Path(target)
                if target_path.is_absolute():
                    resolved = target_path
                else:
                    resolved = src.parent / target_path
                try:
                    resolved_abs = resolved.resolve(strict=False)
                except OSError:
                    return (False, f"unreadable symlink target for {src}")
                if not _within(resolved_abs, source_root.resolve()):
                    return (
                        False,
                        f"symlink {src} -> {target} escapes source_root; refusing to preserve",
                    )
            if dst.is_symlink() and os.readlink(dst) == target:
                return (False, None)
            if dry_run:
                return (True, None)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() or dst.is_symlink():
                dst.unlink()
            os.symlink(target, dst)
            return (True, None)
        if _is_text_file(src):
            content = src.read_text(encoding="utf-8", errors="replace")
            scrubbed = _scrub_text(content, scrubs)
            new_bytes = scrubbed.encode("utf-8")
        else:
            new_bytes = src.read_bytes()
    except OSError as exc:
        return (False, f"read failed for {src}: {exc}")

    if dst.is_symlink():
        # Source used to be a symlink and isn't anymore (or never was a
        # symlink and destination has a stale one). Drop the stale link
        # so the regular file write below isn't attempting to follow it.
        try:
            dst.unlink()
        except OSError:
            pass
    elif dst.is_file():
        try:
            existing = dst.read_bytes()
        except OSError as exc:
            return (False, f"read failed for existing {dst}: {exc}")
        if existing == new_bytes:
            return (False, None)

    if dry_run:
        return (True, None)

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(new_bytes)
        if src.suffix == ".sh" or src.name == "Makefile":
            shutil.copymode(src, dst)
    except OSError as exc:
        return (False, f"write failed for {dst}: {exc}")
    return (True, None)


def _read_prior_audit(destination: Path) -> dict | None:
    """Return the prior .sync-manifest.json contents, or None if absent.

    A missing audit file is the normal first-sync condition; a malformed
    audit file is logged but treated like absent so the next sync can
    rewrite it.
    """
    target = destination / AUDIT_FILENAME
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _stderr(f"WARN: prior audit at {target} is malformed; rewriting: {exc}")
        return None


def _semantically_equal_audit(prior: dict | None, current: dict) -> bool:
    """Compare two audit payloads ignoring synced_at + tool_version.

    Returns True if every load-bearing field matches: source_commit (the
    source identity), source_repo + source_branch (after scrub), the
    two hashes (manifest identity), and the synced_files set (what was
    written). When True, the audit on disk is still accurate and we can
    skip the rewrite (preserving the destination's git diff cleanliness
    for unattended cron runs).
    """
    if prior is None:
        return False
    semantic_fields = (
        "source_commit",
        "source_repo",
        "source_branch",
        "scrub_rules_hash",
        "allowlist_hash",
    )
    for field_name in semantic_fields:
        if prior.get(field_name) != current.get(field_name):
            return False
    prior_files = set(prior.get("synced_files") or [])
    current_files = set(current.get("synced_files") or [])
    return prior_files == current_files


def _warn_manifest_drift(prior: dict | None, current: dict) -> None:
    """If the manifest's hashes changed since the prior sync, warn.

    Recording hashes without comparing them is half an audit trail.
    Surfacing the drift gives the operator a chance to re-read their
    own scrub rule changes before the destination's working tree is
    rewritten under different rules.
    """
    if prior is None:
        return
    if prior.get("scrub_rules_hash") != current.get("scrub_rules_hash"):
        _stderr(
            f"WARN: scrub_rules_hash differs from prior sync "
            f"(prior={prior.get('scrub_rules_hash')}, "
            f"current={current.get('scrub_rules_hash')}); "
            f"every destination file may be rewritten under new rules"
        )
    if prior.get("allowlist_hash") != current.get("allowlist_hash"):
        _stderr(
            f"WARN: allowlist_hash differs from prior sync "
            f"(prior={prior.get('allowlist_hash')}, "
            f"current={current.get('allowlist_hash')}); "
            f"manifest scope changed since last sync"
        )


def _delete_stale_files(
    destination: Path, prior: dict | None, current_files: list[str]
) -> list[str]:
    """Delete files the prior sync wrote that the current sync did not.

    A file that was in prior `synced_files` but is missing from current
    is either: (a) removed from source allowlist, (b) added to denylist,
    or (c) removed from upstream entirely. In every case the operator
    intent is "this file should no longer live under managed paths at
    the destination." Leaving it produces silent drift between
    `.sync-manifest.json` and the destination's working tree.

    Safety: each prior `synced_files` entry is validated before deletion.
    Absolute paths and entries whose resolved target escapes `destination`
    are rejected with a stderr warning. A corrupted or malicious audit
    file containing `../etc/passwd` or `/absolute/path` therefore cannot
    make the next sync delete files outside the destination repo. The
    adversarial review (2026-05-27) surfaced this hole: the prior pass
    only validated writes, not deletions.

    Returns the list of files that were actually deleted (excluding
    those already absent at the destination, which is a no-op).
    """
    if prior is None:
        return []
    prior_files = prior.get("synced_files") or []
    if not isinstance(prior_files, list):
        _stderr(
            f"WARN: prior audit at {destination / AUDIT_FILENAME} has "
            "malformed synced_files (not a list); skipping stale-delete"
        )
        return []
    current_set = set(current_files)
    destination_resolved = destination.resolve()
    deleted: list[str] = []
    for rel in sorted(set(prior_files) - current_set):
        if not isinstance(rel, str) or not rel:
            _stderr("WARN: prior synced_files entry is not a string; skipping")
            continue
        # Reject absolute paths and any traversal that resolves outside
        # destination. Without this, `synced_files: ["../etc/passwd"]`
        # in a corrupted audit would make the next sync unlink that path.
        rel_path = Path(rel)
        if rel_path.is_absolute():
            _stderr(
                f"WARN: prior synced_files contains absolute path {rel!r}; "
                "refusing to delete; audit may be corrupted"
            )
            continue
        target = destination / rel_path
        if not _within(target, destination_resolved):
            _stderr(
                f"WARN: prior synced_files path {rel!r} resolves outside "
                f"destination; refusing to delete"
            )
            continue
        if target.is_symlink() or target.is_file():
            try:
                target.unlink()
                deleted.append(rel)
            except OSError as exc:
                _stderr(f"WARN: could not delete stale {target}: {exc}")
    return deleted


def _build_audit_payload(
    manifest: Manifest,
    source_root: Path,
    source_sha: str,
    source_branch: str,
    synced_files: list[str],
) -> dict:
    """Compose the audit dict (without writing it).

    source_repo and source_branch run through the manifest scrubs so the
    destination's audit metadata doesn't leak the team-identifier tokens
    the rest of the sync was built to remove. source_commit is a hex SHA
    that cannot encode identity by itself; it stays untouched.
    """
    raw_source_repo = _source_remote_url(source_root) or "unknown"
    return {
        "source_repo": _scrub_text(raw_source_repo, manifest.scrubs),
        "source_commit": source_sha,
        "source_branch": _scrub_text(source_branch, manifest.scrubs),
        "synced_at": datetime.now(UTC).isoformat(),
        "scrub_rules_hash": manifest.scrub_rules_hash(),
        "allowlist_hash": manifest.allowlist_hash(),
        "tool_version": TOOL_VERSION,
        "synced_files": synced_files,
    }


def _write_audit_if_changed(
    destination: Path,
    prior: dict | None,
    current: dict,
) -> bool:
    """Write the audit JSON to disk only when the prior is missing or stale.

    Returns True if a write happened. Skipping the write when no semantic
    field changed preserves the destination's git diff cleanliness on
    scheduled cron runs, so the operator sees real updates instead of
    cosmetic synced_at churn.
    """
    if _semantically_equal_audit(prior, current):
        return False
    target = destination / AUDIT_FILENAME
    target.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def _source_remote_url(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _resolve_source_root(override: Path | None) -> Path:
    """Return the source playbook root.

    Tests pass an explicit override to avoid the `__file__`-based default,
    which would otherwise force tests to monkeypatch the module global.
    """
    if override is not None:
        return override
    return Path(__file__).resolve().parent.parent


def run_distribution(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    source_root = _resolve_source_root(getattr(args, "_source_root_override", None))

    if not manifest.destination_path.is_dir():
        _stderr(f"destination directory not found: {manifest.destination_path}")
        return 1

    if manifest.require_clean_git and not args.allow_dirty:
        if not _validate_clean_git(manifest.destination_path):
            _stderr(
                "destination working tree is not clean; use --allow-dirty to override"
            )
            return 1

    # Source dirty state breaks the audit's reproducibility contract:
    # the recorded source_commit doesn't include uncommitted edits in
    # the working tree. Default-on; --allow-source-dirty overrides for
    # the operator who knowingly wants to sync a WIP state.
    if not getattr(args, "allow_source_dirty", False):
        clean, detail = _validate_clean_source(source_root)
        if not clean:
            _stderr(
                f"source working tree is not clean ({detail}); "
                "the audit's source_commit will not reproduce the "
                "synced content. Commit or stash, or pass "
                "--allow-source-dirty to override."
            )
            return 1

    source_sha, source_branch = _source_commit(source_root)
    sources = _resolve_sources(source_root, manifest.allowlist, manifest.denylist)
    if not sources:
        _stderr("allowlist expanded to zero files; nothing to do")
        return 1

    changed = 0
    errors: list[str] = []
    synced_rel: list[str] = []
    destination = manifest.destination_path
    destination_resolved = destination.resolve()
    for src in sources:
        rel = src.relative_to(source_root)
        dst = destination / rel
        # Belt-and-suspenders: even though _resolve_sources already
        # rejected entries escaping source_root, recheck destination at
        # write time. A malformed relative path that survives
        # relative_to would still get caught before we touch the
        # filesystem outside the destination.
        if not _within(dst, destination_resolved):
            errors.append(f"destination path escapes destination_path: {rel}")
            continue
        was_changed, err = _copy_file(
            src, dst, manifest.scrubs, args.dry_run, source_root=source_root
        )
        if err is not None:
            errors.append(err)
            continue
        if was_changed:
            changed += 1
        synced_rel.append(str(rel))

    if errors:
        for e in errors:
            _stderr(f"ERROR: {e}")
        return 3

    prior = _read_prior_audit(destination)
    audit_payload = _build_audit_payload(
        manifest, source_root, source_sha, source_branch, synced_rel
    )
    _warn_manifest_drift(prior, audit_payload)

    deleted: list[str] = []
    if not args.dry_run:
        deleted = _delete_stale_files(destination, prior, synced_rel)
        audit_written = _write_audit_if_changed(destination, prior, audit_payload)
    else:
        audit_written = False

    marketplace_files = _maybe_run_marketplace_emit(manifest, args.dry_run)

    print(f"Source commit: {source_sha} ({source_branch})")
    print(f"Destination:   {destination}")
    print(f"Files scanned: {len(sources)}")
    print(f"Files changed: {changed}{' (dry-run)' if args.dry_run else ''}")
    print(f"Stale removed: {len(deleted)}")
    print(f"Audit updated: {'yes' if audit_written else 'no (idempotent)'}")
    print(f"Scrub rules:   {len(manifest.scrubs)}")
    if marketplace_files is not None:
        print(f"Marketplace:   {marketplace_files} file writes")
    if args.dry_run:
        print(
            "\nDry-run complete. Review the diff at destination "
            "(`git -C <dest> diff`) before re-running without --dry-run."
        )
    return 0


def _maybe_run_marketplace_emit(manifest: Manifest, dry_run: bool) -> int | None:
    """If the manifest declares a [marketplace] block, invoke the emitter
    facade after the content sync completes. Returns the file-write count,
    or None when the block is absent or the step is skipped in dry-run.

    SECURITY (ADR-0042 scrub contract): the emitter reads BOTH profiles and
    base content from the DESTINATION tree, which this run has already
    scrubbed + allowlist/denylist filtered. Reading from the source would
    copy unscrubbed skills/rules/hooks/profiles straight into the public
    plugin directories, bypassing the scrub layer. The operator must
    therefore include `profiles/` (and `base/`) in [sources].allowlist so
    the scrubbed copies exist at the destination before this step runs.

    Because the emit reads the destination, it CANNOT run under --dry-run:
    a dry-run copies nothing, so the destination is empty (fresh) or stale
    (prior run). Emitting then would either fail or verify the wrong tree.
    The step is therefore skipped in dry-run with an explanatory note.
    """
    # Partial blocks are rejected at manifest load; here all-three-present
    # means enabled, none means disabled.
    if not (
        manifest.marketplace_catalog_name
        and manifest.marketplace_author_name
        and manifest.marketplace_profiles_dir
    ):
        return None

    if dry_run:
        _stderr(
            "marketplace emit skipped in dry-run: the emitter reads the "
            "scrubbed destination tree, which a dry-run does not populate. "
            "Re-run without --dry-run to emit the plugin catalogs."
        )
        return None

    from marketplace_config import (
        MarketplaceEmitError,
        SyncMarketplaceManifest,
        run_marketplace_emit,
    )

    dest = manifest.destination_path
    # repo_root == destination: read the SCRUBBED tree, not source.
    adapter = SyncMarketplaceManifest(
        repo_root=dest,
        destination=dest,
        catalog_name=manifest.marketplace_catalog_name or "",
        author_name=manifest.marketplace_author_name or "",
        author_email=manifest.marketplace_author_email,
        profiles_dir=(dest / (manifest.marketplace_profiles_dir or "")).resolve(),
        default_profile_version=manifest.marketplace_default_profile_version,
    )
    try:
        return run_marketplace_emit(adapter, dry_run=False)
    except MarketplaceEmitError as exc:
        # Preserve the emitter's declared exit code (5 = safety failure:
        # reserved name, slug, path-safety, materialize) so the scheduled
        # wrapper can distinguish it from a generic IO error (3).
        _stderr(f"marketplace emit failed: {exc}")
        raise SystemExit(exc.exit_code) from exc


def run_memory(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    if manifest.memory_source_dir is None or manifest.memory_destination_dir is None:
        _stderr(
            "manifest: [memory] requires source_dir and destination_dir for the memory sub-command"
        )
        return 1
    if not manifest.memory_source_dir.is_dir():
        _stderr(f"memory source dir not found: {manifest.memory_source_dir}")
        return 1
    manifest.memory_destination_dir.mkdir(parents=True, exist_ok=True)

    allowlist = manifest.memory_allowlist
    denylist = manifest.memory_denylist

    def _matches(slug: str, patterns: list[str]) -> bool:
        """Match against exact slugs OR fnmatch globs (project_*, etc.)."""
        return any(slug == p or fnmatch.fnmatch(slug, p) for p in patterns)

    changed = 0
    ported: list[str] = []
    for entry in sorted(manifest.memory_source_dir.glob("*.md")):
        slug = entry.stem
        if slug == "MEMORY":
            continue
        if allowlist and not _matches(slug, allowlist):
            continue
        if _matches(slug, denylist):
            continue
        try:
            content = entry.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _stderr(f"ERROR: cannot read {entry}: {exc}")
            return 3
        scrubbed = _scrub_text(content, manifest.scrubs)
        dst = manifest.memory_destination_dir / entry.name
        if dst.is_file():
            existing = dst.read_text(encoding="utf-8", errors="replace")
            if existing == scrubbed:
                ported.append(slug)
                continue
        if not args.dry_run:
            dst.write_text(scrubbed, encoding="utf-8")
        changed += 1
        ported.append(slug)

    deleted_count = 0
    index_written = False
    prior_memory_audit = _read_prior_audit(manifest.memory_destination_dir)
    if not args.dry_run:
        deleted_count = _delete_stale_memory_entries(
            manifest.memory_destination_dir, ported, prior_memory_audit
        )
        index_written = _write_memory_index_if_changed(
            manifest.memory_destination_dir, ported
        )
        # Track which entries this run ported so the next run knows what
        # IT previously wrote and can stale-delete safely.
        _write_memory_audit(manifest.memory_destination_dir, ported, manifest.scrubs)

    print(f"Memory source:      {manifest.memory_source_dir}")
    print(f"Memory destination: {manifest.memory_destination_dir}")
    print(f"Entries ported:     {len(ported)}{' (dry-run)' if args.dry_run else ''}")
    print(f"Entries changed:    {changed}")
    print(f"Stale removed:      {deleted_count}")
    print(f"Index updated:      {'yes' if index_written else 'no (idempotent)'}")
    return 0


def _delete_stale_memory_entries(
    memory_dir: Path,
    ported_slugs: list[str],
    prior_audit: dict | None,
) -> int:
    """Delete memory entries the PRIOR sync wrote that the current sync did not.

    Second-eye review (2026-05-27): the v1 form deleted EVERY destination
    `*.md` not in current `ported`, which would wipe destination-owned
    notes the operator authored directly. The fixed form tracks "files
    we ourselves wrote on the prior sync" via the memory audit and
    deletes only those that left the current port. Files the operator
    created at the destination (never in our prior `ported` list) stay.

    First-time runs against a memory dir that has no prior audit delete
    nothing. The operator's manual prep work is safe.
    """
    if prior_audit is None:
        return 0
    prior_ported = prior_audit.get("synced_files") or []
    if not isinstance(prior_ported, list):
        return 0
    prior_set = {f"{p}.md" for p in prior_ported if isinstance(p, str)}
    current_set = {f"{slug}.md" for slug in ported_slugs}
    memory_dir_resolved = memory_dir.resolve()
    deleted = 0
    for filename in sorted(prior_set - current_set):
        # The audit can only contain slugs (filenames without
        # traversal), but apply the safety guard anyway for parity with
        # _delete_stale_files. A bare filename like "feedback_a.md" can
        # never escape memory_dir; absolute / traversal entries are
        # malformed audit content and get refused with a warning.
        candidate = memory_dir / filename
        if not _within(candidate, memory_dir_resolved):
            _stderr(
                f"WARN: prior memory audit entry {filename!r} resolves outside "
                f"memory_dir; refusing to delete"
            )
            continue
        if candidate.is_file() or candidate.is_symlink():
            try:
                candidate.unlink()
                deleted += 1
            except OSError as exc:
                _stderr(f"WARN: could not delete stale memory entry {candidate}: {exc}")
    return deleted


def _write_memory_audit(
    memory_dir: Path, ported_slugs: list[str], scrubs: list[ScrubPattern]
) -> None:
    """Track which entries this sync ported so the next can stale-delete.

    Mirrors the content `.sync-manifest.json` shape with a `synced_files`
    list of slugs (NOT filenames; the slug-to-filename mapping is
    fixed). Keeps memory + content audits parallel so a future
    consolidation of the two formats is mechanical.

    The audit is overwritten unconditionally per memory sync; idempotency
    at the FILE level is preserved by the existing per-entry skip-when-
    unchanged path in run_memory.
    """
    payload = {
        "synced_files": sorted(ported_slugs),
        "synced_at": datetime.now(UTC).isoformat(),
        "scrub_rules_hash": _scrubs_hash(scrubs),
        "tool_version": TOOL_VERSION,
    }
    target = memory_dir / AUDIT_FILENAME
    # Skip write if existing matches semantically (ignore synced_at).
    if target.is_file():
        try:
            prior = json.loads(target.read_text(encoding="utf-8"))
            if (
                prior.get("synced_files") == payload["synced_files"]
                and prior.get("scrub_rules_hash") == payload["scrub_rules_hash"]
            ):
                return
        except (OSError, json.JSONDecodeError):
            pass
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scrubs_hash(scrubs: list[ScrubPattern]) -> str:
    """Helper: scrub-rules hash usable outside the Manifest dataclass.

    Used by the memory audit which doesn't carry a full Manifest in scope
    at write time. Same hash formula as Manifest.scrub_rules_hash so the
    two audits compare consistently.
    """
    payload = "\n".join(
        f"{p.pattern.pattern}::flags={p.pattern.flags}::{p.replacement}" for p in scrubs
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_memory_index(ported_slugs: list[str]) -> str:
    """Render the MEMORY.md index for the given slug list.

    Pure function so we can compare against the destination's existing
    file and skip the write when nothing changed.
    """
    lines = ["# Memory Index", ""]
    by_type: dict[str, list[str]] = {
        "user": [],
        "project": [],
        "feedback": [],
        "reference": [],
        "other": [],
    }
    for slug in sorted(ported_slugs):
        kind = "other"
        for known in ("user", "project", "feedback", "reference"):
            if slug.startswith(f"{known}_"):
                kind = known
                break
        by_type.setdefault(kind, []).append(slug)
    for kind in ("user", "project", "feedback", "reference", "other"):
        entries = by_type.get(kind, [])
        if not entries:
            continue
        lines.append(f"## {kind.capitalize()}")
        for slug in entries:
            lines.append(f"- [{slug}]({slug}.md)")
        lines.append("")
    return "\n".join(lines) + "\n"


def _write_memory_index_if_changed(memory_dir: Path, ported_slugs: list[str]) -> bool:
    """Rebuild MEMORY.md only when its contents would change.

    The destination is responsible for curating richer descriptions over
    time; the auto-regenerated form here is a starting point. Skipping
    the rewrite when content is identical preserves the destination's
    git diff cleanliness on scheduled cron runs.
    """
    new_content = _build_memory_index(ported_slugs)
    target = memory_dir / "MEMORY.md"
    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = None
        if existing == new_content:
            return False
    target.write_text(new_content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to manifest.toml describing destination, sources, scrubs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + compute changes but do not write to destination",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Run even if destination working tree is not clean",
    )
    parser.add_argument(
        "--allow-source-dirty",
        action="store_true",
        help="Run even if source working tree has uncommitted changes "
        "(breaks the audit's reproducibility contract; default-off)",
    )
    parser.add_argument(
        "--direction",
        default="forward",
        choices=("forward", "reverse"),
        help="Sync direction. 'reverse' is a stub for future use.",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="distribution",
        choices=("distribution", "memory"),
        help="Which sync mode to run (default: distribution)",
    )
    args = parser.parse_args(argv)

    if args.direction == "reverse":
        _stderr(
            "reverse direction is reserved for a future flip; "
            "use 'forward' (default) for now"
        )
        return 4

    try:
        _acquire_lock()
    except SystemExit:
        return 2

    try:
        if args.subcommand == "memory":
            return run_memory(args)
        return run_distribution(args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except Exception:
        _log_failure()
        return 3
    finally:
        _release_lock()


def _log_failure() -> None:
    """Append the current traceback to the runbook log path."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            _write_failure(fh)
    except OSError:
        traceback.print_exc(file=sys.stderr)


def _write_failure(fh: IO[str]) -> None:
    fh.write(f"\n--- {datetime.now(UTC).isoformat()} ---\n")
    traceback.print_exc(file=fh)


if __name__ == "__main__":
    sys.exit(main())
