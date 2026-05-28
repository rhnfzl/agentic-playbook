"""Tests for scripts/marketplace_emitter.py (ADR-0043, v0.14).

Exercises the marketplace metadata emitter in isolation: profile parsing,
catalog generation per-agent, symlink target validation, reserved-name
rejection, idempotency, and per-agent variance (Codex omits unsupported
components).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from marketplace_emitter import (  # noqa: E402
    META_PROFILE_NAME,
    RESERVED_MARKETPLACE_NAMES,
    TOOL_VERSION,
    EmitterConfig,
    Profile,
    _build_meta_profile,
    _claude_marketplace_catalog,
    _claude_plugin_manifest,
    _codex_marketplace_catalog,
    _codex_plugin_manifest,
    _cursor_marketplace_catalog,
    _cursor_plugin_manifest,
    _gemini_extension_manifest,
    _load_profile,
    _load_profiles,
    _symlink_if_changed,
    _validate_components,
    _validate_marketplace_name,
    _write_if_changed,
    emit,
)


# ---------------------------------------------------------------------------
# Test fixtures: minimal destination + profile + base/ tree
# ---------------------------------------------------------------------------


def _build_destination(tmp_path: Path) -> Path:
    """Materialize a minimal destination repo: base/ + profiles/ + VERSION."""
    dest = tmp_path / "dest"
    dest.mkdir()

    base = dest / "base"
    (base / "skills" / "engineering" / "code-review").mkdir(parents=True)
    (base / "skills" / "engineering" / "code-review" / "SKILL.md").write_text(
        "---\nname: code-review\ndescription: Review a PR\n---\n\n# code-review\n"
    )
    (base / "skills" / "productivity" / "handoff").mkdir(parents=True)
    (base / "skills" / "productivity" / "handoff" / "SKILL.md").write_text(
        "---\nname: handoff\ndescription: Hand work off\n---\n\n# handoff\n"
    )
    (base / "skills" / "meta" / "write-a-skill").mkdir(parents=True)
    (base / "skills" / "meta" / "write-a-skill" / "SKILL.md").write_text(
        "---\nname: write-a-skill\ndescription: Author a new skill\n---\n\n# write-a-skill\n"
    )

    (base / "rules").mkdir()
    (base / "rules" / "no-em-dashes.md").write_text("# No em dashes\n")
    (base / "rules" / "writing-style.md").write_text("# Writing style\n")

    (base / "hooks").mkdir()
    (base / "hooks" / "lint-guard.sh").write_text("#!/usr/bin/env bash\necho lint\n")
    (base / "hooks" / "never-push-to-develop.sh").write_text(
        "#!/usr/bin/env bash\necho block\n"
    )

    (base / "mcp").mkdir()
    (base / "mcp" / "tavily.json").write_text(
        '{"command": "npx", "args": ["tavily"]}\n'
    )
    (base / "mcp" / "atlassian").mkdir()
    (base / "mcp" / "atlassian" / "config.json").write_text("{}\n")

    (base / "agents").mkdir()
    (base / "agents" / "second-eye-reviewer.md").write_text(
        "---\nname: second-eye-reviewer\n---\n"
    )

    (base / "commands").mkdir()
    (base / "commands" / "handoff.md").write_text("# /handoff\n")

    (base / "prompts").mkdir()
    (base / "prompts" / "bootstrap-your-playbook.md").write_text("# bootstrap\n")

    profiles = dest / "profiles"
    profiles.mkdir()
    (profiles / "engineering.toml").write_text(
        """
name = "engineering"
description = "Engineering profile for backend + frontend work."

[skills]
include = ["engineering/code-review", "productivity/handoff"]

[rules]
include = ["no-em-dashes", "writing-style"]

[hooks]
include = ["lint-guard"]

[mcp]
include = ["tavily", "atlassian"]
"""
    )
    (profiles / "qa.toml").write_text(
        """
name = "qa"
description = "Quality assurance profile."

[skills]
include = ["productivity/handoff"]

[rules]
include = ["no-em-dashes"]

[hooks]
include = ["never-push-to-develop"]

