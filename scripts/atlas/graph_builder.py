"""Build the JSON adjacency the Atlas D3 graph consumes.

Three node kinds, three edge kinds:

  Nodes
    * adr        from docs/adr/*.md
    * skill      from base/skills/<category>/<name>/SKILL.md
    * trajectory from base/trajectories/<skill>/<scenario>.yaml

  Edges
    * adr -> skill       if the ADR body mentions a skill name
    * trajectory -> skill   trajectory belongs to that skill
                            (directory layout under base/trajectories/)
    * adr -> adr         if A's body contains "Supersedes 00XX"

We deliberately do NOT compute skill -> skill from body text. The
signal is too noisy without curation: most SKILL.md bodies
reference other skills as examples or alternatives, not as a
dependency. A future ADR can add a `requires:` frontmatter key and
this graph builder can pick it up; for now we leave that edge kind
out.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# Allow atlas to share the canonical frontmatter parser with decay,
# ai_bom, and any other consumer.
_SCRIPTS_PARENT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_PARENT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_PARENT))

from skill_identity import parse_frontmatter as _parse_frontmatter  # noqa: E402


_ADR_FILE_RE = re.compile(r"^(\d{4})-(.+)\.md$")
_ADR_SUPERSEDES_RE = re.compile(r"[Ss]upersed(?:e|es)\s+(?:ADR-)?(\d{2,4})")


class Node(NamedTuple):
    id: str          # stable URL slug, e.g. "adr-0044" or "skill-engineering-to-prd"
    kind: str        # "adr" | "skill" | "trajectory"
    label: str       # human-readable title
    href: str        # relative URL into docs/atlas/
    meta: dict       # extra fields rendered on the per-node page


class Edge(NamedTuple):
    source: str      # node id
    target: str      # node id
    kind: str        # "mentions" | "belongs_to" | "supersedes"


class Graph(NamedTuple):
    nodes: list[Node]
    edges: list[Edge]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _tracked_paths(repo_root: Path, subpath: str) -> set[Path] | None:
    """Return the set of git-tracked files under <repo_root>/<subpath>.

    Returns None if `git` is unavailable, repo_root is not a git repo,
    or the call fails. Callers should fall back to glob when None.

    The purpose is reproducibility: an untracked file in docs/adr/
    should not change the committed atlas. CI rebuilds from a clean
    checkout and would otherwise produce a diff against the committed
    pages.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", subpath],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    paths: set[Path] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            paths.add((repo_root / line).resolve())
    return paths


def _frontmatter(text: str) -> dict:
    """Thin wrapper around the canonical parse_frontmatter helper.

    Atlas keeps the local symbol so call sites do not change, but
    the implementation now delegates to the shared parser so future
    quirk fixes apply across atlas + ai_bom + decay at once.
    """
    fm, _ = _parse_frontmatter(text)
    return fm


def _adr_nodes(repo_root: Path) -> tuple[list[Node], dict[str, str]]:
    """Return ADR nodes + a {adr_id: body} cache.

    The cache is the single read of each ADR file; downstream edge
    functions (`_adr_to_skill_edges`, `_adr_to_adr_supersedes`) reuse
    it instead of re-reading from disk.

    When git is available we only consider tracked files, so an
    untracked ADR draft does not change the committed atlas. Falls
    back to a glob when git is unavailable (test scenarios on tmp
    directories).
    """
    adr_dir = repo_root / "docs" / "adr"
    if not adr_dir.is_dir():
        return [], {}
    tracked = _tracked_paths(repo_root, "docs/adr")
    nodes: list[Node] = []
    bodies: dict[str, str] = {}
    for adr_file in sorted(adr_dir.glob("*.md")):
        if adr_file.name == "README.md":
            continue
        if tracked is not None and adr_file.resolve() not in tracked:
            continue
        m = _ADR_FILE_RE.match(adr_file.name)
        if not m:
            continue
        number = m.group(1)
        text = _read_text(adr_file)
        title = adr_file.name[5:-3].replace("-", " ").strip()
        for line in text.splitlines():
            if line.startswith("#"):
                title = line.lstrip("# ").rstrip().lstrip(f"{number}. ")
                break
        node = Node(
            id=f"adr-{number}",
            kind="adr",
            label=f"ADR-{number}: {title}",
            href=f"adr/{number}.html",
            meta={"number": number, "source_path": str(adr_file.relative_to(repo_root))},
        )
        nodes.append(node)
        bodies[node.id] = text
    return nodes, bodies


def _skill_nodes(repo_root: Path) -> list[Node]:
    nodes: list[Node] = []
    for skill_root in (repo_root / "base" / "skills",
                       repo_root / "overlays" / "team" / "skills"):
        if not skill_root.is_dir():
            continue
        for skill_md in sorted(skill_root.rglob("SKILL.md")):
            rel = skill_md.parent.relative_to(skill_root)
            parts = list(rel.parts)
            if not parts:
                continue
            category = parts[0] if len(parts) > 1 else "uncategorized"
            name = parts[-1]
            fm = _frontmatter(_read_text(skill_md))
            scope = "base" if skill_root.name == "skills" and skill_root.parent.name == "base" else "team"
            node_id = f"skill-{scope}-{category}-{name}"
            nodes.append(Node(
                id=node_id,
                kind="skill",
                label=f"{category}/{name}",
                href=f"skill/{scope}-{category}-{name}.html",
                meta={
                    "name": fm.get("name", name),
                    "description": fm.get("description", ""),
                    "version": fm.get("version", ""),
                    "owner": fm.get("owner", ""),
                    "last_reviewed": fm.get("last_reviewed", ""),
                    "category": category,
                    "scope": scope,
                    "source_path": str(skill_md.relative_to(repo_root)),
                    "skill_name": fm.get("name", name),
                },
            ))
    return nodes


