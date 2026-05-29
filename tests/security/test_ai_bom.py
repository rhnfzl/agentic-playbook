"""Tests for the AI-BOM emitter.

The BOM is the canonical "what's imported here" record. Atlas reads
it to render per-skill vetted-as-of badges; CVE feeds diff against
it. Tests verify schema shape, source enumeration, and timestamp
formatting (ISO 8601 with TZ).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from security import ai_bom  # noqa: E402


def _seed_skill(skill_dir: Path, *, name: str, version: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: t\nversion: {version}\n"
        f"owner: t\nlast_reviewed: 2026-05-28\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def test_emits_imported_skills(tmp_path: Path) -> None:
    _seed_skill(
        tmp_path / "base" / "skills" / "imported" / "mattpocock" / "skill-a",
        name="skill-a",
        version="0.1.0",
    )
    _seed_skill(
        tmp_path / "base" / "skills" / "imported" / "obra" / "skill-b",
        name="skill-b",
        version="2.0.0",
    )
    bom = ai_bom.build_bom(tmp_path)
    assert bom["repo"] == "agentic-playbook"
    skills = [c for c in bom["components"] if c["kind"] == "imported_skill"]
    assert {s["source"] for s in skills} == {"mattpocock", "obra"}
    assert {s["name"] for s in skills} == {"skill-a", "skill-b"}


def test_emits_mcp_bundles(tmp_path: Path) -> None:
    bundle = tmp_path / "base" / "mcp" / "anchored-fs"
    bundle.mkdir(parents=True)
    (bundle / "manifest.toml").write_text(
        'name = "anchored-fs"\nversion = "0.3.1"\n',
        encoding="utf-8",
    )
    bom = ai_bom.build_bom(tmp_path)
    bundles = [c for c in bom["components"] if c["kind"] == "mcp_bundle"]
    assert len(bundles) == 1
    assert bundles[0]["name"] == "anchored-fs"
    assert bundles[0]["version"] == "0.3.1"


def test_picks_up_vetted_marker(tmp_path: Path) -> None:
    skill_dir = tmp_path / "base" / "skills" / "imported" / "src" / "skill"
    _seed_skill(skill_dir, name="skill", version="0.1.0")
    (skill_dir / ".vetted-as-of").write_text("2026-04-01", encoding="utf-8")
    bom = ai_bom.build_bom(tmp_path)
    skills = [c for c in bom["components"] if c["kind"] == "imported_skill"]
    assert skills[0]["vetted_as_of"] == "2026-04-01"


def test_bom_writes_iso_timestamp_with_tz(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "base" / "skills" / "imported").mkdir(parents=True)
    out = tmp_path / "bom.json"
    rc = ai_bom.main(["--repo-root", str(tmp_path), "--output", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["generated_at"].endswith("+00:00")


def test_empty_repo_emits_empty_components(tmp_path: Path) -> None:
    bom = ai_bom.build_bom(tmp_path)
    assert bom["components"] == []


def test_bom_is_idempotent_when_components_unchanged(tmp_path: Path) -> None:
    """Two consecutive runs on the same tree must produce the same
    file. Without idempotency `make check` would dirty a clean tree
    on every CI run (the BOM is a make-check target via
    skill-security)."""
    _seed_skill(
        tmp_path / "base" / "skills" / "imported" / "src" / "demo",
        name="demo",
        version="0.1.0",
    )
    out = tmp_path / "ai-bom.json"
    ai_bom.main(["--repo-root", str(tmp_path), "--output", str(out)])
    first = out.read_text(encoding="utf-8")
    ai_bom.main(["--repo-root", str(tmp_path), "--output", str(out)])
    second = out.read_text(encoding="utf-8")
    assert first == second, "second run must preserve generated_at"


def test_bom_writes_fresh_content_when_components_change(tmp_path: Path) -> None:
    """Sanity check the inverse of idempotency: when the component
    list changes the BOM must reflect the new components and the
    file content must differ."""
    out = tmp_path / "ai-bom.json"
    ai_bom.main(["--repo-root", str(tmp_path), "--output", str(out)])
    first = json.loads(out.read_text(encoding="utf-8"))
    _seed_skill(
        tmp_path / "base" / "skills" / "imported" / "src" / "added-later",
        name="added-later",
        version="0.1.0",
    )
    ai_bom.main(["--repo-root", str(tmp_path), "--output", str(out)])
    second = json.loads(out.read_text(encoding="utf-8"))
    assert first["components"] != second["components"]
    assert "added-later" in {c.get("name") for c in second["components"]}
