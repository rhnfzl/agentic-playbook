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
"""

from __future__ import annotations

import argparse
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
from typing import IO


LOCK_PATH = Path("/tmp/playbook-distribution-sync.lock")
LOCK_STALE_AFTER_SECONDS = 3600  # 1 hour
LOG_PATH = Path.home() / "Library" / "Logs" / "playbook-distribution-sync.log"
TOOL_VERSION = "sync_distribution.py v1.0"

# Files we will read+scrub+write as text. Binary files would mangle if
# scrubbed; the conservative play is to copy them as bytes without
# touching content. The list is intentionally explicit so an unknown
# extension errs on the safe side (bytes copy, no scrub).
TEXT_EXTENSIONS = frozenset({
    ".md", ".py", ".toml", ".yaml", ".yml", ".json", ".sh",
    ".jinja", ".jinja2", ".j2", ".html", ".css", ".js", ".ts", ".tsx",
    ".txt", ".cfg", ".ini", ".conf", ".env", ".example",
    ".gitignore", ".gitattributes",
})


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

    def scrub_rules_hash(self) -> str:
        payload = "\n".join(
            f"{p.pattern.pattern}::{p.replacement}" for p in self.scrubs
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
    memory_destination_dir = (
        Path(mdst).expanduser() if isinstance(mdst, str) else None
    )
    if isinstance(memory_allowlist_raw, list):
        memory_allowlist = [str(s) for s in memory_allowlist_raw if isinstance(s, str)]
    else:
        memory_allowlist = []
    if isinstance(memory_denylist_raw, list):
        memory_denylist = [str(s) for s in memory_denylist_raw if isinstance(s, str)]
    else:
        memory_denylist = []

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
    """Whether the file extension marks it as a text file we will scrub."""
    if path.suffix in TEXT_EXTENSIONS:
        return True
    # Special-case files without extension that we know are text:
    if path.name in {"Makefile", "Dockerfile", "LICENSE", "VERSION", "README"}:
        return True
    return False


def _is_path_under(path: str, prefix: str) -> bool:
    """Return True if `path` is under `prefix` (where prefix may end with /)."""
    prefix_norm = prefix.rstrip("/")
    if path == prefix_norm:
        return True
    return path.startswith(prefix_norm + "/")


def _resolve_sources(
    source_root: Path, allowlist: list[str], denylist: list[str]
) -> list[Path]:
    """Expand allowlist entries into a concrete list of source files.

    Files relative to source_root that match an allowlist entry (file or
    directory prefix) and do NOT match any denylist entry are returned.
    """
    result: list[Path] = []
    seen: set[Path] = set()
    for entry in allowlist:
        candidate = source_root / entry.rstrip("/")
        if candidate.is_file():
            if candidate not in seen:
                result.append(candidate)
                seen.add(candidate)
            continue
        if candidate.is_dir():
            for file_path in sorted(candidate.rglob("*")):
                if not file_path.is_file():
                    continue
                if file_path not in seen:
                    result.append(file_path)
                    seen.add(file_path)
            continue
        # Allowlist entry that does not exist on disk is a manifest warning,
        # not a fatal error. The operator may have referenced a file that
        # got removed since the manifest was written.
        _stderr(f"WARN: allowlist entry not found in source: {entry}")

    if not denylist:
        return result

    def _denied(rel: str) -> bool:
        return any(_is_path_under(rel, d) for d in denylist)

    filtered: list[Path] = []
    for file_path in result:
        rel = str(file_path.relative_to(source_root))
        if _denied(rel):
            continue
        filtered.append(file_path)
    return filtered


def _scrub_text(text: str, scrubs: list[ScrubPattern]) -> str:
    for s in scrubs:
        text = s.apply(text)
    return text


def _copy_file(
    src: Path, dst: Path, scrubs: list[ScrubPattern], dry_run: bool
) -> tuple[bool, str | None]:
    """Copy `src` to `dst` with optional scrub.

    Returns (changed, error_message). `changed` is True if dst would be
    modified or created. In dry_run mode no writes happen.

    Symlinks are preserved as symlinks; the link target is copied verbatim
    (no scrub, since scrubbing a path string would break the symlink).
    Without this, materializing a symlink as a plain copy of its target's
    bytes produces a duplicate-content file at the destination, which the
    hook-source-unification check correctly flags as drift.
    """
    try:
        if src.is_symlink():
            target = os.readlink(src)
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


def _write_audit(
    manifest: Manifest,
    source_root: Path,
    source_sha: str,
    source_branch: str,
    synced_files: list[str],
) -> None:
    # source_repo and source_branch are scrubbed through the manifest's
    # patterns: the destination's audit metadata should not leak the
    # team-identifier tokens the rest of the sync was specifically built
    # to remove. The source_sha is left untouched; it is a hex string
    # that cannot encode identity by itself.
    raw_source_repo = _source_remote_url(source_root) or "unknown"
    audit = {
        "source_repo": _scrub_text(raw_source_repo, manifest.scrubs),
        "source_commit": source_sha,
        "source_branch": _scrub_text(source_branch, manifest.scrubs),
        "synced_at": datetime.now(UTC).isoformat(),
        "scrub_rules_hash": manifest.scrub_rules_hash(),
        "allowlist_hash": manifest.allowlist_hash(),
        "tool_version": TOOL_VERSION,
        "synced_files": synced_files,
    }
    target = manifest.destination_path / ".sync-manifest.json"
    target.write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_remote_url(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def run_distribution(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = _load_manifest(manifest_path)
    source_root = Path(__file__).resolve().parent.parent

    if not manifest.destination_path.is_dir():
        _stderr(f"destination directory not found: {manifest.destination_path}")
        return 1

    if manifest.require_clean_git and not args.allow_dirty:
        if not _validate_clean_git(manifest.destination_path):
            _stderr("destination working tree is not clean; use --allow-dirty to override")
            return 1

    source_sha, source_branch = _source_commit(source_root)
    sources = _resolve_sources(source_root, manifest.allowlist, manifest.denylist)
    if not sources:
        _stderr("allowlist expanded to zero files; nothing to do")
        return 1

    changed = 0
    errors: list[str] = []
    synced_rel: list[str] = []
    for src in sources:
        rel = src.relative_to(source_root)
        dst = manifest.destination_path / rel
        was_changed, err = _copy_file(src, dst, manifest.scrubs, args.dry_run)
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

    if not args.dry_run:
        _write_audit(manifest, source_root, source_sha, source_branch, synced_rel)

    print(f"Source commit: {source_sha} ({source_branch})")
    print(f"Destination:   {manifest.destination_path}")
    print(f"Files scanned: {len(sources)}")
    print(f"Files changed: {changed}{' (dry-run)' if args.dry_run else ''}")
    print(f"Scrub rules:   {len(manifest.scrubs)}")
    if args.dry_run:
        print(
            "\nDry-run complete. Review the diff at destination "
            "(`git -C <dest> diff`) before re-running without --dry-run."
        )
    return 0


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

    allowlist = set(manifest.memory_allowlist)
    denylist = set(manifest.memory_denylist)

    changed = 0
    ported: list[str] = []
    for entry in sorted(manifest.memory_source_dir.glob("*.md")):
        slug = entry.stem
        if slug == "MEMORY":
            continue
        if allowlist and slug not in allowlist:
            continue
        if slug in denylist:
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

    if not args.dry_run:
        _regenerate_memory_index(manifest.memory_destination_dir, ported)

    print(f"Memory source:      {manifest.memory_source_dir}")
    print(f"Memory destination: {manifest.memory_destination_dir}")
    print(f"Entries ported:     {len(ported)}{' (dry-run)' if args.dry_run else ''}")
    print(f"Entries changed:    {changed}")
    return 0


def _regenerate_memory_index(memory_dir: Path, ported_slugs: list[str]) -> None:
    """Rebuild MEMORY.md as a minimal one-line-per-entry index.

    The destination is responsible for curating richer descriptions over
    time; the auto-regenerated form here is a starting point so the index
    is not stale after the first port.
    """
    lines = ["# Memory Index", ""]
    by_type: dict[str, list[str]] = {"user": [], "project": [], "feedback": [], "reference": [], "other": []}
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
    (memory_dir / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
