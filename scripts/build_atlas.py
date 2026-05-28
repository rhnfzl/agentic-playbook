#!/usr/bin/env python3
"""Build the Why Atlas under docs/atlas/.

Walks the corpus, builds the JSON adjacency, renders one HTML page
per ADR + skill + trajectory, plus an index. Cross-subsystem signals
(AI-BOM, telemetry, trajectory pass/fail) are picked up at render
time and shown as badges; missing signals degrade gracefully.

Usage:
  python3 scripts/build_atlas.py
  python3 scripts/build_atlas.py --out /tmp/atlas
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from atlas import graph_builder, template_engine as tpl  # noqa: E402


_ATLAS_CSS = """\
:root {
  --bg: #fafafa;
  --fg: #1c1c1c;
  --muted: #6c6c6c;
  --accent: #2a4d8d;
  --border: #d8d8d8;
  --code-bg: #f0f0f0;
}
body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
}
nav.atlas-nav {
  background: var(--accent);
  color: white;
  padding: 0.75rem 2rem;
}
nav.atlas-nav a { color: white; margin-right: 1rem; text-decoration: none; font-weight: 600; }
nav.atlas-nav a:hover { text-decoration: underline; }
main { max-width: 1024px; margin: 0 auto; padding: 2rem; }
h1 { font-size: 1.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; }
ul { padding-left: 1.5rem; }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.75rem;
  margin-right: 0.4rem;
  background: var(--code-bg);
  color: var(--fg);
}
.badge-ok { background: #d4edda; color: #155724; }
.badge-warn { background: #fff3cd; color: #856404; }
.badge-fail { background: #f8d7da; color: #721c24; }
.badge-info { background: #d1ecf1; color: #0c5460; }
.muted { color: var(--muted); }
code, pre { background: var(--code-bg); padding: 0.1rem 0.3rem; border-radius: 0.2rem; }
pre { padding: 1rem; overflow-x: auto; }
.atlas-footer {
  max-width: 1024px;
  margin: 2rem auto;
  padding: 1rem 2rem;
  color: var(--muted);
  font-size: 0.85rem;
  border-top: 1px solid var(--border);
}
"""


def _load_ai_bom(repo_root: Path) -> dict:
    p = repo_root / "docs" / "security" / "ai-bom.json"
    if not p.is_file():
        return {"components": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"components": []}


def _load_telemetry_aggregates() -> list:
    """Best-effort fetch of per-skill aggregates. Empty when telemetry
    is off or the JSONL is missing."""
    try:
        from telemetry import is_enabled, storage_path
        from telemetry.ingest import aggregate, read_jsonl
    except ImportError:
        return []
    if not is_enabled() or not storage_path().is_file():
        return []
    return aggregate(read_jsonl())


def _render_index(graph: graph_builder.Graph) -> str:
    adrs = [n for n in graph.nodes if n.kind == "adr"]
    skills = [n for n in graph.nodes if n.kind == "skill"]
    trajectories = [n for n in graph.nodes if n.kind == "trajectory"]
    body = (
        "<h1>Why Atlas</h1>"
        "<p>A navigable index of every ADR, skill, and trajectory in this playbook. "
        "Every page is auto-generated; the rationale graph stays in sync with the source.</p>"
        + tpl.section(
            f"ADRs ({len(adrs)})",
            [tpl.link(n.href, n.label) for n in adrs],
            id_="adrs",
        )
        + tpl.section(
            f"Skills ({len(skills)})",
            [tpl.link(n.href, n.label) for n in skills],
            id_="skills",
        )
        + tpl.section(
            f"Trajectories ({len(trajectories)})",
            [tpl.link(n.href, n.label) for n in trajectories],
            id_="trajectories",
        )
    )
    return tpl.page(title="Why Atlas", root="./", body=body)


def _render_adr(node: graph_builder.Node, source_text: str,
                incoming_edges: list[graph_builder.Edge],
                node_index: dict) -> str:
    incoming = [
        tpl.link(f"../{node_index[e.source].href}", node_index[e.source].label)
        for e in incoming_edges if e.target == node.id and e.source in node_index
    ]
    body = (
        f"<h1>{tpl.escape(node.label)}</h1>"
        f'<p class="muted">Source: <code>{tpl.escape(node.meta.get("source_path", ""))}</code></p>'
        f'<pre>{tpl.escape(source_text)}</pre>'
        + tpl.section("Mentioned by", incoming or [])
    )
    return tpl.page(title=node.label, root="../", body=body)


def _render_skill(node: graph_builder.Node,
                  bom_index: dict,
                  telemetry_index: dict,
                  trajectory_targets: list,
                  incoming_adrs: list,
                  node_index: dict) -> str:
    meta = node.meta
    bom_entry = bom_index.get(meta.get("source_path", "").rsplit("/SKILL.md", 1)[0], {})
    vetted = bom_entry.get("vetted_as_of")
    telemetry_entry = telemetry_index.get(meta.get("name", ""))

    badges: list[str] = []
    if vetted:
        badges.append(tpl.badge("ok", "vetted", vetted))
    elif bom_entry:
        badges.append(tpl.badge("warn", "vetted", "unvetted"))
    if telemetry_entry is not None:
        badges.append(tpl.badge("info", "triggers", str(telemetry_entry["trigger_count"])))
        badges.append(tpl.badge(
            "info", "last fired",
            telemetry_entry["last_fired_at"][:10] or "unknown",
        ))
    if trajectory_targets:
        badges.append(tpl.badge("info", "trajectories", str(len(trajectory_targets))))

    detail_rows = "".join(
        f"<dt>{tpl.escape(k)}</dt><dd>{tpl.escape(v)}</dd>"
        for k, v in [
            ("name", meta.get("name", "")),
            ("version", meta.get("version", "")),
            ("owner", meta.get("owner", "")),
            ("last_reviewed", meta.get("last_reviewed", "")),
            ("scope", meta.get("scope", "")),
            ("category", meta.get("category", "")),
            ("source_path", meta.get("source_path", "")),
        ]
        if v
    )

    body = (
        f"<h1>{tpl.escape(node.label)}</h1>"
        f'<p>{tpl.escape(meta.get("description", ""))}</p>'
        f"<p>{' '.join(badges)}</p>"
        f"<dl>{detail_rows}</dl>"
        + tpl.section(
            "Trajectories targeting this skill",
            [tpl.link(f"../{node_index[tid].href}", node_index[tid].label)
             for tid in trajectory_targets if tid in node_index],
        )
        + tpl.section(
            "ADRs mentioning this skill",
            [tpl.link(f"../{node_index[aid].href}", node_index[aid].label)
             for aid in incoming_adrs if aid in node_index],
        )
    )
    return tpl.page(title=node.label, root="../", body=body)


def _render_trajectory(node: graph_builder.Node, source_text: str,
                       node_index: dict, edges: list) -> str:
    target_id = next(
        (e.target for e in edges if e.source == node.id and e.kind == "belongs_to"),
        None,
    )
    skill_link = (
        tpl.link(f"../{node_index[target_id].href}", node_index[target_id].label)
        if target_id and target_id in node_index else "<em>unknown</em>"
    )
    body = (
        f"<h1>{tpl.escape(node.label)}</h1>"
        f'<p class="muted">Source: <code>{tpl.escape(node.meta.get("source_path", ""))}</code></p>'
        f"<p>Targets skill: {skill_link}</p>"
        f"<pre>{tpl.escape(source_text)}</pre>"
    )
    return tpl.page(title=node.label, root="../", body=body)


def build_site(repo_root: Path, out_dir: Path) -> int:
    graph = graph_builder.build_graph(repo_root)
    node_index = {n.id: n for n in graph.nodes}
    bom = _load_ai_bom(repo_root)
    bom_index: dict = {}
    for component in bom.get("components", []):
        path = component.get("path") if isinstance(component, dict) else None
        if isinstance(path, str):
            bom_index[path] = component

    aggregates = _load_telemetry_aggregates()
    telemetry_index = {a.skill: a._asdict() for a in aggregates}

    incoming_by_target: dict[str, list[graph_builder.Edge]] = {}
    for edge in graph.edges:
        incoming_by_target.setdefault(edge.target, []).append(edge)
    outgoing_by_source: dict[str, list[graph_builder.Edge]] = {}
    for edge in graph.edges:
        outgoing_by_source.setdefault(edge.source, []).append(edge)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "static").mkdir(parents=True, exist_ok=True)
    (out_dir / "static" / "atlas.css").write_text(_ATLAS_CSS, encoding="utf-8")

    (out_dir / "index.html").write_text(_render_index(graph), encoding="utf-8")

    for node in graph.nodes:
        target = out_dir / node.href
        target.parent.mkdir(parents=True, exist_ok=True)

        if node.kind == "adr":
            source_text = (repo_root / node.meta["source_path"]).read_text(
                encoding="utf-8", errors="replace",
            )
            html_text = _render_adr(
                node, source_text,
                incoming_by_target.get(node.id, []), node_index,
            )
        elif node.kind == "skill":
            trajectory_targets = [
                e.source for e in incoming_by_target.get(node.id, [])
                if e.kind == "belongs_to"
            ]
            incoming_adrs = [
                e.source for e in incoming_by_target.get(node.id, [])
                if e.kind == "mentions"
            ]
            html_text = _render_skill(
                node, bom_index, telemetry_index,
                trajectory_targets, incoming_adrs, node_index,
            )
        elif node.kind == "trajectory":
            source_text = (repo_root / node.meta["source_path"]).read_text(
                encoding="utf-8", errors="replace",
            )
            html_text = _render_trajectory(
                node, source_text, node_index,
                outgoing_by_source.get(node.id, []),
            )
        else:
            continue
        target.write_text(html_text, encoding="utf-8")

    graph_builder.write_graph(graph, out_dir / "graph.json")
    print(f"  ok  atlas built at {out_dir.relative_to(repo_root)} "
          f"({len(graph.nodes)} node(s), {len(graph.edges)} edge(s))")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="defaults to <repo-root>/docs/atlas",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    out_dir = args.out.resolve() if args.out else repo_root / "docs" / "atlas"
    return build_site(repo_root, out_dir)


if __name__ == "__main__":
    sys.exit(main())
