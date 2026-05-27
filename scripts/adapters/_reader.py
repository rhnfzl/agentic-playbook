"""
Content scanners: load all seven content types from the playbook repo.

Per ADR-0031: this module is the read half of the former monolithic
_loader.py. It walks the repo's content directories (skills/, rules/,
hooks/, mcp/, agents/, commands/, prompts/) and returns typed NamedTuples
from _protocol.py. No writes happen here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterator

from ._protocol import (
    Agent,
    Command,
    ContentPaths,
    Hook,
    McpConfig,
    Prompt,
    Rule,
    Skill,
)


def _walk_content_roots(
    content_paths: ContentPaths,
    subdir: str,
    glob: str,
) -> Iterator[Path]:
    """Yield matching paths across content roots in load order.

    v0.11 (ADR-0040): roots are walked in order; the caller keys results
    into a dict so later (overlay) entries override earlier (base) ones.
    Skips roots whose `subdir` does not exist (lets each load_*() not
    repeat the is_dir() guard).
    """
    for root in content_paths.roots:
        type_dir = root / subdir
        if not type_dir.is_dir():
            continue
        for path in sorted(type_dir.glob(glob)):
            yield path


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body) or ({}, full_content) if no frontmatter."""
    if not content.startswith("---"):
        return {}, content
    try:
        end = content.index("---", 3)
    except ValueError:
        return {}, content

    block = content[3:end]
    body = content[end + 3 :].lstrip("\n")
    fm: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(\w+)\s*:\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm, body


def load_skills(content_paths: ContentPaths) -> list[Skill]:
    """Load SKILL.md files across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones. Key for overlay merge is
    `(category, install_name)` to avoid spurious overrides when an
    imported skill happens to share a name with a first-party skill.

    Each Skill gets `name` (dir name from filesystem, matches frontmatter
    for first-party skills) and `install_name` (collision-safe install
    slug). Imported skills (under skills/imported/<source>/...) get
    install_name `imported-<source>-<name>` so they cannot overwrite
    first-party skills with the same name (e.g. mattpocock's `diagnose`
    would collide with our own `engineering/diagnose` without this
    namespacing).
    """
    by_key: dict[tuple[str, str], Skill] = {}
    # Skills use rglob (skills/<cat>/<name>/SKILL.md); per-root walk lets
    # the relative-parts decode the category from the root-relative path.
    for root in content_paths.roots:
        skills_dir = root / "skills"
        if not skills_dir.is_dir():
            continue
        for skill_md in sorted(skills_dir.rglob("SKILL.md")):
            content = skill_md.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(content)
            rel_parts = skill_md.relative_to(skills_dir).parts
            category = rel_parts[0] if len(rel_parts) >= 2 else "uncategorized"
            name = rel_parts[-2] if len(rel_parts) >= 2 else "unknown"

            if rel_parts and rel_parts[0] == "imported" and len(rel_parts) >= 3:
                source = rel_parts[1]
                install_name = f"imported-{source}-{name}"
            else:
                install_name = name

            by_key[(category, install_name)] = Skill(
                path=skill_md,
                category=category,
                name=name,
                frontmatter=fm,
                body=body,
                install_name=install_name,
            )
    return sorted(by_key.values(), key=lambda s: (s.category, s.install_name))


def load_rules(content_paths: ContentPaths) -> list[Rule]:
    """Load rules/*.md across all content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/<name>/rules/foo.md`
    overrides `base/rules/foo.md` when both exist.

    README.md is excluded (it's directory documentation, not a rule).
    AGENTS.md IS loaded as a rule by current install behavior; preserved
    for backward compat in v0.11.
    """
    by_name: dict[str, Rule] = {}
    for rule_md in _walk_content_roots(content_paths, "rules", "*.md"):
        if rule_md.name in ("README.md",):
            continue
        body = rule_md.read_text(encoding="utf-8")
        by_name[rule_md.stem] = Rule(
            path=rule_md, name=rule_md.stem, body=body
        )
    return sorted(by_name.values(), key=lambda r: r.name)


def load_hooks(content_paths: ContentPaths) -> list[Hook]:
    """Load hooks/*.sh across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/<name>/hooks/X.sh`
    overrides `base/hooks/X.sh` when both exist.

    v0.6: skip underscore-prefixed files (e.g. _cascade-translate.sh).
    Those are adapter-internal helper scripts, not hooks themselves;
    each adapter copies + invokes them directly without going through
    the hook registration pipeline.
    """
    by_name: dict[str, Hook] = {}
    for hook in _walk_content_roots(content_paths, "hooks", "*.sh"):
        if hook.name.startswith("_"):
            continue
        by_name[hook.stem] = _load_single_hook(hook)
    return sorted(by_name.values(), key=lambda h: h.name)


def _load_single_hook(hook: Path) -> Hook:
    """Helper: build a Hook from one shell-script path."""
    body = hook.read_text(encoding="utf-8")
    return Hook(path=hook, name=hook.stem, body=body)