def _trajectory_nodes(repo_root: Path) -> list[Node]:
    nodes: list[Node] = []
    for root in (repo_root / "base" / "trajectories",
                 repo_root / "overlays" / "team" / "trajectories"):
        if not root.is_dir():
            continue
        for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for traj in sorted(skill_dir.glob("*.yaml")):
                slug = f"{skill_dir.name}-{traj.stem}"
                nodes.append(Node(
                    id=f"trajectory-{slug}",
                    kind="trajectory",
                    label=f"{skill_dir.name}/{traj.stem}",
                    href=f"trajectory/{slug}.html",
                    meta={
                        "skill_dir_name": skill_dir.name,
                        "scenario": traj.stem,
                        "source_path": str(traj.relative_to(repo_root)),
                    },
                ))
    return nodes


def _adr_to_skill_edges(adr_nodes: list[Node], skill_nodes: list[Node],
                        adr_bodies: dict[str, str]) -> list[Edge]:
    """Heuristic: if an ADR body contains a skill's frontmatter name as
    a whole word, add a mentions edge. Avoids false positives by
    requiring word + hyphen boundaries and a minimum length.

    Reads ADR bodies from the shared cache populated by `_adr_nodes`;
    avoids a second pass over disk."""
    skill_names: dict[str, str] = {}
    for n in skill_nodes:
        nm = n.meta.get("skill_name") or n.label.split("/")[-1]
        if isinstance(nm, str) and len(nm) >= 3:
            skill_names[nm] = n.id

    edges: list[Edge] = []
    for adr in adr_nodes:
        text = adr_bodies.get(adr.id, "")
        for name, sid in skill_names.items():
            # Hyphen is NOT a word character in Python's `re`, so `\b`
            # fires at hyphen boundaries. That means a search for
            # `to-prd` could match inside `push-to-prd-v2` at the hyphen.
            # We assert non-word AND non-hyphen on both sides so the
            # match is a true standalone reference, not a substring of
            # a longer compound name.
            if re.search(
                rf"(?<![\w-]){re.escape(name)}(?![\w-])",
                text,
            ):
                edges.append(Edge(source=adr.id, target=sid, kind="mentions"))
    return edges


def _trajectory_to_skill_edges(trajectory_nodes: list[Node],
                               skill_nodes: list[Node]) -> list[Edge]:
    """Trajectories live under base/trajectories/<skill-name>/. Map by
    matching skill_dir_name against skill labels."""
    by_short_name: dict[str, str] = {}
    for n in skill_nodes:
        short = n.label.split("/")[-1]
        by_short_name.setdefault(short, n.id)
    edges: list[Edge] = []
    for t in trajectory_nodes:
        target_short = t.meta.get("skill_dir_name", "")
        if isinstance(target_short, str):
            tid = by_short_name.get(target_short)
            if tid:
                edges.append(Edge(source=t.id, target=tid, kind="belongs_to"))
    return edges


def _adr_to_adr_supersedes(adr_nodes: list[Node],
                           adr_bodies: dict[str, str]) -> list[Edge]:
    """Reuses the body cache populated by `_adr_nodes`."""
    by_number: dict[str, str] = {n.meta["number"]: n.id for n in adr_nodes}
    edges: list[Edge] = []
    for adr in adr_nodes:
        text = adr_bodies.get(adr.id, "")
        for m in _ADR_SUPERSEDES_RE.finditer(text):
            raw = m.group(1).zfill(4)
            target_id = by_number.get(raw)
            if target_id and target_id != adr.id:
                edges.append(Edge(source=adr.id, target=target_id, kind="supersedes"))
    return edges


def build_graph(repo_root: Path) -> Graph:
    adrs, adr_bodies = _adr_nodes(repo_root)
    skills = _skill_nodes(repo_root)
    trajectories = _trajectory_nodes(repo_root)
    edges = (
        _adr_to_skill_edges(adrs, skills, adr_bodies)
        + _trajectory_to_skill_edges(trajectories, skills)
        + _adr_to_adr_supersedes(adrs, adr_bodies)
    )
    return Graph(nodes=adrs + skills + trajectories, edges=edges)


def graph_to_json(graph: Graph) -> dict:
    return {
        "nodes": [
            {"id": n.id, "kind": n.kind, "label": n.label, "href": n.href}
            for n in graph.nodes
        ],
        "edges": [
            {"source": e.source, "target": e.target, "kind": e.kind}
            for e in graph.edges
        ],
    }


def write_graph(graph: Graph, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph_to_json(graph), indent=2) + "\n", encoding="utf-8")
