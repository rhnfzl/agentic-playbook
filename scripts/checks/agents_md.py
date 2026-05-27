"""AGENTS.md governance check (delegates to scripts/check_agents_md.py).

Per the resolved Candidate 8 design this check will eventually delegate to
the AgentsMd.validate() method on the parsed document type. For now it
still wraps the existing regex-based governance pass.
"""

from __future__ import annotations

from . import CheckContext, CheckResult
from ._legacy import capture_legacy_main


def run(ctx: CheckContext) -> CheckResult:
    return capture_legacy_main("check_agents_md", summary="AGENTS.md governance")
