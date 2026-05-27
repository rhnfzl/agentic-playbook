"""scope_resolution regression tests (v0.11 + ADR-0040).

Covers parse_scope_arg, resolve_git_config_path (standard + worktree
layouts), detect_scope_from_remote, and resolve_scope_arg matrix.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


# === parse_scope_arg ===


def test_parse_scope_arg_handles_none_and_empty() -> None:
    from scope_resolution import parse_scope_arg

    assert parse_scope_arg(None) == []
    assert parse_scope_arg("") == []
    assert parse_scope_arg("   ") == []


def test_parse_scope_arg_handles_single_and_comma_list() -> None:
    from scope_resolution import parse_scope_arg

    assert parse_scope_arg("team") == ["team"]
    assert parse_scope_arg("team,personal") == ["team", "personal"]


def test_parse_scope_arg_strips_whitespace_and_drops_empty() -> None:
    from scope_resolution import parse_scope_arg

    assert parse_scope_arg(" team , personal ") == ["team", "personal"]
    assert parse_scope_arg(",team,,personal,") == ["team", "personal"]


# === resolve_git_config_path ===


def test_resolve_git_config_path_standard_layout(tmp_path: Path) -> None:
    from scope_resolution import resolve_git_config_path

    (tmp_path / ".git").mkdir()
    config = tmp_path / ".git" / "config"
    config.write_text("[core]\n", encoding="utf-8")

    assert resolve_git_config_path(tmp_path) == config


def test_resolve_git_config_path_returns_none_without_git(tmp_path: Path) -> None:
    from scope_resolution import resolve_git_config_path

    assert resolve_git_config_path(tmp_path) is None


def test_resolve_git_config_path_worktree_with_commondir(tmp_path: Path) -> None:
    """Worktree layout: .git is a FILE pointing at the worktree's gitdir;
    that gitdir has a `commondir` file pointing at the main repo's .git/,
    where the canonical config lives."""
    from scope_resolution import resolve_git_config_path

    # Main repo's .git/
    main_git = tmp_path / "main" / ".git"
    main_git.mkdir(parents=True)
    main_config = main_git / "config"
    main_config.write_text("[remote 'origin']\n", encoding="utf-8")

    # Worktree
    worktree_dir = tmp_path / "worktree"
    worktree_dir.mkdir()
    # Worktree's gitdir lives in main/.git/worktrees/<name>/
    worktree_gitdir = main_git / "worktrees" / "wt1"
    worktree_gitdir.mkdir(parents=True)
    # commondir file points back to main_git
    (worktree_gitdir / "commondir").write_text(
        str(main_git), encoding="utf-8"
    )
    # .git file inside the worktree points at the gitdir
    (worktree_dir / ".git").write_text(
        f"gitdir: {worktree_gitdir}\n", encoding="utf-8"
    )

    assert resolve_git_config_path(worktree_dir) == main_config


# === detect_scope_from_remote ===


def test_detect_scope_returns_team_on_match(tmp_path: Path) -> None:
    from scope_resolution import detect_scope_from_remote

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        "[remote \"origin\"]\n"
        "    url = git@<vcs-host>:<team>/coding-agents-playbook.git\n",
        encoding="utf-8",
    )

    assert detect_scope_from_remote(tmp_path, tmp_path) == ["team"]


def test_detect_scope_returns_empty_on_unrecognized_remote(tmp_path: Path) -> None:
    from scope_resolution import detect_scope_from_remote

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        "[remote \"origin\"]\n    url = git@github.com:other/repo.git\n",
        encoding="utf-8",
    )

    assert detect_scope_from_remote(tmp_path, tmp_path) == []


def test_detect_scope_returns_empty_without_git(tmp_path: Path) -> None:
    from scope_resolution import detect_scope_from_remote

    assert detect_scope_from_remote(tmp_path, tmp_path) == []


# === resolve_scope_arg matrix ===


def test_resolve_scope_arg_explicit_overlay(tmp_path: Path) -> None:
    from scope_resolution import resolve_scope_arg

    assert resolve_scope_arg("team", tmp_path, tmp_path) == ["team"]
    assert resolve_scope_arg("a,b,c", tmp_path, tmp_path) == ["a", "b", "c"]


def test_resolve_scope_arg_explicit_none_or_base(tmp_path: Path) -> None:
    from scope_resolution import resolve_scope_arg

    assert resolve_scope_arg("none", tmp_path, tmp_path) == []
    assert resolve_scope_arg("base", tmp_path, tmp_path) == []


def test_resolve_scope_arg_none_falls_through_to_auto_detect(
    tmp_path: Path,
) -> None:
    """When --scope is omitted, auto-detect runs against the target."""
    from scope_resolution import resolve_scope_arg

    # No remote -> auto-detect returns [].
    assert resolve_scope_arg(None, tmp_path, tmp_path) == []
