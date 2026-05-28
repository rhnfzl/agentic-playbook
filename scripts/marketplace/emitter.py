"""Marketplace emitter orchestrator.

Per-profile work (plugin directories, plugin.json files, gemini-extension.json,
per-plugin README, sidecar) happens inside `_emit_plugin_directory`. The
root-level catalog manifests (`.claude-plugin/marketplace.json`, etc.) are
written ONCE in `_emit_marketplace_manifests` with the FULL profile list,
to avoid multi-profile overwrite. See risk callout #13 in the plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from . import TOOL_VERSION
from .content_ops import (
    ResolvedRef,
    _expected_paths,
    _materialize,
    _remove_stale_plugin_content,
    _resolve_profile,
)
from .errors import EmitError
from .hook_aggregator import _build_hooks_json
from .manifests._shared import _plugin_readme
from .manifests.claude import _claude_marketplace_manifest, _claude_plugin_manifest
from .manifests.codex import _codex_marketplace_manifest, _codex_plugin_manifest
from .manifests.cursor import _cursor_marketplace_manifest, _cursor_plugin_manifest
from .manifests.gemini import _gemini_extension_manifest
from .mcp_aggregator import _build_mcp_json
from .profile_loader import _load_profiles
from .types import EmitterConfig, Profile

_PluginManifestBuilder = Callable[[Profile, EmitterConfig], dict]

_PLUGIN_MANIFEST_WRITES: tuple[tuple[str, _PluginManifestBuilder], ...] = (
    (".claude-plugin/plugin.json", _claude_plugin_manifest),
    (".cursor-plugin/plugin.json", _cursor_plugin_manifest),
    (".codex-plugin/plugin.json", _codex_plugin_manifest),
)

_MARKETPLACE_WRITES: tuple[tuple[str, Callable[..., dict]], ...] = (
    (".claude-plugin/marketplace.json", _claude_marketplace_manifest),
    (".cursor-plugin/marketplace.json", _cursor_marketplace_manifest),
    (".codex-plugin/marketplace.json", _codex_marketplace_manifest),
)


def _write_if_changed(path: Path, text: str, dry_run: bool) -> int:
    if dry_run:
        return 0
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return 1


def _emit_plugin_directory(
    profile: Profile, config: EmitterConfig
) -> tuple[int, tuple[ResolvedRef, ...]]:
    plugin_dir = config.dest_root / profile.name
    files_written = 0

    resolved, warnings = _resolve_profile(profile, config)
    for warning in warnings:
        print(f"WARN: {warning}", file=sys.stderr)

    files_written += _materialize(resolved, plugin_dir, dry_run=config.dry_run)
    files_written += _build_hooks_json(profile, resolved, config, plugin_dir)
    files_written += _build_mcp_json(profile, resolved, config, plugin_dir)

    for rel_path, builder in _PLUGIN_MANIFEST_WRITES:
        manifest = builder(profile, config)
        files_written += _write_if_changed(
            plugin_dir / rel_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            config.dry_run,
        )

    sidecar = plugin_dir / ".claude-plugin" / "emitted-by.json"
    files_written += _write_if_changed(
        sidecar,
        json.dumps({"tool": "marketplace", "version": config.tool_version}, indent=2)
        + "\n",
        config.dry_run,
    )

    readme = plugin_dir / "README.md"
    files_written += _write_if_changed(
        readme,
        _plugin_readme(profile, config.version_for(profile)),
        config.dry_run,
    )

    files_written += _write_if_changed(
        plugin_dir / "gemini-extension.json",
        json.dumps(
            _gemini_extension_manifest(profile, config, resolved),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        config.dry_run,
    )

    expected = _expected_paths(resolved, plugin_dir)
    _remove_stale_plugin_content(plugin_dir, expected, dry_run=config.dry_run)
    return files_written, resolved


def _emit_marketplace_manifests(
    profiles: tuple[Profile, ...],
    config: EmitterConfig,
    resolved_by_profile: dict[str, tuple[ResolvedRef, ...]],
    catalog_name: str,
) -> int:
    """Write the per-vendor root-level marketplace.json files ONCE,
    listing ALL profiles. Prevents the multi-profile overwrite bug."""
    files_written = 0
    for rel_path, builder in _MARKETPLACE_WRITES:
        manifest = builder(profiles, config, resolved_by_profile, catalog_name)
        files_written += _write_if_changed(
            config.dest_root / rel_path,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            config.dry_run,
        )
    return files_written


def emit(config: EmitterConfig, *, profiles_dir: Path, catalog_name: str) -> int:
    """Top-level emit entry point. Returns total files written."""
    profiles = _load_profiles(profiles_dir, catalog_name=catalog_name)
    total = 0
    resolved_by_profile: dict[str, tuple[ResolvedRef, ...]] = {}
    for profile in profiles:
        files, resolved = _emit_plugin_directory(profile, config)
        total += files
        resolved_by_profile[profile.name] = resolved
    total += _emit_marketplace_manifests(
        profiles, config, resolved_by_profile, catalog_name
    )
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="marketplace_emitter")
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--dest-root", required=True, type=Path)
    parser.add_argument("--profiles-dir", required=True, type=Path)
    parser.add_argument("--catalog-name", required=True)
    parser.add_argument(
        "--author-name", required=True, help="Person's name (e.g. 'Rehan Fazal')"
    )
    parser.add_argument("--author-email", default=None)
    parser.add_argument("--tool-version", default=TOOL_VERSION)
    parser.add_argument("--default-profile-version", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    config = EmitterConfig(
        repo_root=args.repo_root,
        dest_root=args.dest_root,
        tool_version=args.tool_version,
        author_name=args.author_name,
        author_email=args.author_email,
        dry_run=args.dry_run,
        default_profile_version=args.default_profile_version,
    )
    try:
        files = emit(
            config,
            profiles_dir=args.profiles_dir,
            catalog_name=args.catalog_name,
        )
    except EmitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    print(f"emit complete: {files} file writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
