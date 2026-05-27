"""
Re-export shim for the (formerly monolithic) adapter loader.

Per ADR-0031: the 887-line _loader.py was split into four focused modules:
  _protocol.py: typed contracts (Skill, Rule, Hook, McpConfig, Agent,
    Command, Prompt, InstalledPath, PlaybookContent), the Adapter Protocol,
    and reconcile_managed_json_mcp.
  _reader.py: content scanners (load_skills, load_rules, load_hooks,
    load_mcp_configs, load_agents, load_commands, load_prompts).
  _detect.py: detection helpers (which, vscode_extension_present) and
    target resolution (resolve_target, _validate_target, _prompt_for_target).
  _writer.py: file writes (copy_skill_payload, materialize_mcp_sources,
    agent_to_toml, merge_managed_mcp_into_json, upsert_managed_block,
    remove_managed_block, existing_toml_tables_outside_block) plus
    style lint helpers (find_em_dashes) and constants
    (AGENT_SHARED_MCP_DIR, MARKER_ID, etc.).

This module re-exports every public name so existing
`from ._loader import Adapter, InstalledPath, PlaybookContent` and
`from . import _loader; _loader.which(...)` calls keep working without
adapter rewrites.

New code should prefer the focused submodules.
"""

from __future__ import annotations

from ._detect import (
    _prompt_for_target,
    _validate_target,
    resolve_target,
    vscode_extension_present,
    which,
)
from ._protocol import (
    MARKER_ID,
    Adapter,
    Agent,
    Command,
    ContentPaths,
    Hook,
    InstalledPath,
    McpConfig,
    PlaybookContent,
    Prompt,
    Rule,
    Skill,
    reconcile_managed_hook_commands,
    reconcile_managed_json_mcp,
    resolve_content_paths,
)
from ._reader import (
    _parse_frontmatter,
    load_agents,
    load_commands,
    load_hooks,
    load_mcp_configs,
    load_prompts,
    load_rules,
    load_skills,
)
from ._writer import (
    _EM_DASH_CHARS,
    _marker_line,
    _toml_escape,
    AGENT_SHARED_MCP_DIR,
    AGENT_SHARED_PLACEHOLDER,
    MCP_BUNDLE_SKIP_NAMES,
    PLAYBOOK_OWNERSHIP_MARKER,  # noqa: F401 (re-exported for adapter use)
    PLAYBOOK_TARGET_PLACEHOLDER,
    agent_to_toml,
    compose_agents_md,
    copy_skill_payload,
    ensure_dir,
    existing_toml_tables_outside_block,
    expand_agent_shared_placeholder,
    find_em_dashes,
    first_heading_or_default,  # noqa: F401 (re-exported for adapter use)
    is_playbook_owned_skill_dir,  # noqa: F401 (re-exported for adapter use)
    materialize_mcp_sources,
    merge_managed_mcp_into_json,
    remove_managed_block,
    safe_symlink_or_copy,  # noqa: F401 (re-exported for adapter use, v0.7 Windows fallback)
    upsert_managed_block,
)


__all__ = [
    "_EM_DASH_CHARS",
    "_marker_line",
    "_parse_frontmatter",
    "_prompt_for_target",
    "_toml_escape",
    "_validate_target",
    "AGENT_SHARED_MCP_DIR",
    "AGENT_SHARED_PLACEHOLDER",
    "Adapter",
    "Agent",
    "Command",
    "ContentPaths",
    "Hook",
    "InstalledPath",
    "MARKER_ID",
    "MCP_BUNDLE_SKIP_NAMES",
    "McpConfig",
    "PLAYBOOK_OWNERSHIP_MARKER",
    "PLAYBOOK_TARGET_PLACEHOLDER",
    "PlaybookContent",
    "Prompt",
    "Rule",
    "Skill",
    "agent_to_toml",
    "compose_agents_md",
    "copy_skill_payload",
    "ensure_dir",
    "existing_toml_tables_outside_block",
    "expand_agent_shared_placeholder",
    "find_em_dashes",
    "first_heading_or_default",
    "is_playbook_owned_skill_dir",
    "load_agents",
    "load_commands",
    "load_hooks",
    "load_mcp_configs",
    "load_prompts",
    "load_rules",
    "load_skills",
    "materialize_mcp_sources",
    "merge_managed_mcp_into_json",
    "reconcile_managed_hook_commands",
    "reconcile_managed_json_mcp",
    "remove_managed_block",
    "resolve_content_paths",
    "resolve_target",
    "safe_symlink_or_copy",
    "upsert_managed_block",
    "vscode_extension_present",
    "which",
]
