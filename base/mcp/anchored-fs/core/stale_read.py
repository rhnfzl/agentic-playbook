"""Stale-read detection via mtime + sha256 hash comparison.

Callers that store a read snapshot in history MUST hash the normalized bytes
(i.e. ``hashlib.sha256(normalize_for_hash(raw_bytes)).hexdigest()``) so that
``is_stale`` can compare apples-to-apples when ``normalize_line_endings=True``
(the default).  Storing a hash of un-normalized bytes and then requesting
normalization on the current read will produce a false positive.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_for_hash(content: bytes) -> bytes:
    """Collapse CRLF to LF so line-ending-only changes do not trigger staleness."""
    return content.replace(b"\r\n", b"\n")


def is_stale(
    path: Path,
    *,
    history: dict,
    allow_edit_without_prior_read: bool,
    normalize_line_endings: bool = True,
) -> bool:
    """Return True if *path* has changed since it was last recorded in *history*.

    Args:
        path: Absolute (or resolvable) path to the file being edited.
        history: Mapping of ``str(path.resolve())`` -> snapshot dict with at
            least ``{"sha256_at_read": <hex>}``.  Snapshots must store the hash
            of the *normalized* bytes when ``normalize_line_endings`` is True.
        allow_edit_without_prior_read: When True and no snapshot exists, the
            edit is allowed (returns False).  When False, returns True (stale).
        normalize_line_endings: When True (default), collapse CRLF -> LF before
            hashing the current file content, matching the expectation that the
            stored hash was also produced from normalized bytes.

    Returns:
        True  — file is stale (content differs from snapshot, or file missing).
        False — file is unchanged, or no prior read and edits are permitted.
    """
    key = str(path.resolve())
    entry = history.get(key)

    if entry is None:
        return not allow_edit_without_prior_read

    try:
        current_bytes = path.read_bytes()
    except OSError:
        return True

    if normalize_line_endings:
        current_bytes = normalize_for_hash(current_bytes)

    current_hash = hashlib.sha256(current_bytes).hexdigest()
    return current_hash != entry.get("sha256_at_read")
