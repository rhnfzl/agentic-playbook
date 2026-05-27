"""
Tier 2 adapter: Pi coding agent (pi.dev, npm: @earendil-works/pi-coding-agent).

Pi is a minimal terminal coding harness. Per pi.dev/docs/latest/usage Pi
loads AGENTS.md from ~/.pi/agent/, parent directories, and the current
directory; skills load from ~/.pi/agent/skills/ and ~/.agents/skills/
(cross-tool) among other locations.

Materializes (per Q4 v0.2 lock; Tier 2, skills + prompts only):
  - Skills under ~/.pi/agent/skills/<name>/SKILL.md (Pi's primary skill location)
  - Prompt templates under ~/.pi/agent/prompts/<name>.md if any in repo prompts/

Does NOT write (intentional, per Q4 lock):
  - ~/.pi/agent/AGENTS.md (Pi walks up parent dirs and picks up ~/AGENTS.md,
    which the claude_code adapter already maintains)
  - MCP, subagents, hooks, settings (Pi has none of these surfaces by design)

Reference: https://pi.dev/docs/latest/quickstart
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


class PiAdapter:
    name = "pi"
    tier = 2

    def detect(self) -> bool:
        return (Path.home() / ".pi").is_dir() or _loader.which("pi") is not None

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        _ = prior_managed_keys  # pi doesn't register MCP/hooks; no reconciliation
        home = Path.home()
        pi_dir = home / ".pi" / "agent"
        skills_dir = pi_dir / "skills"
        prompts_dir = pi_dir / "prompts"

        _loader.ensure_dir(pi_dir)
        _loader.ensure_dir(skills_dir)

        for skill in content.skills:
            skill_target = skills_dir / (skill.install_name or skill.name)
            for written in _loader.copy_skill_payload(skill, skill_target):
                yield InstalledPath(written, "owned")
        print(f"   skills:  {len(content.skills)} copied to {skills_dir}")

        if content.prompts:
            _loader.ensure_dir(prompts_dir)
            for prompt in content.prompts:
                prompt_target = prompts_dir / f"{prompt.name}.md"
                shutil.copy2(prompt.path, prompt_target)
                yield InstalledPath(prompt_target, "owned")
            print(f"   prompts: {len(content.prompts)} copied to {prompts_dir}")

        print(
            "   note:    relying on parent-dir AGENTS.md walk (~/AGENTS.md) for rules."
        )
        print("            no MCP / no subagents / no hooks (Pi has none by design).")


ADAPTERS: list[Adapter] = [PiAdapter()]
