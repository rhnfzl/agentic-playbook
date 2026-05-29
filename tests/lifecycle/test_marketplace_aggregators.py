"""Marketplace contract tests: hook + mcp aggregators.

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
from marketplace.hook_aggregator import _build_hooks_json
from marketplace.mcp_aggregator import _build_mcp_json
from marketplace.types import (
    ComponentSpec,
)

from ._marketplace_fixtures import (
    _make_config,
    _make_role_profile,
)


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

    def test_all_hooks_invalid_drops_stale_hooks_json(self, tmp_path, capsys):
        """Regression: hook refs present but every one is rejected (no
        PLAYBOOK-HOOK-EVENT header) must DELETE a previously-emitted
        hooks.json, not leave the stale (now-rejected) command installed.
        """
        cfg = _make_config(tmp_path, tmp_path / "dest")
        plugin_dir = tmp_path / "dest" / "backend-developer"
        (plugin_dir / "hooks").mkdir(parents=True)
        # A previously-valid hooks.json is already installed.
        (plugin_dir / "hooks" / "hooks.json").write_text(
            '{"hooks": {"PreToolUse": [{"command": "stale"}]}}', encoding="utf-8"
        )
        # Current source: a hook ref that resolves but lacks the event header.
        ref = self._seed_hook(tmp_path, "headerless.sh", "echo no header\n")
        p = _make_role_profile(hooks=("headerless.sh",))
        _build_hooks_json(p, (ref,), cfg, plugin_dir)
        assert "no PLAYBOOK-HOOK-EVENT header" in capsys.readouterr().err
        # The stale command must be gone.
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
