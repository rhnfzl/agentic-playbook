#!/usr/bin/env bash
# anchored-fs bootstrap (per ADR-0026 bundle lifecycle convention, v0.5 extension).
#
# Per Codex review P1 (round 2): this used to call `install.py init`, which
# wrote anchored-fs into ~/.claude.json and ~/.codex/config.toml with
# allowed_root=$HOME. When the playbook installer runs this bootstrap as
# part of `make install --target <project>`, the home-scoped registration
# lands BEFORE the playbook adapters get a turn. The adapters then see the
# entries as pre-existing and preserve them, so the target-scoped
# {{PLAYBOOK_TARGET}} config from server.json is never applied. Result:
# anchored-fs accidentally gets home-wide filesystem access in a
# target-scoped install.
#
# v0.5 fix: bootstrap is now a notice-only no-op. The playbook's MCP-
# registering adapters (claude_code, codex, cursor, windsurf) read
# server.json directly and expand {{PLAYBOOK_TARGET}} to the correct
# target dir via _loader.expand_agent_shared_placeholder; they own
# registration end to end. The bundle convention is conformed via the
# file layout (bundle/install.py + bundle/health.sh present); the actual
# init flow (venv, launchd plist, manifest writes) remains accessible via
# `python3 mcp/anchored-fs/install.py init` for users who want the
# original behavior outside the playbook install path.
#
# Deferred to v0.6: a proper bundle/bootstrap.sh that runs venv + plist
# only (no MCP registration) via a new --skip-registration flag on
# install.py, so the playbook installer can lifecycle the venv work
# without conflicting with adapter-owned MCP entries.

set -euo pipefail

echo "[anchored-fs] bootstrap: no-op (playbook adapters own MCP registration)" >&2
exit 0
