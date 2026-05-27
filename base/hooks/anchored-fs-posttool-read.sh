#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PostToolUse
# PLAYBOOK-HOOK-MATCHER: Read
# PLAYBOOK-HOOK-ADAPTERS: claude-code
#
# Wrapper around anchored-fs's posttool_read Python hook (per ADR-0037).
# Same rationale as the pretool_edit wrapper: present a first-class
# playbook hook surface so layer-1/2/3 invariants apply uniformly, and
# scope to claude-code because the Python implementation parses Claude
# Code's tool_response JSON payload.

set -euo pipefail

ANCHORED_FS_ROOT="${ANCHORED_FS_ROOT:-${HOME}/.config/agent-shared/mcp_servers/anchored-fs}"
HOOK_PY="${ANCHORED_FS_ROOT}/hooks/claude-code/posttool_read.py"

if [[ ! -f "${HOOK_PY}" ]]; then
  exit 0
fi

PYTHONPATH="${ANCHORED_FS_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" exec python3 "${HOOK_PY}" "$@"
