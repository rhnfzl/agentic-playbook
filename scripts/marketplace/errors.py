"""Marketplace emitter error hierarchy.

Exit codes (used by the CLI in `scripts/marketplace_emitter.py` shim):

    1  ProfileLoadError       -- profile file missing / unparseable
    5  SlugValidationError    -- catalog/profile name violates schema
    5  ReservedNameError      -- catalog name reserved by Anthropic
    5  MaterializationError   -- writing to plugin dir failed
    5  PathSafetyError        -- destination escapes operator-configured base
"""

from __future__ import annotations


class EmitError(Exception):
    """Base for every marketplace emit-time failure."""

    exit_code: int = 1


class ProfileLoadError(EmitError):
    exit_code = 1


class SlugValidationError(EmitError):
    exit_code = 5


class ReservedNameError(EmitError):
    exit_code = 5


class MaterializationError(EmitError):
    exit_code = 5


class PathSafetyError(EmitError):
    exit_code = 5
