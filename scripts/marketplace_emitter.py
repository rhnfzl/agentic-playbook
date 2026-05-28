#!/usr/bin/env python3
"""Back-compat CLI shim. The implementation lives at scripts/marketplace/.

Re-exports the marketplace package's public surface so existing callers
can continue invoking `python3 scripts/marketplace_emitter.py ...` and
existing `import marketplace_emitter as X` statements keep working.

Run: python3 scripts/marketplace_emitter.py --help
"""

from __future__ import annotations

from marketplace import (
    EmitError,
    EmitterConfig,
    MaterializationError,
    MetaProfile,
    PathSafetyError,
    Profile,
    ProfileLoadError,
    ReservedNameError,
    RoleProfile,
    SlugValidationError,
    TOOL_VERSION,
    emit,
    main,
)

__all__ = [
    "EmitError",
    "EmitterConfig",
    "MaterializationError",
    "MetaProfile",
    "PathSafetyError",
    "Profile",
    "ProfileLoadError",
    "ReservedNameError",
    "RoleProfile",
    "SlugValidationError",
    "TOOL_VERSION",
    "emit",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