[mcp]
include = ["tavily"]
"""
    )

    (dest / "VERSION").write_text("0.14.0\n")
    return dest


def _config(dest: Path, **overrides) -> EmitterConfig:
    defaults = {
        "destination": dest,
        "marketplace_name": "8v-coding-agents-playbook",
        "version": "0.14.0",
        "owner_name": "Test Owner",
        "owner_email": "test@example.com",
        "homepage": "https://example.com",
        "dry_run": False,
    }
    defaults.update(overrides)
    return EmitterConfig(**defaults)


# ---------------------------------------------------------------------------
# _validate_marketplace_name
# ---------------------------------------------------------------------------


def test_validate_marketplace_name_accepts_normal():
    _validate_marketplace_name("8v-coding-agents-playbook")
    _validate_marketplace_name("my-team-skills")


def test_validate_marketplace_name_rejects_reserved():
    for reserved in RESERVED_MARKETPLACE_NAMES:
        with pytest.raises(SystemExit) as exc_info:
            _validate_marketplace_name(reserved)
        assert exc_info.value.code == 5


def test_validate_marketplace_name_rejects_impersonation_prefix():
    for impersonator in ("anthropic-tools", "claude-code-suite", "Anthropic-Plugins"):
        with pytest.raises(SystemExit) as exc_info:
            _validate_marketplace_name(impersonator)
        assert exc_info.value.code == 5


def test_validate_marketplace_name_rejects_empty():
    for empty in ("", "   ", "\n"):
        with pytest.raises(SystemExit) as exc_info:
            _validate_marketplace_name(empty)
        assert exc_info.value.code == 5


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def test_load_profile_parses_toml(tmp_path: Path):
    p = tmp_path / "test.toml"
    p.write_text(
        """
name = "test"
description = "A test profile"

[skills]
include = ["engineering/x", "productivity/y"]

