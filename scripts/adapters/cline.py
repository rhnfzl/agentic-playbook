"""
Tier 2 adapter: Cline (VS Code AI coding agent, OSS Apache 2.0).

Materializes into the resolved target project root, plus user-level global
rules in ~/.cline/:
  - Project rules as a managed block inside .clinerules (project root)
  - Rules as a managed block inside AGENTS.md (newer Cline reads it natively)
  - Global rules as a managed block inside ~/.cline/rules/playbook.md
  - Hook scripts under .clinerules/hooks/<name>.sh + Claude-shaped
    .clinerules/hooks.json (Cline v3.36+ accepts the Claude settings.json
    schema with minor matcher differences). Added in v0.5 per the
    multi-agent hook gap analysis.

Cline has step-by-step approval mode and a 2026 hook surface.

Reference: https://github.com/cline/cline
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd
from hook_registration import (
    claude_shaped_entry,
    is_hook_for_adapter,
    reconcile_claude_shaped_hooks_in_json,
    resolve_hook_event,
    strip_claude_command_from_entries,
)

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class ClineAdapter:
    name = "cline"
    tier = 2

    def detect(self) -> bool:
        return _loader.vscode_extension_present("saoudrizwan.claude-dev")

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        # Hook reconciliation wired in v0.5 per Codex P1 #1; see below.
        if target is None:
            raise ValueError("cline adapter requires a target project directory")
        target_root = target
        cline_rules_file = target_root / ".clinerules"
        agents_md = target_root / "AGENTS.md"

        home = Path.home()
        global_rules_dir = home / ".cline" / "rules"
        global_rules_file = global_rules_dir / "playbook.md"
        # Cline reads .clinerules as a FILE for managed rules; the hooks API
        # accepts a sibling .clinerules-hooks/ directory or ~/.cline/hooks/
        # at user level. Put hooks under ~/.cline/hooks/ so we never collide
        # with the .clinerules rules-file path. Project-local hook
        # registration is a v0.6 follow-up; for now Cline users get the
        # rules at project level and hooks at home level.
        cline_user_hooks_dir = home / ".cline" / "hooks"
        cline_user_hooks_json = home / ".cline" / "hooks.json"

        print(f"   target:  {target_root}")

        body = _loader.compose_agents_md(content.rules).rstrip()

        cline_header = (
            "# .clinerules\n\n"
            "Project rules loaded by Cline at session start. The block below is "
            "auto-managed by the coding-agents-playbook installer; content outside "
            "the markers is hand-authored and preserved across re-installs."
        )
        action = _loader.upsert_managed_block(
            cline_rules_file, body, header=cline_header
        )
        print(
            f"   rules:   {cline_rules_file} ({action}, {len(content.rules)} rule(s))"
        )
        yield InstalledPath(cline_rules_file, "managed")

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="cline")
            .save_to(agents_md)
        )
        print(f"   agents:  {agents_md} ({action})")
        yield InstalledPath(agents_md, "managed")

        _loader.ensure_dir(global_rules_dir)
        global_header = (
            "# Cline Global Playbook Rules\n\n"
            "User-level rules loaded by Cline across all projects. The block below "
            "is auto-managed by the coding-agents-playbook installer."
        )
        action = _loader.upsert_managed_block(
            global_rules_file, body, header=global_header
        )
        print(f"   global:  {global_rules_file} ({action})")
        yield InstalledPath(global_rules_file, "managed")

        # Per the v0.5 cross-agent hook gap analysis + Codex review P2
        # (round 2): reconcile fires unconditionally so an empty-hooks
        # profile still cleans up prior managed entries. The copy/register
        # block stays guarded by agent_hooks.
        #
        # v0.6: cursor-only hooks (e.g., the JSON-stdout advisory wrapper)
        # are not Cline-relevant and would be dead weight under ~/.cline/.
        # v0.8 (ADR-0037): PLAYBOOK-HOOK-ADAPTERS adds bundle-coupled hook
        # scoping; is_hook_for_adapter combines both filters.
        agent_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]

        new_hook_commands: dict[str, set[str]] = {}
        for hook in agent_hooks:
            event = resolve_hook_event(hook)
            new_hook_commands.setdefault(event, set()).add(
                str(cline_user_hooks_dir / f"{hook.name}.sh")
            )
        prior_hooks_raw = (prior_managed_keys or {}).get("hooks", {}) or {}
        prior_hooks = {event: set(paths) for event, paths in prior_hooks_raw.items()}
        removed_hooks = reconcile_claude_shaped_hooks_in_json(
            cline_user_hooks_json, new_hook_commands, prior_hooks
        )
        if removed_hooks:
            print(
                f"   hooks:   removed {removed_hooks} stale managed entr(ies) from {cline_user_hooks_json}"
            )

        if agent_hooks:
            _loader.ensure_dir(cline_user_hooks_dir)
            for hook in agent_hooks:
                hook_target = cline_user_hooks_dir / f"{hook.name}.sh"
                shutil.copy2(hook.path, hook_target)
                hook_target.chmod(
                    hook_target.stat().st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
                yield InstalledPath(hook_target, "owned")
            print(f"   hooks:   {len(agent_hooks)} copied to {cline_user_hooks_dir}")

            existing_hooks_doc: dict = {}
            if cline_user_hooks_json.exists():
                try:
                    existing_hooks_doc = json.loads(
                        cline_user_hooks_json.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    existing_hooks_doc = {}
            hook_block = existing_hooks_doc.setdefault("hooks", {})
            for hook in agent_hooks:
                command_path = str(cline_user_hooks_dir / f"{hook.name}.sh")
                event, entry = claude_shaped_entry(hook, command_path)
                event_block = hook_block.setdefault(event, [])
                event_block[:] = strip_claude_command_from_entries(
                    event_block, command_path
                )
                event_block.append(entry)
            cline_user_hooks_json.write_text(
                json.dumps(existing_hooks_doc, indent=2) + "\n", encoding="utf-8"
            )
            print(f"   hooks:   registered in {cline_user_hooks_json}")
            yield InstalledPath(cline_user_hooks_json, "managed")


ADAPTERS: list[Adapter] = [ClineAdapter()]
