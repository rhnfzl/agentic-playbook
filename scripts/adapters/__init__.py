"""Per-tool adapters (ADR-0024).

Each adapter module exposes `ADAPTERS: list[Adapter]`. Most modules export
one Adapter; `tier3` exports twenty (one per supported Tier 3 tool). The
dispatcher in scripts/install.py walks `ALL_ADAPTERS` instead of consulting
per-adapter hard-coded tables.

Adding a new tool = create a new module that exposes ADAPTERS, then add it
to the import list below. Explicit registry chosen over auto-walk so adding
an Adapter is a single, traceable diff.

Note: tier3 was renamed from agents_md in v0.5 to disambiguate from the
top-level scripts/agents_md.py document type module (the AgentsMd class
that adapters now use via AgentsMd.load_or_empty(p).with_managed_rules(...)).
"""

from . import (
    aider,
    claude_code,
    cline,
    codex,
    copilot,
    cursor,
    gemini_cli,
    pi,
    tier3,
    windsurf,
)
from ._loader import Adapter

ALL_ADAPTERS: list[Adapter] = [
    *claude_code.ADAPTERS,
    *codex.ADAPTERS,
    *cursor.ADAPTERS,
    *windsurf.ADAPTERS,
    *copilot.ADAPTERS,
    *gemini_cli.ADAPTERS,
    *aider.ADAPTERS,
    *cline.ADAPTERS,
    *pi.ADAPTERS,
    *tier3.ADAPTERS,
]
