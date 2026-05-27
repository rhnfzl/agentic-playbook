"""Integration tests for tools/edit_file.py and tools/preview_edit_match.py."""

from pathlib import Path
from tools.edit_file import edit_file, OVERSIZE_THRESHOLD_LINES
from tools.preview_edit_match import preview_edit_match


def test_edit_file_with_upto(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("line 1\ndef foo():\n    x = 1\n    return x\n\nline 6\n")
    result = edit_file(
        path=str(target),
        old_text="def foo():[upto]    return x",
        new_text="def foo():\n    return improved()",
        dry_run=False,
    )
    assert result["ok"] is True
    assert "def foo():\n    return improved()" in target.read_text()


def test_edit_file_returns_failure_envelope_on_ambiguous(tmp_path: Path):
    target = tmp_path / "x.py"
    target.write_text("def foo():\n    a\ndef foo():\n    b\n")
    result = edit_file(
        path=str(target), old_text="def foo():[upto]    a", new_text="x", dry_run=False
    )
    assert result["ok"] is False
    assert result["validator"] == "edit_anchor"
    assert result["kind"] == "prefix_not_unique"


def test_edit_file_auto_rescues_oversize_block_without_upto(tmp_path: Path):
    """A 30-line old_text without [upto] should be auto-rescued from unique anchors."""
    # Build a 30-line file with unique first and last lines
    lines = (
        ["unique_start_line_abc123"]
        + [f"body line {i}" for i in range(28)]
        + ["unique_end_line_xyz789"]
    )
    content = "\n".join(lines) + "\n"
    target = tmp_path / "big.py"
    target.write_text(content)

    # old_text is all 30 lines verbatim, no [upto]
    old_text = "\n".join(lines)
    assert len(old_text.splitlines()) > OVERSIZE_THRESHOLD_LINES

    result = edit_file(path=str(target), old_text=old_text, new_text="replacement")
    assert result["ok"] is True
    assert result.get("auto_rescued") is True
    assert target.read_text() == "replacement\n"


def test_edit_file_under_threshold_passes_through_verbatim(tmp_path: Path):
    """A 10-line old_text (under threshold) should pass through without auto_rescued flag."""
    lines = [f"line {i}" for i in range(10)]
    content = "\n".join(lines) + "\n"
    target = tmp_path / "small.py"
    target.write_text(content)

    old_text = "\n".join(lines)
    assert len(old_text.splitlines()) <= OVERSIZE_THRESHOLD_LINES

    result = edit_file(path=str(target), old_text=old_text, new_text="done")
    assert result["ok"] is True
    assert "auto_rescued" not in result


def test_preview_edit_match_dry_run(tmp_path: Path):
    target = tmp_path / "y.py"
    target.write_text("alpha\nbeta\ngamma\ndelta\n")
    result = preview_edit_match(path=str(target), old_text="alpha[upto]gamma")
    assert result["ok"] is True
    assert result["span_text"] == "alpha\nbeta\ngamma"
    assert result["start_line"] == 1
    assert result["end_line"] == 3
