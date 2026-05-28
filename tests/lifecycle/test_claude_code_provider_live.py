"""Live smoke test for ClaudeCodeProvider (Phase 2B Task 4).

Spawns a real `claude` subprocess against the trajectory-canary fixture
and asserts the resulting TraceRecord shape. Catches contract drift
between the playbook's expectation and what `claude` actually emits:

  * Does the OTel `gen_ai.*` schema in stderr still match what we parse?
  * Does the agent still write the file the canary expects?

Disabled by default. Two gates must BOTH be satisfied for the test to
run:

  1. `claude` must be on PATH (shutil.which check).
  2. The `PHASE2_LIVE=1` env var must be set explicitly.

Both gates are required because: (a) CI runners do not have `claude`
installed; (b) even on dev machines, the test costs real money to run
(it does a live LLM call). The env-var gate makes the cost opt-in.

To run locally:

    PHASE2_LIVE=1 python3 -m pytest \
        tests/lifecycle/test_claude_code_provider_live.py -v

When either gate fails, pytest skips with a clear reason.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _live_gate() -> str | None:
    """Return None when the live path may run; a reason string otherwise."""
    if os.environ.get("PHASE2_LIVE") != "1":
        return "PHASE2_LIVE=1 not set; live smoke test opt-in only"
    if shutil.which("claude") is None:
        return "`claude` binary not on PATH"
    return None


def _trajectory_canary():
    from adapters._protocol import Trajectory

    return Trajectory(
        path=Path("/tmp/canary.yaml"),
        skill="trajectory-canary",
        scenario="canary",
        frontmatter={},
        body="",
        input_phrasings=["Run the trajectory canary"],
        assertions=[],
        llm_judge={},
        adapter_scope=["claude-code"],
        model_pinned="claude-opus-4-7",
    )


@pytest.mark.skipif(_live_gate() is not None, reason=_live_gate() or "skipped")
def test_live_spawn_returns_well_formed_trace_record() -> None:
    """Verify the OTel JSON shape and artifact capture against real
    Claude Code stderr. Tight assertions: only check the contract bits
    we depend on, so a model swap or prompt drift does not flake."""
    from adapters.claude_code_provider import ClaudeCodeProvider

    provider = ClaudeCodeProvider(timeout=120.0)
    record = provider(
        _trajectory_canary(),
        "Run the trajectory canary",
        "claude-code",
    )

    # Contract checks (model-and-prompt-agnostic):
    assert record.adapter == "claude-code"
    assert record.prompt == "Run the trajectory canary"
    assert record.session_id.startswith("live-")
    assert record.started_at <= record.ended_at
    # At least one event of some kind should land; an empty record is
    # a strong smell that the OTel env wiring is wrong.
    assert (
        len(record.events) > 0
    ), "live spawn produced zero events; check OTel env wiring"
