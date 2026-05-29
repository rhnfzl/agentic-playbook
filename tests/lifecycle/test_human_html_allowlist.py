"""human-html-allowlist check regression tests (v0.8 B7 + Codex fold-in)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_human_html_allowlist_check_passes_on_clean_file(tmp_path: Path) -> None:
    """A well-formed .human-html-allowlist passes the check."""
    from checks import CheckContext
    from checks.human_html_allowlist import run

    allowlist = tmp_path / ".human-html-allowlist"
    allowlist.write_text(
        "# Workspace-specific MD lanes\n"
        "myproject/notes/*\n"
        "docs/internal/*\n"
        "\n"
        "scratch/**\n",
        encoding="utf-8",
    )

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "ok", f"clean allowlist must pass; got {result}"


def test_human_html_allowlist_check_flags_command_substitution(tmp_path: Path) -> None:
    """Lines containing $(...) or backticks are FAIL because a future
    read-loop rewrite that lost the case-pattern quoting would treat them
    as command substitutions.
    """
    from checks import CheckContext
    from checks.human_html_allowlist import run

    allowlist = tmp_path / ".human-html-allowlist"
    allowlist.write_text(
        "myproject/notes/*\n$(rm -rf /)\n",
        encoding="utf-8",
    )

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "fail"
    assert any("FAIL" in d for d in result.details)


def test_human_html_allowlist_check_warns_on_path_traversal(tmp_path: Path) -> None:
    """A pattern with `..` is suspicious; flagged as warn (not fail)
    since the hook treats it as a glob match and does not interpret it.
    """
    from checks import CheckContext
    from checks.human_html_allowlist import run

    allowlist = tmp_path / ".human-html-allowlist"
    allowlist.write_text("../etc/passwd\n", encoding="utf-8")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "warn"
    assert any("WARN" in d for d in result.details)


def test_human_html_allowlist_check_returns_ok_when_absent(tmp_path: Path) -> None:
    """No allowlist file under repo_root: ok with the no-files summary."""
    from checks import CheckContext
    from checks.human_html_allowlist import run

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "ok"
    assert "no .human-html-allowlist files in scope" in result.summary


def test_human_html_allowlist_warns_on_single_trailing_backslash(
    tmp_path: Path,
) -> None:
    """v0.8 Codex fold-in: a line ending in a single backslash should
    warn. Previously the regex required two trailing backslashes which
    never matched a real continuation pattern.
    """
    from checks import CheckContext
    from checks.human_html_allowlist import run

    allowlist = tmp_path / ".human-html-allowlist"
    allowlist.write_text("myproject/notes/*\\\n", encoding="utf-8")

    ctx = CheckContext(repo_root=tmp_path, content=None)
    result = run(ctx)
    assert result.status == "warn", (
        f"single trailing backslash must warn; got {result.status}: {result.details}"
    )
    assert any("WARN" in d for d in result.details)
