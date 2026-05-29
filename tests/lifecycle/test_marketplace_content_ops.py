"""Marketplace contract tests: content_ops: resolution, materialize, stale cleanup.

Part of the marketplace suite split out of the former
test_marketplace_package.py monolith. Shared helpers live in
_marketplace_fixtures.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from marketplace import (
    MetaProfile,
    PathSafetyError,
)
from marketplace.content_ops import (
    _SUFFIX_FALLBACKS,
    ResolvedRef,
    _expected_paths,
    _is_stale_path,
    _materialize,
    _plugin_rel_for,
    _ref_escapes_source_dir,
    _refs_for_spec,
    _remove_stale_plugin_content,
    _resolve_profile,
    _resolve_source,
    _within,
)
from marketplace.types import (
    ComponentSpec,
)

from ._marketplace_fixtures import (
    _make_config,
    _make_role_profile,
    _seed_base_dirs,
)


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


class TestRefTraversalGuard:
    """SECURITY: a profile ref must not escape base/<kind> via `..` or an
    absolute path; otherwise an unscrubbed file from outside the content
    root would be copied into the public plugin dirs. Reproduces the
    reviewer's `../../../secret` finding."""

    def test_ref_escapes_predicate(self):
        assert _ref_escapes_source_dir("../../../secret")
        assert _ref_escapes_source_dir("a/../../b")
        assert _ref_escapes_source_dir("/etc/passwd")
        assert not _ref_escapes_source_dir("no-em-dashes")
        assert not _ref_escapes_source_dir("engineering/ci-failure-triage")

    def test_dotdot_rule_ref_does_not_resolve(self, tmp_path):
        _seed_base_dirs(tmp_path)
        # An unscrubbed file outside base/rules that a traversal would target.
        (tmp_path / "secret.md").write_text("UNSCRUBBED", encoding="utf-8")
        spec = ComponentSpec("rules", Path("base/rules"), "rules", "rules")
        assert _resolve_source(spec, "../../secret", tmp_path) is None

    def test_dotdot_ref_is_not_materialized(self, tmp_path):
        _seed_base_dirs(tmp_path)
        (tmp_path / "secret.md").write_text("UNSCRUBBED", encoding="utf-8")
        p = _make_role_profile(rules=("../../secret",))
        cfg = _make_config(tmp_path, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert resolved == ()
        assert warnings  # surfaced as a missing-ref warning, never copied

    def test_absolute_ref_does_not_resolve(self, tmp_path):
        _seed_base_dirs(tmp_path)
        spec = ComponentSpec("rules", Path("base/rules"), "rules", "rules")
        assert _resolve_source(spec, "/etc/passwd", tmp_path) is None


class TestSymlinkSourceEscape:
    """SECURITY: a committed symlink under base/<kind> whose target resolves
    OUTSIDE the repo must not be followed and materialized (shutil.copy2
    follows symlinks). In-repo symlinks (ADR-0035 hooks cross base/hooks ->
    base/skills) MUST still resolve. Reproduces the adversarial finding."""

    def test_in_repo_symlink_still_resolves(self, tmp_path):
        repo = tmp_path / "repo"
        _seed_base_dirs(repo)
        # ADR-0035 shape: base/hooks/X.sh -> base/skills/.../hooks/X.sh
        real = repo / "base" / "skills" / "meta" / "demo" / "hooks"
        real.mkdir(parents=True)
        real_file = real / "demo.sh"
        real_file.write_text("# PLAYBOOK-HOOK-EVENT: Stop\n", encoding="utf-8")
        link = repo / "base" / "hooks" / "demo.sh"
        link.symlink_to(real_file)
        spec = ComponentSpec("hooks", Path("base/hooks"), "hooks", "hooks")
        resolved = _resolve_source(spec, "demo", repo)
        assert resolved is not None  # in-repo cross-subtree symlink is allowed

    def test_out_of_repo_symlink_is_rejected(self, tmp_path):
        repo = tmp_path / "repo"
        _seed_base_dirs(repo)
        outside = tmp_path / "outside-secret.md"
        outside.write_text("UNSCRUBBED_SECRET", encoding="utf-8")
        link = repo / "base" / "rules" / "evil.md"
        link.symlink_to(outside)  # symlink inside base/ -> outside the repo
        spec = ComponentSpec("rules", Path("base/rules"), "rules", "rules")
        # exists() is True (target exists) but it escapes the repo -> rejected.
        assert _resolve_source(spec, "evil", repo) is None

    def test_out_of_repo_symlink_not_materialized_end_to_end(self, tmp_path):
        repo = tmp_path / "repo"
        _seed_base_dirs(repo)
        outside = tmp_path / "outside-secret.md"
        outside.write_text("UNSCRUBBED_SECRET", encoding="utf-8")
        (repo / "base" / "rules" / "evil.md").symlink_to(outside)
        p = _make_role_profile(rules=("evil",))
        cfg = _make_config(repo, tmp_path / "dest")
        resolved, warnings = _resolve_profile(p, cfg)
        assert resolved == ()  # never resolved -> never copied
        assert warnings


class TestSuffixFallbackParity:
    """Insurance against the recurring drop-bug (fixed in the bare-stem
    commit): _SUFFIX_FALLBACKS must stay aligned with the globs the
    canonical loader scripts/adapters/_reader.py uses, so a future
    content-type change cannot silently drop content from emitted plugins."""

    def test_matches_reader_globs(self):
        import re
        from pathlib import Path as _P

        reader = (
            _P(__file__).resolve().parents[2] / "scripts" / "adapters" / "_reader.py"
        ).read_text(encoding="utf-8")
        # Extract _walk_content_roots(content_paths, "<kind>", "*<ext>") calls.
        pairs = dict(
            re.findall(
                r'_walk_content_roots\(content_paths,\s*"(\w+)",\s*"\*(\.\w+)"\)',
                reader,
            )
        )
        assert pairs, "could not find any _walk_content_roots globs in _reader.py"
        for kind, ext in pairs.items():
            assert kind in _SUFFIX_FALLBACKS, (
                f"_reader globs {kind}/*{ext} but _SUFFIX_FALLBACKS has no entry; "
                "emitter would silently drop bare-stem refs for this kind"
            )
            assert ext in _SUFFIX_FALLBACKS[kind], (
                f"_reader globs {kind}/*{ext} but _SUFFIX_FALLBACKS[{kind!r}]="
                f"{_SUFFIX_FALLBACKS[kind]} omits it"
            )


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
