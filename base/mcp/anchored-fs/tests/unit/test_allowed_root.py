from pathlib import Path
from core.allowed_root import is_within_root, resolve_root


def test_is_within_root_accepts_descendant(tmp_path: Path):
    (tmp_path / "child").mkdir()
    (tmp_path / "child" / "leaf.py").write_text("x")
    assert is_within_root(tmp_path / "child" / "leaf.py", tmp_path) is True


def test_is_within_root_rejects_sibling(tmp_path: Path):
    sibling = tmp_path.parent / "outside.txt"
    assert is_within_root(sibling, tmp_path) is False


def test_is_within_root_rejects_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    link = tmp_path / "link"
    link.symlink_to(outside)
    assert is_within_root(link, tmp_path) is False


def test_resolve_root_finds_git_dir(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    assert resolve_root(nested) == tmp_path


def test_resolve_root_falls_back_to_cwd_when_no_marker(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_root(tmp_path) == tmp_path
