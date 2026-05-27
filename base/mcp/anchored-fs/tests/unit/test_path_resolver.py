from pathlib import Path
from core.path_resolver import find_candidates


def test_finds_exact_basename_match(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "formatter.py").write_text("x")
    candidates = find_candidates("formatter.py", tmp_path)
    assert any(c.path.name == "formatter.py" for c in candidates)


def test_ranks_basename_match_above_partial(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "formatter.py").write_text("x")
    (tmp_path / "src" / "format_utils.py").write_text("y")
    candidates = find_candidates("formatter.py", tmp_path, limit=5)
    assert candidates[0].path.name == "formatter.py"
    assert candidates[0].similarity > 0.95


def test_excludes_default_ignored_directories(tmp_path: Path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "formatter.py").write_text("x")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "formatter.py").write_text("y")
    candidates = find_candidates("formatter.py", tmp_path)
    assert all("node_modules" not in str(c.path) for c in candidates)


def test_scan_budget_caps_at_file_limit(tmp_path: Path):
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text("x")
    candidates = find_candidates("f5.py", tmp_path, file_scan_cap=3)
    assert len(candidates) <= 5
