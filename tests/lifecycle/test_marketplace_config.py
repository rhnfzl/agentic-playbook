"""Contract tests for scripts/marketplace_config.py + the sync integration.

The facade exists so sync_distribution.py can call marketplace emit
without importing from the marketplace package directly. Tests pin
the facade's composition of EmitterConfig (every field hand-mapped),
the propagation of dry_run + the emit() return value, the re-exported
safety-exception contract, and the sync integration's read-from-scrubbed-
destination + exit-code-preservation behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import sync_distribution
from marketplace import EmitError, ReservedNameError, TOOL_VERSION
from marketplace_config import (
    MarketplaceEmitError,
    emitter_tool_version,
    run_marketplace_emit,
)


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


class TestSafetyExceptionReexport:
    def test_marketplace_emit_error_is_emit_error(self):
        """The facade re-exports the package's EmitError so callers can
        catch emit-time safety failures without importing the package."""
        assert MarketplaceEmitError is EmitError

    def test_run_marketplace_emit_propagates_reserved_name(self, tmp_path):
        """A reserved catalog name raises a MarketplaceEmitError carrying
        the declared exit code (5)."""
        repo_root = tmp_path / "repo"
        repo_root.mkdir()
        profiles_dir = _seed_minimal_playbook(repo_root)
        manifest = _FakeManifest(
            repo_root=repo_root,
            destination=tmp_path / "dest",
            catalog_name="anthropic-plugins",  # reserved
            author_name="Rehan Fazal",
            author_email=None,
            profiles_dir=profiles_dir,
            default_profile_version=None,
        )
        with pytest.raises(MarketplaceEmitError) as excinfo:
            run_marketplace_emit(manifest, dry_run=False)
        assert isinstance(excinfo.value, ReservedNameError)
        assert excinfo.value.exit_code == 5


def _make_marketplace_manifest(dest: Path, **overrides) -> sync_distribution.Manifest:
    """Build a sync Manifest with the [marketplace] block populated."""
    fields = {
        "destination_path": dest,
        "require_clean_git": False,
        "allowlist": ["base/", "profiles/"],
        "denylist": [],
        "scrubs": [],
        "marketplace_catalog_name": "rhnfzl",
        "marketplace_author_name": "Rehan Fazal",
        "marketplace_author_email": None,
        "marketplace_profiles_dir": "profiles/",
        "marketplace_default_profile_version": None,
    }
    fields.update(overrides)
    return sync_distribution.Manifest(**fields)


class TestSyncIntegration:
    def test_emit_reads_from_scrubbed_destination_not_source(self, tmp_path):
        """P1 scrub-safety: the emitter reads profiles + base content from
        the DESTINATION (already scrubbed), never from the source. We seed
        ONLY the destination; if the integration read from anywhere else it
        would find nothing and emit zero plugin dirs."""
        dest = tmp_path / "dest"
        dest.mkdir()
        _seed_minimal_playbook(dest)  # scrubbed tree lives at the destination
        manifest = _make_marketplace_manifest(dest)
        written = sync_distribution._maybe_run_marketplace_emit(manifest, dry_run=False)
        assert written is not None and written > 0
        # Emitted from the destination's own (scrubbed) content.
        assert (dest / "backend" / "skills" / "alpha" / "SKILL.md").exists()
        assert (dest / ".claude-plugin" / "marketplace.json").exists()

    def test_absent_marketplace_block_returns_none(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()
        manifest = _make_marketplace_manifest(dest, marketplace_catalog_name=None)
        assert (
            sync_distribution._maybe_run_marketplace_emit(manifest, dry_run=False)
            is None
        )

    def test_dry_run_skips_marketplace_emit(self, tmp_path, capsys):
        """Regression: the emit reads the destination, which a dry-run does
        not populate. Dry-run must SKIP emit (return None + explain), not
        fail on an empty destination or verify stale content."""
        dest = tmp_path / "dest"
        dest.mkdir()  # intentionally empty: a dry-run copied nothing here
        manifest = _make_marketplace_manifest(dest)
        result = sync_distribution._maybe_run_marketplace_emit(manifest, dry_run=True)
        assert result is None
        assert "skipped in dry-run" in capsys.readouterr().err
        # Nothing emitted.
        assert not (dest / ".claude-plugin").exists()
        assert not (dest / "backend").exists()

    def test_reserved_name_raises_systemexit_with_code_5(self, tmp_path):
        """P5 exit-code preservation: an EmitError (reserved catalog name)
        surfaces as SystemExit(5), not the generic exit 3, so the scheduled
        wrapper can distinguish a marketplace safety failure from IO error."""
        dest = tmp_path / "dest"
        dest.mkdir()
        _seed_minimal_playbook(dest)
        manifest = _make_marketplace_manifest(
            dest, marketplace_catalog_name="anthropic-plugins"
        )
        with pytest.raises(SystemExit) as excinfo:
            sync_distribution._maybe_run_marketplace_emit(manifest, dry_run=False)
        assert excinfo.value.code == 5

    def test_profiles_dir_escaping_dest_raises_systemexit_5(self, tmp_path):
        """SECURITY (P1): a profiles_dir that resolves OUTSIDE the
        destination (e.g. '../raw-profiles') must be refused before emit, so
        the emitter never reads an unscrubbed tree. Reproduces the reviewer's
        traversal finding."""
        dest = tmp_path / "dest"
        dest.mkdir()
        _seed_minimal_playbook(dest)
        # Plant an unscrubbed profiles tree as a sibling of dest.
        outside = tmp_path / "raw-profiles"
        outside.mkdir()
        (outside / "leak.toml").write_text(
            'description = "UNSCRUBBED"\n', encoding="utf-8"
        )
        manifest = _make_marketplace_manifest(
            dest, marketplace_profiles_dir="../raw-profiles"
        )
        with pytest.raises(SystemExit) as excinfo:
            sync_distribution._maybe_run_marketplace_emit(manifest, dry_run=False)
        assert excinfo.value.code == 5
        # Nothing emitted from the outside tree.
        assert not (dest / "leak").exists()


class TestManifestMarketplaceValidation:
    def test_partial_marketplace_block_raises_systemexit_1(self, tmp_path):
        """A [marketplace] block with only some required keys fails LOUD at
        manifest load (exit 1), never silently skips emit at run time."""
        m = tmp_path / "manifest.toml"
        m.write_text(
            f'[destination]\npath = "{tmp_path}"\n'
            '[sources]\nallowlist = ["base/"]\n'
            '[marketplace]\ncatalog_name = "rhnfzl"\n',  # missing author_name + profiles_dir
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as excinfo:
            sync_distribution._load_manifest(m)
        assert "partially configured" in str(excinfo.value)

    def test_complete_marketplace_block_loads(self, tmp_path):
        m = tmp_path / "manifest.toml"
        m.write_text(
            f'[destination]\npath = "{tmp_path}"\n'
            '[sources]\nallowlist = ["base/"]\n'
            "[marketplace]\n"
            'catalog_name = "rhnfzl"\n'
            'author_name = "Rehan Fazal"\n'
            'profiles_dir = "profiles/"\n',
            encoding="utf-8",
        )
        manifest = sync_distribution._load_manifest(m)
        assert manifest.marketplace_catalog_name == "rhnfzl"
        assert manifest.marketplace_author_name == "Rehan Fazal"

    def test_no_marketplace_block_loads(self, tmp_path):
        m = tmp_path / "manifest.toml"
        m.write_text(
            f'[destination]\npath = "{tmp_path}"\n[sources]\nallowlist = ["base/"]\n',
            encoding="utf-8",
        )
        manifest = sync_distribution._load_manifest(m)
        assert manifest.marketplace_catalog_name is None
