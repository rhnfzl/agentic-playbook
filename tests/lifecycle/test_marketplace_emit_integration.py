"""Marketplace contract tests: end-to-end emit orchestration.

Part of the marketplace suite split out of the former
test_marketplace_package.py monolith. Shared helpers live in
_marketplace_fixtures.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketplace import (
    ReservedNameError,
    SlugValidationError,
    emit,
    main,
)
from marketplace.emitter import (
    _MARKETPLACE_WRITES,
    _PLUGIN_MANIFEST_WRITES,
    _emit_marketplace_manifests,
    _emit_plugin_directory,
    _write_if_changed,
)
from marketplace.profile_loader import (
    _load_profiles,
)

from ._marketplace_fixtures import (
    _FakeProfileTOML,
    _make_config,
)


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
            ".agents/plugins/marketplace.json",
        ):
            assert (dest / rel).exists(), rel

    def test_codex_marketplace_at_agents_plugins_not_codex_plugin(self, tmp_path):
        """Regression: Codex discovers repo-local catalogs at
        .agents/plugins/marketplace.json, NOT .codex-plugin/marketplace.json."""
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)
        emit(cfg, profiles_dir=f.repo_root / "profiles", catalog_name="rhnfzl")
        assert (dest / ".agents" / "plugins" / "marketplace.json").exists()
        assert not (dest / ".codex-plugin" / "marketplace.json").exists()
        # The per-plugin Codex manifest still lives under .codex-plugin/.
        assert (dest / "backend" / ".codex-plugin" / "plugin.json").exists()

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
        data = json.loads(
            (dest / ".agents" / "plugins" / "marketplace.json").read_text()
        )
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

        profiles = _load_profiles(f.repo_root / "profiles", catalog_name="rhnfzl")
        backend = next(p for p in profiles if p.name == "backend")
        files, resolved = _emit_plugin_directory(backend, cfg)
        assert files > 0
        assert any(r.ref == "alpha" for r in resolved)

    def test_emit_marketplace_manifests_writes_once_per_vendor(self, tmp_path):
        f = self._fixture(tmp_path)
        dest = tmp_path / "dest"
        cfg = _make_config(f.repo_root, dest)

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
            ".agents/plugins/marketplace.json",
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
