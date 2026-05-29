"""Marketplace emit facade used by sync_distribution.py.

Keeps sync_distribution.py decoupled from the marketplace package's
internal layout. Only this module imports from marketplace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from marketplace import EmitError, EmitterConfig, TOOL_VERSION, emit

# Re-export under a facade-local name so sync_distribution.py can catch
# emit-time safety failures (and preserve the declared exit code) without
# importing from the marketplace package directly.
MarketplaceEmitError = EmitError

__all__ = ["MarketplaceEmitError", "emitter_tool_version", "run_marketplace_emit"]


class _ManifestLike(Protocol):
    repo_root: Path
    destination: Path
    catalog_name: str
    author_name: str
    author_email: str | None
    profiles_dir: Path
    default_profile_version: str | None


def emitter_tool_version() -> str:
    return TOOL_VERSION


def run_marketplace_emit(manifest: _ManifestLike, dry_run: bool) -> int:
    config = EmitterConfig(
        repo_root=manifest.repo_root,
        dest_root=manifest.destination,
        tool_version=TOOL_VERSION,
        author_name=manifest.author_name,
        author_email=manifest.author_email,
        dry_run=dry_run,
        default_profile_version=manifest.default_profile_version,
    )
    return emit(
        config,
        profiles_dir=manifest.profiles_dir,
        catalog_name=manifest.catalog_name,
    )
