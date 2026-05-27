"""Native edit_file with [upto] anchor support. Returns plain dicts (MCP wrapping at Task 11)."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Mapping
from core.upto_resolver import resolve, ResolveFailure
from core.envelope import build_envelope
from core.adoption_tracker import AdoptionRecord, log_edit

OVERSIZE_THRESHOLD_LINES = 25

_DEFAULT_ADOPTION_LOG = (
    Path(os.environ.get("HOME", str(Path.home())))
    / ".config"
    / "agent-shared"
    / "state"
    / "adoption.jsonl"
)


def _find_unique_anchor(lines: list[str], content: str, from_start: bool) -> str | None:
    """Find shortest N-line span from start or end of lines that is unique in content."""
    if from_start:
        for n in range(1, len(lines) + 1):
            candidate = "\n".join(lines[:n])
            if content.count(candidate) == 1:
                return candidate
    else:
        for n in range(1, len(lines) + 1):
            candidate = "\n".join(lines[-n:])
            if content.count(candidate) == 1:
                return candidate
    return None


def _auto_rescue(old_text: str, content: str) -> tuple[str, bool]:
    """Try to synthesize a unique prefix+suffix pair from old_text.

    Returns (resolved_old_text, rescued) where rescued=True if anchors were found.
    """
    lines = old_text.splitlines()
    prefix = _find_unique_anchor(lines, content, from_start=True)
    if prefix is None:
        return old_text, False
    suffix = _find_unique_anchor(lines, content, from_start=False)
    if suffix is None:
        return old_text, False

    # Don't rescue if prefix and suffix overlap (same short text)
    if prefix == suffix:
        return old_text, False

    synthesized = f"{prefix}[upto]{suffix}"
    result = resolve(content, synthesized)
    if isinstance(result, ResolveFailure):
        return old_text, False
    return result.text, True


def edit_file(
    *,
    path: str,
    old_text: str,
    new_text: str,
    dry_run: bool = False,
    session: str = "unknown",
    adoption_log_path: Path | None = None,
) -> Mapping[str, Any]:
    p = Path(path)
    if not p.exists():
        return build_envelope(
            validator="edit_anchor",
            kind="path_not_found",
            message=f"file not found: {path}",
            hint="check the path and retry",
            context={"file": path},
        )
    content = p.read_text()
    used_upto = "[upto]" in old_text
    auto_rescued = False

    if used_upto:
        result = resolve(content, old_text)
        if isinstance(result, ResolveFailure):
            return build_envelope(
                validator="edit_anchor",
                kind=result.kind,
                message=result.message,
                candidates=result.candidates,
                hint="use a longer prefix or different anchor",
                context={"file": path, "anchor_pattern": old_text},
            )
        resolved_old = result.text
    else:
        num_lines = len(old_text.splitlines())
        if num_lines > OVERSIZE_THRESHOLD_LINES:
            rescued_text, auto_rescued = _auto_rescue(old_text, content)
            if auto_rescued:
                resolved_old = rescued_text
            else:
                # Fall through to verbatim path
                if old_text not in content:
                    return build_envelope(
                        validator="edit_anchor",
                        kind="anchor_not_found",
                        message="old_text not found verbatim",
                        hint="verify file content matches old_text exactly, or use [upto] anchoring",
                        context={"file": path},
                    )
                if content.count(old_text) > 1:
                    return build_envelope(
                        validator="edit_anchor",
                        kind="anchor_not_unique",
                        message=f"old_text matches {content.count(old_text)} times",
                        hint="add more context to make old_text unique, or use [upto] anchoring",
                        context={"file": path},
                    )
                resolved_old = old_text
        else:
            if old_text not in content:
                return build_envelope(
                    validator="edit_anchor",
                    kind="anchor_not_found",
                    message="old_text not found verbatim",
                    hint="verify file content matches old_text exactly, or use [upto] anchoring",
                    context={"file": path},
                )
            if content.count(old_text) > 1:
                return build_envelope(
                    validator="edit_anchor",
                    kind="anchor_not_unique",
                    message=f"old_text matches {content.count(old_text)} times",
                    hint="add more context to make old_text unique, or use [upto] anchoring",
                    context={"file": path},
                )
            resolved_old = old_text

    new_content = content.replace(resolved_old, new_text, 1)

    # Log adoption telemetry (fail-soft)
    try:
        log_path = (
            adoption_log_path
            if adoption_log_path is not None
            else _DEFAULT_ADOPTION_LOG
        )
        record = AdoptionRecord(
            agent="mcp",
            session=session,
            used_upto=used_upto,
            old_lines=len(old_text.splitlines()),
            rescued=auto_rescued,
            file_extension=Path(path).suffix,
        )
        log_edit(log_path, record)
    except Exception:
        pass

    if dry_run:
        ret: dict = {
            "ok": True,
            "dry_run": True,
            "diff_chars": len(new_content) - len(content),
        }
        if auto_rescued:
            ret["auto_rescued"] = True
        return ret

    p.write_text(new_content)
    ret = {
        "ok": True,
        "replaced_chars": len(resolved_old),
        "wrote_chars": len(new_text),
    }
    if auto_rescued:
        ret["auto_rescued"] = True
    return ret
