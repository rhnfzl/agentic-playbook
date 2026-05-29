"""Marketplace contract tests: shared helpers + per-vendor manifest builders.

Part of the marketplace suite split out of the former
test_marketplace_package.py monolith. Shared helpers live in
_marketplace_fixtures.py.
"""

from __future__ import annotations

import json
from pathlib import Path


from marketplace.content_ops import (
    ResolvedRef,
)
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
)
from marketplace.manifests.cursor import (
    _cursor_marketplace_manifest,
    _cursor_plugin_manifest,
)
from marketplace.manifests.gemini import _gemini_extension_manifest, _mcp_servers_block
from marketplace.types import (
    ComponentSpec,
)

from ._marketplace_fixtures import (
    _make_config,
    _make_role_profile,
)


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

    def test_agent_file_uses_materialized_md_path(self, tmp_path):
        """Regression: a file agent referenced by bare stem `scout`
        materializes to agents/scout.md; the manifest agents entry must be
        `agents/scout.md`, not `agents/scout` (which would not exist)."""
        cfg = _make_config(tmp_path, tmp_path / "dest")
        spec = ComponentSpec("agents", Path("base/agents"), "agents", "agents")
        f = tmp_path / "scout.md"
        f.write_text("body")
        resolved = (
            ResolvedRef(
                spec=spec, ref="scout", source=f, plugin_rel=Path("agents/scout.md")
            ),
        )
        p = _make_role_profile()
        entry = _claude_plugin_entry(p, cfg, resolved)
        assert entry["agents"] == ["agents/scout.md"]

    def test_agent_dir_uses_agent_md_entry(self, tmp_path):
        """A directory-style agent exposes its entry at agent.md."""
        cfg = _make_config(tmp_path, tmp_path / "dest")
        spec = ComponentSpec("agents", Path("base/agents"), "agents", "agents")
        d = tmp_path / "scout"
        d.mkdir()
        resolved = (
            ResolvedRef(
                spec=spec, ref="scout", source=d, plugin_rel=Path("agents/scout")
            ),
        )
        p = _make_role_profile()
        entry = _claude_plugin_entry(p, cfg, resolved)
        assert entry["agents"] == ["agents/scout/agent.md"]

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

    def test_emitted_policy_values_are_in_the_documented_enums(self):
        # The emitted defaults must be members of the documented Codex enums.
        cfg = _make_config(Path("/repo"), Path("/repo/dest"))
        entry = _codex_plugin_entry(_make_role_profile(), cfg)
        assert entry["policy"]["authentication"] in _CODEX_AUTH
        assert entry["policy"]["installation"] in _CODEX_INSTALLATION

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
