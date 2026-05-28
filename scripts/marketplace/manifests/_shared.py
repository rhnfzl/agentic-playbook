"""Shared helpers used by every per-platform manifest builder."""

from __future__ import annotations

from ..types import Profile


def _default_marketplace_description(profile: Profile) -> str:
    if profile.description:
        return profile.description
    return f"{profile.catalog_name} catalog profile '{profile.name}'"


def _plugin_readme(profile: Profile, version: str) -> str:
    body = profile.description or _default_marketplace_description(profile)
    return (
        f"# {profile.name}\n\n"
        f"{body}\n\n"
        f"Version: `{version}`. Part of the `{profile.catalog_name}` marketplace.\n"
    )
