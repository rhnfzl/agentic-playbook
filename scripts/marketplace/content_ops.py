"""Materialize / resolve / stale-clean content into the plugin directory."""

from __future__ import annotations

import filecmp
import shutil
from dataclasses import dataclass
from pathlib import Path

from .errors import MaterializationError, PathSafetyError
from .types import ComponentSpec, EmitterConfig, Profile, RoleProfile, specs_for


@dataclass(frozen=True)
class ResolvedRef:
    spec: ComponentSpec
    ref: str
    source: Path
    plugin_rel: Path


def _is_stale_path(path: Path, expected: set[Path]) -> bool:
    """Return True when `path` is not in `expected` and shares no
    parent/child relationship with any expected path."""
    if path in expected:
        return False
    for exp in expected:
        if exp == path:
            continue
        if path.is_relative_to(exp):
            return False
        if exp.is_relative_to(path):
            return False
    return True


def _within(target: Path, base: Path) -> bool:
    """Path-safety predicate. True iff target is inside base."""
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _refs_for_spec(profile: Profile, spec: ComponentSpec) -> tuple[str, ...]:
    if isinstance(profile, RoleProfile):
        return tuple(getattr(profile, spec.profile_field, ()))
    seen: dict[str, None] = {}
    for member in profile.members:
        for ref in getattr(member, spec.profile_field, ()):
            seen.setdefault(ref, None)
    return tuple(seen.keys())


# Profiles reference content by BARE STEM (e.g. "lint-guard", "no-em-dashes"),
# matching the canonical loaders in `scripts/adapters/_reader.py`, which glob
# each content root with a fixed extension and key by `path.stem`. Skills are
# the exception: they are directories referenced by their full sub-path
# (e.g. "engineering/ci-failure-triage"), so they need no suffix fallback.
# Keep this map in sync with the `_walk_content_roots(..., "<kind>", "<glob>")`
# calls in `_reader.py` so the emitter resolves the same files the installer does.
_SUFFIX_FALLBACKS: dict[str, tuple[str, ...]] = {
    "rules": (".md",),
    "hooks": (".sh",),
    "agents": (".md",),
    "commands": (".md",),
    "prompts": (".md",),
    "mcp": (".json",),
}


def _ref_escapes_source_dir(ref: str) -> bool:
    """True if `ref` is absolute or traverses out of base/<kind> via `..`.

    SECURITY: refs come from profile TOML and name content WITHIN
    base/<kind>. A ref like `../../../secret` or `/etc/passwd` would
    otherwise resolve to a file outside the (scrubbed) content root and be
    copied raw into the public plugin dirs. The check is LEXICAL on the ref
    so it blocks traversal while still allowing the in-repo symlinks that
    base/hooks/*.sh use to point at base/skills/<cat>/<name>/hooks/ (ADR-0035).
    """
    ref_path = Path(ref)
    return ref_path.is_absolute() or ".." in ref_path.parts


def _resolve_source(spec: ComponentSpec, ref: str, repo_root: Path) -> Path | None:
    """Resolve a profile ref to its source path on disk, or None if absent
    or if the ref escapes the content root.

    Tries the bare ref first (directory-style content such as skills, and
    bundle-style MCP servers). Falls back to the extension(s) the canonical
    loader globs for that kind so bare-stem refs resolve to `<ref><suffix>`.
    """
    if _ref_escapes_source_dir(ref):
        return None
    base = repo_root / spec.source_dir / ref
    if base.exists():
        return base
    for suffix in _SUFFIX_FALLBACKS.get(spec.kind, ()):
        alt = repo_root / spec.source_dir / f"{ref}{suffix}"
        if alt.exists():
            return alt
    return None


def _plugin_rel_for(spec: ComponentSpec, ref: str, source: Path) -> Path:
    """Derive plugin-dir-relative path from spec + resolved source.

    Directory-style content keeps the ref path so a category prefix
    survives (skills/engineering/ci-failure-triage, mcp/<bundle>).
    File-style content keeps the resolved filename so the extension the
    canonical loader expects survives (rules/<name>.md, hooks/<name>.sh,
    mcp/<name>.json).
    """
    dst = "mcp" if spec.plugin_dst == "mcp_either" else spec.plugin_dst
    if source.is_dir():
        return Path(dst) / ref
    return Path(dst) / source.name


