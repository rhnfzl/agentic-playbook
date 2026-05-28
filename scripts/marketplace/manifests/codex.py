"""Codex plugin manifest builders.

Schema constraints validated 2026-05-28 against
developers.openai.com/codex/plugins/build + openai/codex SKILL.md:

  .codex-plugin/plugin.json:
    Required: `name`
    Optional: `description`, `version`, `author`, `interface.displayName`
    NOTE: `policy` does NOT belong in plugin.json -- it lives only in
    the marketplace.json plugin entry.

  marketplace.json:
    Top-level: `name`, `interface.displayName`, `plugins[]`
    (Codex uses interface.displayName, not Claude's `owner`.)
    Each plugin: `name`, `source` (object with `source` discriminator),
    `policy.installation` in {'AVAILABLE','NOT_AVAILABLE','INSTALLED_BY_DEFAULT'},
    `policy.authentication` in {'ON_INSTALL','ON_USE'}, `category`.

  source object discriminators (Codex):
    local:      {source, path}             (local IS a valid discriminator)
    url:        {source, url, ref?}
    git-subdir: {source, url, path, ref?}  (uses url/path, not repo/subdir)
    github:     {source, repo, ref?, sha?}

  'NONE' is NOT in the authentication enum and is silently dropped; never emit it.
"""

from __future__ import annotations

from ..content_ops import ResolvedRef
from ..types import EmitterConfig, Profile
from ._shared import _default_marketplace_description

_CODEX_AUTH = ("ON_INSTALL", "ON_USE")
_CODEX_INSTALLATION = ("AVAILABLE", "NOT_AVAILABLE", "INSTALLED_BY_DEFAULT")


def _codex_plugin_manifest(profile: Profile, config: EmitterConfig) -> dict:
    return {
        "name": profile.name,
        "version": config.version_for(profile),
        "description": _default_marketplace_description(profile),
        "author": config.author_block(),
    }


def _codex_plugin_entry(profile: Profile, config: EmitterConfig) -> dict:
    return {
        "name": profile.name,
        "description": _default_marketplace_description(profile),
        "version": config.version_for(profile),
        "source": {"source": "local", "path": f"./{profile.name}"},
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Productivity",
    }


def _codex_marketplace_manifest(
    profiles: tuple[Profile, ...],
    config: EmitterConfig,
    _resolved_by_profile: dict[str, tuple[ResolvedRef, ...]],
    catalog_name: str,
) -> dict:
    return {
        "name": catalog_name,
        "interface": {"displayName": f"{catalog_name} catalog"},
        "plugins": [_codex_plugin_entry(profile, config) for profile in profiles],
    }


def _is_valid_codex_auth(value: str) -> bool:
    return value in _CODEX_AUTH


def _is_valid_codex_installation(value: str) -> bool:
    return value in _CODEX_INSTALLATION
