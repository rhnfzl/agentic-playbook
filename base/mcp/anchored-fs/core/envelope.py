"""Standard rescue payload format. All validators emit this same shape on failure."""

from __future__ import annotations
from typing import Literal, TypedDict


Validator = Literal["edit_anchor", "path_resolver", "stale_read_guard"]
Kind = Literal[
    "anchor_not_unique",
    "anchor_not_found",
    "suffix_not_found",
    "no_upto_marker",
    "path_ambiguous",
    "path_not_found",
    "stale_read",
    "prefix_not_found",
    "prefix_not_unique",
]


class Envelope(TypedDict):
    ok: bool
    validator: Validator
    kind: Kind
    message: str
    candidates: list[dict]
    hint: str
    context: dict


def build_envelope(
    *,
    validator: Validator,
    kind: Kind,
    message: str,
    hint: str,
    candidates: list[dict] | None = None,
    context: dict | None = None,
) -> Envelope:
    return {
        "ok": False,
        "validator": validator,
        "kind": kind,
        "message": message,
        "candidates": candidates or [],
        "hint": hint,
        "context": context or {},
    }
