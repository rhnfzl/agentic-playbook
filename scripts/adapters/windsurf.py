"""
Tier 1 adapter: Windsurf (Cognition, formerly Codeium).

Materializes:

  USER-LEVEL (~/.codeium/windsurf/):
    - global_rules.md (6000-char ceiling)
    - hooks/<name>.sh + hooks.json (Cascade-shaped, snake_case events)

  PROJECT-LEVEL (<target>/.windsurf/):
    - rules/<name>.md (always_on trigger)
    - skills/<name>/SKILL.md
    - hooks/<name>.sh + hooks.json (Cascade-shaped)
    - mcp.json (mcpServers block)
    - AGENTS.md managed block at project root

Subagents and slash commands are skipped: Windsurf's Cascade has custom
agent configurations but the file format is undocumented.

v0.6 (gap-analysis F16, F24, F26): Windsurf hooks now ship via a dedicated
Cascade translator (hooks/_cascade-translate.sh). Cascade's 12-event model
(pre_write_code / pre_run_command / etc.) and tool_info stdin shape do
not map one-to-one onto Claude's PreToolUse/PostToolUse {tool_name, tool_input}
shape. Instead of forking every hook script:

  1. Core hook scripts are copied to <windsurf>/hooks/<name>.sh unchanged.
  2. A single shared translator script (_cascade-translate.sh) is copied
     alongside; it reads Cascade stdin and re-encodes to Claude-shaped
     stdin before invoking the core.
  3. hooks.json entries register the translator + core path as the
     command (e.g. "/abs/.codeium/windsurf/hooks/_cascade-translate.sh
     /abs/.codeium/windsurf/hooks/never-push-to-develop.sh").

Auto-derive map (PreToolUse+Bash -> pre_run_command, PreToolUse+Edit-family
-> pre_write_code, etc.) lives in scripts/hook_registration.py. Authors
can pin a specific Cascade event with PLAYBOOK-HOOK-WINDSURF-EVENT.

Reference: https://docs.windsurf.com/windsurf/rules
            https://docs.windsurf.com/windsurf/cascade/hooks
            https://windsurf.com/changelog
"""

from __future__ import annotations

import json
import shutil
import stat
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd
from hook_registration import (
    is_hook_for_adapter,
    reconcile_windsurf_shaped_hooks_in_json,
    resolve_windsurf_events,
    strip_windsurf_command_from_entries,
    windsurf_shaped_entry,
    windsurf_show_output,
)

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


WINDSURF_GLOBAL_CHAR_LIMIT = 6000
CASCADE_TRANSLATOR_NAME = "_cascade-translate.sh"


