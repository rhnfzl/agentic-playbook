# Phase 0.1 Spike Result

**Date:** 2026-05-24
**Goal:** Verify subprocess-proxy approach (A1) is feasible for wrapping `@modelcontextprotocol/server-filesystem` from a Python FastMCP server.

## Findings

- `npx` is available at `/opt/homebrew/bin/npx` (Node v26.0.0, npx v11.12.1).
- `@modelcontextprotocol/server-filesystem@2026.1.14` started cleanly via stdio JSON-RPC.
- The full handshake completed: `initialize` returned `serverInfo {name: "secure-filesystem-server", version: "0.2.0", protocolVersion: "2025-03-26"}`; `notifications/initialized` accepted; `tools/list` returned 14 tools; `tools/call list_directory` returned real entries from `~`.
- Subprocess terminated cleanly via `.terminate()` + `.wait(timeout=5)`.
- Total wall time ~4.9s, dominated by npx cache check + Node startup. Once warm, per-call latency is sub-100ms.

## Refinements for Phase 0 (inform Tasks 9, 10, 11)

1. **Pin the package version, do not float via `npx -y`.** Node v26 + stale npx cache caused an ESM resolution failure on the first attempt (older zod dependency lacked the `exports` field for Node v26 ESM resolution). Production wrapping in `delegate.py` should spawn `npx --package @modelcontextprotocol/server-filesystem@2026.1.14 -y server-filesystem ...` or install the package locally and invoke directly, rather than relying on `npx -y` floating to the latest.

2. **The stock server exposes 14 tools, not 7.** Full list:
   - `read_file` (deprecated alias)
   - `read_text_file`
   - `read_media_file`
   - `read_multiple_files`
   - `write_file`
   - `edit_file` (we override this)
   - `create_directory`
   - `list_directory`
   - `list_directory_with_sizes`
   - `directory_tree`
   - `move_file`
   - `search_files`
   - `get_file_info`
   - `list_allowed_directories`

   Task 11 (`server.py`) must register passthrough for all 13 non-overridden tools (`edit_file` is overridden, and we add `preview_edit_match`).

3. **`tools/call` result shape is content-block wrapped.** The stock server returns results as:
   ```json
   {"content": [{"type": "text", "text": "<actual content>"}]}
   ```
   not as a flat string or dict. Our `tools/edit_file.py` (Task 10) overrides must wrap their return value in the same shape, e.g.:
   ```python
   return {"content": [{"type": "text", "text": json.dumps({"ok": True, ...})}]}
   ```
   so MCP clients see a uniform envelope.

## Decision

**Phase 0.1 GATE PASSED. Commit to A1 (subprocess proxy).** Proceed to Phase 0 with the three refinements above incorporated into the plan.
