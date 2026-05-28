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
    Trajectory,
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
    roots override earlier ones, so `overlays/team/rules/foo.md`
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
    roots override earlier ones, so `overlays/team/hooks/X.sh`
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
    # let `base/mcp/foo.json` AND `overlays/team/mcp/foo/server.json`
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
    roots override earlier ones, so `overlays/team/agents/X.md`
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
    roots override earlier ones, so `overlays/team/commands/X.md`
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


def _parse_inline_list(raw: str) -> list[str]:
    """Parse YAML inline list `[a, b, c]` (or bare string) into list[str]."""
    s = raw.strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [
            tok.strip().strip('"').strip("'")
            for tok in inner.split(",")
            if tok.strip()
        ]
    return [s.strip('"').strip("'")]


def _split_top_level_commas(s: str) -> list[str]:
    """Split `s` on commas that are NOT inside braces or brackets. Used to
    tokenize a YAML flow-style sequence like `{a: 1, b: 2}, {c: 3, d: 4}`
    into the two map literals without breaking the inner `a: 1, b: 2`."""
    out: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(s):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(s[start:i])
            start = i + 1
    out.append(s[start:])
    return [tok.strip() for tok in out if tok.strip()]


def _parse_inline_dict(s: str) -> dict[str, str]:
    """Parse `{k: v, k2: v2}` into a dict. Tolerant of quoted scalars."""
    body = s.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1]
    result: dict[str, str] = {}
    for token in _split_top_level_commas(body):
        if ":" not in token:
            continue
        k, v = token.split(":", 1)
        result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def _parse_inline_list_of_dicts(raw: str) -> list[dict[str, str]]:
    """Parse `[{a: 1, b: 2}, {c: 3}]` into a list of dicts. Returns []
    if the shape is not recognized; the linter is the gate."""
    s = raw.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return []
    inner = s[1:-1].strip()
    if not inner:
        return []
    out: list[dict[str, str]] = []
    for token in _split_top_level_commas(inner):
        if token.startswith("{") and token.endswith("}"):
            out.append(_parse_inline_dict(token))
    return out


def _parse_trajectory_body(body: str) -> tuple[list[str], list[dict], dict]:
    """Parse trajectory YAML body into (phrasings, assertions, llm_judge).

    Naive parser tuned to the documented trajectory shape (ADR-0044).
    Out-of-shape content (deeply nested assertion values, etc.) is left for
    the trajectory linter (scripts/checks/trajectory.py) to surface; we
    return what we can read so the linter has an attribution path.

    Shape we understand:

      input:
        phrasings:
          - "first phrasing"
          - "second phrasing"
        variant_strategy: parallel        # captured under llm_judge meta? no
                                          # variant_strategy is reader-ignored

      assertions:
        - simple_key: value
        - another_key: value

      llm_judge:
        threshold: 0.7
        rubric: |
          multi
          line
        model: claude-sonnet-4-6
    """
    phrasings: list[str] = []
    assertions: list[dict] = []
    llm_judge: dict = {}

    section: str | None = None
    in_phrasings = False
    in_rubric_block = False
    rubric_indent: int | None = None
    rubric_lines: list[str] = []

    for raw in body.splitlines():
        if in_rubric_block:
            # Block-scalar collection. End when we hit a less-indented line.
            stripped = raw.rstrip()
            if not stripped.strip():
                rubric_lines.append("")
                continue
            indent = len(raw) - len(raw.lstrip())
            if rubric_indent is None:
                rubric_indent = indent
            if indent < rubric_indent:
                # End of block scalar; close it and re-process this line.
                llm_judge["rubric"] = "\n".join(rubric_lines).rstrip()
                in_rubric_block = False
                rubric_lines = []
                rubric_indent = None
                # Fall through to normal handling for this line.
            else:
                rubric_lines.append(raw[rubric_indent:])
                continue

        line_stripped = raw.lstrip()
        if line_stripped.startswith("#") or not line_stripped:
            continue
        line = raw.rstrip()

        # Top-level section detection (zero indent + `name:` form).
        if line and not line.startswith(" "):
            head = line.split(":", 1)[0].strip()
            if head == "input":
                section = "input"
                in_phrasings = False
                continue
            if head == "assertions":
                section = "assertions"
                in_phrasings = False
                continue
            if head == "llm_judge":
                section = "llm_judge"
                in_phrasings = False
                continue
            section = None
            in_phrasings = False
            continue

        if section == "input":
            # `  phrasings:` opens a list of strings.
            if line.lstrip().startswith("phrasings:"):
                in_phrasings = True
                continue
            if in_phrasings and line.lstrip().startswith("- "):
                phrasings.append(
                    line.split("- ", 1)[1].strip().strip('"').strip("'")
                )
                continue
            # Any non-list-item under input ends the phrasings sub-section.
            if in_phrasings and not line.lstrip().startswith("- "):
                in_phrasings = False

        elif section == "assertions":
            # Each list item is `  - key: value` (single-pair dict). Values
            # may be:
            #   - bare scalars (e.g. `must_invoke_tool: Write`),
            #   - inline lists of scalars (e.g. `no_skill_load_after: [a, b]`),
            #   - inline lists of dicts (e.g. `call_order:
            #     [{tool: X, before: Y}, {tool: A, before: B}]`).
            # The naive YAML parser does NOT cover block-scalar nested forms;
            # the linter rejects those with a clear message rather than
            # silently dropping them.
            if line.lstrip().startswith("- "):
                payload = line.split("- ", 1)[1]
                if ":" in payload:
                    k, v = payload.split(":", 1)
                    key = k.strip()
                    raw_value = v.strip()
                    value: object = raw_value.strip('"').strip("'")
                    if raw_value.startswith("[{") and raw_value.endswith("]"):
                        value = _parse_inline_list_of_dicts(raw_value)
                    elif raw_value.startswith("[") and raw_value.endswith("]"):
                        value = _parse_inline_list(raw_value)
                    assertions.append({key: value})

        elif section == "llm_judge":
            payload = line.strip()
            if ":" in payload:
                k, v = payload.split(":", 1)
                key = k.strip()
                value_str = v.strip()
                if value_str == "|":
                    # Open a block scalar; collect indented lines below.
                    in_rubric_block = True
                    rubric_lines = []
                    rubric_indent = None
                    continue
                # Coerce numeric values.
                cleaned = value_str.strip('"').strip("'")
                if key == "threshold":
                    try:
                        llm_judge[key] = float(cleaned)
                    except ValueError:
                        llm_judge[key] = cleaned
                else:
                    llm_judge[key] = cleaned

    # Close any unterminated block scalar at EOF.
    if in_rubric_block:
        llm_judge["rubric"] = "\n".join(rubric_lines).rstrip()

    return phrasings, assertions, llm_judge


