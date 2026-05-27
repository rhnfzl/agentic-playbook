"""ignored-containment check regression tests (v0.11 precursor).

Each test uses two subdirs of tmp_path:
  - <tmp_path>/scan: the simulated repo_root the check walks.
  - <tmp_path>/config.toml: the external config file, OUTSIDE the scan tree,
    matching the design (the config never lives in the repo it audits).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _make_scan_dir(tmp_path: Path) -> Path:
    scan = tmp_path / "scan"
    scan.mkdir()
    return scan


def _make_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_ignored_containment_warns_when_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default behavior (env var unset, not strict): WARN."""
    from checks import CheckContext
    from checks.ignored_containment import run

    monkeypatch.delenv("PLAYBOOK_CONTAINMENT_TERMS", raising=False)
    monkeypatch.delenv("PLAYBOOK_CONTAINMENT_STRICT", raising=False)

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "warn"
    assert "unconfigured" in result.summary


def test_ignored_containment_fails_when_unconfigured_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """STRICT=1 + env var unset: FAIL."""
    from checks import CheckContext
    from checks.ignored_containment import run

    monkeypatch.delenv("PLAYBOOK_CONTAINMENT_TERMS", raising=False)
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_STRICT", "1")

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "STRICT" in result.summary


def test_ignored_containment_fails_when_config_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env var points at non-existent path: FAIL."""
    from checks import CheckContext
    from checks.ignored_containment import run

    monkeypatch.setenv(
        "PLAYBOOK_CONTAINMENT_TERMS", str(tmp_path / "does-not-exist.toml")
    )

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "non-existent" in result.summary


def test_ignored_containment_fails_on_invalid_toml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed TOML in config file: FAIL with parse error."""
    from checks import CheckContext
    from checks.ignored_containment import run

    config = _make_config(tmp_path, "terms = [unclosed-bracket\n")
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "failed to parse" in result.summary


def test_ignored_containment_warns_on_empty_terms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config with empty terms list: WARN (configured but vacuous)."""
    from checks import CheckContext
    from checks.ignored_containment import run

    config = _make_config(tmp_path, "terms = []\n")
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "warn"
    assert "empty" in result.summary


def test_ignored_containment_passes_on_clean_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured terms, no matches in scan tree: OK."""
    from checks import CheckContext
    from checks.ignored_containment import run

    scan = _make_scan_dir(tmp_path)
    (scan / "innocent.md").write_text("Nothing to see here.\n", encoding="utf-8")

    config = _make_config(tmp_path, 'terms = ["forbidden-thing"]\n')
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=scan, content=None)
    result = run(ctx)
    assert result.status == "ok", (
        f"clean tree must pass; got {result.status}: {result.details}"
    )
    assert "no containment leaks" in result.summary


def test_ignored_containment_fails_with_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Match in scan tree: FAIL with file:line:content detail."""
    from checks import CheckContext
    from checks.ignored_containment import run

    scan = _make_scan_dir(tmp_path)
    leak = scan / "leaky.md"
    leak.write_text(
        "Line 1\nThis line mentions FORBIDDEN-THING\nLine 3\n",
        encoding="utf-8",
    )

    config = _make_config(tmp_path, 'terms = ["forbidden-thing"]\n')
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=scan, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "1 containment leak" in result.summary
    assert len(result.details) == 1
    assert "leaky.md:2:" in result.details[0]
    assert "FORBIDDEN-THING" in result.details[0]


def test_ignored_containment_matches_case_insensitively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Match ignores case (mixed-case org names appear in mixed forms)."""
    from checks import CheckContext
    from checks.ignored_containment import run

    scan = _make_scan_dir(tmp_path)
    (scan / "mixed.md").write_text("MyOrg makes products\n", encoding="utf-8")

    config = _make_config(tmp_path, 'terms = ["myorg"]\n')
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=scan, content=None)
    result = run(ctx)
    assert result.status == "fail"


def test_ignored_containment_respects_exclude_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files under explicit exclude_dirs are not scanned."""
    from checks import CheckContext
    from checks.ignored_containment import run

    scan = _make_scan_dir(tmp_path)
    excluded_dir = scan / "vendored" / "lib"
    excluded_dir.mkdir(parents=True)
    (excluded_dir / "thirdparty.md").write_text(
        "third party content mentions forbidden-thing\n", encoding="utf-8"
    )

    config = _make_config(
        tmp_path,
        'terms = ["forbidden-thing"]\nexclude_dirs = ["vendored"]\n',
    )
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=scan, content=None)
    result = run(ctx)
    assert result.status == "ok", (
        f"vendored/ should be excluded, got {result.status}: {result.details}"
    )


def test_ignored_containment_default_excludes_dot_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default .git exclusion is applied when exclude_dirs omitted."""
    from checks import CheckContext
    from checks.ignored_containment import run

    scan = _make_scan_dir(tmp_path)
    git_dir = scan / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("forbidden-thing\n", encoding="utf-8")

    config = _make_config(tmp_path, 'terms = ["forbidden-thing"]\n')
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=scan, content=None)
    result = run(ctx)
    assert result.status == "ok", (
        f".git/ should be excluded by default, got {result.status}: {result.details}"
    )


def test_ignored_containment_invalid_regex_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An invalid regex in terms is caught at compile time."""
    from checks import CheckContext
    from checks.ignored_containment import run

    config = _make_config(tmp_path, 'terms = ["[unclosed-class"]\n')
    monkeypatch.setenv("PLAYBOOK_CONTAINMENT_TERMS", str(config))

    ctx = CheckContext(repo_root=_make_scan_dir(tmp_path), content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert "invalid regex" in result.summary
