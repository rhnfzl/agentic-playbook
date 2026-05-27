"""
Tier 1 adapter: Claude Code (Anthropic).

Per Anthropic's official docs (code.claude.com/docs/en/memory) Claude Code
reads CLAUDE.md, not AGENTS.md. The recommended pattern is `@AGENTS.md`
inside CLAUDE.md. This adapter writes rules into the user's global
~/AGENTS.md as a managed block (the user is expected to have a
`@~/AGENTS.md` line in ~/.claude/CLAUDE.md to wire it in; the install
output reminds them if not).

Materializes:
  - Skills under ~/.claude/skills/<name>/SKILL.md (one dir per skill)
  - Subagents under ~/.claude/agents/<name>.md (markdown native)
  - Slash commands under ~/.claude/commands/<name>.md
  - Hooks under ~/.claude/hooks/<name>.sh
  - Hook registration in ~/.claude/settings.json (event read from each hook's
    `# PLAYBOOK-HOOK-EVENT:` header line, per ADR-0027)
  - MCP server configs upserted into ~/.claude.json mcpServers block
  - Rules concatenated as a managed block in ~/AGENTS.md (per ADR 0007)

Reference: https://docs.claude.com/en/docs/claude-code
"""

from __future__ import annotations

import json
import re
import shutil
import stat
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd
from hook_registration import is_hook_for_adapter

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


_HOOK_EVENT_HEADER_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-EVENT:\s*(\w+)\s*$")
_HOOK_MATCHER_HEADER_RE = re.compile(r"^#\s*PLAYBOOK-HOOK-MATCHER:\s*(.+?)\s*$")