def load_trajectories(content_paths: ContentPaths) -> list[Trajectory]:
    """Load trajectory YAML files across content roots with overlay-wins merge.

    v0.2 (ADR-0044): the 8th content type. Trajectory files live at
    `<root>/trajectories/<skill>/<scenario>.yaml`. The reader is permissive:
    files without frontmatter come back with empty frontmatter so the
    trajectory linter (scripts/checks/trajectory.py) can attribute failures
    to a specific path. Files outside the documented shape (extra keys,
    deeply nested values) are read best-effort; the linter is the gate.

    Key for overlay merge is `(skill, scenario)`; later roots win.
    """
    by_key: dict[tuple[str, str], Trajectory] = {}
    for root in content_paths.roots:
        trajectories_dir = root / "trajectories"
        if not trajectories_dir.is_dir():
            continue
        for skill_dir in sorted(p for p in trajectories_dir.iterdir() if p.is_dir()):
            skill_name = skill_dir.name
            for traj_yaml in sorted(skill_dir.glob("*.yaml")):
                scenario = traj_yaml.stem
                text = traj_yaml.read_text(encoding="utf-8")
                fm, body = _parse_frontmatter(text)
                phrasings, assertions, llm_judge = _parse_trajectory_body(body)
                adapter_scope_raw = fm.get("adapter_scope", "")
                adapter_scope = _parse_inline_list(adapter_scope_raw)
                by_key[(skill_name, scenario)] = Trajectory(
                    path=traj_yaml,
                    skill=skill_name,
                    scenario=scenario,
                    frontmatter=fm,
                    body=body,
                    input_phrasings=phrasings,
                    assertions=assertions,
                    llm_judge=llm_judge,
                    adapter_scope=adapter_scope,
                    model_pinned=fm.get("model_pinned", "").strip(),
                )
    return sorted(by_key.values(), key=lambda t: (t.skill, t.scenario))


def load_prompts(content_paths: ContentPaths) -> list[Prompt]:
    """Load prompts/*.md across content roots with overlay-wins merge.

    v0.11 (ADR-0040): walks each root in `content_paths.roots`. Later
    roots override earlier ones, so `overlays/team/prompts/X.md`
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
