"""Contract tests for scripts/marketplace/ (ADR-0043).

Suite layout:
    TestErrors                  exit-code mapping for the EmitError hierarchy.
    TestTypes                   RoleProfile / MetaProfile / EmitterConfig /
                                ComponentSpec / specs_for shape contracts.
    TestProfileLoader           slug validation, reserved-name rejection,
                                TOML parsing, meta profile aggregation.
    TestContentOps              _is_stale_path 5-branch table, _within,
                                _plugin_rel_for layout resolver,
                                _resolve_profile flat vs bundle MCP,
                                _materialize idempotency + path safety,
                                _remove_stale_plugin_content.
    TestHookAggregator          WARN on unreadable / missing header,
                                valid hook output, empty cleanup.
    TestMcpAggregator           WARN on unparseable / non-dict,
                                aggregation + dedup, empty cleanup.
    TestSharedHelpers           default description + plugin README.
    TestClaudeBuilders          plugin.json + marketplace.json shape,
                                bare-string source regression-guard,
                                author/catalog identity split,
                                multi-profile no overwrite.
    TestCursorBuilders          passthrough identity to Claude.
    TestCodexBuilders           plugin.json has NO policy, marketplace has
                                policy.installation + category +
                                interface.displayName.
    TestGeminiBuilders          NO author, mcpServers populated,
                                MCP WARN on unparseable JSON.
    TestEmitterOrchestrator     end-to-end emit() per platform,
                                idempotency, dry-run, stale cleanup,
                                EmitError exit-code propagation,
                                multi-profile guard.

Run: pytest tests/lifecycle/test_marketplace_package.py -v
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from marketplace import (
    EmitError,
    EmitterConfig,
    MaterializationError,
    MetaProfile,
    PathSafetyError,
    ProfileLoadError,
    ReservedNameError,
    RoleProfile,
    SlugValidationError,
    emit,
    main,
)
from marketplace.content_ops import (
    ResolvedRef,
    _expected_paths,
    _is_stale_path,
    _materialize,
    _plugin_rel_for,
    _refs_for_spec,
    _remove_stale_plugin_content,
    _resolve_profile,
    _resolve_source,
    _within,
)
from marketplace.emitter import (
    _MARKETPLACE_WRITES,
    _PLUGIN_MANIFEST_WRITES,
    _emit_marketplace_manifests,
    _emit_plugin_directory,
    _write_if_changed,
)
from marketplace.hook_aggregator import _build_hooks_json
from marketplace.manifests._shared import (
    _default_marketplace_description,
    _plugin_readme,
)
from marketplace.manifests.claude import (
    _claude_marketplace_manifest,
    _claude_plugin_entry,
    _claude_plugin_manifest,
)
from marketplace.manifests.codex import (
    _CODEX_AUTH,
    _CODEX_INSTALLATION,
    _codex_marketplace_manifest,
    _codex_plugin_entry,
    _codex_plugin_manifest,
    _is_valid_codex_auth,
    _is_valid_codex_installation,
)
from marketplace.manifests.cursor import (
    _cursor_marketplace_manifest,
    _cursor_plugin_manifest,
)
from marketplace.manifests.gemini import _gemini_extension_manifest, _mcp_servers_block
from marketplace.mcp_aggregator import _build_mcp_json
from marketplace.profile_loader import (
    RESERVED_MARKETPLACE_NAMES,
    _build_meta_profile,
    _load_profile,
    _load_profiles,
    _validate_marketplace_name,
    _validate_slug,
)
from marketplace.types import (
    COMPONENT_SPECS,
    ComponentSpec,
    specs_for,
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


class TestErrors:
    def test_emit_error_default_exit_code(self):
        assert EmitError.exit_code == 1

    def test_profile_load_error_exit_code_1(self):
        assert ProfileLoadError.exit_code == 1

    def test_slug_validation_error_exit_code_5(self):
        assert SlugValidationError.exit_code == 5

    def test_reserved_name_error_exit_code_5(self):
        assert ReservedNameError.exit_code == 5

    def test_materialization_error_exit_code_5(self):
        assert MaterializationError.exit_code == 5

    def test_path_safety_error_exit_code_5(self):
        assert PathSafetyError.exit_code == 5

    def test_all_subclass_emit_error(self):
        for cls in (
            ProfileLoadError,
            SlugValidationError,
            ReservedNameError,
            MaterializationError,
            PathSafetyError,
        ):
            assert issubclass(cls, EmitError)


# ===================================================================
# Types
# ===================================================================


class TestTypes:
    def test_role_profile_is_frozen(self):
        p = _make_role_profile()
        with pytest.raises(FrozenInstanceError):
            p.name = "other"  # type: ignore[misc]

    def test_meta_profile_is_frozen(self):
        members = (_make_role_profile(),)
        m = MetaProfile(
            name="_all",
            catalog_name="rhnfzl",
            description="agg",
            members=members,
        )
        with pytest.raises(FrozenInstanceError):
            m.name = "other"  # type: ignore[misc]

    def test_emitter_config_is_frozen(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        with pytest.raises(FrozenInstanceError):
            cfg.author_name = "Other"  # type: ignore[misc]

    def test_version_for_profile_override_wins(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest", default_profile_version="0.9.0")
        p = _make_role_profile(version="0.5.0")
        assert cfg.version_for(p) == "0.5.0"

    def test_version_for_default_beats_tool_version(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest", default_profile_version="0.9.0")
        p = _make_role_profile()
        assert cfg.version_for(p) == "0.9.0"

    def test_version_for_falls_back_to_tool_version(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        assert cfg.version_for(p) == "0.11.0"

    def test_author_block_without_email(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest", author_name="Rehan Fazal")
        assert cfg.author_block() == {"name": "Rehan Fazal"}

    def test_author_block_with_email(self, tmp_path):
        cfg = _make_config(
            tmp_path,
            tmp_path / "dest",
            author_name="Rehan Fazal",
            author_email="rehan@example.com",
        )
        assert cfg.author_block() == {
            "name": "Rehan Fazal",
            "email": "rehan@example.com",
        }

    def test_author_block_returns_fresh_dict(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        a, b = cfg.author_block(), cfg.author_block()
        assert a == b
        a["mutated"] = "yes"
        assert "mutated" not in cfg.author_block()

    def test_component_specs_count(self):
        # skills, rules, hooks, mcp, agents, commands, prompts
        assert len(COMPONENT_SPECS) == 7

    def test_component_specs_unique_kinds(self):
        kinds = [s.kind for s in COMPONENT_SPECS]
        assert len(kinds) == len(set(kinds))

    def test_specs_for_role_profile_filters_populated(self):
        p = _make_role_profile(skills=("a",), rules=())
        kinds = {s.kind for s in specs_for(p)}
        assert kinds == {"skills"}

    def test_specs_for_meta_profile_unions_members(self):
        a = _make_role_profile(name="a", skills=("a-skill",))
        b = _make_role_profile(name="b", rules=("b-rule",))
        m = MetaProfile(
            name="_all", catalog_name="rhnfzl", description="agg", members=(a, b)
        )
        kinds = {s.kind for s in specs_for(m)}
        assert kinds == {"skills", "rules"}


# ===================================================================
# Profile loader
# ===================================================================


class TestProfileLoader:
    def test_reserved_names_includes_anthropic_canonical(self):
        for entry in (
            "claude-code-marketplace",
            "claude-code-plugins",
            "claude-plugins-official",
            "anthropic-marketplace",
            "anthropic-plugins",
            "agent-skills",
            "anthropic-agent-skills",
            "knowledge-work-plugins",
            "life-sciences",
        ):
            assert entry in RESERVED_MARKETPLACE_NAMES

    def test_reserved_names_includes_recent_additions(self):
        for entry in (
            "claude-for-legal",
            "claude-for-financial-services",
            "financial-services-plugins",
        ):
            assert entry in RESERVED_MARKETPLACE_NAMES

    def test_validate_slug_accepts_kebab(self):
        _validate_slug("backend-developer", kind="profile")

    def test_validate_slug_rejects_uppercase(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("BackendDev", kind="profile")

    def test_validate_slug_rejects_starting_digit(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("1stbase", kind="profile")

    def test_validate_slug_rejects_trailing_hyphen(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("backend-", kind="profile")

    def test_validate_slug_rejects_underscore(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("backend_dev", kind="profile")

    def test_validate_slug_rejects_too_short(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("a", kind="profile")

    def test_validate_slug_rejects_too_long(self):
        with pytest.raises(SlugValidationError):
            _validate_slug("a" + "b" * 99, kind="profile")

    def test_validate_marketplace_name_accepts_personal_handle(self):
        _validate_marketplace_name("rhnfzl")

    def test_validate_marketplace_name_rejects_reserved_canonical(self):
        with pytest.raises(ReservedNameError, match="reserved by Anthropic"):
            _validate_marketplace_name("anthropic-plugins")

    def test_validate_marketplace_name_rejects_official_token(self):
        with pytest.raises(ReservedNameError, match="reserved token"):
            _validate_marketplace_name("my-official-tools")

    def test_validate_marketplace_name_rejects_anthropic_token(self):
        with pytest.raises(ReservedNameError, match="reserved token"):
            _validate_marketplace_name("my-anthropic-tools")

    def test_validate_marketplace_name_rejects_claude_token(self):
        with pytest.raises(ReservedNameError, match="reserved token"):
            _validate_marketplace_name("my-claude-tools")

    def test_load_profile_minimal(self, tmp_path):
        path = _seed_profile_toml(
            tmp_path, "backend-developer", 'description = "Backend"\n'
        )
        p = _load_profile(path, catalog_name="rhnfzl")
        assert p.name == "backend-developer"
        assert p.catalog_name == "rhnfzl"
        assert p.description == "Backend"

    def test_load_profile_includes_sections(self, tmp_path):
        path = _seed_profile_toml(
            tmp_path,
            "backend-developer",
            'description = ""\n[skills]\ninclude = ["a", "b"]\n[rules]\ninclude = ["r"]\n',
        )
        p = _load_profile(path, catalog_name="rhnfzl")
        assert p.skills == ("a", "b")
        assert p.rules == ("r",)

    def test_load_profile_missing_file_raises(self, tmp_path):
        with pytest.raises(ProfileLoadError):
            _load_profile(tmp_path / "missing.toml", catalog_name="rhnfzl")

    def test_load_profile_bad_toml_raises(self, tmp_path):
        path = _seed_profile_toml(tmp_path, "broken", "not = valid = toml")
        with pytest.raises(ProfileLoadError):
            _load_profile(path, catalog_name="rhnfzl")

    def test_build_meta_profile_empty_members_raises(self):
        with pytest.raises(ProfileLoadError):
            _build_meta_profile((), catalog_name="rhnfzl")

    def test_build_meta_profile_aggregates(self):
        a = _make_role_profile(name="a")
        b = _make_role_profile(name="b")
        m = _build_meta_profile((a, b), catalog_name="rhnfzl")
        assert m.name == "_all"
        assert m.members == (a, b)

    def test_load_profiles_missing_dir_raises(self, tmp_path):
        with pytest.raises(ProfileLoadError):
            _load_profiles(tmp_path / "missing", catalog_name="rhnfzl")

    def test_load_profiles_empty_dir_raises(self, tmp_path):
        (tmp_path / "profiles").mkdir()
        with pytest.raises(ProfileLoadError):
            _load_profiles(tmp_path / "profiles", catalog_name="rhnfzl")

    def test_load_profiles_returns_role_plus_meta(self, tmp_path):
        pdir = tmp_path / "profiles"
        _seed_profile_toml(pdir, "alpha", 'description = "A"\n')
        _seed_profile_toml(pdir, "beta", 'description = "B"\n')
        profiles = _load_profiles(pdir, catalog_name="rhnfzl")
        names = [p.name for p in profiles]
        assert names == ["alpha", "beta", "_all"]

    def test_load_profiles_validates_catalog_name(self, tmp_path):
        pdir = tmp_path / "profiles"
        _seed_profile_toml(pdir, "alpha", 'description = "A"\n')
        with pytest.raises(ReservedNameError):
            _load_profiles(pdir, catalog_name="anthropic-plugins")


# ===================================================================
# Content ops
# ===================================================================


class TestIsStalePath:
    def test_path_in_expected_is_not_stale(self, tmp_path):
        p = tmp_path / "a"
        assert not _is_stale_path(p, {p})

    def test_child_of_expected_is_not_stale(self, tmp_path):
        p = tmp_path / "a"
        child = tmp_path / "a" / "b"
        assert not _is_stale_path(child, {p})

    def test_ancestor_of_expected_is_not_stale(self, tmp_path):
        p = tmp_path / "a"
        ancestor = tmp_path
        assert not _is_stale_path(ancestor, {p})

    def test_unrelated_is_stale(self, tmp_path):
        p = tmp_path / "a"
        unrelated = tmp_path / "b"
        assert _is_stale_path(unrelated, {p})

    def test_empty_expected_is_stale(self, tmp_path):
        p = tmp_path / "a"
        assert _is_stale_path(p, set())


class TestWithin:
    def test_inside_base_is_within(self, tmp_path):
        target = tmp_path / "sub" / "leaf"
        target.parent.mkdir()
        target.write_text("x")
        assert _within(target, tmp_path)

    def test_outside_base_is_not_within(self, tmp_path):
        target = tmp_path.parent
        assert not _within(target, tmp_path)


class TestPluginRelFor:
    def test_non_mcp_uses_simple_join(self, tmp_path):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        rel = _plugin_rel_for(spec, "foo", tmp_path / "foo")
        assert rel == Path("skills/foo")

    def test_mcp_flat_layout(self, tmp_path):
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        f = tmp_path / "tavily.json"
        f.write_text("{}")
        rel = _plugin_rel_for(spec, "tavily", f)
        assert rel == Path("mcp/tavily.json")

    def test_mcp_bundle_layout(self, tmp_path):
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        d = tmp_path / "anchored-fs"
        d.mkdir()
        rel = _plugin_rel_for(spec, "anchored-fs", d)
        assert rel == Path("mcp/anchored-fs")

    def test_hook_file_keeps_sh_extension(self, tmp_path):
        spec = ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks")
        f = tmp_path / "lint-guard.sh"
        f.write_text("#")
        rel = _plugin_rel_for(spec, "lint-guard", f)
        assert rel == Path("hooks/lint-guard.sh")

    def test_rule_file_keeps_md_extension(self, tmp_path):
        spec = ComponentSpec("rules", Path("base/rules"), "rules", "rules")
        f = tmp_path / "no-em-dashes.md"
        f.write_text("#")
        rel = _plugin_rel_for(spec, "no-em-dashes", f)
        assert rel == Path("rules/no-em-dashes.md")


class TestRefsForSpec:
    def test_role_profile_passthrough(self):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        p = _make_role_profile(skills=("a", "b"))
        assert _refs_for_spec(p, spec) == ("a", "b")

    def test_meta_profile_dedupes(self):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        a = _make_role_profile(name="a", skills=("shared", "a-only"))
        b = _make_role_profile(name="b", skills=("shared", "b-only"))
        m = MetaProfile(
            name="_all", catalog_name="rhnfzl", description="agg", members=(a, b)
        )
        refs = _refs_for_spec(m, spec)
        assert sorted(refs) == ["a-only", "b-only", "shared"]


class TestResolveProfile:
    def test_missing_ref_produces_warning(self, tmp_path):
        _seed_base_dirs(tmp_path)
        p = _make_role_profile(skills=("missing",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert resolved == ()
        assert any("missing" in w for w in warnings)

    def test_present_ref_resolves(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "base" / "skills" / "alpha").mkdir(parents=True)
        p = _make_role_profile(skills=("alpha",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        assert len(resolved) == 1
        assert resolved[0].ref == "alpha"

    def test_mcp_flat_resolves_with_json_suffix(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "base" / "mcp" / "tavily.json").write_text("{}", encoding="utf-8")
        p = _make_role_profile(mcp=("tavily",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        assert len(resolved) == 1
        assert resolved[0].plugin_rel == Path("mcp/tavily.json")

    def test_mcp_bundle_resolves(self, tmp_path):
        _seed_base_dirs(tmp_path)
        d = tmp_path / "base" / "mcp" / "anchored-fs"
        d.mkdir()
        (d / "server.json").write_text("{}", encoding="utf-8")
        p = _make_role_profile(mcp=("anchored-fs",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        assert resolved[0].plugin_rel == Path("mcp/anchored-fs")


class TestBareStemResolution:
    """Profiles reference content by BARE STEM; the file on disk carries the
    extension the canonical loader globs for. Regression guard for the bug
    where every hook + rule + agent + command + prompt ref was dropped
    because the resolver did a literal path check with no suffix fallback.
    """

    def test_hook_bare_stem_resolves_to_sh(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "base" / "hooks" / "lint-guard.sh").write_text(
            "# PLAYBOOK-HOOK-EVENT: PreToolUse\n", encoding="utf-8"
        )
        p = _make_role_profile(hooks=("lint-guard",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        assert len(resolved) == 1
        assert resolved[0].ref == "lint-guard"
        assert resolved[0].source.name == "lint-guard.sh"
        assert resolved[0].plugin_rel == Path("hooks/lint-guard.sh")

    def test_rule_bare_stem_resolves_to_md(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "base" / "rules" / "no-em-dashes.md").write_text(
            "rule body", encoding="utf-8"
        )
        p = _make_role_profile(rules=("no-em-dashes",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        assert resolved[0].plugin_rel == Path("rules/no-em-dashes.md")

    def test_agent_command_prompt_bare_stem_resolve_to_md(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "base" / "agents" / "scout.md").write_text("a", encoding="utf-8")
        (tmp_path / "base" / "commands" / "ship.md").write_text("c", encoding="utf-8")
        (tmp_path / "base" / "prompts" / "kickoff.md").write_text("p", encoding="utf-8")
        p = _make_role_profile(
            agents=("scout",), commands=("ship",), prompts=("kickoff",)
        )
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        rels = {r.plugin_rel for r in resolved}
        assert Path("agents/scout.md") in rels
        assert Path("commands/ship.md") in rels
        assert Path("prompts/kickoff.md") in rels

    def test_skill_dir_ref_needs_no_suffix(self, tmp_path):
        _seed_base_dirs(tmp_path)
        skill_dir = tmp_path / "base" / "skills" / "engineering" / "ci-failure-triage"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill", encoding="utf-8")
        p = _make_role_profile(skills=("engineering/ci-failure-triage",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert warnings == ()
        # Category prefix survives in the plugin destination.
        assert resolved[0].plugin_rel == Path("skills/engineering/ci-failure-triage")

    def test_resolve_source_returns_none_when_truly_absent(self, tmp_path):
        _seed_base_dirs(tmp_path)
        spec = ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks")
        assert _resolve_source(spec, "does-not-exist", tmp_path) is None

    def test_bare_path_wins_over_suffix_fallback(self, tmp_path):
        # If a bare ref exists as-is (e.g. an extensionless file), it is
        # preferred over the suffixed fallback.
        _seed_base_dirs(tmp_path)
        spec = ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks")
        (tmp_path / "base" / "hooks" / "exact").write_text("bare", encoding="utf-8")
        (tmp_path / "base" / "hooks" / "exact.sh").write_text("sh", encoding="utf-8")
        resolved = _resolve_source(spec, "exact", tmp_path)
        assert resolved is not None
        assert resolved.name == "exact"


class TestMaterialize:
    def test_dry_run_writes_nothing(self, tmp_path):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        src = tmp_path / "source"
        src.mkdir()
        (src / "SKILL.md").write_text("hi")
        plugin_dir = tmp_path / "plugin"
        ref = ResolvedRef(
            spec=spec, ref="alpha", source=src, plugin_rel=Path("skills/alpha")
        )
        count = _materialize((ref,), plugin_dir, dry_run=True)
        assert count == 0
        assert not (plugin_dir / "skills" / "alpha").exists()

    def test_copies_directory_recursively(self, tmp_path):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        src = tmp_path / "source"
        (src / "nested").mkdir(parents=True)
        (src / "SKILL.md").write_text("hi")
        (src / "nested" / "ref.md").write_text("there")
        plugin_dir = tmp_path / "plugin"
        ref = ResolvedRef(
            spec=spec, ref="alpha", source=src, plugin_rel=Path("skills/alpha")
        )
        count = _materialize((ref,), plugin_dir, dry_run=False)
        assert count == 1
        assert (plugin_dir / "skills" / "alpha" / "SKILL.md").read_text() == "hi"
        assert (
            plugin_dir / "skills" / "alpha" / "nested" / "ref.md"
        ).read_text() == "there"

    def test_copies_file(self, tmp_path):
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        src = tmp_path / "tavily.json"
        src.write_text("{}")
        plugin_dir = tmp_path / "plugin"
        ref = ResolvedRef(
            spec=spec, ref="tavily", source=src, plugin_rel=Path("mcp/tavily.json")
        )
        count = _materialize((ref,), plugin_dir, dry_run=False)
        assert count == 1
        assert (plugin_dir / "mcp" / "tavily.json").read_text() == "{}"

    def test_path_safety_blocks_traversal(self, tmp_path):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        src = tmp_path / "source"
        src.mkdir()
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        bad_ref = ResolvedRef(
            spec=spec,
            ref="alpha",
            source=src,
            plugin_rel=Path("../escape"),
        )
        with pytest.raises(PathSafetyError):
            _materialize((bad_ref,), plugin_dir, dry_run=False)


class TestExpectedPaths:
    def test_expected_paths_builds_set(self, tmp_path):
        spec = ComponentSpec("skills", Path("base/skills"), "skills", "skills")
        r1 = ResolvedRef(
            spec=spec, ref="a", source=tmp_path, plugin_rel=Path("skills/a")
        )
        r2 = ResolvedRef(
            spec=spec, ref="b", source=tmp_path, plugin_rel=Path("skills/b")
        )
        s = _expected_paths((r1, r2), tmp_path / "plugin")
        assert s == {
            tmp_path / "plugin" / "skills" / "a",
            tmp_path / "plugin" / "skills" / "b",
        }


class TestRemoveStalePluginContent:
    def test_leaves_expected_paths_alone(self, tmp_path):
        plugin = tmp_path / "plugin"
        keeper = plugin / "skills" / "alpha"
        keeper.mkdir(parents=True)
        (keeper / "SKILL.md").write_text("x")
        expected = {keeper}
        _remove_stale_plugin_content(plugin, expected, dry_run=False)
        assert keeper.exists()

    def test_removes_unrelated_path(self, tmp_path):
        plugin = tmp_path / "plugin"
        plugin.mkdir()
        stale = plugin / "old"
        stale.mkdir()
        (stale / "thing.md").write_text("stale")
        _remove_stale_plugin_content(plugin, set(), dry_run=False)
        assert not stale.exists()

    def test_preserves_protected_manifests(self, tmp_path):
        plugin = tmp_path / "plugin"
        plugin.mkdir()
        protected = plugin / "plugin.json"
        protected.write_text("{}")
        _remove_stale_plugin_content(plugin, set(), dry_run=False)
        assert protected.exists()


# ===================================================================
# Hook aggregator
# ===================================================================


class TestHookAggregator:
    def _seed_hook(self, repo_root: Path, name: str, body: str) -> ResolvedRef:
        spec = ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks")
        src = repo_root / "base" / "hooks" / name
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(body, encoding="utf-8")
        return ResolvedRef(
            spec=spec, ref=name, source=src, plugin_rel=Path(f"hooks/{name}")
        )

    def test_missing_event_header_warns(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_hook(tmp_path, "bad.sh", "#!/bin/sh\necho no header here\n")
        p = _make_role_profile(hooks=("bad.sh",))
        _build_hooks_json(p, (ref,), cfg, tmp_path / "dest" / p.name)
        err = capsys.readouterr().err
        assert "no PLAYBOOK-HOOK-EVENT header" in err
        assert "bad.sh" in err
        assert p.name in err

    def test_unreadable_file_warns(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_hook(tmp_path, "vanish.sh", "# placeholder")
        ref.source.unlink()
        p = _make_role_profile(hooks=("vanish.sh",))
        _build_hooks_json(p, (ref,), cfg, tmp_path / "dest" / p.name)
        err = capsys.readouterr().err
        assert "unreadable" in err
        assert "vanish.sh" in err

    def test_valid_hook_produces_payload(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        body = "# PLAYBOOK-HOOK-EVENT: PreToolUse\n# PLAYBOOK-HOOK-MATCHER: Bash\necho hi\n"
        ref = self._seed_hook(tmp_path, "ok.sh", body)
        p = _make_role_profile(hooks=("ok.sh",))
        plugin_dir = tmp_path / "dest" / p.name
        written = _build_hooks_json(p, (ref,), cfg, plugin_dir)
        assert written == 1
        assert capsys.readouterr().err == ""
        data = json.loads((plugin_dir / "hooks" / "hooks.json").read_text())
        assert "PreToolUse" in data["hooks"]
        assert data["hooks"]["PreToolUse"][0]["matcher"] == "Bash"

    def test_no_hooks_removes_stale_file(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        plugin_dir = tmp_path / "dest" / "backend-developer"
        (plugin_dir / "hooks").mkdir(parents=True)
        (plugin_dir / "hooks" / "hooks.json").write_text("{}")
        p = _make_role_profile()
        _build_hooks_json(p, (), cfg, plugin_dir)
        assert not (plugin_dir / "hooks" / "hooks.json").exists()


# ===================================================================
# MCP aggregator
# ===================================================================


class TestMcpAggregator:
    def _seed_mcp(self, repo_root: Path, ref: str, body: str) -> ResolvedRef:
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        src = repo_root / "base" / "mcp" / f"{ref}.json"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(body, encoding="utf-8")
        return ResolvedRef(
            spec=spec, ref=ref, source=src, plugin_rel=Path(f"mcp/{ref}.json")
        )

    def _seed_mcp_bundle(self, repo_root: Path, ref: str, body: str) -> ResolvedRef:
        """Bundle layout: source is a DIRECTORY whose config is server.json."""
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        bundle = repo_root / "base" / "mcp" / ref
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "server.json").write_text(body, encoding="utf-8")
        return ResolvedRef(
            spec=spec, ref=ref, source=bundle, plugin_rel=Path(f"mcp/{ref}")
        )

    def test_unparseable_warns(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_mcp(tmp_path, "broken", "not valid json")
        p = _make_role_profile(mcp=("broken",))
        _build_mcp_json(p, (ref,), cfg, tmp_path / "dest" / p.name)
        err = capsys.readouterr().err
        assert "unparseable" in err
        assert "broken" in err

    def test_non_dict_warns(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_mcp(tmp_path, "asarr", "[1, 2, 3]")
        p = _make_role_profile(mcp=("asarr",))
        _build_mcp_json(p, (ref,), cfg, tmp_path / "dest" / p.name)
        err = capsys.readouterr().err
        assert "must be a top-level JSON object" in err

    def test_aggregates_servers(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_mcp(tmp_path, "ok", json.dumps({"alpha": {"command": "node"}}))
        p = _make_role_profile(mcp=("ok",))
        plugin_dir = tmp_path / "dest" / p.name
        _build_mcp_json(p, (ref,), cfg, plugin_dir)
        data = json.loads((plugin_dir / ".mcp.json").read_text())
        assert "alpha" in data["mcpServers"]

    def test_bundle_layout_reads_server_json(self, tmp_path):
        """Regression: when the MCP source is a directory (bundle layout),
        the aggregator reads `<source>/server.json`, not the directory
        itself. Guards the dir-branch added for parity with gemini."""
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_mcp_bundle(
            tmp_path, "anchored-fs", json.dumps({"anchored-fs": {"command": "node"}})
        )
        p = _make_role_profile(mcp=("anchored-fs",))
        plugin_dir = tmp_path / "dest" / p.name
        written = _build_mcp_json(p, (ref,), cfg, plugin_dir)
        assert written == 1
        data = json.loads((plugin_dir / ".mcp.json").read_text())
        assert "anchored-fs" in data["mcpServers"]

    def test_bundle_layout_missing_server_json_warns(self, tmp_path, capsys):
        """Bundle dir with no server.json -> WARN, no crash on the dir read."""
        cfg = _make_config(tmp_path, tmp_path / "dest")
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        bundle = tmp_path / "base" / "mcp" / "empty-bundle"
        bundle.mkdir(parents=True)
        ref = ResolvedRef(
            spec=spec,
            ref="empty-bundle",
            source=bundle,
            plugin_rel=Path("mcp/empty-bundle"),
        )
        p = _make_role_profile(mcp=("empty-bundle",))
        _build_mcp_json(p, (ref,), cfg, tmp_path / "dest" / p.name)
        err = capsys.readouterr().err
        assert "unparseable" in err
        assert "empty-bundle" in err

    def test_empty_set_removes_stale_file(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        plugin_dir = tmp_path / "dest" / "backend-developer"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / ".mcp.json").write_text("{}")
        p = _make_role_profile()
        _build_mcp_json(p, (), cfg, plugin_dir)
        assert not (plugin_dir / ".mcp.json").exists()

    def test_idempotent_no_rewrite(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        ref = self._seed_mcp(tmp_path, "ok", json.dumps({"alpha": {"command": "node"}}))
        p = _make_role_profile(mcp=("ok",))
        plugin_dir = tmp_path / "dest" / p.name
        _build_mcp_json(p, (ref,), cfg, plugin_dir)
        # Second run is no-op.
        assert _build_mcp_json(p, (ref,), cfg, plugin_dir) == 0

    def test_mixed_valid_and_invalid(self, tmp_path, capsys):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        good = self._seed_mcp(tmp_path, "good", json.dumps({"alpha": {"command": "x"}}))
        bad = self._seed_mcp(tmp_path, "bad", "[1,2,3]")
        p = _make_role_profile(mcp=("good", "bad"))
        plugin_dir = tmp_path / "dest" / p.name
        _build_mcp_json(p, (good, bad), cfg, plugin_dir)
        err = capsys.readouterr().err
        assert "bad" in err
        data = json.loads((plugin_dir / ".mcp.json").read_text())
        assert "alpha" in data["mcpServers"]

    def test_dedup_same_server_name(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        a = self._seed_mcp(tmp_path, "a", json.dumps({"shared": {"command": "first"}}))
        b = self._seed_mcp(tmp_path, "b", json.dumps({"shared": {"command": "second"}}))
        p = _make_role_profile(mcp=("a", "b"))
        plugin_dir = tmp_path / "dest" / p.name
        _build_mcp_json(p, (a, b), cfg, plugin_dir)
        data = json.loads((plugin_dir / ".mcp.json").read_text())
        # Last entry wins.
        assert data["mcpServers"]["shared"]["command"] == "second"


# ===================================================================
# Shared helpers
# ===================================================================


class TestSharedHelpers:
    def test_default_description_uses_profile_description_when_present(self):
        p = _make_role_profile(description="Backend")
        assert _default_marketplace_description(p) == "Backend"

    def test_default_description_falls_back_when_empty(self):
        p = _make_role_profile(description="")
        text = _default_marketplace_description(p)
        assert "rhnfzl" in text
        assert "backend-developer" in text

    def test_plugin_readme_contains_name_and_version(self):
        p = _make_role_profile(description="Backend")
        text = _plugin_readme(p, "1.2.3")
        assert "# backend-developer" in text
        assert "1.2.3" in text
        assert "rhnfzl" in text


# ===================================================================
# Claude builders
# ===================================================================


class TestClaudeBuilders:
    def test_plugin_manifest_shape(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _claude_plugin_manifest(p, cfg)
        assert set(m.keys()) == {"name", "version", "description", "author"}
        assert m["author"] == {"name": "Rehan Fazal"}

    def test_plugin_manifest_includes_email_when_set(self, tmp_path):
        cfg = _make_config(
            tmp_path, tmp_path / "dest", author_email="rehan@example.com"
        )
        p = _make_role_profile()
        m = _claude_plugin_manifest(p, cfg)
        assert m["author"]["email"] == "rehan@example.com"

    def test_marketplace_uses_bare_string_source(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        entry = _claude_plugin_entry(p, cfg, ())
        assert entry["source"] == "./backend-developer"
        assert not isinstance(entry["source"], dict)

    def test_marketplace_shape(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _claude_marketplace_manifest((p,), cfg, {p.name: ()}, "rhnfzl")
        assert m["name"] == "rhnfzl"
        assert m["owner"]["name"] == "Rehan Fazal"
        assert isinstance(m["plugins"], list)
        assert m["plugins"][0]["name"] == "backend-developer"

    def test_agents_omitted_when_empty(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        entry = _claude_plugin_entry(p, cfg, ())
        assert "agents" not in entry

    def test_agents_present_when_resolved(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        spec = ComponentSpec("agents", Path("base/agents"), "agents", "agents")
        f = tmp_path / "agent.md"
        f.write_text("body")
        resolved = (
            ResolvedRef(
                spec=spec, ref="agent.md", source=f, plugin_rel=Path("agents/agent.md")
            ),
        )
        p = _make_role_profile()
        entry = _claude_plugin_entry(p, cfg, resolved)
        assert "agents" in entry
        assert isinstance(entry["agents"], list)

    def test_multi_profile_no_overwrite(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        a = _make_role_profile(name="a")
        b = _make_role_profile(name="b")
        c = _make_role_profile(name="c")
        m = _claude_marketplace_manifest(
            (a, b, c), cfg, {"a": (), "b": (), "c": ()}, "rhnfzl"
        )
        names = [p["name"] for p in m["plugins"]]
        assert names == ["a", "b", "c"]

    def test_author_is_person_not_catalog(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest", author_name="Rehan Fazal")
        p = _make_role_profile(catalog_name="rhnfzl")
        plugin = _claude_plugin_manifest(p, cfg)
        marketplace = _claude_marketplace_manifest((p,), cfg, {p.name: ()}, "rhnfzl")
        assert plugin["author"]["name"] == "Rehan Fazal"
        assert marketplace["owner"]["name"] == "Rehan Fazal"
        assert plugin["author"]["name"] != p.catalog_name
        assert marketplace["name"] == "rhnfzl"


# ===================================================================
# Cursor builders
# ===================================================================


class TestCursorBuilders:
    def test_plugin_manifest_passthrough(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        assert _cursor_plugin_manifest(p, cfg) == _claude_plugin_manifest(p, cfg)

    def test_marketplace_passthrough(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        a = _cursor_marketplace_manifest((p,), cfg, {p.name: ()}, "rhnfzl")
        b = _claude_marketplace_manifest((p,), cfg, {p.name: ()}, "rhnfzl")
        assert a == b


# ===================================================================
# Codex builders
# ===================================================================


class TestCodexBuilders:
    def test_plugin_manifest_has_no_policy(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _codex_plugin_manifest(p, cfg)
        assert "policy" not in m
        assert m["author"]["name"] == "Rehan Fazal"

    def test_marketplace_has_interface_displayname_not_owner(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _codex_marketplace_manifest((p,), cfg, {p.name: ()}, "rhnfzl")
        assert "owner" not in m
        assert m["interface"]["displayName"] == "rhnfzl catalog"

    def test_marketplace_plugin_entry_includes_policy_installation(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        entry = _codex_plugin_entry(p, cfg)
        assert entry["policy"]["installation"] == "AVAILABLE"
        assert entry["policy"]["authentication"] == "ON_INSTALL"
        assert entry["category"] == "Productivity"

    def test_source_is_nested_object_with_local_discriminator(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        entry = _codex_plugin_entry(p, cfg)
        assert isinstance(entry["source"], dict)
        assert entry["source"]["source"] == "local"
        assert entry["source"]["path"] == "./backend-developer"

    def test_is_valid_codex_auth(self):
        assert _is_valid_codex_auth("ON_INSTALL")
        assert _is_valid_codex_auth("ON_USE")
        assert not _is_valid_codex_auth("NONE")
        assert not _is_valid_codex_auth("anything")

    def test_is_valid_codex_installation(self):
        for v in _CODEX_INSTALLATION:
            assert _is_valid_codex_installation(v)
        assert not _is_valid_codex_installation("UNKNOWN")

    def test_codex_auth_enum_matches_docs(self):
        assert set(_CODEX_AUTH) == {"ON_INSTALL", "ON_USE"}

    def test_codex_installation_enum_matches_docs(self):
        assert set(_CODEX_INSTALLATION) == {
            "AVAILABLE",
            "NOT_AVAILABLE",
            "INSTALLED_BY_DEFAULT",
        }

    def test_multi_profile_no_overwrite(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        a = _make_role_profile(name="a")
        b = _make_role_profile(name="b")
        m = _codex_marketplace_manifest((a, b), cfg, {"a": (), "b": ()}, "rhnfzl")
        names = [p["name"] for p in m["plugins"]]
        assert names == ["a", "b"]


# ===================================================================
# Gemini builders
# ===================================================================


class TestGeminiBuilders:
    def test_no_author_field(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _gemini_extension_manifest(p, cfg, ())
        assert "author" not in m

    def test_required_name_and_version(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _gemini_extension_manifest(p, cfg, ())
        assert m["name"] == "backend-developer"
        assert m["version"] == "0.11.0"

    def test_mcp_servers_absent_when_no_mcp_refs(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        p = _make_role_profile()
        m = _gemini_extension_manifest(p, cfg, ())
        assert "mcpServers" not in m

    def test_mcp_servers_populated_when_resolved(self, tmp_path):
        cfg = _make_config(tmp_path, tmp_path / "dest")
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        f = tmp_path / "tavily.json"
        f.write_text(json.dumps({"tavily": {"command": "node"}}))
        resolved = (
            ResolvedRef(
                spec=spec, ref="tavily", source=f, plugin_rel=Path("mcp/tavily.json")
            ),
        )
        p = _make_role_profile(mcp=("tavily",))
        m = _gemini_extension_manifest(p, cfg, resolved)
        assert "tavily" in m["mcpServers"]

    def test_mcp_warn_on_unparseable(self, tmp_path, capsys):
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        f = tmp_path / "broken.json"
        f.write_text("not valid")
        resolved = (
            ResolvedRef(
                spec=spec, ref="broken", source=f, plugin_rel=Path("mcp/broken.json")
            ),
        )
        p = _make_role_profile(mcp=("broken",))
        _mcp_servers_block(p, resolved)
        err = capsys.readouterr().err
        assert "unparseable" in err

    def test_mcp_block_keys_sorted(self, tmp_path):
        spec = ComponentSpec("mcp", Path("base/mcp"), "mcp_either", "mcp")
        f = tmp_path / "x.json"
        f.write_text(json.dumps({"zebra": {}, "alpha": {}}))
        resolved = (
            ResolvedRef(spec=spec, ref="x", source=f, plugin_rel=Path("mcp/x.json")),
        )
        p = _make_role_profile(mcp=("x",))
        servers = _mcp_servers_block(p, resolved)
        assert list(servers.keys()) == ["alpha", "zebra"]


# ===================================================================
# Emitter orchestrator
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


class TestEmitterOrchestrator:
    def _fixture(self, tmp_path: Path) -> _FakeProfileTOML:
        f = _FakeProfileTOML(tmp_path / "repo")
        f.add_skill("alpha")
        f.add_rule("rule-one.md")
        f.add_profile("backend", skills=["alpha"], rules=["rule-one.md"])
        return f

    def test_emit_creates_plugin_dir(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        assert (dest / "backend" / "skills" / "alpha" / "SKILL.md").exists()

    def test_emit_writes_claude_plugin_json(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads(
            (dest / "backend" / ".claude-plugin" / "plugin.json").read_text()
        )
        assert data["name"] == "backend"
        assert data["author"]["name"] == "Rehan Fazal"

    def test_emit_writes_codex_plugin_json_without_policy(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads(
            (dest / "backend" / ".codex-plugin" / "plugin.json").read_text()
        )
        assert "policy" not in data

    def test_emit_writes_gemini_extension_without_author(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads((dest / "backend" / "gemini-extension.json").read_text())
        assert "author" not in data

    def test_emit_writes_root_marketplaces(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        for rel in (
            ".claude-plugin/marketplace.json",
            ".cursor-plugin/marketplace.json",
            ".codex-plugin/marketplace.json",
        ):
            assert (dest / rel).exists(), rel

    def test_emit_claude_marketplace_uses_bare_string_source(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads((dest / ".claude-plugin" / "marketplace.json").read_text())
        # Find the role-profile entry (not the _all aggregate).
        sources = {p["name"]: p["source"] for p in data["plugins"]}
        assert sources["backend"] == "./backend"
        assert isinstance(sources["backend"], str)

    def test_emit_codex_marketplace_uses_object_source(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads((dest / ".codex-plugin" / "marketplace.json").read_text())
        sources = {p["name"]: p["source"] for p in data["plugins"]}
        assert sources["backend"] == {"source": "local", "path": "./backend"}

    def test_emit_multi_profile_no_overwrite(self, tmp_path):
        f = _FakeProfileTOML(tmp_path / "repo")
        f.add_skill("a")
        f.add_skill("b")
        f.add_profile("alpha", skills=["a"])
        f.add_profile("beta", skills=["b"])
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads((dest / ".claude-plugin" / "marketplace.json").read_text())
        names = sorted(p["name"] for p in data["plugins"])
        # Two role profiles plus the _all meta.
        assert names == ["_all", "alpha", "beta"]

    def test_emit_idempotent(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        first_run = emit(
            cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl"
        )
        assert first_run == 0  # second run writes nothing.

    def test_emit_dry_run_creates_nothing(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest, dry_run=True)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        assert not (dest / "backend").exists()

    def test_emit_sidecar_payload(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        sidecar = json.loads(
            (dest / "backend" / ".claude-plugin" / "emitted-by.json").read_text()
        )
        assert sidecar == {"tool": "marketplace", "version": "0.11.0"}

    def test_emit_per_plugin_readme(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        readme = (dest / "backend" / "README.md").read_text()
        assert "# backend" in readme
        assert "rhnfzl" in readme

    def test_emit_reserved_catalog_name_raises(self, tmp_path):
        f = self._fixture(tmp_path)
        cfg = _make_config(f.repo_root, tmp_path / "dest")
        with pytest.raises(ReservedNameError):
            emit(
                cfg,
                profiles_dir=f.repo_root / "profiles",
                catalog_name="anthropic-plugins",
            )

    def test_emit_invalid_catalog_slug_raises(self, tmp_path):
        f = self._fixture(tmp_path)
        cfg = _make_config(f.repo_root, tmp_path / "dest")
        with pytest.raises(SlugValidationError):
            emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="BadName")

    def test_stale_path_cleaned_on_reemit(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        # Drop the skill ref and re-emit.
        toml_path = f.repo_root / "profiles" / "backend.toml"
        toml_path.write_text(
            'description = "Profile backend"\n[skills]\ninclude = []\n[rules]\ninclude = []\n'
        )
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        assert not (dest / "backend" / "skills" / "alpha").exists()

    def test_main_returns_zero_on_success(self, tmp_path, capsys):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        rc = main(
            [
                "--repo-root",
                str(f.repo_root),
                "--dest-root",
                str(dest),
                "--profiles-dir",
                str(f.repo_root / "profiles"),
                "--catalog-name",
                "rhnfzl",
                "--author-name",
                "Rehan Fazal",
                "--tool-version",
                "0.11.0",
            ]
        )
        assert rc == 0
        assert "emit complete" in capsys.readouterr().out

    def test_main_propagates_emit_error_exit_code(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        rc = main(
            [
                "--repo-root",
                str(f.repo_root),
                "--dest-root",
                str(dest),
                "--profiles-dir",
                str(f.repo_root / "profiles"),
                "--catalog-name",
                "anthropic-plugins",
                "--author-name",
                "Rehan Fazal",
            ]
        )
        assert rc == 5  # ReservedNameError exit code

    def test_emitter_plugin_writes_table_isolated_per_platform(self):
        # Verify _PLUGIN_MANIFEST_WRITES has zero platform-specific branching
        # in its callers: each tuple entry is (rel_path, builder), nothing else.
        for rel_path, builder in _PLUGIN_MANIFEST_WRITES:
            assert callable(builder)
            assert isinstance(rel_path, str)

    def test_emitter_marketplace_writes_table_isolated_per_platform(self):
        for rel_path, builder in _MARKETPLACE_WRITES:
            assert callable(builder)
            assert isinstance(rel_path, str)

    def test_write_if_changed_dry_run_skips(self, tmp_path):
        path = tmp_path / "new.json"
        n = _write_if_changed(path, "x", dry_run=True)
        assert n == 0
        assert not path.exists()

    def test_write_if_changed_writes_new(self, tmp_path):
        path = tmp_path / "new.json"
        n = _write_if_changed(path, "x", dry_run=False)
        assert n == 1
        assert path.read_text() == "x"

    def test_write_if_changed_skips_when_unchanged(self, tmp_path):
        path = tmp_path / "new.json"
        _write_if_changed(path, "x", dry_run=False)
        n = _write_if_changed(path, "x", dry_run=False)
        assert n == 0

    def test_emit_plugin_directory_returns_resolved(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        from marketplace.profile_loader import _load_profiles

        profiles = _load_profiles(f.repo_root / "profiles", catalog_name="rhnfzl")
        backend = next(p for p in profiles if p.name == "backend")
        files, resolved = _emit_plugin_directory(backend, cfg)
        assert files > 0
        assert any(r.ref == "alpha" for r in resolved)

    def test_emit_marketplace_manifests_writes_once_per_vendor(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        from marketplace.profile_loader import _load_profiles

        profiles = _load_profiles(f.repo_root / "profiles", catalog_name="rhnfzl")
        resolved_by_profile = {p.name: () for p in profiles}
        files = _emit_marketplace_manifests(
            profiles, cfg, resolved_by_profile, "rhnfzl"
        )
        # 3 vendors -> at most 3 writes.
        assert files <= 3

    def test_emit_marketplace_lists_all_profiles_in_each_vendor(self, tmp_path):
        f = _FakeProfileTOML(tmp_path / "repo")
        f.add_skill("a")
        f.add_skill("b")
        f.add_skill("c")
        f.add_profile("alpha", skills=["a"])
        f.add_profile("beta", skills=["b"])
        f.add_profile("gamma", skills=["c"])
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        for rel in (
            ".claude-plugin/marketplace.json",
            ".cursor-plugin/marketplace.json",
            ".codex-plugin/marketplace.json",
        ):
            data = json.loads((dest / rel).read_text())
            names = sorted(p["name"] for p in data["plugins"])
            assert names == ["_all", "alpha", "beta", "gamma"], rel

    def test_emit_no_owner_field_equals_catalog_name(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest, author_name="Rehan Fazal")
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        data = json.loads((dest / ".claude-plugin" / "marketplace.json").read_text())
        # Owner is the person, not the catalog handle.
        assert data["owner"]["name"] == "Rehan Fazal"
        assert data["owner"]["name"] != "rhnfzl"

    def test_emit_bare_stem_hook_and_rule_end_to_end(self, tmp_path):
        """Regression: profiles reference hooks + rules by bare stem; files on
        disk carry .sh / .md. Both MUST materialize and hooks.json MUST point
        at the .sh filename. Guards the bug where every hook + rule was
        silently dropped because the resolver did a literal path check."""
        f = _FakeProfileTOML(tmp_path / "repo")
        f.add_skill("alpha")
        f.add_rule_stem("no-em-dashes")
        f.add_hook("lint-guard", event="PreToolUse", matcher="Bash")
        f.add_profile(
            "backend",
            skills=["alpha"],
            rules=["no-em-dashes"],
            hooks=["lint-guard"],
        )
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")

        # Rule materialized with its .md extension.
        assert (dest / "backend" / "rules" / "no-em-dashes.md").exists()
        # Hook script materialized with its .sh extension.
        assert (dest / "backend" / "hooks" / "lint-guard.sh").exists()
        # hooks.json emitted and the command points at the .sh filename,
        # not the bare ref.
        hooks_json = json.loads(
            (dest / "backend" / "hooks" / "hooks.json").read_text(encoding="utf-8")
        )
        cmd = hooks_json["hooks"]["PreToolUse"][0]["command"]
        assert cmd == "${PLUGIN_ROOT}/hooks/lint-guard.sh"

    def test_emit_bare_stem_refs_produce_no_warnings(self, tmp_path, capsys):
        """The bare-stem hook + rule refs must resolve cleanly (no WARN noise
        on stderr) now that the suffix fallback is in place."""
        f = _FakeProfileTOML(tmp_path / "repo")
        f.add_skill("alpha")
        f.add_rule_stem("writing-style")
        f.add_hook("never-push-to-develop")
        f.add_profile(
            "backend",
            skills=["alpha"],
            rules=["writing-style"],
            hooks=["never-push-to-develop"],
        )
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        err = capsys.readouterr().err
        assert "missing on disk" not in err
