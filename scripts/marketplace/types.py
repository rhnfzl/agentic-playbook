"""Typed shapes for the marketplace emitter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Union


@dataclass(frozen=True)
class RoleProfile:
    name: str
    catalog_name: str
    description: str
    version: str | None = None
    skills: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    hooks: tuple[str, ...] = ()
    mcp: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    prompts: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetaProfile:
    """The aggregate `_all` profile derived from union of role profiles."""

    name: str
    catalog_name: str
    description: str
    members: tuple[RoleProfile, ...]
    version: str | None = None


Profile = Union[RoleProfile, MetaProfile]


@dataclass(frozen=True)
class EmitterConfig:
    repo_root: Path
    dest_root: Path
    tool_version: str
    author_name: str
    author_email: str | None = None
    dry_run: bool = False
    default_profile_version: str | None = None

    def version_for(self, profile: Profile) -> str:
        return profile.version or self.default_profile_version or self.tool_version

    def author_block(self) -> dict[str, str]:
        block: dict[str, str] = {"name": self.author_name}
        if self.author_email:
            block["email"] = self.author_email
        return block


@dataclass(frozen=True)
class ComponentSpec:
    """One row in the materialization table."""

    kind: Literal["skills", "rules", "hooks", "mcp", "agents", "commands", "prompts"]
    source_dir: Path
    plugin_dst: str
    profile_field: str


COMPONENT_SPECS: tuple[ComponentSpec, ...] = (
    ComponentSpec("skills", Path("base/skills"), "skills", "skills"),
    ComponentSpec("rules", Path("base/rules"), "rules", "rules"),
    ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks"),
    ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp"),
    ComponentSpec("agents", Path("base/agents"), "agents", "agents"),
    ComponentSpec("commands", Path("base/commands"), "commands", "commands"),
    ComponentSpec("prompts", Path("base/prompts"), "prompts", "prompts"),
)


def specs_for(profile: Profile) -> tuple[ComponentSpec, ...]:
    """Return only ComponentSpecs the profile actually populates."""

    def _populated(p: RoleProfile, spec: ComponentSpec) -> bool:
        return bool(getattr(p, spec.profile_field, ()))

    if isinstance(profile, RoleProfile):
        return tuple(s for s in COMPONENT_SPECS if _populated(profile, s))

    populated_kinds: set[str] = set()
    for member in profile.members:
        for spec in COMPONENT_SPECS:
            if _populated(member, spec):
                populated_kinds.add(spec.kind)
    return tuple(s for s in COMPONENT_SPECS if s.kind in populated_kinds)
