"""Shared fixtures + helpers for the marketplace test suite.

Split out of the former monolithic test_marketplace_package.py so each
per-area test module stays focused (see test_marketplace_*.py).
"""

from __future__ import annotations

from pathlib import Path


from marketplace import (
    EmitterConfig,
    RoleProfile,
)


# ===================================================================
# Shared helpers
# ===================================================================


def _make_config(
    repo_root: Path,
    dest_root: Path,
    *,
    author_name: str = "Rehan Fazal",
    author_email: str | None = None,
    dry_run: bool = False,
    default_profile_version: str | None = None,
) -> EmitterConfig:
    return EmitterConfig(
        repo_root=repo_root,
        dest_root=dest_root,
        tool_version="0.11.0",
        author_name=author_name,
        author_email=author_email,
        dry_run=dry_run,
        default_profile_version=default_profile_version,
    )


def _make_role_profile(
    name: str = "backend-developer",
    catalog_name: str = "rhnfzl",
    description: str = "Backend developer profile.",
    **kwargs,
) -> RoleProfile:
    return RoleProfile(
        name=name,
        catalog_name=catalog_name,
        description=description,
        **kwargs,
    )


def _seed_base_dirs(repo_root: Path) -> None:
    """Create empty base/ subdirectories used by the resolver."""
    for sub in ("skills", "rules", "hooks", "mcp", "agents", "commands", "prompts"):
        (repo_root / "base" / sub).mkdir(parents=True, exist_ok=True)


def _seed_profile_toml(profiles_dir: Path, name: str, body: str) -> Path:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    path = profiles_dir / f"{name}.toml"
    path.write_text(body, encoding="utf-8")
    return path


# ===================================================================
# Errors
# ===================================================================


class _FakeProfileTOML:
    """Helper that lays out a tiny valid playbook tree for end-to-end emit."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        _seed_base_dirs(repo_root)
        (repo_root / "VERSION").write_text("0.11.0\n", encoding="utf-8")

    def add_skill(self, name: str) -> None:
        d = self.repo_root / "base" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(f"# {name}", encoding="utf-8")

    def add_rule(self, name: str) -> None:
        f = self.repo_root / "base" / "rules" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"# {name}", encoding="utf-8")

    def add_rule_stem(self, stem: str) -> None:
        """Real convention: file is `<stem>.md`, profile refs the bare stem."""
        (self.repo_root / "base" / "rules" / f"{stem}.md").write_text(
            f"# {stem}", encoding="utf-8"
        )

    def add_hook(
        self, stem: str, *, event: str = "PreToolUse", matcher: str = "Bash"
    ) -> None:
        """Real convention: file is `<stem>.sh`, profile refs the bare stem."""
        (self.repo_root / "base" / "hooks" / f"{stem}.sh").write_text(
            f"# PLAYBOOK-HOOK-EVENT: {event}\n# PLAYBOOK-HOOK-MATCHER: {matcher}\necho hi\n",
            encoding="utf-8",
        )

    def add_profile(self, name: str, skills=(), rules=(), hooks=()) -> Path:
        pdir = self.repo_root / "profiles"
        pdir.mkdir(parents=True, exist_ok=True)
        body_lines = [
            f'description = "Profile {name}"',
            "[skills]",
            f"include = {list(skills)}",
            "[rules]",
            f"include = {list(rules)}",
            "[hooks]",
            f"include = {list(hooks)}",
        ]
        body = "\n".join(body_lines) + "\n"
        path = pdir / f"{name}.toml"
        path.write_text(body, encoding="utf-8")
        return path
