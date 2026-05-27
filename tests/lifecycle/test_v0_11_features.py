"""v0.11 feature regression tests: profile requires_overlays + lockfile content_scope.

These tests exercise the v0.11 surfaces that aren't already covered by
the per-feature test files (test_content_paths, test_scope_boundary,
test_adr_number_unique, test_ignored_containment, test_playbook_version):
  * validate_profile_scope: rejects base-only install when profile
    requires an overlay; accepts when scope satisfies.
  * load_profile: parses requires_overlays correctly; rejects malformed.
  * load_profiles: unions requires_overlays across multi-profile composition.
  * generate_lockfile: round-trips content_scope as list[str].
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


# === validate_profile_scope ===


def test_validate_profile_scope_passes_when_no_requires() -> None:
    """Profile without requires_overlays is always valid."""
    from playbook_profile import Profile, validate_profile_scope

    p = Profile(name="x", description="", skills=[], rules=[], hooks=[], mcp=[])
    validate_profile_scope(p, [])
    validate_profile_scope(p, ["any-overlay"])


def test_validate_profile_scope_rejects_missing_overlay() -> None:
    """Profile that requires an overlay rejects empty scope."""
    from playbook_profile import Profile, validate_profile_scope

    p = Profile(
        name="devops",
        description="",
        skills=[],
        rules=[],
        hooks=[],
        mcp=[],
        requires_overlays=["team"],
    )
    with pytest.raises(ValueError) as exc_info:
        validate_profile_scope(p, [])
    assert "team" in str(exc_info.value)
    assert "devops" in str(exc_info.value)
    assert "--scope team" in str(exc_info.value)


def test_validate_profile_scope_accepts_satisfying_scope() -> None:
    """Profile that requires team overlay passes when team is active."""
    from playbook_profile import Profile, validate_profile_scope

    p = Profile(
        name="devops",
        description="",
        skills=[],
        rules=[],
        hooks=[],
        mcp=[],
        requires_overlays=["team"],
    )
    validate_profile_scope(p, ["team"])
    validate_profile_scope(p, ["team", "extra"])


# === load_profile + load_profiles requires_overlays parsing ===


def _write_profile(tmp_path: Path, name: str, body: str) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    path = profiles_dir / f"{name}.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_profile_parses_requires_overlays(tmp_path: Path) -> None:
    """requires_overlays is read into the Profile dataclass."""
    from playbook_profile import load_profile

    _write_profile(
        tmp_path,
        "devops",
        'name = "devops"\n'
        'description = "DevOps profile"\n'
        'requires_overlays = ["team"]\n'
        '[skills]\ninclude = []\n'
        '[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n'
        '[mcp]\ninclude = []\n',
    )
    p = load_profile(tmp_path, "devops")
    assert p.requires_overlays == ["team"]


def test_load_profile_defaults_requires_overlays_to_empty(tmp_path: Path) -> None:
    """A profile without requires_overlays loads with empty list."""
    from playbook_profile import load_profile

    _write_profile(
        tmp_path,
        "research",
        'name = "research"\n'
        'description = "Research profile"\n'
        '[skills]\ninclude = []\n'
        '[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n'
        '[mcp]\ninclude = []\n',
    )
    p = load_profile(tmp_path, "research")
    assert p.requires_overlays == []


def test_load_profile_rejects_malformed_requires_overlays(tmp_path: Path) -> None:
    """Non-list / non-string entries fail with a clear message."""
    from playbook_profile import load_profile

    _write_profile(
        tmp_path,
        "bad",
        'name = "bad"\n'
        'description = ""\n'
        'requires_overlays = "team"\n'  # string instead of list
        '[skills]\ninclude = []\n[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n[mcp]\ninclude = []\n',
    )
    with pytest.raises(ValueError) as exc:
        load_profile(tmp_path, "bad")
    assert "requires_overlays" in str(exc.value)


def test_load_profiles_unions_requires_overlays(tmp_path: Path) -> None:
    """Multi-profile composition unions requires_overlays."""
    from playbook_profile import load_profiles

    _write_profile(
        tmp_path,
        "devops",
        'name = "devops"\ndescription = ""\nrequires_overlays = ["team"]\n'
        '[skills]\ninclude = []\n[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n[mcp]\ninclude = []\n',
    )
    _write_profile(
        tmp_path,
        "qa",
        'name = "qa"\ndescription = ""\nrequires_overlays = ["team"]\n'
        '[skills]\ninclude = []\n[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n[mcp]\ninclude = []\n',
    )
    _write_profile(
        tmp_path,
        "research",
        'name = "research"\ndescription = ""\n'
        '[skills]\ninclude = []\n[rules]\ninclude = []\n'
        '[hooks]\ninclude = []\n[mcp]\ninclude = []\n',
    )

    merged = load_profiles(tmp_path, ["devops", "qa", "research"])
    assert merged.requires_overlays == ["team"]  # union + dedupe + sort


# === Lockfile content_scope ===


def test_generate_lockfile_persists_content_scope(tmp_path: Path) -> None:
    """content_scope is written to the lockfile as list[str]."""
    from install_lockfile import generate_lockfile

    path = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.11.0",
        content_scope=["team"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content_scope"] == ["team"]


def test_generate_lockfile_writes_null_when_no_scope(tmp_path: Path) -> None:
    """content_scope serializes as null when not passed (or empty)."""
    from install_lockfile import generate_lockfile

    path = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.11.0",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content_scope"] is None


def test_generate_lockfile_preserves_scope_order(tmp_path: Path) -> None:
    """Multi-overlay scope round-trips with caller's order preserved."""
    from install_lockfile import generate_lockfile

    path = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.11.0",
        content_scope=["personal", "team"],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["content_scope"] == ["personal", "team"]
