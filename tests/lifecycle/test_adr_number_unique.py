"""adr-number-unique check regression tests (v0.11 precursor)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_adr(adr_dir: Path, name: str, body: str = "stub") -> Path:
    """Create a fixture ADR file."""
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def test_adr_number_unique_passes_on_unique_prefixes(tmp_path: Path) -> None:
    """A clean docs/adr/ with no number collisions passes."""
    from checks import CheckContext
    from checks.adr_number_unique import run

    adr_dir = tmp_path / "docs" / "adr"
    _make_adr(adr_dir, "0001-first.md")
    _make_adr(adr_dir, "0002-second.md")
    _make_adr(adr_dir, "0003-third.md")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "ok", f"unique-prefix tree must pass; got {result}"
    assert "3 ADR" in result.summary


def test_adr_number_unique_fails_on_duplicate_prefix(tmp_path: Path) -> None:
    """Two files with the same 4-digit prefix fail with both names in details."""
    from checks import CheckContext
    from checks.adr_number_unique import run

    adr_dir = tmp_path / "docs" / "adr"
    _make_adr(adr_dir, "0032-first-conflict.md")
    _make_adr(adr_dir, "0032-second-conflict.md")
    _make_adr(adr_dir, "0033-no-conflict.md")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "1 duplicate" in result.summary
    assert len(result.details) == 1
    detail = result.details[0]
    assert detail.startswith("0032:")
    assert "0032-first-conflict.md" in detail
    assert "0032-second-conflict.md" in detail


def test_adr_number_unique_reports_multiple_collisions(tmp_path: Path) -> None:
    """Two separate duplicate-pairs both appear in details."""
    from checks import CheckContext
    from checks.adr_number_unique import run

    adr_dir = tmp_path / "docs" / "adr"
    _make_adr(adr_dir, "0010-a.md")
    _make_adr(adr_dir, "0010-b.md")
    _make_adr(adr_dir, "0020-x.md")
    _make_adr(adr_dir, "0020-y.md")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "2 duplicate" in result.summary
    assert len(result.details) == 2
    assert any(d.startswith("0010:") for d in result.details)
    assert any(d.startswith("0020:") for d in result.details)


def test_adr_number_unique_ignores_non_conforming_files(tmp_path: Path) -> None:
    """README.md, .gitkeep, and other non-numbered files don't trigger the check."""
    from checks import CheckContext
    from checks.adr_number_unique import run

    adr_dir = tmp_path / "docs" / "adr"
    _make_adr(adr_dir, "README.md")
    _make_adr(adr_dir, ".gitkeep", body="")
    _make_adr(adr_dir, "draft.md")
    _make_adr(adr_dir, "0001-only-real-adr.md")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "ok"
    assert "1 ADR" in result.summary


def test_adr_number_unique_passes_when_dir_missing(tmp_path: Path) -> None:
    """A repo without docs/adr/ at all is not a failure (just nothing to check)."""
    from checks import CheckContext
    from checks.adr_number_unique import run

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "ok"
    assert "no docs/adr/" in result.summary
