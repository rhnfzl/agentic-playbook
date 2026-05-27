"""
core/upto_resolver.py

Pure-logic resolver for `prefix[upto]suffix` anchor patterns.
No IO, no fuzzy matching, no path handling — only span resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

UPTO_MARKER = "[upto]"
ESCAPED_MARKER = r"\[upto\]"
ESCAPED_PLACEHOLDER = "\x00UPTO_LITERAL\x00"


@dataclass
class ResolvedSpan:
    text: str
    start_line: int
    end_line: int


FailureKind = Literal[
    "no_upto_marker",
    "prefix_not_found",
    "prefix_not_unique",
    "suffix_not_found",
]


@dataclass
class ResolveFailure:
    kind: FailureKind
    message: str
    candidates: list[dict] = field(default_factory=list)


def _split_on_first_unescaped_upto(pattern: str) -> tuple[str, str] | None:
    """Split pattern into (prefix, suffix) at the first unescaped [upto] marker.

    Returns None if no unescaped [upto] marker is present.
    """
    # Mask escaped markers so we can find the first real one
    masked = pattern.replace(ESCAPED_MARKER, ESCAPED_PLACEHOLDER)

    idx = masked.find(UPTO_MARKER)
    if idx == -1:
        return None

    raw_prefix = masked[:idx]
    raw_suffix = masked[idx + len(UPTO_MARKER) :]

    # Restore escaped markers to literal [upto] in both halves
    prefix = raw_prefix.replace(ESCAPED_PLACEHOLDER, UPTO_MARKER)
    suffix = raw_suffix.replace(ESCAPED_PLACEHOLDER, UPTO_MARKER)
    return prefix, suffix


def _line_of(content: str, offset: int) -> int:
    """Return the 1-based line number of the character at `offset` in `content`."""
    return content.count("\n", 0, offset) + 1


def resolve(content: str, pattern: str) -> ResolvedSpan | ResolveFailure:
    """Resolve a `prefix[upto]suffix` pattern against `content`.

    Returns ResolvedSpan on success, ResolveFailure on any error.
    """
    split = _split_on_first_unescaped_upto(pattern)
    if split is None:
        return ResolveFailure(
            kind="no_upto_marker", message="pattern lacks [upto] marker"
        )

    prefix, suffix = split

    # Find all positions of prefix in content
    positions: list[int] = []
    start = 0
    while True:
        pos = content.find(prefix, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    if len(positions) == 0:
        return ResolveFailure(
            kind="prefix_not_found",
            message=f"prefix not found: {prefix[:40]!r}",
        )

    if len(positions) > 1:
        candidates = [{"line": _line_of(content, p)} for p in positions]
        return ResolveFailure(
            kind="prefix_not_unique",
            message=f"prefix matches {len(positions)} locations",
            candidates=candidates,
        )

    prefix_start = positions[0]
    prefix_end = prefix_start + len(prefix)

    suffix_idx = content.find(suffix, prefix_end)
    if suffix_idx == -1:
        return ResolveFailure(
            kind="suffix_not_found",
            message=f"suffix not found after prefix: {suffix[:40]!r}",
        )

    span_end = suffix_idx + len(suffix)
    span_text = content[prefix_start:span_end]

    return ResolvedSpan(
        text=span_text,
        start_line=_line_of(content, prefix_start),
        end_line=_line_of(content, span_end - 1),
    )
