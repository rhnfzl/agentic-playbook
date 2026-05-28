"""Claude Code manifest builders.

Schema constraints validated 2026-05-28 against code.claude.com/docs:
  - marketplace.json name is kebab-case, 2-64 chars, lowercase
  - Reserved names blocked (handled in profile_loader)
  - agents field is a list of .md paths (NOT a directory string)
  - LOCAL source is a bare string starting with './' (NOT an object)
  - Object source discriminators: 'github' | 'url' | 'git-subdir' | 'npm'
"""

from __future__ import annotations

from ..content_ops import ResolvedRef
from ..types import EmitterConfig, Profile
from ._shared import _default_marketplace_description


def _claude_plugin_manifest(profile: Profile, config: EmitterConfig) -> dict:
    return {
        "name": profile.name,
        "version": config.version_for(profile),
        "description": _default_marketplace_description(profile),
        "author": config.author_block(),
    }


def _agent_relpaths(resolved: tuple[ResolvedRef, ...]) -> list[str]:
    return sorted(
        f"agents/{r.ref}" if r.source.is_file() else f"agents/{r.ref}/agent.md"
        for r in resolved
        if r.spec.kind == "agents"
    )


def _claude_plugin_entry(
    profile: Profile, config: EmitterConfig, resolved: tuple[ResolvedRef, ...]
) -> dict:
    entry: dict = {
        "name": profile.name,
        "description": _default_marketplace_description(profile),
        "version": config.version_for(profile),
        "source": f"./{profile.name}",
    }
    agents = _agent_relpaths(resolved)
    if agents:
        entry["agents"] = agents
    return entry


def _claude_marketplace_manifest(
    profiles: tuple[Profile, ...],
    config: EmitterConfig,
    resolved_by_profile: dict[str, tuple[ResolvedRef, ...]],
    catalog_name: str,
) -> dict:
    return {
        "name": catalog_name,
        "owner": config.author_block(),
        "plugins": [
            _claude_plugin_entry(profile, config, resolved_by_profile[profile.name])
            for profile in profiles
        ],
    }
