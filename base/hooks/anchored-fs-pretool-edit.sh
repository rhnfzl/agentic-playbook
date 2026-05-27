#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|MultiEdit|Write
# PLAYBOOK-HOOK-ADAPTERS: claude-code
#
# Wrapper around anchored-fs's pretool_edit Python hook (per ADR-0037).
#
# Why a wrapper sits at hooks/ instead of inside the bundle:
# - The bundle's hook used to self-register in ~/.claude/settings.json via
#   `python install.py init`, which ran in parallel with the playbook
#   adapter pipeline and produced two parallel hook systems (one shell-in-
#   root, one Python-in-bundle). The playbook's hook_source_unification
#   gate plus doctor-verify couldn't see the Python hook.
# - The wrapper presents the bundle's hook as a first-class playbook hook
#   so all the layer-1/2/3 invariants (ADRs 0035 + 0036) apply uniformly.
# - PLAYBOOK-HOOK-ADAPTERS: claude-code scopes it to the only adapter
#   whose hook payload shape matches what the Python implementation
#   parses (Claude Code's tool_input/tool_response JSON).
#
# Why we don't inline the Python logic here: the bundle's pretool_edit.py
# imports `from daemon.client import call as daemon_call` and other bundle-
# internal modules. Re-implementing in pure bash would duplicate the daemon
# protocol; better to keep the implementation Pythonic and shell out.
#
# Graceful no-op if the bundle isn't materialized yet (e.g., the playbook
# install registered the hook but `make install` hasn't materialized
# ~/.config/agent-shared/mcp_servers/anchored-fs/ for this user). Exit 0
# preserves the underlying Edit; the daemon would no-op anyway.

set -euo pipefail

ANCHORED_FS_ROOT="${ANCHORED_FS_ROOT:-${HOME}/.config/agent-shared/mcp_servers/anchored-fs}"
HOOK_PY="${ANCHORED_FS_ROOT}/hooks/claude-code/pretool_edit.py"

if [[ ! -f "${HOOK_PY}" ]]; then
  exit 0
fi

PYTHONPATH="${ANCHORED_FS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" exec python3 "${HOOK_PY}" "$@"
