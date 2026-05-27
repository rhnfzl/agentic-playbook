"""playbook-version check regression tests (v0.11 precursor).

Validates ADR-0040's VERSION-file-as-single-source-of-truth rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _setup(tmp_path: Path, version: str | None, install_body: str | None) -> Path:
    """Build a synthetic repo_root with given VERSION file + install.py body."""
    if version is not None:
        (tmp_path / "VERSION").write_text(version, encoding="utf-8")
    if install_body is not None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "install.py").write_text(install_body, encoding="utf-8")
    return tmp_path


def test_playbook_version_passes_on_canonical_setup(tmp_path: Path) -> None:
    """VERSION file with valid semver + install.py reads it: OK."""
    from checks import CheckContext
    from checks.playbook_version import run

    repo_root = _setup(
        tmp_path,
        version="0.11.0\n",
        install_body=(
            "from pathlib import Path\n"
            "def _read_version():\n"
            "    return (Path(__file__).parent.parent / 'VERSION').read_text().strip()\n"
            "PLAYBOOK_VERSION = _read_version()\n"
        ),
    )
    ctx = CheckContext(repo_root=repo_root, content=None)
    result = run(ctx)
    assert result.status == "ok"
    assert "0.11.0" in result.summary


def test_playbook_version_fails_when_version_missing(tmp_path: Path) -> None:
    """VERSION file missing: FAIL."""
    from checks import CheckContext
    from checks.playbook_version import run

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "missing" in result.summary


def test_playbook_version_fails_on_non_semver(tmp_path: Path) -> None:
    """VERSION content that isn't semver: FAIL."""
    from checks import CheckContext
    from checks.playbook_version import run

    repo_root = _setup(tmp_path, version="latest\n", install_body=None)
    ctx = CheckContext(repo_root=repo_root, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "not semver" in result.summary


def test_playbook_version_accepts_prerelease_suffix(tmp_path: Path) -> None:
    """Semver with pre-release / build suffix is accepted."""
    from checks import CheckContext
    from checks.playbook_version import run

    repo_root = _setup(tmp_path, version="0.11.0-rc1\n", install_body=None)
    ctx = CheckContext(repo_root=repo_root, content=None)
    result = run(ctx)
    assert result.status == "ok"


def test_playbook_version_fails_on_hardcoded_constant(tmp_path: Path) -> None:
    """install.py with a hardcoded PLAYBOOK_VERSION = 'X.Y.Z' string literal: FAIL."""
    from checks import CheckContext
    from checks.playbook_version import run

    repo_root = _setup(
        tmp_path,
        version="0.11.0\n",
        install_body=(
            'LOCKFILE_NAME = ".playbook-lock.json"\n'
            'PLAYBOOK_VERSION = "0.4.0"\n'
        ),
    )
    ctx = CheckContext(repo_root=repo_root, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "hardcodes" in result.summary
    assert len(result.details) == 1
    assert "PLAYBOOK_VERSION" in result.details[0]


def test_playbook_version_allows_function_call_form(tmp_path: Path) -> None:
    """install.py with PLAYBOOK_VERSION = <function call>: OK (no hardcode)."""
    from checks import CheckContext
    from checks.playbook_version import run

    repo_root = _setup(
        tmp_path,
        version="0.11.0\n",
        install_body=(
            "PLAYBOOK_VERSION = _read_playbook_version()\n"
        ),
    )
    ctx = CheckContext(repo_root=repo_root, content=None)
    result = run(ctx)
    assert result.status == "ok"