class WindsurfAdapter:
    name = "windsurf"
    tier = 1

    def detect(self) -> bool:
        return (Path.home() / ".codeium").is_dir() or Path(
            "/Applications/Windsurf.app"
        ).exists()

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        if target is None:
            raise ValueError("windsurf adapter requires a target project directory")
        target_root = target
        windsurf_dir = target_root / ".windsurf"
        rules_dir = windsurf_dir / "rules"
        skills_dir = windsurf_dir / "skills"
        mcp_json = windsurf_dir / "mcp.json"
        agents_md = target_root / "AGENTS.md"

        home = Path.home()
        global_rules_dir = home / ".codeium" / "windsurf" / "memories"
        global_rules_path = global_rules_dir / "global_rules.md"
        user_windsurf_dir = home / ".codeium" / "windsurf"
        user_hooks_dir = user_windsurf_dir / "hooks"
        user_hooks_json = user_windsurf_dir / "hooks.json"

        _loader.ensure_dir(windsurf_dir)
        _loader.ensure_dir(rules_dir)

        # v0.9 (ADR-0039): per-(adapter, config_path) managed_keys schema.
        # Windsurf currently writes MCP only to <target>/.windsurf/mcp.json
        # (single config). managed_entries_for_config filters the lockfile
        # entry list to names installed at THIS path.
        from install_lockfile import managed_entries_for_config

        prior_mcp_all = (prior_managed_keys or {}).get("mcp_servers", [])
        prior_mcp_for_path = managed_entries_for_config(prior_mcp_all, mcp_json)
        new_mcp = {m.name for m in content.mcp_configs}
        removed = _loader.reconcile_managed_json_mcp(
            mcp_json,
            "mcpServers",
            new_mcp,
            prior_mcp_for_path,
        )
        if removed:
            print(
                f"   mcp:     removed {removed} stale managed entr(ies) from {mcp_json}"
            )

        print(f"   target:  {target_root}")

        default_desc = "Auto-distributed rule from coding-agents-playbook"
        for rule in content.rules:
            rule_target = rules_dir / f"{rule.name}.md"
            frontmatter = (
                "---\n"
                "trigger: always_on\n"
                "description: "
                + _loader.first_heading_or_default(rule.body, default=default_desc)
                + "\n"
                "---\n\n"
            )
            rule_target.write_text(frontmatter + rule.body, encoding="utf-8")
            yield InstalledPath(rule_target, "owned")
        print(f"   workspace rules:  {len(content.rules)} written to {rules_dir}")

        if content.skills:
            _loader.ensure_dir(skills_dir)
            for skill in content.skills:
                skill_target = skills_dir / (skill.install_name or skill.name)
                for written in _loader.copy_skill_payload(skill, skill_target):
                    yield InstalledPath(written, "owned")
            print(f"   skills:  {len(content.skills)} copied to {skills_dir}")

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="windsurf")
            .save_to(agents_md)
        )
        print(f"   agents:  {agents_md} ({action})")
        yield InstalledPath(agents_md, "managed")

        if global_rules_dir.parent.parent.is_dir():
            global_block = _loader.compose_agents_md(content.rules).rstrip()
            if len(global_block) > WINDSURF_GLOBAL_CHAR_LIMIT:
                print(
                    f"   warning: global rules ({len(global_block)} chars) exceed Windsurf's "
                    f"{WINDSURF_GLOBAL_CHAR_LIMIT}-char limit; truncating"
                )
                global_block = (
                    global_block[: WINDSURF_GLOBAL_CHAR_LIMIT - 50]
                    + "\n\n... (truncated by installer)"
                )
            global_header = (
                "# Windsurf Global Rules\n\n"
                "User-level rules loaded into every Windsurf session. The block below "
                "is auto-managed by the coding-agents-playbook installer; content "
                "outside the markers is hand-authored and preserved."
            )
            action = _loader.upsert_managed_block(
                global_rules_path, global_block, header=global_header
            )
            print(f"   global:  {global_rules_path} ({action})")
            yield InstalledPath(global_rules_path, "managed")
        else:
            print("   global:  ~/.codeium/windsurf/ not found; skipping global rules")

        if content.mcp_configs:
            # v0.8 (C2 + Codex adversarial fix): 3rd return is inserted
            # names list; managed_keys recording happens in
            # scripts/install.py:_new_managed_keys_for which now
            # considers existing user entries.
            added, skipped, inserted_names = _loader.merge_managed_mcp_into_json(
                mcp_json,
                block_key="mcpServers",
                mcp_configs=content.mcp_configs,
                target=target,
            )
            print(f"   mcp:     {added} new added to {mcp_json}, {skipped} preserved")
            yield InstalledPath(mcp_json, "managed")

        # v0.6: Cascade hooks. Install at BOTH user-level (so global hooks
        # follow the user across workspaces) AND project-level (so
        # repo-scoped hooks land in .windsurf/hooks.json). Skip cursor-only
        # hooks (e.g. the JSON-stdout advisory wrapper); they're not
        # Cascade-relevant.
        # v0.6 (Codex review P2): _materialize_cascade_hooks runs even when
        # the new profile has zero hooks so that a profile narrow cleans
        # up prior managed Cascade entries instead of leaving stale
        # registrations referencing absent hook scripts. The empty-hooks
        # branch runs only the reconcile path.
        # v0.8 (ADR-0037): is_hook_for_adapter combines cursor-only +
        # PLAYBOOK-HOOK-ADAPTERS so bundle-coupled hooks scoped to a
        # different adapter are dropped here too.
        cascade_hooks = [h for h in content.hooks if is_hook_for_adapter(h, self.name)]
        if user_windsurf_dir.parent.is_dir():
            yield from self._materialize_cascade_hooks(
                cascade_hooks,
                hooks_dir=user_hooks_dir,
                hooks_json=user_hooks_json,
                prior_managed_keys=prior_managed_keys,
                scope_label="user",
            )
        yield from self._materialize_cascade_hooks(
            cascade_hooks,
            hooks_dir=windsurf_dir / "hooks",
            hooks_json=windsurf_dir / "hooks.json",
            prior_managed_keys=prior_managed_keys,
            scope_label="project",
        )

    def _materialize_cascade_hooks(
        self,
        hooks: list,
        *,
        hooks_dir: Path,
        hooks_json: Path,
        prior_managed_keys: dict | None,
        scope_label: str,
    ) -> Iterable[InstalledPath]:
        """Copy core hooks + the Cascade translator, write Cascade-shaped
        hooks.json. Reconciles dropped entries against prior_managed_keys.

        prior_managed_keys.windsurf_hooks (set[str]): set of prior hook
        names (no extension) registered last install. Used to surgically
        drop entries that fell out of the new profile.
        """
        _loader.ensure_dir(hooks_dir)
        translator_dest = hooks_dir / CASCADE_TRANSLATOR_NAME
        # v0.11 (ADR-0040): hooks/ moved to base/hooks/; legacy fallback
        # left in for transition resilience (will be dropped once all
        # adapters route through PlaybookContent.load).
        repo_root = _repo_root()
        translator_source = repo_root / "base" / "hooks" / CASCADE_TRANSLATOR_NAME
        if not translator_source.exists():
            translator_source = repo_root / "hooks" / CASCADE_TRANSLATOR_NAME
        if not translator_source.exists():
            print(
                f"   hooks:   WARNING translator script missing at {translator_source}; skipping Cascade registration"
            )
            return
        shutil.copy2(translator_source, translator_dest)
        translator_dest.chmod(
            translator_dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )
        yield InstalledPath(translator_dest, "owned")

        # Copy + register each hook with derived Cascade events.
        prior_hook_paths_raw = (prior_managed_keys or {}).get(
            "windsurf_hooks", {}
        ) or {}
        prior_hook_paths: set[str] = set()
        for name in prior_hook_paths_raw:
            prior_hook_paths.add(str(hooks_dir / f"{name}.sh"))

        new_hook_paths: set[str] = set()
        copied = 0
        registrations: list[tuple[str, str, bool]] = []
        for hook in hooks:
            events = resolve_windsurf_events(hook)
            if not events:
                # No Cascade equivalent; skip both copy and registration.
                continue
            hook_dest = hooks_dir / f"{hook.name}.sh"
            shutil.copy2(hook.path, hook_dest)
            hook_dest.chmod(
                hook_dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )
            yield InstalledPath(hook_dest, "owned")
            copied += 1
            new_hook_paths.add(str(hook_dest))
            show = windsurf_show_output(hook)
            for event in events:
                registrations.append((event, str(hook_dest), show))

        # Reconcile: surgical strip of prior hook paths before fresh
        # registrations. Runs unconditionally so an empty new set still
        # cleans up prior entries.
        removed = reconcile_windsurf_shaped_hooks_in_json(
            hooks_json, new_hook_paths, prior_hook_paths
        )
        if removed:
            print(
                f"   hooks:   removed {removed} stale managed Cascade entr(ies) from {hooks_json}"
            )

        if not registrations:
            return

        existing: dict = {}
        if hooks_json.exists():
            try:
                existing = json.loads(hooks_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        hook_block = existing.setdefault("hooks", {})

        # Strip current playbook command strings from every event slot so
        # re-runs are idempotent and event-migrations (auto-derive change)
        # don't leave stale entries behind.
        for _, hook_path, _ in registrations:
            for event_entries in hook_block.values():
                if isinstance(event_entries, list):
                    event_entries[:] = strip_windsurf_command_from_entries(
                        event_entries, hook_path
                    )

        translator_str = str(translator_dest)
        for event, hook_path, show in registrations:
            entry = windsurf_shaped_entry(
                command_path=hook_path,
                translator_path=translator_str,
                show_output=show,
            )
            hook_block.setdefault(event, []).append(entry)

        hooks_json.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        print(
            f"   hooks:   {copied} copied + {len(registrations)} Cascade registrations "
            f"in {hooks_json} ({scope_label})"
        )
        yield InstalledPath(hooks_json, "managed")


# v0.6 review-2 fixup: the canonical repo-root constant lives in
# scripts/install.py (REPO_ROOT). We import it lazily because both
# adapters/__init__.py and install.py reach into this module at startup,
# so an unconditional top-level import would cycle.
def _repo_root() -> Path:
    """Return the playbook repo root using the canonical install.py
    constant. Lazy import avoids a startup cycle between install.py and
    adapters/__init__.py.
    """
    from install import REPO_ROOT

    return REPO_ROOT


# _rule_description was inlined; rule descriptions now come from
# _loader.first_heading_or_default (per v0.6 review-2 fixup that
# consolidated the helper from cursor.py + windsurf.py + target_materializer.py).


ADAPTERS: list[Adapter] = [WindsurfAdapter()]
