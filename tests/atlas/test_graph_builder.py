"""Tests for the atlas graph builder.

Exercises node enumeration, edge heuristics (mentions, belongs_to,
supersedes), and the JSON serialization shape downstream
consumers (including the D3 view) depend on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from atlas import graph_builder  # noqa: E402


def _seed_adr(repo: Path, number: str, title: str, body: str = "") -> Path:
    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    p = adr_dir / f"{number}-{title.lower().replace(' ', '-')}.md"
    p.write_text(
        f"# {number}. {title}\n\n## Status\nAccepted\n\n## Context\n{body}\n",
        encoding="utf-8",
    )
    return p


def _seed_skill(repo: Path, scope: str, category: str, name: str) -> Path:
    base = repo / ("base" if scope == "base" else "overlays/team")
    p = base / "skills" / category / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nname: {name}\ndescription: A {name} skill\nversion: 0.1.0\n"
        f"owner: t\nlast_reviewed: 2026-05-28\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return p


def _seed_trajectory(repo: Path, skill_name: str, scenario: str) -> Path:
    p = repo / "base" / "trajectories" / skill_name / f"{scenario}.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"name: {skill_name}/{scenario}\n", encoding="utf-8")
    return p


def test_enumerates_three_node_kinds(tmp_path: Path) -> None:
    _seed_adr(tmp_path, "0001", "First", "context")
    _seed_skill(tmp_path, "base", "engineering", "to-prd")
    _seed_trajectory(tmp_path, "to-prd", "happy-path")
    graph = graph_builder.build_graph(tmp_path)
    by_kind = {kind: [n for n in graph.nodes if n.kind == kind]
               for kind in ("adr", "skill", "trajectory")}
    assert len(by_kind["adr"]) == 1
    assert len(by_kind["skill"]) == 1
    assert len(by_kind["trajectory"]) == 1


def test_adr_to_skill_edge_when_body_mentions_skill(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "base", "engineering", "trajectory-arc")
    _seed_adr(
        tmp_path, "0044", "Trajectories",
        body="The trajectory-arc skill is the surface this ADR addresses.",
    )
    graph = graph_builder.build_graph(tmp_path)
    mentions = [e for e in graph.edges if e.kind == "mentions"]
    assert len(mentions) == 1


def test_trajectory_to_skill_belongs_to_edge(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "base", "engineering", "to-prd")
    _seed_trajectory(tmp_path, "to-prd", "happy-path")
    graph = graph_builder.build_graph(tmp_path)
    belongs = [e for e in graph.edges if e.kind == "belongs_to"]
    assert len(belongs) == 1
    assert belongs[0].source.startswith("trajectory-")
    assert belongs[0].target.startswith("skill-")


def test_adr_supersedes_edge(tmp_path: Path) -> None:
    _seed_adr(tmp_path, "0001", "Original", "context")
    _seed_adr(
        tmp_path, "0050", "Replacement",
        body="Supersedes 0001 because the original premise no longer holds.",
    )
    graph = graph_builder.build_graph(tmp_path)
    supersedes = [e for e in graph.edges if e.kind == "supersedes"]
    assert len(supersedes) == 1
    assert supersedes[0].source == "adr-0050"
    assert supersedes[0].target == "adr-0001"


def test_graph_to_json_round_trip(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "base", "engineering", "demo")
    _seed_adr(tmp_path, "0001", "First", "demo")
    graph = graph_builder.build_graph(tmp_path)
    payload = graph_builder.graph_to_json(graph)
    assert "nodes" in payload and "edges" in payload
    # Round-trip via JSON.
    text = json.dumps(payload)
    reread = json.loads(text)
    assert {n["id"] for n in reread["nodes"]} == {n.id for n in graph.nodes}


def test_write_graph_creates_parent_dir(tmp_path: Path) -> None:
    _seed_skill(tmp_path, "base", "engineering", "demo")
    graph = graph_builder.build_graph(tmp_path)
    out = tmp_path / "out" / "nested" / "graph.json"
    graph_builder.write_graph(graph, out)
    assert out.is_file()
    assert "demo" in out.read_text(encoding="utf-8")


def test_empty_repo_produces_empty_graph(tmp_path: Path) -> None:
    graph = graph_builder.build_graph(tmp_path)
    assert graph.nodes == []
    assert graph.edges == []


def test_hyphenated_skill_name_not_matched_inside_compound(
    tmp_path: Path,
) -> None:
    """Python's `\\b` does not fire as expected at hyphen boundaries,
    so a naive `\\bto-prd\\b` would match inside `push-to-prd-v2`.
    The graph builder must use a hyphen-aware boundary."""
    _seed_skill(tmp_path, "base", "engineering", "to-prd")
    # ADR body mentions a longer compound that contains "to-prd"
    # as a substring but is NOT a reference to the skill.
    _seed_adr(
        tmp_path, "0001", "Compound",
        body="The push-to-prd-v2 pipeline was deprecated last quarter.",
    )
    graph = graph_builder.build_graph(tmp_path)
    mentions = [e for e in graph.edges if e.kind == "mentions"]
    assert mentions == [], (
        "compound name push-to-prd-v2 should not produce a to-prd mention"
    )


def test_hyphenated_skill_name_still_matches_real_reference(
    tmp_path: Path,
) -> None:
    """Sanity check that the hyphen-aware boundary still fires for
    genuine references, not just compound exclusions."""
    _seed_skill(tmp_path, "base", "engineering", "to-prd")
    _seed_adr(
        tmp_path, "0001", "Real",
        body="The to-prd skill is the canonical example here.",
    )
    graph = graph_builder.build_graph(tmp_path)
    mentions = [e for e in graph.edges if e.kind == "mentions"]
    assert len(mentions) == 1
