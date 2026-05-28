"""End-to-end build_atlas test.

Seeds a tiny corpus, runs `build_site`, asserts the output
structure and per-skill badge composition (security + telemetry +
trajectory). Cross-subsystem integration is verified here because
no other test exercises all three signals at once.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import build_atlas  # noqa: E402


def _seed_corpus(tmp: Path) -> None:
    # ADR
    adr = tmp / "docs" / "adr" / "0001-first.md"
    adr.parent.mkdir(parents=True, exist_ok=True)
    adr.write_text(
        "# 0001. First\n\n## Context\nThis mentions the demo skill.\n",
        encoding="utf-8",
    )
    # Skill
    skill = tmp / "base" / "skills" / "engineering" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\nname: demo\ndescription: A demo skill\nversion: 0.1.0\n"
        "owner: t\nlast_reviewed: 2026-05-28\n---\n\n# demo\n",
        encoding="utf-8",
    )
    # Trajectory
    traj = tmp / "base" / "trajectories" / "demo" / "happy-path.yaml"
    traj.parent.mkdir(parents=True, exist_ok=True)
    traj.write_text("name: demo/happy-path\n", encoding="utf-8")


def test_build_site_writes_index_and_pages(tmp_path: Path) -> None:
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    rc = build_atlas.build_site(tmp_path, out_dir)
    assert rc == 0
    assert (out_dir / "index.html").is_file()
    assert (out_dir / "static" / "atlas.css").is_file()
    assert (out_dir / "graph.json").is_file()
    assert (out_dir / "adr" / "0001.html").is_file()
    assert (out_dir / "skill" / "base-engineering-demo.html").is_file()
    assert (out_dir / "trajectory" / "demo-happy-path.html").is_file()


def test_index_lists_all_kinds(tmp_path: Path) -> None:
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    index = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "ADRs (1)" in index
    assert "Skills (1)" in index
    assert "Trajectories (1)" in index


def test_skill_page_renders_bom_badge(tmp_path: Path) -> None:
    _seed_corpus(tmp_path)
    bom = tmp_path / "docs" / "security" / "ai-bom.json"
    bom.parent.mkdir(parents=True, exist_ok=True)
    bom.write_text(json.dumps({
        "components": [{
            "kind": "imported_skill",
            "path": "base/skills/engineering/demo",
            "name": "demo",
            "vetted_as_of": "2026-05-01",
        }],
    }), encoding="utf-8")
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "vetted: 2026-05-01" in skill_html


def test_skill_page_includes_trajectory_link(tmp_path: Path) -> None:
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "demo/happy-path" in skill_html


def test_graph_json_has_nodes_and_edges(tmp_path: Path) -> None:
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    payload = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert {n["kind"] for n in payload["nodes"]} == {"adr", "skill", "trajectory"}
    assert any(e["kind"] == "belongs_to" for e in payload["edges"])


def test_telemetry_off_omits_telemetry_badges(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("TELEMETRY", "off")
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "triggers:" not in skill_html


def test_atlas_telemetry_requires_explicit_opt_in(
    tmp_path: Path, monkeypatch,
) -> None:
    """Privacy: even with TELEMETRY unset (default-enabled per the
    standard contract), atlas must NOT render telemetry into committed
    pages. A contributor with local telemetry running would otherwise
    silently bake personal usage signals into HTML headed to PRs."""
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "triggers:" not in skill_html, (
        "atlas must default to off for telemetry rendering, not is_enabled()"
    )


def test_atlas_telemetry_renders_when_explicit_opt_in(
    tmp_path: Path, monkeypatch,
) -> None:
    """Sanity check the inverse: TELEMETRY=on should opt the contributor
    into local rendering for personal browsing."""
    _seed_corpus(tmp_path)
    tele_dir = tmp_path / "tele"
    tele_dir.mkdir()
    (tele_dir / "skills.jsonl").write_text(json.dumps({
        "skill": "demo", "adapter": "claude-code", "model": "m",
        "fired_at": "2026-05-28T12:00:00+00:00",
        "latency_ms": 100, "input_tokens": 1, "output_tokens": 2,
    }) + "\n", encoding="utf-8")
    monkeypatch.setenv("TELEMETRY", "on")
    monkeypatch.setenv("TELEMETRY_DIR", str(tele_dir))
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "triggers: 1" in skill_html


def test_skill_page_lists_adr_mentions(tmp_path: Path) -> None:
    """ADR-0001 body mentions the demo skill (heuristic edge); the
    skill page should backlink to the ADR via its 'ADRs mentioning
    this skill' section."""
    _seed_corpus(tmp_path)
    out_dir = tmp_path / "atlas"
    build_atlas.build_site(tmp_path, out_dir)
    skill_html = (out_dir / "skill" / "base-engineering-demo.html").read_text(
        encoding="utf-8",
    )
    assert "ADR-0001" in skill_html
