"""Profile loader + catalog name / slug validation."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from .errors import ProfileLoadError, ReservedNameError, SlugValidationError
from .types import MetaProfile, Profile, RoleProfile

RESERVED_MARKETPLACE_NAMES: frozenset[str] = frozenset(
    {
        "claude-code-marketplace",
        "claude-code-plugins",
        "claude-plugins-official",
        "anthropic-marketplace",
        "anthropic-plugins",
        "agent-skills",
        "anthropic-agent-skills",
        "knowledge-work-plugins",
        "life-sciences",
        "claude-for-legal",
        "claude-for-financial-services",
        "financial-services-plugins",
    }
)

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}[a-z0-9]$")
_RESERVED_TOKENS = ("official", "anthropic", "claude")


def _validate_slug(slug: str, *, kind: str) -> None:
    if not _SLUG_RE.match(slug):
        raise SlugValidationError(
            f"{kind} slug '{slug}' must be 2-64 chars, lowercase + digits + hyphen, "
            "start with a letter, end alphanumeric"
        )


def _validate_marketplace_name(name: str) -> None:
    _validate_slug(name, kind="marketplace")
    if name in RESERVED_MARKETPLACE_NAMES:
        raise ReservedNameError(
            f"marketplace name '{name}' is reserved by Anthropic; pick a "
            "personal-brand slug (e.g. your GitHub handle)"
        )
    for token in _RESERVED_TOKENS:
        if token in name.split("-"):
            raise ReservedNameError(
                f"marketplace name '{name}' contains reserved token '{token}'; "
                "Anthropic blocks names with official/anthropic/claude tokens "
                "in official-sounding combinations"
            )


def _load_profile(path: Path, *, catalog_name: str) -> RoleProfile:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileLoadError(f"cannot read profile {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileLoadError(f"profile {path} is not valid TOML: {exc}") from exc

    name = path.stem
    _validate_slug(name, kind="profile")
    description = str(data.get("description", "") or "")

    def _list(section: str) -> tuple[str, ...]:
        section_data = data.get(section) or {}
        return tuple(section_data.get("include") or ())

    return RoleProfile(
        name=name,
        catalog_name=catalog_name,
        description=description,
        version=data.get("version"),
        skills=_list("skills"),
        rules=_list("rules"),
        hooks=_list("hooks"),
        mcp=_list("mcp"),
        agents=_list("agents"),
        commands=_list("commands"),
        prompts=_list("prompts"),
    )


def _build_meta_profile(
    members: tuple[RoleProfile, ...], *, catalog_name: str
) -> MetaProfile:
    if not members:
        raise ProfileLoadError("cannot build meta profile from empty members tuple")
    # Name must be a valid installable slug: it becomes a plugin name in the
    # Claude / Cursor / Codex catalogs, and `_all` (leading underscore) fails
    # both this package's _validate_slug and Codex's hyphen-case requirement.
    return MetaProfile(
        name="all-profiles",
        catalog_name=catalog_name,
        description=f"Aggregate of all role profiles in the {catalog_name} catalog",
        members=members,
    )


def _load_profiles(profiles_dir: Path, *, catalog_name: str) -> tuple[Profile, ...]:
    _validate_marketplace_name(catalog_name)
    if not profiles_dir.is_dir():
        raise ProfileLoadError(f"profiles directory not found: {profiles_dir}")
    role_profiles = tuple(
        sorted(
            (
                _load_profile(p, catalog_name=catalog_name)
                for p in profiles_dir.glob("*.toml")
            ),
            key=lambda rp: rp.name,
        )
    )
    if not role_profiles:
        raise ProfileLoadError(f"no profile TOML files found under {profiles_dir}")
    meta = _build_meta_profile(role_profiles, catalog_name=catalog_name)
    return role_profiles + (meta,)
