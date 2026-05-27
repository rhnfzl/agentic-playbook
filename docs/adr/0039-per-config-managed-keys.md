---
status: accepted
date: 2026-05-26
amends: ["0024"]
related: ["0026", "0036", "0037", "0038"]
---

# ADR-0039: Per-(adapter, config_path) managed_keys with ownership metadata (v0.9 hard schema cut)

## Status

Accepted. Implementation in v0.9.

## Context

v0.8 surfaced a managed_keys ownership gap during the Cursor multi-config
review rounds (5 through 9). The v0.8 lockfile keys ownership per
adapter only:

```json
"managed_keys": {
  "mcp_servers": {
    "cursor": ["anchored-fs", "tavily"]
  }
}
```

This cannot represent the same server name installed into different
config paths. Cursor supports two MCP config locations:

- `~/.cursor/mcp.json` ("global" in Cursor docs, user-scope)
- `<project>/.cursor/mcp.json` ("project-managed", workspace-scope)

Project-scope wins on name collision per Cursor precedence. A user-only
entry and a project-only entry can share a name. On uninstall the
per-adapter set cannot tell which config to clean.

ADR-0024 v0.8 amendment documented this gap as deferred work. v0.8
shipped a Cursor-specific UNION pre_existing trade-off that errs on the
side of NOT deleting user-only data, accepting that project-level
entries can orphan after a user narrows scope.

### Research informing v0.9 (2026-05-26 Tavily survey)

A six-query Tavily research pass synthesized current MCP lifecycle
conventions across Cursor, Windsurf, Claude Code, Cline, GitHub Copilot,
and Codex CLI:

1. **No vendor offers a native managedBy field** in mcp.json
   equivalents. External installers must maintain their own ownership
   lockfile (the v0.8 approach is the right pattern, not a workaround).
2. **Multi-config is industry-broad**, not Cursor-only. GitHub Copilot
   has three config locations (`.github/mcp.json`, `.vscode/mcp.json`,
   `.vs/mcp.json`). Claude Code has three scopes (local / project /
   user). Per-(adapter, config_path) keying generalizes to all of them.
3. **Streamable HTTP is the canonical MCP transport** since 2025-03-26
   spec; SSE was deprecated June 2025. HTTP MCP probes must target
   Streamable HTTP, not legacy SSE.
4. **Auth-header substitution syntaxes diverge** across vendors: Cursor
   uses `${env:VAR}`, Codex uses a `bearer_token_env_var` field, generic
   `{{VAR}}` templating exists in some gateways. v0.9 probe supports
   all three.
5. **Hook event names diverge** across vendors (Claude Code PascalCase
   vs Cursor camelCase) but the underlying model (PreToolUse /
   PostToolUse / permission gates) has converged. Per-adapter resolution
   is correct.
6. **Programmatic SDKs exist for some adapters** (Codex `codex mcp add`,
   Copilot SDK) but not all. File-edit-based install remains the lowest
   common denominator; SDK migration is deferred to v0.10+.

## Decision

### Hard schema cut to per-(adapter, config_path) entries with ownership metadata

The lockfile's `managed_keys.mcp_servers` field changes from
`dict[adapter, list[name]]` to `dict[adapter, list[Entry]]` where Entry
is:

```json
{
  "id": "<uuid4>",
  "name": "<mcp-server-name>",
  "config_path": "<absolute path>",
  "scope": "global" | "project",
  "installed_at": "<ISO8601 UTC>"
}
```

Example post-install lockfile:

```json
{
  "lockfile_version": 3,
  "managed_keys": {
    "mcp_servers": {
      "cursor": [
        {
          "id": "c1a2b3d4-...",
          "name": "anchored-fs",
          "config_path": "/Users/me/.cursor/mcp.json",
          "scope": "global",
          "installed_at": "2026-05-26T12:00:00Z"
        },
        {
          "id": "d4e5f6g7-...",
          "name": "tavily",
          "config_path": "/Users/me/projects/foo/.cursor/mcp.json",
          "scope": "project",
          "installed_at": "2026-05-26T12:00:00Z"
        }
      ],
      "claude-code": [
        {
          "id": "g7h8i9j0-...",
          "name": "anchored-fs",
          "config_path": "/Users/me/.claude.json",
          "scope": "global",
          "installed_at": "2026-05-26T12:00:00Z"
        }
      ]
    }
  }
}
```

Field semantics:

- **id**: uuid4 generated at install time; stable identity that
  survives renames or duplicate names across configs. Allows future
  cross-host registry references.
- **name**: human MCP server name; not authoritative for identity
  (collisions across scopes are expected).
- **config_path**: absolute path to the native MCP config file the
  entry was written into. Used by uninstall to target the exact file.