def load_mcp_configs(content_paths: ContentPaths) -> list[McpConfig]:
    """Load MCP configs across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later roots
    override earlier ones, so an overlay can replace a base MCP config with
    the same name. Within a single root, two layouts coexist:
      1. <root>/mcp/<name>.json (flat) for hosted or npx MCPs.
      2. <root>/mcp/<name>/server.json (dir) for locally-hosted Python MCPs
         that ship their own .py source. The source_dir field on the
         returned McpConfig tells adapters and materialize_mcp_sources where
         to find the source files to symlink into
         ~/.config/agent-shared/mcp_servers/<name>/.

    Returns flat-first, then directory configs, alphabetized within each
    group; overlay wins by name within each group.
    """
    # Single dict keyed by name across BOTH layouts (flat *.json and
    # subdir/server.json). v0.11 Codex second-eye fix: an earlier
    # implementation kept separate dicts and concatenated them, which
    # let `base/mcp/foo.json` AND `overlays/<name>/mcp/foo/server.json`
    # both survive instead of overlay winning by name. The order of
    # discovery within each root is flat-first-then-dir, so a same-name
    # collision inside ONE root prefers the dir layout (richer; has
    # source_dir). Across roots, later roots (overlays) win by name.
    by_name: dict[str, McpConfig] = {}
    for root in content_paths.roots:
        mcp_dir = root / "mcp"
        if not mcp_dir.is_dir():
            continue
        for mcp_json in sorted(mcp_dir.glob("*.json")):
            try:
                cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            by_name[mcp_json.stem] = McpConfig(
                path=mcp_json, name=mcp_json.stem, config=cfg, source_dir=None
            )
        for subdir in sorted(p for p in mcp_dir.iterdir() if p.is_dir()):
            server_json = subdir / "server.json"
            if not server_json.is_file():
                continue
            try:
                cfg = json.loads(server_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            by_name[subdir.name] = McpConfig(
                path=server_json, name=subdir.name, config=cfg, source_dir=subdir
            )
    # Sort flat-first-then-dir (preserves the prior contract); within
    # each group sort alphabetically.
    flat = [m for m in by_name.values() if m.source_dir is None]
    directory = [m for m in by_name.values() if m.source_dir is not None]
    return (
        sorted(flat, key=lambda m: m.name)
        + sorted(directory, key=lambda m: m.name)
    )


def load_agents(content_paths: ContentPaths) -> list[Agent]:
    """Load agents/*.md across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/<name>/agents/X.md`
    overrides `base/agents/X.md` when both exist.

    Per ADR-0009 schema: YAML frontmatter + markdown body. Files lacking
    `name` or `description` (README.md, AGENTS.md) are silently skipped.
    """
    by_name: dict[str, Agent] = {}
    for agent_md in _walk_content_roots(content_paths, "agents", "*.md"):
        content = agent_md.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(content)
        if not fm.get("name") or not fm.get("description"):
            continue
        by_name[agent_md.stem] = Agent(
            path=agent_md, name=agent_md.stem, frontmatter=fm, body=body
        )
    return sorted(by_name.values(), key=lambda a: a.name)


def load_commands(content_paths: ContentPaths) -> list[Command]:
    """Load commands/*.md across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/<name>/commands/X.md`
    overrides `base/commands/X.md` when both exist. User-triggered
    slash actions (Cursor/Claude commands). Files lacking frontmatter
    name+description are silently skipped (README.md, AGENTS.md).
    """
    by_name: dict[str, Command] = {}
    for cmd_md in _walk_content_roots(content_paths, "commands", "*.md"):
        content = cmd_md.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(content)
        if not fm.get("name") or not fm.get("description"):
            continue
        by_name[cmd_md.stem] = Command(
            path=cmd_md, name=cmd_md.stem, frontmatter=fm, body=body
        )
    return sorted(by_name.values(), key=lambda c: c.name)


def load_prompts(content_paths: ContentPaths) -> list[Prompt]:
    """Load prompts/*.md across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/<name>/prompts/X.md`
    overrides `base/prompts/X.md` when both exist.

    Existing prompts/*.md without frontmatter `name` are setup /
    onboarding docs (bootstrap-your-playbook, etc.) and are NOT
    runtime templates; they're silently skipped. README.md is also
    skipped explicitly.

    Runtime template format (Pi-flavored /name expansion):
      ---
      name: my-template
      description: When to use this template
      ---

      Template body with {{placeholders}}.
    """
    by_name: dict[str, Prompt] = {}
    for prompt_md in _walk_content_roots(content_paths, "prompts", "*.md"):
        if prompt_md.name in ("README.md",):
            continue
        content = prompt_md.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(content)
        if not fm.get("name"):
            continue
        by_name[prompt_md.stem] = Prompt(
            path=prompt_md, name=prompt_md.stem, body=body
        )
    return sorted(by_name.values(), key=lambda p: p.name)
