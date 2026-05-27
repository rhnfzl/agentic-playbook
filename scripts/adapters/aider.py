"""
Tier 2 adapter: Aider (git-native terminal coding agent).

Materializes into the resolved target project root:
  - .aider.conf.yml so Aider auto-reads AGENTS.md on every session
  - Rules as a managed block inside AGENTS.md (preserves user content)

Aider has no skills system; rules in AGENTS.md provide always-on context.

Reference: https://aider.chat/docs/config/aider_conf.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class AiderAdapter:
    name = "aider"
    tier = 2

    def detect(self) -> bool:
        return _loader.which("aider") is not None

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        _ = prior_managed_keys  # aider doesn't register MCP/hooks; no reconciliation
        if target is None:
            raise ValueError("aider adapter requires a target project directory")
        target_root = target
        conf_path = target_root / ".aider.conf.yml"
        agents_md = target_root / "AGENTS.md"

        print(f"   target:  {target_root}")

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="aider")
            .save_to(agents_md)
        )
        print(f"   agents:  {agents_md} ({action})")
        yield InstalledPath(agents_md, "managed")

        existing_lines: list[str] = []
        if conf_path.exists():
            existing_lines = conf_path.read_text(encoding="utf-8").splitlines()

        has_read_agents = any("AGENTS.md" in line for line in existing_lines)
        if has_read_agents:
            print(f"   config:  {conf_path} already references AGENTS.md")
        else:
            new_lines = existing_lines + [
                "",
                "# Auto-added by coding-agents-playbook installer",
                "read:",
                "  - AGENTS.md",
            ]
            conf_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            print(f"   config:  {conf_path} (added read: AGENTS.md)")
        yield InstalledPath(conf_path, "managed")


ADAPTERS: list[Adapter] = [AiderAdapter()]