[rules]
include = ["rule-a"]
"""
    )
    profile = _load_profile(p)
    assert profile.name == "test"
    assert profile.description == "A test profile"
    assert profile.skills == ["engineering/x", "productivity/y"]
    assert profile.rules == ["rule-a"]
    assert profile.hooks == []
    assert profile.mcp == []


def test_load_profile_falls_back_to_filename_for_name(tmp_path: Path):
    p = tmp_path / "fallback.toml"
    p.write_text("# no name field\n")
    profile = _load_profile(p)
    assert profile.name == "fallback"


def test_build_meta_profile_includes_meta_skills_agents_commands_prompts(
    tmp_path: Path,
):
    dest = _build_destination(tmp_path)
    base = dest / "base"
    meta = _build_meta_profile(base)
    assert meta.name == META_PROFILE_NAME
    assert meta.skills == ["meta/write-a-skill"]
    assert meta.agents == ["second-eye-reviewer"]
    assert meta.commands == ["handoff"]
    assert meta.prompts == ["bootstrap-your-playbook"]


def test_load_profiles_returns_role_profiles_plus_meta(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    names = [p.name for p in profiles]
    assert "engineering" in names
    assert "qa" in names
    assert META_PROFILE_NAME in names
    # Meta sits last in browse order
    assert names[-1] == META_PROFILE_NAME


def test_load_profiles_missing_dir_exits(tmp_path: Path):
    with pytest.raises(SystemExit):
        _load_profiles(tmp_path / "nonexistent", tmp_path / "also-missing")


# ---------------------------------------------------------------------------
# Component validation (profile references must exist)
# ---------------------------------------------------------------------------


def test_validate_components_passes_when_all_exist(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profile = Profile(
        name="x",
        description="ok",
        skills=["engineering/code-review"],
        rules=["no-em-dashes"],
        hooks=["lint-guard"],
        mcp=["tavily"],
    )
    errors = _validate_components(profile, dest / "base")
    assert errors == []


def test_validate_components_reports_missing_skill(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profile = Profile(
        name="x",
        description="ok",
        skills=["engineering/nonexistent"],
    )
    errors = _validate_components(profile, dest / "base")
    assert len(errors) == 1
    assert "engineering/nonexistent" in errors[0]


def test_validate_components_reports_missing_rule(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profile = Profile(
        name="x",
        description="ok",
        rules=["nonexistent-rule"],
    )
    errors = _validate_components(profile, dest / "base")
    assert len(errors) == 1
    assert "nonexistent-rule" in errors[0]


def test_validate_components_reports_missing_hook(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profile = Profile(
        name="x",
        description="ok",
        hooks=["nonexistent-hook"],
    )
    errors = _validate_components(profile, dest / "base")
    assert len(errors) == 1


def test_validate_components_reports_missing_mcp(tmp_path: Path):
    dest = _build_destination(tmp_path)
    profile = Profile(
        name="x",
        description="ok",
        mcp=["nonexistent-mcp"],
    )
    errors = _validate_components(profile, dest / "base")
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# Marketplace catalog shape (per agent)
# ---------------------------------------------------------------------------


def test_claude_marketplace_catalog_shape(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    catalog = _claude_marketplace_catalog(profiles, config)
    assert catalog["name"] == "8v-coding-agents-playbook"
    assert catalog["owner"]["name"] == "Test Owner"
    assert catalog["owner"]["email"] == "test@example.com"
    assert len(catalog["plugins"]) == len(profiles)
    for entry in catalog["plugins"]:
        assert entry["source"].startswith("./plugins/")
        assert entry["version"] == "0.14.0"


def test_cursor_marketplace_catalog_mirrors_claude(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    claude = _claude_marketplace_catalog(profiles, config)
    cursor = _cursor_marketplace_catalog(profiles, config)
    assert cursor == claude


def test_codex_marketplace_catalog_uses_source_path(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    catalog = _codex_marketplace_catalog(profiles, config)
    for entry in catalog["plugins"]:
        assert isinstance(entry["source"], dict)
        assert entry["source"]["path"].startswith("./plugins/")
        assert entry["policy"]["installation"] == "AVAILABLE"


def test_gemini_extension_includes_profile_metadata(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    manifest = _gemini_extension_manifest(profiles, config)
    assert manifest["name"] == "8v-coding-agents-playbook"
    assert manifest["skillsPath"] == "./base/skills"
    assert manifest["metadata"]["profileCount"] == len(profiles)
    assert "engineering" in manifest["metadata"]["profileNames"]
    assert manifest["metadata"]["emittedBy"] == TOOL_VERSION


# ---------------------------------------------------------------------------
# Plugin manifest shape (per agent)
# ---------------------------------------------------------------------------


def test_claude_plugin_manifest_uses_dot_slash_paths(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profiles = _load_profiles(dest / "profiles", dest / "base")
    engineering = next(p for p in profiles if p.name == "engineering")
    manifest = _claude_plugin_manifest(engineering, config)
    # Claude Code 2.1.144+ requires "./"-prefixed paths
    for field in ("skills", "rules", "hooks", "mcpServers"):
        if field in manifest:
            for path in manifest[field]:
                assert path.startswith("./"), f"{field} path missing ./ prefix: {path}"


def test_codex_plugin_manifest_omits_subagents_commands_hooks(tmp_path: Path):
    """Codex does not support sub-agents, commands, or hooks in plugins."""
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profile = Profile(
        name="meta",
        description="meta pack",
        skills=["meta/write-a-skill"],
        agents=["second-eye-reviewer"],
        commands=["handoff"],
        hooks=["lint-guard"],
        mcp=["tavily"],
    )
    manifest = _codex_plugin_manifest(profile, config)
    assert "skills" in manifest
    assert "mcpServers" in manifest
    # Codex output omits these even if the profile lists them
    assert "agents" not in manifest
    assert "commands" not in manifest
    assert "hooks" not in manifest


def test_codex_plugin_manifest_has_interface_block(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profile = Profile(
        name="engineering",
        description="Engineering work",
        skills=["engineering/code-review"],
    )
    manifest = _codex_plugin_manifest(profile, config)
    assert "interface" in manifest
    assert manifest["interface"]["displayName"] == "Engineering"
    assert "category" in manifest["interface"]
    assert "skills" in manifest["interface"]["capabilities"]


def test_cursor_plugin_manifest_matches_claude(tmp_path: Path):
    """Cursor and Claude Code plugin schemas are near-identical."""
    dest = _build_destination(tmp_path)
    config = _config(dest)
    profile = Profile(
        name="engineering",
        description="Engineering",
        skills=["engineering/code-review"],
        rules=["no-em-dashes"],
    )
    assert _cursor_plugin_manifest(profile, config) == _claude_plugin_manifest(
        profile, config
    )


# ---------------------------------------------------------------------------
# Symlink safety
# ---------------------------------------------------------------------------


def test_symlink_target_inside_base_is_accepted(tmp_path: Path):
    dest = _build_destination(tmp_path)
    base = dest / "base"
    target = base / "skills" / "engineering" / "code-review"
    link = dest / "plugins" / "engineering" / "skills" / "code-review"
    link.parent.mkdir(parents=True)
    changed = _symlink_if_changed(link, target, base, dest, dry_run=False)
    assert changed
    assert link.is_symlink()


def test_symlink_target_outside_base_is_rejected(tmp_path: Path):
    dest = _build_destination(tmp_path)
    base = dest / "base"
    # Try to point at something outside base/
    outside_target = dest / "VERSION"
    link = dest / "plugins" / "x" / "evil"
    link.parent.mkdir(parents=True)
    with pytest.raises(SystemExit) as exc_info:
        _symlink_if_changed(link, outside_target, base, dest, dry_run=False)
    assert exc_info.value.code == 5


def test_symlink_target_outside_destination_is_rejected(tmp_path: Path):
    dest = _build_destination(tmp_path)
    base = dest / "base"
    # Synthesize a target outside the destination entirely
    outside_dest = tmp_path / "outside"
    outside_dest.mkdir()
    outside_target = outside_dest / "target.md"
    outside_target.write_text("evil")
    link = dest / "plugins" / "x" / "evil"
    link.parent.mkdir(parents=True)
    with pytest.raises(SystemExit) as exc_info:
        _symlink_if_changed(link, outside_target, base, dest, dry_run=False)
    assert exc_info.value.code == 5


def test_symlink_idempotent_when_target_unchanged(tmp_path: Path):
    dest = _build_destination(tmp_path)
    base = dest / "base"
    target = base / "skills" / "engineering" / "code-review"
    link = dest / "plugins" / "engineering" / "skills" / "code-review"
    link.parent.mkdir(parents=True)
    _symlink_if_changed(link, target, base, dest, dry_run=False)
    # Second call should be a no-op
    changed = _symlink_if_changed(link, target, base, dest, dry_run=False)
    assert not changed


def test_within_helper(tmp_path: Path):
    from marketplace_emitter import _within as fn

    parent = tmp_path / "p"
    parent.mkdir()
    child = parent / "child"
    child.mkdir()
    assert fn(child, parent)
    assert fn(parent, parent)
    other = tmp_path / "other"
    other.mkdir()
    assert not fn(other, parent)


# ---------------------------------------------------------------------------
# End-to-end emit
# ---------------------------------------------------------------------------


def test_emit_writes_all_catalogs(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    rc = emit(config)
    assert rc == 0
    assert (dest / ".claude-plugin" / "marketplace.json").is_file()
    assert (dest / ".cursor-plugin" / "marketplace.json").is_file()
    assert (dest / ".agents" / "plugins" / "marketplace.json").is_file()
    assert (dest / "gemini-extension.json").is_file()


def test_emit_writes_per_plugin_manifests(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    assert emit(config) == 0
    for profile_name in ("engineering", "qa", "meta"):
        plugin_dir = dest / "plugins" / profile_name
        assert (plugin_dir / ".claude-plugin" / "plugin.json").is_file()
        assert (plugin_dir / ".cursor-plugin" / "plugin.json").is_file()
        assert (plugin_dir / ".codex-plugin" / "plugin.json").is_file()
        assert (plugin_dir / "README.md").is_file()


def test_emit_creates_symlinks_into_base(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    assert emit(config) == 0
    # engineering profile includes engineering/code-review; we preserve
    # the <category>/<slug> namespace under plugins/<profile>/skills/ so
    # two skills with the same final-segment name don't collide.
    link = dest / "plugins" / "engineering" / "skills" / "engineering" / "code-review"
    assert link.is_symlink()
    # Symlink target resolves into base/skills/
    resolved = link.resolve()
    assert (dest / "base" / "skills").resolve() in resolved.parents


def test_emit_skill_namespace_avoids_collision(tmp_path: Path):
    """Two skills with the same final segment but different categories must
    not collide on the same symlink path. Regression for the original flat
    naming bug (Path(skill_ref).name dropped the category prefix)."""
    dest = _build_destination(tmp_path)
    # Add two skills with the same final segment name in different categories
    (dest / "base" / "skills" / "engineering" / "overlap").mkdir(parents=True)
    (dest / "base" / "skills" / "engineering" / "overlap" / "SKILL.md").write_text(
        "---\nname: overlap-eng\ndescription: From engineering\n---\n"
    )
    (dest / "base" / "skills" / "productivity" / "overlap").mkdir(parents=True)
    (dest / "base" / "skills" / "productivity" / "overlap" / "SKILL.md").write_text(
        "---\nname: overlap-prod\ndescription: From productivity\n---\n"
    )
    # Profile that references both
    (dest / "profiles" / "engineering.toml").write_text(
        """