def _resolve_profile(
    profile: Profile, config: EmitterConfig
) -> tuple[tuple[ResolvedRef, ...], tuple[str, ...]]:
    """Resolve every ref the profile lists. Returns (resolved, warnings)."""
    resolved: list[ResolvedRef] = []
    warnings: list[str] = []
    for spec in specs_for(profile):
        for ref in _refs_for_spec(profile, spec):
            source = _resolve_source(spec, ref, config.repo_root)
            if source is None:
                warnings.append(
                    f"profile '{profile.name}' ref '{ref}' under {spec.kind} "
                    f"missing on disk at {config.repo_root / spec.source_dir / ref}"
                )
                continue
            plugin_rel = _plugin_rel_for(spec, ref, source)
            resolved.append(
                ResolvedRef(spec=spec, ref=ref, source=source, plugin_rel=plugin_rel)
            )
    return tuple(resolved), tuple(warnings)


def _trees_match(a: Path, b: Path) -> bool:
    """True if `a` and `b` have the same file contents recursively.

    Uses byte-level comparison (`filecmp.cmp(shallow=False)`) for every
    common file. The default `filecmp.dircmp.diff_files` does only a
    shallow stat-based compare, which produces false matches for files
    with identical size + mtime but different bytes.
    """
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    for filename in cmp.common_files:
        if not filecmp.cmp(a / filename, b / filename, shallow=False):
            return False
    for sub in cmp.common_dirs:
        if not _trees_match(a / sub, b / sub):
            return False
    return True


def _materialize(
    resolved: tuple[ResolvedRef, ...], plugin_dir: Path, *, dry_run: bool
) -> int:
    """Copy every resolved source into the plugin dir. Idempotent: skips
    write when the destination already matches the source content."""
    files_written = 0
    for entry in resolved:
        dest = plugin_dir / entry.plugin_rel
        if not _within(dest, plugin_dir):
            raise PathSafetyError(f"refusing to materialize outside plugin dir: {dest}")
        if dry_run:
            continue
        try:
            if entry.source.is_dir():
                if dest.exists() and dest.is_dir() and _trees_match(entry.source, dest):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(entry.source, dest)
            else:
                if dest.exists() and filecmp.cmp(entry.source, dest, shallow=False):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(entry.source, dest)
            files_written += 1
        except OSError as exc:
            raise MaterializationError(
                f"materialize {entry.source} -> {dest}: {exc}"
            ) from exc
    return files_written


def _expected_paths(resolved: tuple[ResolvedRef, ...], plugin_dir: Path) -> set[Path]:
    return {plugin_dir / r.plugin_rel for r in resolved}


_PROTECTED_FILES = frozenset(
    {
        "plugin.json",
        "marketplace.json",
        "emitted-by.json",
        "README.md",
        "gemini-extension.json",
        "hooks.json",
        ".mcp.json",
    }
)
# Directory names the emitter owns directly. They survive the stale
# sweep even when no `expected` path falls inside them, because they
# may legitimately hold ONLY emitted manifests (which are themselves
# protected by name but cannot exist without their parent dir).
_PROTECTED_DIR_NAMES = frozenset(
    {".claude-plugin", ".cursor-plugin", ".codex-plugin", "hooks"}
)


def _remove_stale_plugin_content(
    plugin_dir: Path, expected: set[Path], *, dry_run: bool
) -> int:
    """Walk plugin_dir and remove paths that are not expected.

    Protection is name-based only. A directory survives iff:
      * it is an ancestor of some expected path (handled by _is_stale_path), OR
      * its own name is in `_PROTECTED_DIR_NAMES` (e.g. `.claude-plugin/`).

    The earlier "contains protected descendant" heuristic was too broad
    (a stale skill dir containing a README.md would never be cleaned).
    """
    if not plugin_dir.exists():
        return 0
    files_removed = 0
    for path in sorted(plugin_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not _is_stale_path(path, expected):
            continue
        if path.name in _PROTECTED_FILES:
            continue
        if path.is_dir() and path.name in _PROTECTED_DIR_NAMES:
            continue
        if dry_run:
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            files_removed += 1
        except OSError:
            continue
    return files_removed
