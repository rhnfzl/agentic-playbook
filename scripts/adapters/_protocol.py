"""
Adapter Protocol + content types + cross-adapter reconciliation primitives.

Per ADR-0031: this module owns the typed contracts that every adapter
implements and the few helpers that operate on shared user-config files
(claude.json, cursor mcp.json, settings.json, etc.). Pure data and
protocols; no filesystem reads or writes beyond the in-place edits done
by reconcile_*.

Other split partners:
  _reader.py: loads PlaybookContent from disk.
  _writer.py: file writes (managed blocks, copy_skill_payload, etc.).
  _detect.py: detection helpers (which, vscode_extension_present, resolve_target).
  _loader.py: re-export shim that flattens all four back to a single namespace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Literal, NamedTuple, Protocol


MARKER_ID = "coding-agents-playbook"


class Skill(NamedTuple):
    path: Path  # path to SKILL.md
    category: str  # engineering/productivity/observability/meta
    name: str  # skill slug (matches directory name)
    frontmatter: dict[str, str]
    body: str  # everything after the closing --- of frontmatter
    install_name: str = (
        ""  # namespaced for collision-free install; falls back to name if empty
    )


class Rule(NamedTuple):
    path: Path
    name: str  # slug (matches filename without .md)
    body: str  # full markdown content


class Hook(NamedTuple):
    path: Path
    name: str  # slug
    body: str  # full script content


class McpConfig(NamedTuple):
    path: Path
    name: str  # slug
    config: dict  # parsed JSON
    source_dir: Path | None = (
        None  # set for Python-source MCPs at mcp/<name>/; None for flat mcp/<name>.json
    )


class Agent(NamedTuple):
    path: Path
    name: str  # slug
    frontmatter: dict[str, str]
    body: str


class Command(NamedTuple):
    path: Path
    name: str  # slug
    frontmatter: dict[str, str]
    body: str


class Prompt(NamedTuple):
    path: Path
    name: str  # slug
    body: str


class Trajectory(NamedTuple):
    """Cross-adapter trajectory spec (ADR-0043, 8th content type).

    Each Trajectory binds one (skill, scenario) to a 5-phrasings prompt
    set, a list of DSL assertions over the resulting tool-call trace,
    and an LLM-judge rubric. The harness consumes Trajectory instances
    and replays them across each adapter in `adapter_scope`.

    Field semantics:
      path             -- on-disk YAML at base/trajectories/<skill>/<scenario>.yaml
      skill            -- skill slug; must resolve to base/skills/<cat>/<skill>/
      scenario         -- scenario slug; matches filename without .yaml
      frontmatter      -- raw frontmatter dict (name, description, version,
                          owner, last_reviewed, tags, etc.)
      body             -- everything after the closing --- of the frontmatter
      input_phrasings  -- ordered list of user-prompt variants (typically 5)
      assertions       -- list of DSL-assertion dicts (see ADR-0045)
      llm_judge        -- judge config: {threshold, rubric, model}
      adapter_scope    -- which adapters must pass; subset of Tier-1 names
      model_pinned     -- model the reference was captured against (drift signal)
    """

    path: Path
    skill: str
    scenario: str
    frontmatter: dict[str, str]
    body: str
    input_phrasings: list[str]
    assertions: list[dict]
    llm_judge: dict
    adapter_scope: list[str]
    model_pinned: str


class InstalledPath(NamedTuple):
    """One path written or otherwise touched by an Adapter's install().

    The dispatcher hashes `path` at Lockfile-write time, so Adapters don't
    carry hashing responsibility. `ownership` follows the ADR-0023 model:
      "owned"   - playbook fully owns the file; safe to unlink on remove.
      "managed" - file mixes playbook + user content; remove never unlinks.
    """

    path: Path
    ownership: Literal["owned", "managed"]


class ContentPaths(NamedTuple):
    """Ordered content roots for the load pass (ADR-0040, v0.11).

    Each load_*() pass in _reader walks roots in order. Later roots
    override earlier ones (overlay-wins merge), so callers express the
    layering by ordering: `[base, overlay_team]` means the team
    overlay wins on conflicts.

    Pre-v0.11 callers passed `repo_root` directly. Their behavior is
    preserved by `resolve_content_paths(scope=None, repo_root)` which
    returns a single-root ContentPaths anchored at `base/` if present,
    falling back to `repo_root` so the loader keeps working during the
    v0.11 per-content-type migration window.
    """

    roots: list[Path]


def resolve_content_paths(
    scope: list[str] | None,
    repo_root: Path,
) -> ContentPaths:
    """Resolve a scope list to ordered content roots.

    Layering rule (ADR-0040):
      - `base/` is always first (or `repo_root` if `base/` does not
        exist yet, preserving pre-v0.11 layout while the refactor is
        in flight).
      - Each overlay in `scope` is appended in caller order. An overlay
        dir that does not exist is skipped silently; install-time profile
        validation (`validate_profile_scope`) catches missing required
        overlays earlier in the dispatch.

    `scope=None` is equivalent to `scope=[]` (base only). Callers needing
    auto-detect from git remote URL do that in `install.py` per the
    ADR-0040 matrix, then pass the resolved list here.
    """
    base = repo_root / "base"
    roots: list[Path] = [base if base.is_dir() else repo_root]

    if scope:
        for overlay_name in scope:
            overlay = repo_root / "overlays" / overlay_name
            if overlay.is_dir():
                roots.append(overlay)

    return ContentPaths(roots=roots)


class PlaybookContent(NamedTuple):
    """All eight content types pre-loaded once by the dispatcher.

    v0.2 (ADR-0043): trajectories joined the canonical content set. The
    install adapters still consume the original seven; trajectories are
    consumed by the harness (scripts/trajectory_harness.py) and the
    Phase 0 quality gates (scripts/checks/trajectory.py).

    Adapters receive a PlaybookContent through their install() method
    instead of calling load_*(repo_root) themselves. Loading once and
    passing in keeps the dispatcher pure-ish: same content -> same writes.
    """

    skills: list[Skill]
    rules: list[Rule]
    hooks: list[Hook]
    mcp_configs: list[McpConfig]
    agents: list[Agent]
    commands: list[Command]
    prompts: list[Prompt]
    trajectories: list[Trajectory] = []

    @classmethod
    def load(
        cls,
        repo_root: Path,
        scope: list[str] | None = None,
    ) -> "PlaybookContent":
        """Load all eight content types via ContentPaths (ADR-0040, ADR-0043).

        `scope` selects which overlays layer onto `base/` (None = base
        only). ALL load_*() functions are ContentPaths-shaped post-v0.11;
        the seam is `resolve_content_paths` + the overlay-wins merge in
        each loader.
        """
        # Lazy import to avoid circular: _reader imports the type classes from here.
        from . import _reader

        content_paths = resolve_content_paths(scope, repo_root)

        return cls(
            skills=_reader.load_skills(content_paths),
            rules=_reader.load_rules(content_paths),
            hooks=_reader.load_hooks(content_paths),
            mcp_configs=_reader.load_mcp_configs(content_paths),
            agents=_reader.load_agents(content_paths),
            commands=_reader.load_commands(content_paths),
            prompts=_reader.load_prompts(content_paths),
            trajectories=_reader.load_trajectories(content_paths),
        )


class Adapter(Protocol):
    """Per-tool translator. Each adapter module exposes `ADAPTERS: list[Adapter]`.

    Most modules export one Adapter; agents_md exports twenty (one per Tier 3
    tool). The dispatcher walks the union of every module's ADAPTERS list.

    `prior_managed_keys` (optional) is the lockfile's record of what THIS
    adapter previously registered inside shared config files (MCP server
    names in ~/.claude.json, hook commands in ~/.claude/settings.json,
    etc.). Tier 1 adapters use it to remove playbook-managed entries that
    dropped out of the current install (e.g. when narrowing from full to
    --profile qa). Adapters that don't write registrations may ignore it.
    Shape: {"mcp_servers": ["atlassian", ...], "hooks": [{...}, ...]}.
    """

    name: str  # slug, e.g. "claude-code"
    tier: int  # 1, 2, or 3

    def detect(self) -> bool: ...

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]: ...


def reconcile_managed_json_mcp(
    json_path: Path,
    block_key: str,
    new_managed_names: set[str],
    prior_managed_names: set[str],
) -> int:
    """Remove playbook-managed MCP entries that fell out of the new install.

    Used by claude_code, cursor, windsurf (JSON-based MCP configs). Entries
    NOT in prior_managed_names are treated as user-authored and preserved;
    entries in prior_managed_names BUT NOT in new_managed_names are
    deleted (the playbook owned them last time but doesn't anymore).

    Returns the number of removed entries. Writes the file in-place only
    if anything changed.
    """
    if not json_path.exists() or not prior_managed_names:
        return 0
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    block = data.get(block_key)
    if not isinstance(block, dict):
        return 0
    to_drop = [
        name
        for name in list(block.keys())
        if name in prior_managed_names and name not in new_managed_names
    ]
    if not to_drop:
        return 0
    for name in to_drop:
        del block[name]
    json_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return len(to_drop)


def reconcile_managed_hook_commands(
    settings_path: Path,
    new_hooks: dict[str, set[str]],
    prior_hooks: dict[str, set[str]],
) -> int:
    """Remove playbook-managed hook entries from ~/.claude/settings.json that
    fell out of the new install (per ADR-0029).

    ``new_hooks`` and ``prior_hooks`` map an event name (PreToolUse,
    PostToolUse, SessionStart, Stop) to the set of absolute hook command
    paths the playbook registers / registered for that event.

    For each event, paths in ``prior - new`` are removed from
    ``settings["hooks"][event]``:

      * If an entry's nested ``hooks[*].command`` is entirely in to_drop,
        the entry is dropped wholesale.
      * If an entry mixes managed + user hooks under the same matcher,
        only the managed command is removed and the entry is kept.

    User-authored entries (any command path NOT in prior_hooks) are never
    touched. Returns the count of individual command commands removed.
    Writes the file only if anything changed.
    """
    if not settings_path.exists() or not prior_hooks:
        return 0
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    hook_block = settings.get("hooks")
    if not isinstance(hook_block, dict):
        return 0

    removed_count = 0
    for event, event_entries in list(hook_block.items()):
        if not isinstance(event_entries, list):
            continue
        prior = set(prior_hooks.get(event, set()))
        current = set(new_hooks.get(event, set()))
        to_drop = prior - current
        if not to_drop:
            continue
        new_entries: list = []
        for entry in event_entries:
            if not isinstance(entry, dict):
                new_entries.append(entry)
                continue
            hooks_list = entry.get("hooks", [])
            if not isinstance(hooks_list, list):
                new_entries.append(entry)
                continue
            kept = [
                h
                for h in hooks_list
                if not (
                    isinstance(h, dict)
                    and isinstance(h.get("command"), str)
                    and h["command"] in to_drop
                )
            ]
            dropped_here = len(hooks_list) - len(kept)
            removed_count += dropped_here
            if not kept:
                continue
            if dropped_here:
                new_entry = {**entry, "hooks": kept}
                new_entries.append(new_entry)
            else:
                new_entries.append(entry)
        hook_block[event] = new_entries

    if removed_count == 0:
        return 0
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return removed_count
