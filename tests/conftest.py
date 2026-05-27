"""Shared pytest fixtures for the v0.5 lifecycle test suite.

Pytest is the v0.5 test entry point for lifecycle regression scenarios
(per the grilling decision; not in a dedicated ADR). The existing
scripts/test_adapters.py 192-check Reporter smoke continues to run via
`python3 scripts/test_adapters.py`; the lifecycle scenarios in
tests/lifecycle/ exercise the v0.5 additions (target materialization,
hook reconciliation, AgentsMd round-trip).

Fixtures injected by conftest.py:

  repo_root      Path to the playbook checkout (script-resolved).
  tmp_home       Tmp directory with $HOME redirected via monkeypatch.
                 Use when an adapter writes into ~/.claude/, ~/.codex/,
                 etc., and the test must not touch the real machine.
  tmp_target     Fresh project directory for per-target install tests.
                 Already exists as a directory; add AGENTS.md +
                 .playbook-config.yaml inside the test as needed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


@pytest.fixture
def repo_root() -> Path:
    """Path to the playbook checkout."""
    return REPO_ROOT


@pytest.fixture
def tmp_home(monkeypatch, tmp_path) -> Path:
    """Redirect HOME to a tmpdir so home-touching adapters don't pollute
    the real environment. Sets HOME for both os.environ and the
    Path.home() resolver. Cleaned up by pytest's tmp_path fixture.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def tmp_target(tmp_path) -> Path:
    """Fresh project directory for per-target install tests."""
    target = tmp_path / "project"
    target.mkdir()
    return target
