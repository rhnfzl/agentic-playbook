"""Net-new tool: dry-run anchor resolution without writing. Returns plain dicts."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping
from core.upto_resolver import resolve, ResolveFailure
from core.envelope import build_envelope


def preview_edit_match(*, path: str, old_text: str) -> Mapping[str, Any]:
    p = Path(path)
    if not p.exists():
        return build_envelope(
            validator="edit_anchor",
            kind="path_not_found",
            message=f"file not found: {path}",
            hint="check the path",
            context={"file": path},
        )
    content = p.read_text()
    if "[upto]" not in old_text:
        return build_envelope(
            validator="edit_anchor",
            kind="no_upto_marker",
            message="old_text has no [upto] marker; nothing to preview",
            hint="add [upto] between prefix and suffix",
            context={"file": path},
        )
    result = resolve(content, old_text)
    if isinstance(result, ResolveFailure):
        return build_envelope(
            validator="edit_anchor",
            kind=result.kind,
            message=result.message,
            candidates=result.candidates,
            hint="use longer anchors",
            context={"file": path, "anchor_pattern": old_text},
        )
    return {
        "ok": True,
        "span_text": result.text,
        "start_line": result.start_line,
        "end_line": result.end_line,
    }
