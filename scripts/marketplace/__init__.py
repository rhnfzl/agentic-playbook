"""Marketplace emitter public surface.

Stable names: emit, main, TOOL_VERSION, EmitterConfig, RoleProfile,
MetaProfile, Profile, EmitError, ProfileLoadError, SlugValidationError,
ReservedNameError, MaterializationError, PathSafetyError.
"""

from __future__ import annotations

from pathlib import Path

TOOL_VERSION = (
    (Path(__file__).parent.parent.parent / "VERSION")
    .read_text(encoding="utf-8")
    .strip()
)

from .errors import (  # noqa: E402
    EmitError,
    MaterializationError,
    PathSafetyError,
    ProfileLoadError,
    ReservedNameError,
    SlugValidationError,
)
from .types import EmitterConfig, MetaProfile, Profile, RoleProfile  # noqa: E402
from .emitter import emit, main  # noqa: E402

__all__ = [
    "TOOL_VERSION",
    "emit",
    "main",
    "EmitterConfig",
    "RoleProfile",
    "MetaProfile",
    "Profile",
    "EmitError",
    "ProfileLoadError",
    "SlugValidationError",
    "ReservedNameError",
    "MaterializationError",
    "PathSafetyError",
]
