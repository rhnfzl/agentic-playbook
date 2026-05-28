"""AI Bill of Materials emitter.

Walks the playbook and produces `docs/security/ai-bom.json` listing
every external skill source, every vendored MCP bundle, and (where
known) the upstream pinned SHA. Consumers:

  * Atlas renders a "vetted as of" badge per skill from the BOM
  * `make audit-security` checks the BOM is fresh
  * Future supply-chain CVE feeds can diff against the BOM

The BOM is deliberately flat JSON, not SBOM/CycloneDX, because we
want it readable by people skimming the atlas. A CycloneDX export
can be added later as a derived view if a customer asks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_text_safely(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _vetted_as_of(skill_dir: Path) -> str | None:
    marker = skill_dir / ".vetted-as-of"
    if not marker.is_file():
        return None
    raw = _read_text_safely(marker).strip()
    return raw or None


def _skill_frontmatter_field(skill_md: Path, key: str) -> str | None:
    text = _read_text_safely(skill_md)
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    head = text[3:end]
    needle = f"{key}:"
    for line in head.splitlines():
        line = line.strip()
        if line.startswith(needle):
            return line[len(needle):].strip().strip('"').strip("'")
    return None


def _imported_skill_sources(repo_root: Path) -> list[dict]:
    rows: list[dict] = []
    base = repo_root / "base" / "skills" / "imported"
    if not base.is_dir():
        return rows
    for source_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        source = source_dir.name
        for skill_md in sorted(source_dir.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            rows.append({
                "kind": "imported_skill",
                "source": source,
                "path": str(skill_dir.relative_to(repo_root)),
                "name": _skill_frontmatter_field(skill_md, "name"),
                "version": _skill_frontmatter_field(skill_md, "version"),
                "vetted_as_of": _vetted_as_of(skill_dir),
            })
    return rows


def _vendored_mcp_bundles(repo_root: Path) -> list[dict]:
    rows: list[dict] = []
    bundles = repo_root / "base" / "mcp"
    if not bundles.is_dir():
        return rows
    for bundle in sorted(p for p in bundles.iterdir() if p.is_dir()):
        manifest = bundle / "manifest.toml"
        version: str | None = None
        if manifest.is_file():
            for line in _read_text_safely(manifest).splitlines():
                line = line.strip()
                if line.startswith("version"):
                    version = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    break
        rows.append({
            "kind": "mcp_bundle",
            "name": bundle.name,
            "path": str(bundle.relative_to(repo_root)),
            "version": version,
            "vetted_as_of": _vetted_as_of(bundle),
        })
    return rows


def build_bom(repo_root: Path) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repo": "agentic-playbook",
        "components": _imported_skill_sources(repo_root) + _vendored_mcp_bundles(repo_root),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parent.parent.parent
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="defaults to <repo-root>/docs/security/ai-bom.json",
    )
    parser.add_argument(
        "--print", action="store_true",
        help="also print BOM to stdout",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    output = args.output or (repo_root / "docs" / "security" / "ai-bom.json")
    output.parent.mkdir(parents=True, exist_ok=True)

    bom = build_bom(repo_root)
    output.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
    print(f"  ok  AI-BOM written to {output.relative_to(repo_root)} "
          f"({len(bom['components'])} component(s))")
    if args.print:
        print(json.dumps(bom, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
