"""
Tier 1 adapter: OpenAI Codex CLI.

Materializes:
  - Skills under ~/.agents/skills/<name>/SKILL.md (Codex's USER skill root
    per developers.openai.com/codex/skills)
  - Subagents under ~/.codex/agents/<name>.toml (TOML format per Codex
    subagents spec, converted from canonical markdown agents/<name>.md
    via _loader.agent_to_toml)
  - Rules as a managed block inside ~/.codex/AGENTS.md (Codex's primary
    rules surface)
  - MCP server configs as a managed block inside ~/.codex/config.toml
    [mcp_servers.*] tables (idempotent)
  - Hook scripts under ~/.codex/hooks/<name>.sh + Claude-shaped
    ~/.codex/hooks.json (per OpenAI's [features].hooks = true contract,
    Claude-compatible JSON schema). Added in v0.5 per the multi-agent
    hook gap analysis.

Reference:
  - https://developers.openai.com/codex/skills
  - https://developers.openai.com/codex/subagents
  - https://developers.openai.com/codex/hooks
  - https://github.com/openai/codex
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd
from hook_registration import (
    codex_event_for,
    codex_shaped_entry,
    is_hook_for_adapter,
    reconcile_claude_shaped_hooks_in_json,
    strip_claude_command_from_entries,
)

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class CodexAdapter:
    name = "codex"
    tier = 1

    def detect(self) -> bool:
        return (Path.home() / ".codex").is_dir()

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        # Codex stores MCP entries in a managed block inside config.toml; that
        # block is fully overwritten on every install, so a profile narrowing
        # already drops removed entries naturally. prior_managed_keys is
        # accepted for Protocol conformance but unused here.
        home = Path.home()
        codex_dir = home / ".codex"
        # Skills live in ~/.agents/skills/ (cross-tool USER skill root per OpenAI
        # docs), NOT ~/.codex/skills/. The latter is not scanned by Codex.
        skills_dir = home / ".agents" / "skills"
        agents_dir = codex_dir / "agents"
        hooks_dir = codex_dir / "hooks"
        agents_md = codex_dir / "AGENTS.md"
        config_toml = codex_dir / "config.toml"
        hooks_json = codex_dir / "hooks.json"

        _loader.ensure_dir(codex_dir)
        _loader.ensure_dir(skills_dir)

        # v0.9 (ADR-0039): managed_keys.mcp_servers is now list[ManagedMcpEntry]
        # but Codex MCP block is fully overwritten on every install (the
        # [mcp_servers.*] tables are emitted by the managed-block writer
        # below), so no reconciliation needed. prior_managed_keys is
        # accepted for Protocol conformance and acknowledged here.
        _ = (prior_managed_keys or {}).get("mcp_servers", [])

        # v0.6 adversarial-review hardening: prove playbook ownership
        # before overwriting an existing ~/.agents/skills/<name> directory.
        # Ownership = .playbook-owned marker OR legacy SKILL.md frontmatter
        # matching install_name. Otherwise leave the user's content alone.
        copied = 0
        preserved = 0
        for skill in content.skills:
            install_name = skill.install_name or skill.name
            skill_target = skills_dir / install_name
            if (
                skill_target.exists()
                and not skill_target.is_symlink()
                and not _loader.is_playbook_owned_skill_dir(skill_target, install_name)
            ):
                print(
                    f"   note:    leaving {skill_target} (user-authored; not replaced)"
                )
                preserved += 1
                continue
            for written in _loader.copy_skill_payload(skill, skill_target):
                yield InstalledPath(written, "owned")
            copied += 1
        suffix = f" ({preserved} preserved)" if preserved else ""
        print(
            f"   skills:  {copied} copied to {skills_dir} (Codex USER skill root){suffix}"
        )

        if content.agents:
            _loader.ensure_dir(agents_dir)
            for agent in content.agents:
                agent_target = agents_dir / f"{agent.name}.toml"
                agent_target.write_text(_loader.agent_to_toml(agent), encoding="utf-8")
                yield InstalledPath(agent_target, "owned")
            print(
                f"   agents:  {len(content.agents)} subagents converted to TOML at {agents_dir}"
            )

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="codex", comment_style="hash")
            .save_to(agents_md)
        )
        print(f"   rules:   {agents_md} ({action}, {len(content.rules)} rule(s))")
        yield InstalledPath(agents_md, "managed")

        # Per the v0.5 cross-agent hook gap analysis: Codex hooks are
        # stable behind [features].hooks = true and use a Claude-compatible
        # JSON schema. Copy hook scripts and write a managed hooks.json so
        # Codex users get the same enforcement Claude Code has had.
        #
        # Reconcile runs OUTSIDE the `if content.hooks:` guard (Codex
        # review P2, round 2): if a later profile contains zero hooks, the
        # reconcile must still fire so that prior playbook-managed entries
        # get removed from hooks.json. Otherwise orphan cleanup deletes the
        # scripts but leaves stale registrations pointing at missing files.
        #
        # v0.6: cursor-only hooks (e.g., the JSON-stdout advisory wrapper)
        # are not Codex-relevant and would be dead weight under ~/.codex/.
        # v0.8 (ADR-0037): PLAYBOOK-HOOK-ADAPTERS additionally restricts
        # bundle-coupled hooks (anchored-fs claude-shape hooks) to their
        # owning adapter; is_hook_for_adapter covers both filters.
        agent_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]

        # v0.6: use codex_event_for() so the reconcile keyspace matches the
        # registration keyspace. A PreToolUse+non-Bash hook is registered
        # under PostToolUse (auto-promotion); prior managed paths must be
        # looked up under the same effective event to clean up properly.
        new_hook_commands: dict[str, set[str]] = {}
        for hook in agent_hooks:
            event = codex_event_for(hook)
            new_hook_commands.setdefault(event, set()).add(
                str(hooks_dir / f"{hook.name}.sh")
            )
        prior_hooks_raw = (prior_managed_keys or {}).get("hooks", {}) or {}
        prior_hooks = {event: set(paths) for event, paths in prior_hooks_raw.items()}
        removed_hooks = reconcile_claude_shaped_hooks_in_json(
            hooks_json, new_hook_commands, prior_hooks
        )
        if removed_hooks:
            print(
                f"   hooks:   removed {removed_hooks} stale managed entr(ies) from {hooks_json}"
            )

        if agent_hooks:
            _loader.ensure_dir(hooks_dir)
            for hook in agent_hooks:
                hook_target = hooks_dir / f"{hook.name}.sh"
                shutil.copy2(hook.path, hook_target)
                hook_target.chmod(
                    hook_target.stat().st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
                yield InstalledPath(hook_target, "owned")
            print(f"   hooks:   {len(agent_hooks)} copied to {hooks_dir}")

            existing_hooks_doc: dict = {}
            if hooks_json.exists():
                try:
                    existing_hooks_doc = json.loads(
                        hooks_json.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    existing_hooks_doc = {}
            hook_block = existing_hooks_doc.setdefault("hooks", {})
            # Strip the playbook command from EVERY event slot first, so a
            # v0.5->v0.6 upgrade that promotes a PreToolUse hook to
            # PostToolUse for Codex doesn't leave a stale PreToolUse entry.
            for hook in agent_hooks:
                command_path = str(hooks_dir / f"{hook.name}.sh")
                for event_entries in hook_block.values():
                    if isinstance(event_entries, list):
                        event_entries[:] = strip_claude_command_from_entries(
                            event_entries, command_path
                        )
            for hook in agent_hooks:
                command_path = str(hooks_dir / f"{hook.name}.sh")
                event, entry = codex_shaped_entry(hook, command_path)
                event_block = hook_block.setdefault(event, [])
                event_block.append(entry)
            hooks_json.write_text(
                json.dumps(existing_hooks_doc, indent=2) + "\n", encoding="utf-8"
            )
            print(f"   hooks:   registered in {hooks_json}")
            yield InstalledPath(hooks_json, "managed")

        # v0.9 round-11 adversarial HIGH fix: ALWAYS reconcile the
        # Codex MCP managed block on install. Earlier code only entered
        # MCP handling when content.mcp_configs was non-empty AND only
        # rewrote the block when new_configs was non-empty. A profile
        # narrow from "had MCPs" to "zero MCPs" (or to MCPs that all
        # pre-exist outside the managed block) left the prior
        # PLAYBOOK-MANAGED block in ~/.codex/config.toml even though
        # the v3 lockfile no longer recorded those servers. The stale
        # servers stayed callable but unverified. Now: always update
        # (or remove) the managed block so it matches the current
        # set the profile ships.
        pre_existing = _loader.existing_toml_tables_outside_block(
            config_toml,
            table_prefix="mcp_servers",
            comment_prefix="#",
            comment_suffix="",
        )
        skipped = sorted({m.name for m in content.mcp_configs} & pre_existing)
        new_configs = [m for m in content.mcp_configs if m.name not in pre_existing]
        if skipped:
            print(
                f"   mcp:     skipped (already configured outside managed block): "
                f"{', '.join(skipped)}"
            )
        if new_configs:
            expanded_configs = [
                m._replace(
                    config=_loader.expand_agent_shared_placeholder(
                        m.config, m.name, target=target
                    )
                )
                for m in new_configs
            ]
            toml_block = _render_mcp_toml(expanded_configs).rstrip()
            action = _loader.upsert_managed_block(
                config_toml,
                toml_block,
                comment_prefix="#",
                comment_suffix="",
            )
            print(f"   mcp:     {config_toml} ({action}, {len(new_configs)} server(s))")
            yield InstalledPath(config_toml, "managed")
        elif config_toml.exists():
            # Narrow to zero MCPs (or all-skipped): remove any prior
            # PLAYBOOK-MANAGED block so stale servers don't linger.
            removal = _loader.remove_managed_block(
                config_toml,
                comment_prefix="#",
                comment_suffix="",
            )
            if removal == "removed":
                print(
                    f"   mcp:     removed prior managed block from "
                    f"{config_toml} (profile has zero managed MCPs)"
                )


def _render_mcp_toml(mcp_configs) -> str:
    """Render a list of MCP configs as one or more [mcp_servers.<name>] TOML tables."""
    lines: list[str] = []
    for mcp in mcp_configs:
        lines.append(f"[mcp_servers.{mcp.name}]")
        for key, value in mcp.config.items():
            lines.append(f"{key} = {_format_toml_value(value)}")
        lines.append("")
    return "\n".join(lines)


def _format_toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        return "[" + ", ".join(_format_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        inner = ", ".join(f"{k} = {_format_toml_value(v)}" for k, v in value.items())
        return "{ " + inner + " }"
    return str(value)


ADAPTERS: list[Adapter] = [CodexAdapter()]
