"""Contract tests for scripts/marketplace_config.py.

The facade exists so sync_distribution.py can call marketplace emit
without importing from the marketplace package directly. Tests pin
the facade's composition of EmitterConfig (every field hand-mapped)
and the propagation of dry_run + the emit() return value.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from marketplace import TOOL_VERSION
from marketplace_config import emitter_tool_version, run_marketplace_emit


@dataclass
class _FakeManifest:
    repo_root: Path
    destination: Path
    catalog_name: str
    author_name: str
    author_email: str | None
    profiles_dir: Path
    default_profile_version: str | None


def _seed_minimal_playbook(repo_root: Path) -> Path:
    (repo_root / "base" / "skills" / "alpha").mkdir(parents=True)
    (repo_root / "base" / "skills" / "alpha" / "SKILL.md").write_text(
        "# alpha", encoding="utf-8"
    )
    for sub in ("rules", "hooks", "mcp", "agents", "commands", "prompts"):
        (repo_root / "base" / sub).mkdir(parents=True, exist_ok=True)
    (repo_root / "VERSION").write_text("0.11.0\n", encoding="utf-8")
    profiles_dir = repo_root / "profiles"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "backend.toml").write_text(
        'description = "Backend"\n[skills]\ninclude = ["alpha"]\n',
        encoding="utf-8",
    )
    return profiles_dir


class TestEmitterToolVersion:
    def test_returns_package_tool_version(self):
        assert emitter_tool_version() == TOOL_VERSION


class TestRunMarketplaceEmit:
    def test_composes_emitter_config_and_invokes_emit(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        profiles_dir = _seed_minimal_playbook(repo_root)
        dest = tmp_path / "dest"
        manifest = _FakeManifest(
            repo_root=repo_root,
            destination=dest,
            catalog_name="rhnfzl",
            author_name="Rehan Fazal",
            author_email=None,
            profiles_dir=profiles_dir,
            default_profile_version=None,
        )
        files_written = run_marketplace_emit(manifest, dry_run=False)
        assert files_written > 0
        assert (dest / "backend" / "skills" / "alpha" / "SKILL.md").exists()

    def test_dry_run_propagates(self, tmp_path):
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        profiles_dir = _seed_minimal_playbook(repo_root)
        dest = tmp_path / "dest"
        manifest = _FakeManifest(
            repo_root=repo_root,
            destination=dest,
            catalog_name="rhnfzl",
            author_name="Rehan Fazal",
            author_email=None,
            profiles_dir=profiles_dir,
            default_profile_version=None,
        )
        run_marketplace_emit(manifest, dry_run=True)
        # dry_run must NOT materialize anything.
        assert not (dest / "backend").exists()

    def test_author_email_passes_through(self, tmp_path):
        import json

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        profiles_dir = _seed_minimal_playbook(repo_root)
        dest = tmp_path / "dest"
        manifest = _FakeManifest(
            repo_root=repo_root,
            destination=dest,
            catalog_name="rhnfzl",
            author_name="Rehan Fazal",
            author_email="rehan@example.com",
            profiles_dir=profiles_dir,
            default_profile_version=None,
        )
        run_marketplace_emit(manifest, dry_run=False)
        plugin_json = json.loads(
            (dest / "backend" / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        assert plugin_json["author"] == {
            "name": "Rehan Fazal",
            "email": "rehan@example.com",
        }

    def test_default_profile_version_passes_through(self, tmp_path):
        import json

        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        profiles_dir = _seed_minimal_playbook(repo_root)
        dest = tmp_path / "dest"
        manifest = _FakeManifest(
            repo_root=repo_root,
            destination=dest,
            catalog_name="rhnfzl",
            author_name="Rehan Fazal",
            author_email=None,
            profiles_dir=profiles_dir,
            default_profile_version="0.5.0",
        )
        run_marketplace_emit(manifest, dry_run=False)
        plugin_json = json.loads(
            (dest / "backend" / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        # No per-profile version override, no default in TOML -> default_profile_version wins.
        assert plugin_json["version"] == "0.5.0"