class ClaudeCodeAdapter:
    name = "claude-code"
    tier = 1

    def detect(self) -> bool:
        return (Path.home() / ".claude").is_dir()

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        home = Path.home()
        claude_dir = home / ".claude"
        skills_dir = claude_dir / "skills"
        agents_dir = claude_dir / "agents"
        commands_dir = claude_dir / "commands"
        hooks_dir = claude_dir / "hooks"
        claude_md = claude_dir / "CLAUDE.md"
        settings_path = claude_dir / "settings.json"
        claude_json = home / ".claude.json"
        user_agents_md = home / "AGENTS.md"

        _loader.ensure_dir(claude_dir)
        _loader.ensure_dir(skills_dir)
        _loader.ensure_dir(hooks_dir)

        # v0.9 (ADR-0039): per-(adapter, config_path) managed_keys schema.
        # Claude Code currently writes only to ~/.claude.json (single
        # config); managed_entries_for_config filters the lockfile's
        # entry list to names installed at THIS path so reconcile only
        # touches what the playbook actually owns here.
        from install_lockfile import managed_entries_for_config

        prior_mcp_all = (prior_managed_keys or {}).get("mcp_servers", [])
        prior_mcp_for_path = managed_entries_for_config(prior_mcp_all, claude_json)
        new_mcp = {m.name for m in content.mcp_configs}
        removed = _loader.reconcile_managed_json_mcp(
            claude_json,
            "mcpServers",
            new_mcp,
            prior_mcp_for_path,
        )
        if removed:
            print(
                f"   mcp:     removed {removed} stale managed entr(ies) from {claude_json}"
            )

        # Reconcile hook commands that were registered by a prior wider install
        # but dropped out of the current profile (per ADR-0029). The lockfile
        # records managed_hook_commands keyed by event; on narrow we remove the
        # prior commands the playbook no longer ships, leaving user-authored
        # settings.json entries untouched.
        # v0.6: hooks marked PLAYBOOK-HOOK-CURSOR-ONLY: true (e.g., the JSON-
        # stdout advisory wrapper) are skipped by every non-cursor adapter for
        # both copy and registration. They are dead weight under ~/.claude/.
        # v0.8 (ADR-0037): PLAYBOOK-HOOK-ADAPTERS scopes bundle-coupled hooks
        # like the anchored-fs Claude-specific wrappers. is_hook_for_adapter
        # encapsulates both checks (cursor-only + ADAPTERS allowlist).
        agent_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]

        prior_hooks_raw = (prior_managed_keys or {}).get("hooks", {}) or {}
        prior_hooks: dict[str, set[str]] = {
            event: set(paths) for event, paths in prior_hooks_raw.items()
        }
        new_hook_commands: dict[str, set[str]] = {}
        for hook in agent_hooks:
            event = _resolve_hook_event(hook)
            new_hook_commands.setdefault(event, set()).add(
                str(hooks_dir / f"{hook.name}.sh")
            )
        removed_hooks = _loader.reconcile_managed_hook_commands(
            settings_path,
            new_hook_commands,
            prior_hooks,
        )
        if removed_hooks:
            print(
                f"   hooks:   removed {removed_hooks} stale managed entr(ies) from {settings_path}"
            )

        for skill in content.skills:
            skill_target = skills_dir / (skill.install_name or skill.name)
            for written in _loader.copy_skill_payload(skill, skill_target):
                yield InstalledPath(written, "owned")
        print(f"   skills:  {len(content.skills)} copied to {skills_dir}")

        if content.agents:
            _loader.ensure_dir(agents_dir)
            for agent in content.agents:
                agent_target = agents_dir / f"{agent.name}.md"
                shutil.copy2(agent.path, agent_target)
                yield InstalledPath(agent_target, "owned")
            print(f"   agents:  {len(content.agents)} subagents copied to {agents_dir}")

        if content.commands:
            _loader.ensure_dir(commands_dir)
            for command in content.commands:
                command_target = commands_dir / f"{command.name}.md"
                shutil.copy2(command.path, command_target)
                yield InstalledPath(command_target, "owned")
            print(
                f"   commands:{len(content.commands)} slash commands copied to {commands_dir}"
            )

        for hook in agent_hooks:
            hook_target = hooks_dir / f"{hook.name}.sh"
            shutil.copy2(hook.path, hook_target)
            hook_target.chmod(
                hook_target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            yield InstalledPath(hook_target, "owned")
        print(f"   hooks:   {len(agent_hooks)} copied to {hooks_dir}")

        action = (
            AgentsMd.load_or_empty(user_agents_md)
            .with_managed_rules(content.rules, label="claude-code")
            .save_to(user_agents_md)
        )
        print(f"   rules:   {user_agents_md} ({action}, {len(content.rules)} rule(s))")
        yield InstalledPath(user_agents_md, "managed")

        if not _claude_md_imports_agents(claude_md):
            print(f"   note:    {claude_md} does not @-import ~/AGENTS.md.")
            print(
                f"            Add this line near the top of {claude_md} to auto-load these rules:"
            )
            print("              @~/AGENTS.md")

        if content.mcp_configs:
            # v0.8 (C2 + Codex adversarial fix): merge logic centralised
            # in _writer.merge_managed_mcp_into_json. Returns (added,
            # skipped, inserted_names). The 3rd field is the exact list
            # the playbook owns; recording the full configured set as
            # managed lets a later narrow reconcile delete user-
            # authored entries that happened to share a name.
            added, skipped, inserted_names = _loader.merge_managed_mcp_into_json(
                claude_json,
                block_key="mcpServers",
                mcp_configs=content.mcp_configs,
                target=target,
            )
            print(
                f"   mcp:     {added} new added to {claude_json}, {skipped} preserved"
            )
            yield InstalledPath(claude_json, "managed")

        if agent_hooks:
            settings: dict = {}
            if settings_path.exists():
                try:
                    settings = json.loads(settings_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    settings = {}

            hook_block = settings.setdefault("hooks", {})
            for hook in agent_hooks:
                event = _resolve_hook_event(hook)
                matcher = _resolve_hook_matcher(hook)
                event_block = hook_block.setdefault(event, [])
                command_path = str(hooks_dir / f"{hook.name}.sh")
                entry: dict = {"hooks": [{"type": "command", "command": command_path}]}
                if matcher and matcher != "*":
                    entry["matcher"] = matcher
                # Surgically strip the playbook command from any existing
                # entry that references it (covers v0.4 -> v0.5 matcher
                # upgrades). Keep the entry whenever other user-authored
                # hooks remain under the same matcher; only drop entries
                # whose hooks list becomes empty after the strip. Mirrors
                # reconcile_managed_hook_commands so a mixed entry like
                # [playbook hook, custom hook] preserves the custom hook
                # (adversarial review high-severity finding).
                event_block[:] = _strip_command_from_entries(event_block, command_path)
                event_block.append(entry)
            settings_path.write_text(
                json.dumps(settings, indent=2) + "\n", encoding="utf-8"
            )
            print(f"   hooks registered in {settings_path}")
            yield InstalledPath(settings_path, "managed")


def _claude_md_imports_agents(claude_md: Path) -> bool:
    """Detect whether the user's CLAUDE.md already @-imports ~/AGENTS.md."""
    if not claude_md.exists():
        return False
    text = claude_md.read_text(encoding="utf-8")
    needles = ("@~/AGENTS.md", "@$HOME/AGENTS.md", "@/Users/", "@AGENTS.md")
    return any(needle in text for needle in needles[:3]) or any(
        line.strip().startswith("@") and line.strip().endswith("AGENTS.md")
        for line in text.splitlines()
    )


def _resolve_hook_event(hook: _loader.Hook) -> str:
    """Resolve a hook's event from its `# PLAYBOOK-HOOK-EVENT:` header.

    v0.8 (C4): the hook-metadata check (scripts/checks/hook_metadata.py)
    enforces that every hook declares the header, so the filename-
    inference fallback that lived here can never fire. Removed.
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_EVENT_HEADER_RE.match(line.strip())
        if m:
            return m.group(1)
    raise RuntimeError(
        f"hook {hook.name!r} is missing the PLAYBOOK-HOOK-EVENT header; "
        f"the hook-metadata check should have caught this at make check time"
    )


def _entry_references_command(entry: object, command_path: str) -> bool:
    """True iff this settings.json hook entry's nested hooks list contains
    a command pointing at command_path. Used to de-dupe a hook command by
    path (independent of matcher) so v0.4 -> v0.5 upgrades replace the old
    no-matcher entry with the new matcher-equipped one.
    """
    if not isinstance(entry, dict):
        return False
    hooks_list = entry.get("hooks")
    if not isinstance(hooks_list, list):
        return False
    return any(
        isinstance(h, dict) and h.get("command") == command_path for h in hooks_list
    )


def _strip_command_from_entries(entries: list, command_path: str) -> list:
    """Return a new entries list with command_path removed from each entry's
    nested hooks list. Entries whose hooks list becomes empty are dropped.
    Mixed entries that still have user-authored hooks after the strip are
    preserved verbatim (with only the playbook command gone).
    """
    out: list = []
    for entry in entries:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        hooks_list = entry.get("hooks")
        if not isinstance(hooks_list, list):
            out.append(entry)
            continue
        kept = [
            h
            for h in hooks_list
            if not (isinstance(h, dict) and h.get("command") == command_path)
        ]
        if len(kept) == len(hooks_list):
            out.append(entry)
            continue
        if not kept:
            continue
        out.append({**entry, "hooks": kept})
    return out


def _resolve_hook_matcher(hook: _loader.Hook) -> str | None:
    """Resolve a hook's tool matcher from the `# PLAYBOOK-HOOK-MATCHER:` header.

    Returns the matcher string (e.g. ``"Edit|Write|MultiEdit"``) when the
    header is present. Returns the literal string ``"*"`` for hooks that
    explicitly opt into match-all behavior (e.g. SessionStart). Returns
    None when the header is missing entirely, in which case the caller
    falls back to "no matcher field" (Claude Code interprets the absence
    as match-all, but the install warning surfaces the omission so a
    maintainer can decide whether to add a matcher).
    """
    for line in hook.body.splitlines()[:15]:
        m = _HOOK_MATCHER_HEADER_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return None


ADAPTERS: list[Adapter] = [ClaudeCodeAdapter()]
