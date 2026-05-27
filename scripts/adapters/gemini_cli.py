"""
Tier 2 adapter: Gemini CLI (Google).

Materializes into the resolved target project root:
  - .gemini/settings.json with context.fileName pointed at AGENTS.md
  - Rules as a managed block inside AGENTS.md (preserves user content)

Gemini CLI does not have a skills system; the rules in AGENTS.md function
as its always-on context.

Reference: https://github.com/google-gemini/gemini-cli
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agents_md import AgentsMd

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class GeminiCliAdapter:
    name = "gemini-cli"
    tier = 2

    def detect(self) -> bool:
        return (Path.home() / ".gemini").is_dir() or _loader.which("gemini") is not None

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        _ = prior_managed_keys  # gemini-cli doesn't register MCP/hooks; no reconciliation
        if target is None:
            raise ValueError("gemini-cli adapter requires a target project directory")
        target_root = target
        gemini_dir = target_root / ".gemini"
        settings_path = gemini_dir / "settings.json"
        agents_md = target_root / "AGENTS.md"

        _loader.ensure_dir(gemini_dir)
        print(f"   target:  {target_root}")

        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label="gemini-cli")
            .save_to(agents_md)
        )
        print(f"   agents:  {agents_md} ({action})")
        yield InstalledPath(agents_md, "managed")

        settings: dict = {}
        if settings_path.exists():
            try:
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                settings = {}

        settings.setdefault("context", {})["fileName"] = "AGENTS.md"
        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
        print(f"   config:  {settings_path} (context.fileName=AGENTS.md)")
        yield InstalledPath(settings_path, "managed")


ADAPTERS: list[Adapter] = [GeminiCliAdapter()]
