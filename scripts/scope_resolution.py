"""Scope resolution: target-project remote -> content scope (ADR-0040 v0.11).

Lifted out of install.py per the thermo-nuclear review: scope resolution is
POLICY (deciding which overlays apply), not install ORCHESTRATION (dispatch
to adapters). install.py was deliberately decomposed in v0.7-v0.10 and the
v0.11 scope flags re-fattened the dispatcher; this module restores the
boundary so future overlay additions don't grow install.py further.

Public API:
  - resolve_git_config_path(project_dir): handles standard / worktree /
    relative-gitdir layouts.
  - detect_scope_from_remote(target, repo_root): auto-detect from the
    TARGET project's remote URL (not the playbook checkout's).
  - parse_scope_arg(value): parse comma-separated --scope value. Split
    from parse_profile_arg so a future profile named "base" or overlay
    named "research" can't cross-contaminate.
  - resolve_scope_arg(scope_arg, target, repo_root): full CLI matrix
    collapse (explicit name / "none" / "base" / auto-detect).
"""

from __future__ import annotations

from pathlib import Path


def resolve_git_config_path(project_dir: Path) -> Path | None:
    """Resolve the .git/config path for `project_dir`, handling worktrees.

    Standard layout: <project>/.git/ is a directory containing config.
    Worktree layout: <project>/.git is a FILE containing
    `gitdir: <path-to-real-gitdir>`; the config lives at the gitdir's
    `commondir/config` (or `commondir` itself is the main repo's .git/).

    Returns None when no usable config path is found.
    """
    git_path = project_dir / ".git"
    if git_path.is_dir():
        config = git_path / "config"
        return config if config.is_file() else None
    if git_path.is_file():
        try:
            text = git_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not text.startswith("gitdir:"):
            return None
        gitdir_str = text.split(":", 1)[1].strip()
        gitdir = Path(gitdir_str)
        if not gitdir.is_absolute():
            gitdir = (project_dir / gitdir).resolve()
        commondir_file = gitdir / "commondir"
        if commondir_file.is_file():
            try:
                common_str = commondir_file.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            common = Path(common_str)
            if not common.is_absolute():
                common = (gitdir / common).resolve()
            config = common / "config"
            return config if config.is_file() else None
        config = gitdir / "config"
        return config if config.is_file() else None
    return None


def _extract_remote_origin_url(config_text: str) -> str | None:
    """Return the url= for `[remote "origin"]` in a git config, or None.

    v0.11 Codex second-eye fix: an earlier implementation searched the
    whole config text for a substring match. That conflated multi-remote
    configs (origin pointing somewhere generic, a secondary remote
    pointing at team) and resolved to the overlay anyway. The correct
    primary-remote signal is the `origin` section's url, not any url.
    """
    in_origin = False
    for raw in config_text.splitlines():
        line = raw.strip()
        if line.startswith("[remote "):
            in_origin = line.startswith('[remote "origin"]')
            continue
        if line.startswith("["):
            in_origin = False
            continue
        if not in_origin:
            continue
        if line.startswith("url"):
            _, sep, value = line.partition("=")
            if sep:
                return value.strip()
    return None


def detect_scope_from_remote(target: Path | None, repo_root: Path) -> list[str]:
    """Auto-detect content scope from the TARGET project's git remote URL.

    Per ADR-0040 (v0.11) scope-resolution matrix: target project's remote
    drives the auto-detect, not the playbook checkout's remote. The two
    can differ when the playbook and the target are separate clones.

    Looks at the `origin` remote only (the primary). Secondary remotes
    that happen to point at team must not trigger the overlay; an
    install into a fork should default to base-only unless --scope is
    explicit.

    Returns [] when no recognized origin is found (silent base-only).
    Caller is responsible for warning when this is unexpected.
    """
    project_dir = target if target is not None else repo_root
    git_config = resolve_git_config_path(project_dir)
    if git_config is None:
        return []
    try:
        config_text = git_config.read_text(encoding="utf-8")
    except OSError:
        return []
    origin_url = _extract_remote_origin_url(config_text)
    if origin_url is None:
        return []
    if "<vcs-host>:<team>/" in origin_url or "<vcs-host>:<team>/" in origin_url:
        return ["team"]
    return []


def parse_scope_arg(value: str | None) -> list[str]:
    """Parse a --scope CLI value into a list of overlay names.

    Same tokenizer shape as `playbook_profile.parse_profile_arg` but kept
    separate so the two domains can evolve independently (a profile named
    "base" or an overlay named "research" should never be ambiguous via a
    shared parser).
    """
    if value is None:
        return []
    names = [token.strip() for token in value.split(",")]
    return [name for name in names if name]


def resolve_scope_arg(
    scope_arg: str | None,
    target: Path | None,
    repo_root: Path,
) -> list[str]:
    """Collapse the --scope CLI matrix (ADR-0040 L137-149).

    Branches:
      - Explicit "none" or "base" -> base-only.
      - Explicit overlay name(s)  -> parsed comma-separated list.
      - None (flag omitted)       -> auto-detect from target remote.
    """
    if scope_arg in ("none", "base"):
        return []
    if scope_arg is None:
        return detect_scope_from_remote(target, repo_root)
    return parse_scope_arg(scope_arg)
