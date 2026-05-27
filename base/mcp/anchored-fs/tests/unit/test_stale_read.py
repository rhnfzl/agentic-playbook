import hashlib
from pathlib import Path
from core.stale_read import is_stale, normalize_for_hash


def test_is_stale_returns_false_when_no_prior_read(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("hello")
    assert is_stale(f, history={}, allow_edit_without_prior_read=True) is False


def test_is_stale_returns_false_when_content_unchanged(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("hello")
    normalized = normalize_for_hash(b"hello")
    history = {
        str(f.resolve()): {
            "mtime_at_read": f.stat().st_mtime,
            "sha256_at_read": hashlib.sha256(normalized).hexdigest(),
        }
    }
    assert is_stale(f, history=history, allow_edit_without_prior_read=True) is False


def test_is_stale_returns_true_when_content_changed(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text("hello")
    old_hash = hashlib.sha256(normalize_for_hash(b"hello")).hexdigest()
    history = {str(f.resolve()): {"mtime_at_read": 0.0, "sha256_at_read": old_hash}}
    f.write_text("goodbye")
    assert is_stale(f, history=history, allow_edit_without_prior_read=True) is True


def test_normalize_for_hash_collapses_line_endings():
    assert normalize_for_hash(b"a\r\nb\r\nc") == normalize_for_hash(b"a\nb\nc")


def test_is_stale_ignores_line_ending_only_change(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_bytes(b"a\nb\n")
    history = {
        str(f.resolve()): {
            "mtime_at_read": 0.0,
            "sha256_at_read": hashlib.sha256(normalize_for_hash(b"a\nb\n")).hexdigest(),
        }
    }
    f.write_bytes(b"a\r\nb\r\n")
    assert (
        is_stale(
            f,
            history=history,
            allow_edit_without_prior_read=True,
            normalize_line_endings=True,
        )
        is False
    )
