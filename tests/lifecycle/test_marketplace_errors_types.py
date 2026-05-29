"""Marketplace contract tests: Errors + types + profile loader.

Part of the marketplace suite split out of the former
test_marketplace_package.py monolith. Shared helpers live in
_marketplace_fixtures.py.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from marketplace import (
    EmitError,
    MaterializationError,
    MetaProfile,
    PathSafetyError,
    ProfileLoadError,
    ReservedNameError,
    SlugValidationError,
)
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
    specs_for,
)

from ._marketplace_fixtures import (
    _make_config,
    _make_role_profile,
    _seed_profile_toml,
)


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
