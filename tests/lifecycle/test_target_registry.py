"""Multi-target registry regression tests (v0.8 B3, ADR-0038)."""

from __future__ import annotations

import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def test_target_registry_record_and_list(tmp_path: Path) -> None:
    """record_target writes a target into the registry; list_targets
    returns the recorded entry.
    """
    from target_registry import list_targets, record_target

    registry_path = tmp_path / "targets.json"
    proj = tmp_path / "proj-a"
    proj.mkdir()

    record_target(
        proj, profile="backend-developer", install_mode="symlink", path=registry_path
    )
    records = list_targets(path=registry_path)
    assert len(records) == 1
    assert records[0].path == proj.resolve()
    assert records[0].profile == "backend-developer"
    assert records[0].install_mode == "symlink"
    assert records[0].registered_at


def test_target_registry_dedupes_by_path(tmp_path: Path) -> None:
    """A second record_target call for the same path updates the entry
    in place; registered_at survives, last_updated_at moves forward.
    """
    from target_registry import list_targets, load_registry, record_target

    registry_path = tmp_path / "targets.json"
    proj = tmp_path / "proj-b"
    proj.mkdir()

    record_target(proj, profile="qa", install_mode="pointer", path=registry_path)
    first = load_registry(registry_path)["targets"][str(proj.resolve())]
    time.sleep(1.0)
    record_target(proj, profile="qa", install_mode="copy", path=registry_path)
    second = load_registry(registry_path)["targets"][str(proj.resolve())]

    assert len(list_targets(path=registry_path)) == 1
    assert first["registered_at"] == second["registered_at"]
    assert second["last_updated_at"] >= first["last_updated_at"]
    assert second["install_mode"] == "copy"


def test_target_registry_prune_missing_targets(tmp_path: Path) -> None:
    """prune_missing_targets drops entries pointing at deleted directories."""
    from target_registry import (
        list_targets,
        prune_missing_targets,
        record_target,
    )

    registry_path = tmp_path / "targets.json"
    alive = tmp_path / "alive"
    alive.mkdir()
    ghost = tmp_path / "ghost"
    ghost.mkdir()

    record_target(alive, profile="qa", install_mode="pointer", path=registry_path)
    record_target(ghost, profile="qa", install_mode="pointer", path=registry_path)

    ghost.rmdir()
    pruned = prune_missing_targets(path=registry_path)
    assert pruned == [ghost]
    remaining = list_targets(path=registry_path)
    assert [r.path for r in remaining] == [alive.resolve()]


def test_target_registry_empty_on_missing_or_malformed_file(tmp_path: Path) -> None:
    """Missing or corrupt registry file degrades gracefully (empty
    registry instead of raising).
    """
    from target_registry import load_registry

    missing = tmp_path / "absent.json"
    data = load_registry(path=missing)
    assert data["targets"] == {}

    malformed = tmp_path / "broken.json"
    malformed.write_text("{not valid json", encoding="utf-8")
    data = load_registry(path=malformed)
    assert data["targets"] == {}


def test_target_registry_atomic_write_does_not_leak_tempfile(tmp_path: Path) -> None:
    """save_registry uses os.replace through a .tmp sibling, so a
    successful save leaves only the canonical file (no .tmp leftover).
    """
    from target_registry import record_target

    registry_path = tmp_path / "targets.json"
    proj = tmp_path / "proj-c"
    proj.mkdir()

    record_target(
        proj, profile="tech-lead", install_mode="pointer", path=registry_path
    )
    assert registry_path.is_file()
    assert not registry_path.with_suffix(".json.tmp").exists()


def test_cmd_targets_doctor_default_is_report_only(tmp_path: Path) -> None:
    """v0.8 Codex adversarial fix: default cmd_targets_doctor() must
    NOT mutate the registry. A temporarily-unmounted workspace,
    permission issue, or transient path problem must not silently
    drop the target's metadata.
    """
    import target_registry as tr

    saved_path = tr.REGISTRY_PATH
    fake_registry = tmp_path / "targets.json"
    tr.REGISTRY_PATH = fake_registry  # type: ignore[assignment]
    try:
        alive = tmp_path / "alive"
        alive.mkdir()
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        tr.record_target(alive, profile="qa", install_mode="pointer")
        tr.record_target(ghost, profile="qa", install_mode="pointer")
        ghost.rmdir()

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tr.cmd_targets_doctor()  # default prune=False
        out = buf.getvalue()

        # Registry should STILL contain ghost; the user must opt in to
        # destruction via --prune. The ghost entry is reported as
        # MISSING but not removed.
        records = tr.list_targets(path=fake_registry)
        assert len(records) == 2, (
            "default targets-doctor must not mutate the registry; ghost "
            "should still be present"
        )
        assert "MISSING" in out
        assert "ghost" in out
        assert "PRUNE=1" in out, (
            "report-only mode must tell the user how to opt into pruning"
        )
    finally:
        tr.REGISTRY_PATH = saved_path  # type: ignore[assignment]

    assert rc == 0


def test_cmd_targets_doctor_with_prune_removes_missing(tmp_path: Path) -> None:
    """v0.8 Codex adversarial fix: explicit prune=True is the only path
    that mutates the registry; matches the new `make targets-doctor
    PRUNE=1` opt-in convention.
    """
    import target_registry as tr

    saved_path = tr.REGISTRY_PATH
    fake_registry = tmp_path / "targets.json"
    tr.REGISTRY_PATH = fake_registry  # type: ignore[assignment]
    try:
        alive = tmp_path / "alive"
        alive.mkdir()
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        tr.record_target(alive, profile="qa", install_mode="pointer")
        tr.record_target(ghost, profile="qa", install_mode="pointer")
        ghost.rmdir()

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = tr.cmd_targets_doctor(prune=True)
        out = buf.getvalue()

        records = tr.list_targets(path=fake_registry)
        assert len(records) == 1
        assert records[0].path == alive.resolve()
        assert "Pruned 1 stale target(s)" in out
    finally:
        tr.REGISTRY_PATH = saved_path  # type: ignore[assignment]

    assert rc == 0
