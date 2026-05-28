"""Quarantined symlink-mode helper (production emit uses materialization).

This file exists so a future flag can flip the emitter from copy-mode to
symlink-mode without re-discovering the helper. Do not import from
content_ops; the production path lives there.
"""

from __future__ import annotations

import os
from pathlib import Path


def _symlink_if_changed(source: Path, dest: Path) -> bool:
    """Idempotently link `dest -> source`. Returns True iff a write happened."""
    if dest.is_symlink():
        if Path(os.readlink(dest)) == source:
            return False
        dest.unlink()
    elif dest.exists():
        raise FileExistsError(f"cannot symlink: {dest} exists and is not a symlink")
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(source, dest)
    return True