name = "engineering"
description = "test"

[skills]
include = ["engineering/overlap", "productivity/overlap"]
"""
    )
    config = _config(dest)
    assert emit(config) == 0
    # Both should land at distinct paths
    eng_link = (
        dest / "plugins" / "engineering" / "skills" / "engineering" / "overlap"
    )
    prod_link = (
        dest / "plugins" / "engineering" / "skills" / "productivity" / "overlap"
    )
    assert eng_link.is_symlink()
    assert prod_link.is_symlink()
    # Targets resolve to different SKILL.md files
    assert (eng_link.resolve() / "SKILL.md").read_text().startswith("---\nname: overlap-eng")
    assert (prod_link.resolve() / "SKILL.md").read_text().startswith("---\nname: overlap-prod")


def test_emit_is_idempotent_second_run(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    assert emit(config) == 0
    # Read the catalog content
    catalog_path = dest / ".claude-plugin" / "marketplace.json"
    first = catalog_path.read_text()
    first_mtime = catalog_path.stat().st_mtime
    # Re-emit should be no-op
    assert emit(config) == 0
    second = catalog_path.read_text()
    second_mtime = catalog_path.stat().st_mtime
    assert first == second
    assert first_mtime == second_mtime, (
        "idempotent re-emit should not rewrite unchanged file"
    )


def test_emit_dry_run_writes_nothing(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest, dry_run=True)
    assert emit(config) == 0
    assert not (dest / ".claude-plugin" / "marketplace.json").exists()
    assert not (dest / "gemini-extension.json").exists()


def test_emit_fails_when_destination_missing_base(tmp_path: Path):
    dest = tmp_path / "empty-dest"
    dest.mkdir()
    (dest / "profiles").mkdir()
    config = _config(dest)
    assert emit(config) == 1


def test_emit_fails_when_marketplace_name_reserved(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest, marketplace_name="claude-plugins-official")
    rc = emit(config)
    assert rc == 5


def test_emit_warns_and_prunes_when_profile_references_missing_skill(
    tmp_path: Path, capsys
):
    """Missing references warn + prune (not fail) because scrubbed profile
    TOMLs at the destination often reference renamed-but-not-existent slugs.
    """
    dest = _build_destination(tmp_path)
    # Profile with one valid skill + one missing skill
    (dest / "profiles" / "engineering.toml").write_text(
        """
