"""
Tier 1 adapter: Cursor (IDE + CLI).

USER-LEVEL is the primary install target (so the playbook follows researchers
across all their Cursor CLI projects). PROJECT-LEVEL is materialized in
parallel when a non-$HOME target is selected.

USER-LEVEL (~/.cursor/):
  - Skills under ~/.cursor/skills/<name>/SKILL.md
  - Rules under ~/.cursor/rules/<name>.mdc
  - Subagents under ~/.cursor/agents/<name>.md
  - Slash commands under ~/.cursor/commands/<name>.md
  - MCP servers merged into ~/.cursor/mcp.json

PROJECT-LEVEL (<target>/.cursor/, only if target != $HOME):
  - Same content at <target>/.cursor/*
  - Plus AGENTS.md at project root via AgentsMd.with_managed_rules

Reference: https://docs.cursor.com/context/rules ; https://cursor.com/cli
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd
from hook_registration import (
    cursor_event_for,
    cursor_shaped_entry,
    is_hook_for_adapter,
    is_wrapped_core,
    reconcile_cursor_shaped_hooks_in_json,
    strip_cursor_command_from_entries,
)

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class CursorAdapter:
    name = "cursor"
    tier = 1

    def detect(self) -> bool:
        return (Path.home() / ".cursor").is_dir() or Path(
            "/Applications/Cursor.app"
        ).exists()

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        home = Path.home()

        # v0.9 (ADR-0039): per-(adapter, config_path) managed_keys schema
        # means prior MCP names are filtered PER config file. The same
        # name in user vs project is tracked separately, so reconcile
        # on narrow only removes entries from the file that actually
        # owned them. Closes the Cursor multi-config orphan risk that
        # the v0.8 round-5..9 UNION trade-off worked around.
        from install_lockfile import managed_entries_for_config

        prior_mcp_all = (prior_managed_keys or {}).get("mcp_servers", [])
        new_mcp = {m.name for m in content.mcp_configs}
        user_cfg = home / ".cursor" / "mcp.json"
        prior_mcp_user = managed_entries_for_config(prior_mcp_all, user_cfg)
        removed_user = _loader.reconcile_managed_json_mcp(
            user_cfg,
            "mcpServers",
            new_mcp,
            prior_mcp_user,
        )
        if removed_user:
            print(
                f"   mcp:     removed {removed_user} stale managed entr(ies) from ~/.cursor/mcp.json"
            )
        if target is not None and target.resolve() != home.resolve():
            project_cfg = target / ".cursor" / "mcp.json"
            prior_mcp_project = managed_entries_for_config(prior_mcp_all, project_cfg)
            removed_proj = _loader.reconcile_managed_json_mcp(
                project_cfg,
                "mcpServers",
                new_mcp,
                prior_mcp_project,
            )
            if removed_proj:
                print(
                    f"   mcp:     removed {removed_proj} stale managed entr(ies) from {target}/.cursor/mcp.json"
                )

        # Cursor hook reconciliation per Codex P1 #1: drop prior-but-not-new
        # entries from ~/.cursor/hooks.json before the install loop writes
        # the current set. Per Codex review P2 (round 2): runs even when the
        # new profile has zero hooks, so prior managed entries get pruned
        # from hooks.json instead of lingering after a narrow.
        #
        # v0.6 review-2 fixup: cursor_event_for() centralizes the
        # PascalCase->camelCase event map (previously duplicated as inline
        # dicts here). is_wrapped_core() filters wrapped-core hooks so the
        # pre-reconcile keyspace matches the registration keyspace (only
        # the wrapper actually lands in hooks.json).
        new_cursor_hooks: dict[str, set[str]] = {}
        user_hooks_dir = home / ".cursor" / "hooks"
        # v0.8 (ADR-0037): is_hook_for_adapter drops hooks scoped to a
        # different adapter via PLAYBOOK-HOOK-ADAPTERS (e.g., anchored-fs
        # hooks pinned to claude-code). Cursor-only hooks pass the filter
        # because is_cursor_only inside is_hook_for_adapter allows them
        # under the cursor adapter specifically.
        cursor_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]
        for hook in cursor_hooks:
            if is_wrapped_core(hook):
                continue
            event_camel = cursor_event_for(hook)
            new_cursor_hooks.setdefault(event_camel, set()).add(
                str(user_hooks_dir / f"{hook.name}.sh")
            )
        prior_cursor_hooks_raw = (prior_managed_keys or {}).get("hooks", {}) or {}
        prior_cursor_hooks: dict[str, set[str]] = {}
        _claude_to_cursor_event: dict[str, str] = {
            "PreToolUse": "preToolUse",
            "PostToolUse": "postToolUse",
            "SessionStart": "sessionStart",
            "Stop": "stop",
        }
        for ev, paths in prior_cursor_hooks_raw.items():
            ev_str = str(ev)
            ev_camel: str = _claude_to_cursor_event.get(ev_str, ev_str)
            prior_cursor_hooks[ev_camel] = set(paths)
        removed_cursor_hooks = reconcile_cursor_shaped_hooks_in_json(
            home / ".cursor" / "hooks.json",
            new_cursor_hooks,
            prior_cursor_hooks,
        )
        if removed_cursor_hooks:
            print(
                f"   hooks:   removed {removed_cursor_hooks} stale managed entr(ies) from ~/.cursor/hooks.json"
            )

        print("   user:    ~/.cursor/")
        yield from _write_cursor_tree(
            content,
            home / ".cursor",
            scope="user",
            target=target,
            prior_hooks=prior_cursor_hooks,
        )

        # Only write project-level if target is meaningfully different from $HOME.
        if target is not None and target.resolve() != home.resolve():
            # v0.8 Codex round-8 fix: write project-level MCPs even when
            # the same name pre-exists at user level. Anchored-fs and
            # similar bundles expand {{PLAYBOOK_TARGET}} into per-target
            # values (e.g., --allowed-dir <target>), so a second
            # project install needs its OWN project entry; skipping
            # would leave Cursor using a stale wider scope.
            #
            # Trade-off: the project entry can orphan after profile
            # narrow because managed_keys excludes user-overlapping
            # names (round-6 user-data-loss prevention). The
            # architectural fix is per-(adapter, config_path)
            # managed_keys schema -- tracked as v0.9 work in the v0.8
            # handoff. Round-7's project_mcp_skip_names path remains
            # supported for callers that explicitly want it.
            print(f"   project: {target}")
            yield from _write_cursor_tree(
                content,
                target / ".cursor",
                scope="project",
                target=target,
                project_root=target,
                prior_hooks=prior_cursor_hooks,
            )


def _write_cursor_tree(
    content: PlaybookContent,
    cursor_dir: Path,
    *,
    scope: str,
    target: Path | None,
    project_root: Path | None = None,
    prior_hooks: dict[str, set[str]] | None = None,
    project_mcp_skip_names: set[str] | None = None,
) -> Iterable[InstalledPath]:
    """Write the full Cursor content tree to a given .cursor/ directory.

    prior_hooks (Codex adversarial round-2 [high]): prior playbook-managed
    Cursor hook commands keyed by camelCase event. Used to reconcile
    project-level hooks.json on profile narrow. User-level reconciliation
    already happens in the parent install(); this duplicates the surgical
    strip for project-level so dropped commands don't linger there either.
    Caller MUST translate command paths to the project's own hooks_dir
    BEFORE passing (the helper does not translate paths).
    """
    import stat as _stat

    rules_dir = cursor_dir / "rules"
    skills_dir = cursor_dir / "skills"
    agents_dir = cursor_dir / "agents"
    commands_dir = cursor_dir / "commands"
    hooks_dir = cursor_dir / "hooks"
    mcp_json = cursor_dir / "mcp.json"
    hooks_json = cursor_dir / "hooks.json"

    _loader.ensure_dir(cursor_dir)
    _loader.ensure_dir(rules_dir)
    _loader.ensure_dir(skills_dir)

    default_desc = "Auto-distributed rule from coding-agents-playbook"
    for rule in content.rules:
        rule_target = rules_dir / f"{rule.name}.mdc"
        frontmatter = (
            "---\n"
            "description: "
            + _loader.first_heading_or_default(rule.body, default=default_desc)
            + "\n"
            "alwaysApply: true\n"
            'globs: "**/*"\n'
            "---\n\n"
        )
        rule_target.write_text(frontmatter + rule.body, encoding="utf-8")
        yield InstalledPath(rule_target, "owned")
    print(f"     rules:    {len(content.rules)} mdc files in {rules_dir}")

    # v0.6 (gap-analysis F8 / F14): symlink user-level skills to
    # ~/.agents/skills/<name> (the cross-tool USER skill root Codex uses)
    # instead of deep-copying ~220+ files into ~/.cursor/skills/.
    #
    # Adversarial-review hardening (round 1, post-v0.6): prove playbook
    # ownership before BOTH writing ~/.agents/skills/<name> AND replacing
    # ~/.cursor/skills/<name>. Ownership = .playbook-owned marker OR a
    # legacy SKILL.md frontmatter matching install_name (v0.5 fallback).
    # Anything else is treated as user-authored content; the adapter
    # warns and skips that skill rather than clobber.
    if scope == "user":
        home = Path.home()
        agents_skills_root = home / ".agents" / "skills"
        agents_skills_root.mkdir(parents=True, exist_ok=True)
        symlinked = 0
        warned = 0
        for skill in content.skills:
            install_name = skill.install_name or skill.name
            canonical_target = agents_skills_root / install_name
            # Guard 1: ~/.agents/skills/<name>. A user with a personal
            # skill at the same name must not be silently overwritten by
            # copy_skill_payload. Skip the whole skill if we can't prove
            # ownership; the cursor symlink would point at unreliable
            # content anyway.
            if (
                canonical_target.exists()
                and not canonical_target.is_symlink()
                and not _loader.is_playbook_owned_skill_dir(
                    canonical_target, install_name
                )
            ):
                print(
                    f"     note:     leaving ~/.agents/skills/{install_name} "
                    f"(user-authored; not replaced)"
                )
                warned += 1
                continue
            for written in _loader.copy_skill_payload(skill, canonical_target):
                yield InstalledPath(written, "owned")
            # Guard 2: ~/.cursor/skills/<name>. Symlinks are always
            # playbook-owned (this adapter is the only writer of symlinks
            # at that path). Real dirs are checked for ownership; if not
            # proven, leave them and warn. Non-dir files at the same name
            # are likely user-authored notes, also preserved.
            cursor_link = skills_dir / install_name
            if cursor_link.is_symlink():
                cursor_link.unlink()
            elif cursor_link.exists():
                if cursor_link.is_dir() and _loader.is_playbook_owned_skill_dir(
                    cursor_link, install_name
                ):
                    shutil.rmtree(cursor_link)
                else:
                    print(
                        f"     note:     leaving {cursor_link} "
                        f"(user-authored; not replaced)"
                    )
                    warned += 1
                    continue
            _loader.safe_symlink_or_copy(
                cursor_link,
                Path("../..") / ".agents" / "skills" / install_name,
                target_is_directory=True,
            )
            yield InstalledPath(cursor_link, "owned")
            symlinked += 1
        suffix = f" ({warned} preserved)" if warned else ""
        print(
            f"     skills:   {symlinked} symlinked to ~/.agents/skills/ via {skills_dir}{suffix}"
        )
    else:
        for skill in content.skills:
            install_name = skill.install_name or skill.name
            skill_target = skills_dir / install_name
            if (
                skill_target.exists()
                and not skill_target.is_symlink()
                and not _loader.is_playbook_owned_skill_dir(skill_target, install_name)
            ):
                print(
                    f"     note:     leaving {skill_target} "
                    f"(user-authored; not replaced)"
                )
                continue
            for written in _loader.copy_skill_payload(skill, skill_target):
                yield InstalledPath(written, "owned")
        print(
            f"     skills:   {len(content.skills)} dirs in {skills_dir} (Cursor auto-invokes)"
        )

    if content.agents:
        _loader.ensure_dir(agents_dir)
        for agent in content.agents:
            agent_target = agents_dir / f"{agent.name}.md"
            shutil.copy2(agent.path, agent_target)
            yield InstalledPath(agent_target, "owned")
        print(f"     agents:   {len(content.agents)} subagents in {agents_dir}")

    if content.commands:
        _loader.ensure_dir(commands_dir)
        for command in content.commands:
            cmd_target = commands_dir / f"{command.name}.md"
            shutil.copy2(command.path, cmd_target)
            yield InstalledPath(cmd_target, "owned")
        print(
            f"     commands: {len(content.commands)} slash commands in {commands_dir}"
        )

    if content.mcp_configs:
        # v0.8 (C2 + Codex round-7 fix): the project-level Cursor write
        # passes skip_names=user_mcp_names so we never insert a name
        # the user has at user level. Without this, the project entry
        # would orphan after profile narrow (managed_keys correctly
        # excludes the name to prevent user data loss; reconcile then
        # can't remove the project entry it doesn't own).
        added, skipped, inserted_names = _loader.merge_managed_mcp_into_json(
            mcp_json,
            block_key="mcpServers",
            mcp_configs=content.mcp_configs,
            target=target,
            skip_names=project_mcp_skip_names,
        )
        print(
            f"     mcp:      {added} new server(s) added to {mcp_json}, "
            f"{skipped} preserved (already configured)"
        )
        yield InstalledPath(mcp_json, "managed")

    # Per the v0.5 cross-agent hook gap analysis: Cursor has a native
    # hooks.json + hooks/ surface; copy the playbook hook scripts in and
    # write a cursor-shaped hooks.json so Cursor users get the same
    # enforcement Claude Code has had since v0.4.
    if content.hooks:
        # Codex adversarial round-2 [high]: reconcile prior-but-not-new
        # entries at this scope's hooks.json BEFORE the strip-add loop.
        # The strip-add only catches same-command-path upgrades; dropped
        # commands (in prior_hooks but not in the new set) need explicit
        # removal so a narrow profile doesn't leave them lingering. User-
        # level prior_hooks come straight from prior_managed_keys; project-
        # level prior_hooks are translated to the project's hooks_dir
        # before being passed in. v0.5 only reliably tracks user-level
        # paths in prior_managed_keys so the project-level reconcile uses
        # the same set for now (commands that match are stripped; commands
        # whose paths don't match this scope's hooks_dir pass through as
        # potentially-user-authored entries and survive).
        # v0.6 wrapper convention: when a hook declares
        # PLAYBOOK-HOOK-CURSOR-WRAPPER: <wrapper>.sh, the wrapper is what
        # Cursor fires. The core script is still copied (the wrapper invokes
        # it as a sibling) but NOT registered in hooks.json. The wrapper's
        # own PLAYBOOK-HOOK-CURSOR-ONLY entry registers itself when its turn
        # comes in the loop. is_wrapped_core() is the shared predicate
        # (hook_registration.py) used here, in install.py for lockfile
        # bookkeeping, and in the target materializer.
        # v0.8 (ADR-0037): scope cursor-installed hooks to those allowed for
        # the cursor adapter. is_hook_for_adapter drops hooks pinned to
        # PLAYBOOK-HOOK-ADAPTERS: <other-slug> (anchored-fs claude-shape).
        scope_cursor_hooks = [
            h for h in content.hooks if is_hook_for_adapter(h, "cursor")
        ]
        if prior_hooks:
            new_for_event: dict[str, set[str]] = {}
            for hook in scope_cursor_hooks:
                if is_wrapped_core(hook):
                    continue
                event_camel, _ = cursor_shaped_entry(
                    hook, str(hooks_dir / f"{hook.name}.sh")
                )
                new_for_event.setdefault(event_camel, set()).add(
                    str(hooks_dir / f"{hook.name}.sh")
                )
            translated_prior: dict[str, set[str]] = {}
            for event, paths in prior_hooks.items():
                translated_prior[event] = {str(hooks_dir / Path(p).name) for p in paths}
            removed = reconcile_cursor_shaped_hooks_in_json(
                hooks_json, new_for_event, translated_prior
            )
            if removed:
                print(
                    f"     hooks:    removed {removed} stale managed entr(ies) from {hooks_json}"
                )
        _loader.ensure_dir(hooks_dir)
        # Copy every cursor-scope hook (including wrapped cores) so wrappers
        # can find their sibling. Only the registration loop filters wrapped
        # cores; ADAPTERS-restricted hooks (e.g., anchored-fs) are already
        # excluded by scope_cursor_hooks.
        for hook in scope_cursor_hooks:
            hook_target = hooks_dir / f"{hook.name}.sh"
            shutil.copy2(hook.path, hook_target)
            hook_target.chmod(
                hook_target.stat().st_mode
                | _stat.S_IXUSR
                | _stat.S_IXGRP
                | _stat.S_IXOTH
            )
            yield InstalledPath(hook_target, "owned")
        print(f"     hooks:    {len(scope_cursor_hooks)} copied to {hooks_dir}")

        existing_hooks_doc: dict = {"version": 1, "hooks": {}}
        if hooks_json.exists():
            try:
                existing_hooks_doc = json.loads(hooks_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing_hooks_doc = {"version": 1, "hooks": {}}
        existing_hooks_doc.setdefault("version", 1)
        hook_block = existing_hooks_doc.setdefault("hooks", {})
        registered = 0
        for hook in scope_cursor_hooks:
            if is_wrapped_core(hook):
                continue
            command_path = str(hooks_dir / f"{hook.name}.sh")
            event, entry = cursor_shaped_entry(hook, command_path)
            event_block = hook_block.setdefault(event, [])
            event_block[:] = strip_cursor_command_from_entries(
                event_block, command_path
            )
            event_block.append(entry)
            registered += 1
        hooks_json.write_text(
            json.dumps(existing_hooks_doc, indent=2) + "\n", encoding="utf-8"
        )
        print(f"     hooks:    {registered} registered in {hooks_json}")
        yield InstalledPath(hooks_json, "managed")

    # Project scope only: write AGENTS.md at the project root via managed block.
    if scope == "project" and project_root is not None:
        project_agents_md = project_root / "AGENTS.md"
        action = (
            AgentsMd.load_or_empty(project_agents_md)
            .with_managed_rules(content.rules, label="cursor")
            .save_to(project_agents_md)
        )
        print(f"     agents.md:{project_agents_md} ({action})")
        yield InstalledPath(project_agents_md, "managed")


# _rule_description was inlined; rule descriptions now come from
# _loader.first_heading_or_default (per v0.6 review-2 fixup that
# consolidated the helper from cursor.py + windsurf.py + target_materializer.py).


ADAPTERS: list[Adapter] = [CursorAdapter()]
