#!/usr/bin/env python3
"""Backwards-compat shim for anchored-fs's root install.py entry point.

The canonical installer is `mcp/anchored-fs/bundle/install.py` per
ADR-0026 (v0.5 extension). This shim forwards every invocation so the
documented commands (`uv run python install.py init`, `uv run python
install.py check`, etc.) keep working from the anchored-fs project
root and from any external automation that pre-dates the bundle move.

Tracked deletion target: once mcp/anchored-fs/README.md, every external
runbook, and every CI workflow that invokes this path have been
migrated to `python bundle/install.py <subcommand>`, this shim can be
removed. Until then it is load-bearing per the v0.8 Codex review.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUNDLE_INSTALL = HERE / "bundle" / "install.py"

if not BUNDLE_INSTALL.is_file():
    print(
        f"ERROR: expected {BUNDLE_INSTALL} but it does not exist. "
        f"Check the anchored-fs bundle layout.",
        file=sys.stderr,
    )
    sys.exit(1)

os.execv(sys.executable, [sys.executable, str(BUNDLE_INSTALL), *sys.argv[1:]])
