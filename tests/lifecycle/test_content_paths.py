"""resolve_content_paths + ContentPaths regression tests (v0.11 foundation).

These tests cover the seam ADR-0040 names as the integration point for
the base + overlay subtree split. The actual file-move work and the
load_*() rewrite to consume ContentPaths land in follow-up commits.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_resolve_content_paths_none_scope_no_base_falls_back_to_repo_root(
    tmp_path: Path,
) -> None:
    """Pre-v0.11 layout (no base/ dir): single root anchored at repo_root."""
    from adapters._protocol import ContentPaths, resolve_content_paths

    result = resolve_content_paths(None, tmp_path)
    assert isinstance(result, ContentPaths)
    assert result.roots == [tmp_path]


def test_resolve_content_paths_none_scope_with_base_anchors_at_base(
    tmp_path: Path,
) -> None:
    """Post-v0.11 layout with base/ but no overlay requested: single root at base/."""
    from adapters._protocol import resolve_content_paths

    (tmp_path / "base").mkdir()
    result = resolve_content_paths(None, tmp_path)
    assert result.roots == [tmp_path / "base"]


def test_resolve_content_paths_empty_scope_is_equivalent_to_none(
    tmp_path: Path,
) -> None:
    """An explicit `scope=[]` produces the same result as `scope=None`."""
    from adapters._protocol import resolve_content_paths

    (tmp_path / "base").mkdir()
    from_none = resolve_content_paths(None, tmp_path)
    from_empty = resolve_content_paths([], tmp_path)
    assert from_none.roots == from_empty.roots


def test_resolve_content_paths_with_overlay_appends_after_base(
    tmp_path: Path,
) -> None:
    """scope=['team'] appends overlays/<name>/ AFTER base/."""
    from adapters._protocol import resolve_content_paths

    (tmp_path / "base").mkdir()
    (tmp_path / "overlays" / "team").mkdir(parents=True)

    result = resolve_content_paths(["team"], tmp_path)
    assert result.roots == [
        tmp_path / "base",
        tmp_path / "overlays" / "team",
    ]


def test_resolve_content_paths_skips_missing_overlay_silently(
    tmp_path: Path,
) -> None:
    """An overlay name that does not have a directory is silently skipped.

    Install-time validate_profile_scope (per ADR-0040) catches missing
    required overlays earlier in the dispatch; this resolver does not
    second-guess that gate.
    """
    from adapters._protocol import resolve_content_paths

    (tmp_path / "base").mkdir()
    result = resolve_content_paths(["nonexistent"], tmp_path)
    assert result.roots == [tmp_path / "base"]


def test_resolve_content_paths_preserves_overlay_order(tmp_path: Path) -> None:
    """Caller order is preserved (later overlays win on conflicts)."""
    from adapters._protocol import resolve_content_paths

    (tmp_path / "base").mkdir()
    (tmp_path / "overlays" / "team").mkdir(parents=True)
    (tmp_path / "overlays" / "personal").mkdir(parents=True)

    result_a = resolve_content_paths(["team", "personal"], tmp_path)
    result_b = resolve_content_paths(["personal", "team"], tmp_path)

    assert result_a.roots == [
        tmp_path / "base",
        tmp_path / "overlays" / "team",
        tmp_path / "overlays" / "personal",
    ]
    assert result_b.roots == [
        tmp_path / "base",
        tmp_path / "overlays" / "personal",
        tmp_path / "overlays" / "team",
    ]


def test_content_paths_and_resolver_are_reexported_from_loader(tmp_path: Path) -> None:
    """The _loader.py re-export shim surfaces the new names for legacy imports."""
    from adapters._loader import ContentPaths as LoaderContentPaths
    from adapters._loader import resolve_content_paths as loader_resolve
    from adapters._protocol import ContentPaths as ProtocolContentPaths

    assert LoaderContentPaths is ProtocolContentPaths
    result = loader_resolve(None, tmp_path)
    assert isinstance(result, LoaderContentPaths)