name = "engineering"
description = "partial"

[skills]
include = ["engineering/code-review", "engineering/does-not-exist"]
"""
    )
    config = _config(dest)
    rc = emit(config)
    assert rc == 0  # warning, not fatal
    captured = capsys.readouterr()
    assert "does-not-exist" in captured.err
    # Plugin manifest still emitted; symlink for the valid skill exists
    # at its category/slug path; symlink for the missing one does NOT.
    plugin_dir = dest / "plugins" / "engineering"
    assert (plugin_dir / "skills" / "engineering" / "code-review").is_symlink()
    assert not (plugin_dir / "skills" / "engineering" / "does-not-exist").exists()


def test_emit_succeeds_when_only_some_references_resolve(tmp_path: Path):
    """Profile with one missing rule still emits the rest of its content."""
    dest = _build_destination(tmp_path)
    (dest / "profiles" / "engineering.toml").write_text(
        """
name = "engineering"
description = "partial"

[skills]
include = ["engineering/code-review"]

[rules]
include = ["no-em-dashes", "scrubbed-into-oblivion"]
"""
    )
    config = _config(dest)
    rc = emit(config)
    assert rc == 0
    # The one valid rule symlink exists; the missing one is absent
    plugin_dir = dest / "plugins" / "engineering"
    assert (plugin_dir / "rules" / "no-em-dashes.md").is_symlink()
    assert not (plugin_dir / "rules" / "scrubbed-into-oblivion.md").exists()


def test_emit_records_owner_email_optional(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest, owner_email=None)
    assert emit(config) == 0
    catalog = json.loads((dest / ".claude-plugin" / "marketplace.json").read_text())
    assert "email" not in catalog["owner"]


def test_emit_readme_lists_profile_contents(tmp_path: Path):
    dest = _build_destination(tmp_path)
    config = _config(dest)
    assert emit(config) == 0
    readme = (dest / "plugins" / "engineering" / "README.md").read_text()
    assert "engineering/code-review" in readme
    assert "no-em-dashes" in readme
    assert "/plugin install engineering@8v-coding-agents-playbook" in readme


# ---------------------------------------------------------------------------
# _write_if_changed semantic check
# ---------------------------------------------------------------------------


def test_write_if_changed_returns_false_on_identical(tmp_path: Path):
    path = tmp_path / "x.json"
    path.write_text("hello\n")
    assert not _write_if_changed(path, "hello\n", dry_run=False)


def test_write_if_changed_returns_true_on_diff(tmp_path: Path):
    path = tmp_path / "x.json"
    path.write_text("hello\n")
    assert _write_if_changed(path, "world\n", dry_run=False)
    assert path.read_text() == "world\n"


def test_write_if_changed_dry_run_does_not_write(tmp_path: Path):
    path = tmp_path / "x.json"
    assert _write_if_changed(path, "new\n", dry_run=True)
    assert not path.exists()