- **scope**: `"global"` for user-home configs, `"project"` for
  workspace configs. Records the agent's precedence position at
  install time. v0.9 adapter map:
  - Cursor: `global = ~/.cursor/mcp.json`,
    `project = <target>/.cursor/mcp.json`
  - Claude Code: `global = ~/.claude.json`,
    `project = <target>/.mcp.json`
  - GitHub Copilot: `global = ~/.copilot/mcp-config.json`,
    `project = .vscode/mcp.json` or `.github/mcp.json`
  - Codex: `global = ~/.codex/config.toml` (single scope)
  - Windsurf: `global = ~/.codeium/windsurf/mcp_config.json` (single
    scope)
  - Cline: single workspace scope
- **installed_at**: ISO8601 UTC timestamp; audit trail and supports
  "uninstall everything from before date X" workflows.

### Native managedBy marker

When the adapter's native MCP config format permits arbitrary
top-level fields, the installer also writes:

```json
{
  "mcpServers": { ... },
  "metadata": {
    "managedBy": "coding-agents-playbook",
    "lockfile_version": 3,
    "last_updated_at": "2026-05-26T12:00:00Z"
  }
}
```

Format-by-format support:

- Cursor `mcp.json`: extra top-level keys allowed; write marker.
- Claude Code `~/.claude.json` + project `.mcp.json`: extra top-level
  keys allowed; write marker.
- Codex `config.toml`: write `[metadata]` table; write marker.
- Copilot `mcp-config.json`: extra top-level keys allowed; write
  marker.
- Windsurf `mcp_config.json`: extra top-level keys allowed; write
  marker.
- Cline: scope TBD; if format permits, write marker.

The marker is informational. The lockfile remains authoritative for
ownership decisions. The marker exists so a future operator (or
auditor) reading mcp.json can identify which entries are tool-managed
without consulting the lockfile. The write is wrapped in try/except;
if a vendor changes the schema to reject extra fields, the marker
write silently degrades to lockfile-only ownership.

### Streamable HTTP probe with env-var substitution

