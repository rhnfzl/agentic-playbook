"""
Tier 2 adapter: GitHub Copilot / Copilot Workspace.

Materializes into the resolved target project root:
  - Rules as a managed block inside .github/copilot-instructions.md
  - Rules as a managed block inside AGENTS.md (Copilot reads it natively too)
  - Hook scripts under .github/hooks/<name>.sh + Claude-shaped
    .github/hooks.json (VS Code Insiders preview accepts Claude
    settings.json-compatible schema). Added in v0.5 per the multi-agent
    hook gap analysis.

Both files use managed blocks so pre-existing hand-authored content is
preserved across re-installs.

Reference: https://docs.github.com/en/copilot/customizing-copilot/about-customizing-github-copilot-chat-responses
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


class CopilotAdapter:
    name = "copilot"
    tier = 2

    def detect(self) -> bool:
        return (
            Path.home() / ".config" / "github-copilot"
        ).is_dir() or _loader.vscode_extension_present("github.copilot")

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        # Hook reconciliation wired in v0.5 per Codex P1 #1; see below.
        if target is None:
            raise ValueError("copilot adapter requires a target project directory")
        target_root = target
        github_dir = target_root / ".github"
        copilot_md = github_dir / "copilot-instructions.md"
        agents_md = target_root / "AGENTS.md"
        copilot_hooks_dir = github_dir / "hooks"
        copilot_hooks_json = github_dir / "hooks.json"

        _loader.ensure_dir(github_dir)
        print(f"   target:  {target_root}")

        body = _loader.compose_agents_md(content.rules).rstrip()
        copilot_header = (
            "# Copilot Instructions\n\n"
            "Repository-wide guidance for GitHub Copilot. The block below is "
            "auto-managed by the coding-agents-playbook installer; content outside "
            "the markers is hand-authored and preserved across re-installs."
        )
        action = _loader.upsert_managed_block(copilot_md, body, header=copilot_header)
        print(f"   copilot: {copilot_md} ({action})")
        yield InstalledPath(copilot_md, "managed")

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="copilot")
            .save_to(agents_md)
        )
        print(f"   agents:  {agents_md} ({action})")
        yield InstalledPath(agents_md, "managed")

        # Per the v0.5 cross-agent hook gap analysis + Codex review P2
        # (round 2): reconcile fires unconditionally so an empty-hooks
        # profile still cleans up prior managed entries. The copy/register
        # block stays guarded by agent_hooks.
        #
        # v0.6: cursor-only hooks (e.g., the JSON-stdout advisory wrapper)
        # are not Copilot-relevant.
        # v0.8 (ADR-0037): is_hook_for_adapter also drops bundle-coupled
        # hooks scoped to other adapters via PLAYBOOK-HOOK-ADAPTERS.
        agent_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]

        new_hook_commands: dict[str, set[str]] = {}
        for hook in agent_hooks:
            event = resolve_hook_event(hook)
            new_hook_commands.setdefault(event, set()).add(
                str(copilot_hooks_dir / f"{hook.name}.sh")
            )
        prior_hooks_raw = (prior_managed_keys or {}).get("hooks", {}) or {}
        prior_hooks = {event: set(paths) for event, paths in prior_hooks_raw.items()}
        removed_hooks = reconcile_claude_shaped_hooks_in_json(
            copilot_hooks_json, new_hook_commands, prior_hooks
        )
        if removed_hooks:
            print(
                f"   hooks:   removed {removed_hooks} stale managed entr(ies) from {copilot_hooks_json}"
            )

        if agent_hooks:
            _loader.ensure_dir(copilot_hooks_dir)
            for hook in agent_hooks:
                hook_target = copilot_hooks_dir / f"{hook.name}.sh"
                shutil.copy2(hook.path, hook_target)
                hook_target.chmod(
                    hook_target.stat().st_mode
                    | stat.S_IXUSR
                    | stat.S_IXGRP
                    | stat.S_IXOTH
                )
                yield InstalledPath(hook_target, "owned")
            print(f"   hooks:   {len(agent_hooks)} copied to {copilot_hooks_dir}")

            existing_hooks_doc: dict = {}
            if copilot_hooks_json.exists():
                try:
                    existing_hooks_doc = json.loads(
                        copilot_hooks_json.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    existing_hooks_doc = {}
            hook_block = existing_hooks_doc.setdefault("hooks", {})
            for hook in agent_hooks:
                command_path = str(copilot_hooks_dir / f"{hook.name}.sh")
                event, entry = claude_shaped_entry(hook, command_path)
                event_block = hook_block.setdefault(event, [])
                event_block[:] = strip_claude_command_from_entries(
                    event_block, command_path
                )
                event_block.append(entry)
            copilot_hooks_json.write_text(
                json.dumps(existing_hooks_doc, indent=2) + "\n", encoding="utf-8"
            )
            print(f"   hooks:   registered in {copilot_hooks_json}")
            yield InstalledPath(copilot_hooks_json, "managed")


ADAPTERS: list[Adapter] = [CopilotAdapter()]