The HTTP MCP probe extension (v0.9 item #2) targets the 2025-03-26
Streamable HTTP spec:

1. Detect transport type from config: `url`-only entries are HTTP;
   `command`-based entries are stdio (v0.8 probe path).
2. POST `<url>` (typically ending in `/mcp`) with a single JSON-RPC
   InitializeRequest body and
   `Accept: application/json, text/event-stream` header.
3. Read response. Success requires HTTP 200 + JSON body containing
   `result.serverInfo` (matches stdio probe contract).
4. If response includes `Mcp-Session-Id` header, record it
   (informational; no follow-up DELETE in v0.9).
5. SSE-only entries (no Streamable HTTP support) skip with reason
   `"skipped: sse-only-not-supported"`.

Header substitution:

- `${env:VAR_NAME}` (Cursor syntax) and `{{VAR_NAME}}` (generic) are
  substituted from the process environment.
- An explicit `bearer_token_env_var` field (Codex syntax) resolves to
  `Authorization: Bearer <env value>` before the request.
- If any referenced env var is unset, probe skips with reason
  `"skipped: env-var-unset:<VAR_NAME>"`. The probe NEVER reads user
  secrets to satisfy a substitution; missing means skip.

### No migration script

The playbook is in build phase. Existing v0.8 lockfiles exist only on
the two-developer team's machines. Hard cut means
`playbook uninstall && playbook install` to upgrade. No version-bumped
dual-read code path. No legacy shape detection. No migration logic
anywhere. The lockfile_version bumps from 2 to 3; readers MUST
require lockfile_version 3 or error.

## Consequences

### Positive

- Per-config ownership becomes representable; Cursor multi-config
  orphan risk closes.
- Generalizes to GitHub Copilot's three-location split and Claude
  Code's three-scope split without further schema change.
- List-of-records is future-extensible (add fields per entry without
  breaking the schema).
- Native managedBy marker improves operator-readability without
  compromising the authoritative lockfile.
- ADR-0024 v0.8 amendment trade-off (Cursor UNION pre_existing) is no
  longer needed; ownership is precise per (adapter, config_path).
- HTTP transport coverage closes the v0.8 probe gap (Tavily / error-tracking
  style entries no longer silently skip).
- Streamable HTTP target aligns with current MCP spec (2025-03-26 +
  June 2025 SSE deprecation).
- Env-var substitution skip-on-unset prevents secret-reading attack
  surface.

### Negative

- v0.8 lockfiles require uninstall+reinstall to upgrade. Acceptable
  in build phase.
- Slightly heavier JSON per entry (~80 bytes vs ~20). Trivial impact
  at the playbook's scale.
- Each adapter must now know its config_path precedence rules.
  Centralized in `mcp_native_config.py` (already exists from v0.8).

### Risk

- Cross-host id reuse: uuid4 collision probability is effectively
  zero, but two machines installing the same MCP server independently
  produce different ids. Acceptable; ids are per-install, not
  per-server-type.
- Native marker format drift: if a vendor changes mcp.json schema to
  reject extra fields, the marker write would fail. v0.9 install
  wraps the marker write in try/except and falls back to
  lockfile-only ownership.

## Implementation

What actually shipped (round-3 amendment per Cursor review):

- `scripts/install_lockfile.py`: `ManagedMcpEntry` TypedDict,
  `make_managed_mcp_entry`, `managed_entries_for_config`,
  `LOCKFILE_VERSION = 3`, `incompatible_lockfile_path`. `load_lockfile`
  refuses non-v3 (returns None with stderr warning); install
  dispatcher calls `incompatible_lockfile_path` and aborts with exit
  code 3.
- `scripts/install_managed_keys.py` (round-3 Cursor #1 extraction):
  per-(adapter, config_path) ownership policy lives here.
  `snapshot_pre_install_mcp` + `compute_managed_keys_for`. Replaces
  the v0.8 Cursor UNION pre_existing trade-off.
- `scripts/install.py`: thin `_new_managed_keys_for` shim that
  forwards to `install_managed_keys.compute_managed_keys_for` with
  the install.py-local hook directory factory. Pre-install snapshot
  uses `snapshot_pre_install_mcp`.
- `scripts/install_orphans.py`: unchanged in v0.9. Per-config
  cleanup is achieved at the adapter layer via
  `reconcile_managed_json_mcp` consuming the per-config filtered set
  from `managed_entries_for_config`.
- `scripts/adapters/_writer.py`: writes
  `_playbook_metadata` (underscore-prefixed for collision safety in
  shared files like `~/.claude.json`) into JSON MCP configs. Marker
  write is wrapped in `try/except` so a vendor schema change that
  rejects the extra key silently degrades to lockfile-only ownership.
- `scripts/adapters/{cursor,claude_code,codex,windsurf}.py`: use
  `managed_entries_for_config` to filter prior managed names per
  config_path before reconciling. Codex MCP block is fully
  overwritten on every install so it has no native marker. Copilot
  and Cline are hooks-only adapters today (no MCP registrations);
  no v0.9 work needed.
- `scripts/install_verify.py`: per-config expected sets via
  canonicalized path comparison (handles `--target ../project`);
  trust boundary classifies against the current target dir, falling
  through to under-$HOME when `target == $HOME`.
- `scripts/mcp_runtime_probe.py`: Streamable HTTP transport branch
  (POST `/mcp` + parse JSON OR SSE `data:` event), env-var
  substitution (`${env:VAR}` / `{{VAR}}` / `bearer_token_env_var`),
  skip-on-unset semantics. Module-level `_has_placeholder` shared by
  stdio and HTTP paths.
- `scripts/mcp_native_config.py`: `scope_for_config_path` helper.
- `tests/lifecycle/test_mcp_probe_and_schema.py` (was
  `test_v0_9_additions.py`; renamed to feature-based name): schema
  foundation +
  native marker idempotency + HTTP probe matrix (success / 5xx /
  env-var-unset / SSE / bearer token / URL substitution / SSE response
  body parsing) + lockfile-version validation + canonicalized path
  comparison. 26 tests at the time of v0.9 ship.

### Native marker key naming

ADR's original sketch used `"metadata"`. Implementation uses
`"_playbook_metadata"` (underscore-prefixed) because the marker shares
file space with non-MCP keys in `~/.claude.json` and other shared
configs. The underscore prefix signals "internal" namespacing and
reduces collision risk if a vendor later defines a top-level
`metadata` key. The marker is informational; the lockfile remains
authoritative for ownership decisions.

### Codex `[metadata]` TOML table

Deferred. Codex MCP entries live in a managed block bracketed by
`# PLAYBOOK-MANAGED BEGIN`/`END` markers that are fully overwritten on
every install. The managed block IS the marker for Codex; adding a
parallel `[metadata]` table is redundant.

### Exit codes

The install dispatcher uses three exit codes:

- `0` -- success.
- `1` -- generic failure (one or more adapters failed to install,
  detection issues, etc.).
- `3` -- incompatible lockfile detected (v0.8 lockfile present;
  upgrade in progress). The dispatcher prints the v0.8 cleanup
  workflow before exiting. Distinct from `1` so callers (Make targets,
  CI scripts) can distinguish the "needs cleanup" state from a runtime
  failure. Tested by
  `test_run_install_exits_3_on_incompatible_lockfile`.

## Related

- ADR-0024 (managed_keys ownership): superseded by this ADR's hard
  cut. The v0.8 amendment is now closed.
- ADR-0026 (lockfile structure): version bumps 2 to 3; this ADR is
  the rationale.
- ADR-0036 (three-layer content contract): unchanged; v0.9 changes
  the data shape but not the three-layer model.
- ADR-0037 (generalized PLAYBOOK-HOOK-ADAPTERS): related to v0.9 #3
  split, which keeps the v0.8 ADAPTERS header contract intact.
- ADR-0038 (multi-target registry): unchanged; v0.9 lockfile changes
  happen per-target as before.
