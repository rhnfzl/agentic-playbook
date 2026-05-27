# 0029. Hook reconciliation + PLAYBOOK-HOOK-MATCHER convention

## Status

Accepted (2026-05-25); landing in v0.5.

## Context

Two coupled gaps in v0.4 hook registration surfaced during the v0.5 grilling:

### Gap 1: registered hooks fire on every tool event

Looking at the current claude_code adapter (scripts/adapters/claude_code.py lines 161-187), a playbook hook gets written to `~/.claude/settings.json` as:

```json
{
  "PreToolUse": [
    {
      "hooks": [{"type": "command", "command": "/Users/X/.claude/hooks/my-hook.sh"}]
    }
  ]
}
```

There is no `matcher` field. Claude Code interprets the missing matcher as "match every tool event for this lifecycle stage." That means a PreToolUse hook authored for Edit/Write fires on Bash, MultiEdit, NotebookEdit, Read, and every other tool. The hook scripts themselves bail out internally when their match condition is not met, so behavior is correct, but every call pays the fork-exec cost.

The human-html skill's documented hook shape (which the playbook itself ships) includes the matcher field:

```json
{
  "PreToolUse": [{
    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
    "hooks": [{"type": "command", "command": "...", "timeout": 5}]
  }]
}
```

So our own ecosystem expects matchers; our installer just doesn't write them.

### Gap 2: hook entries don't reconcile on profile narrow

The v0.4 hook registration code is add-only:

```python
if entry not in event_block:
    event_block.append(entry)
```

When a user narrows their profile (e.g. from `tech-lead` to `qa`), hooks that fall out of the new profile remain in `settings.json` forever. The MCP equivalent of this gap was caught by the Codex adversarial review of the v0.4 architecture PR and fixed via the `managed_keys` lockfile pattern (per ADR-0024 finding 2). Hooks share the same shape (entries in a shared, user-touchable config file) but did not get the same fix.

## Decision

### Add `# PLAYBOOK-HOOK-MATCHER:` header convention

Every playbook hook script (under `hooks/`) declares its matcher in a header line, alongside the existing `# PLAYBOOK-HOOK-EVENT:` header introduced by ADR-0027:

```bash
#!/usr/bin/env bash
# PLAYBOOK-HOOK-EVENT: PreToolUse
# PLAYBOOK-HOOK-MATCHER: Edit|Write|MultiEdit|NotebookEdit

# ... hook body ...
```

The installer reads both headers and writes the resulting settings.json entry with the matcher field populated. A hook script that EXPLICITLY sets `PLAYBOOK-HOOK-MATCHER: *` opts into match-all (the installer omits the matcher field, letting the tool's default fire on every event). A hook script that OMITS the header entirely is treated as missing metadata and fails the `hook-metadata` check at install time (per the gap Cursor flagged in v0.5); no silent "fall back" path lets a hook ship without explicit declaration.

Per ADR-0027's reasoning for PLAYBOOK-HOOK-EVENT: declaring the matcher in the script itself (rather than in a separate registry the installer maintains) keeps the hook self-documenting. A future reader of the hook can answer "when does this fire?" without cross-referencing the installer code.

### Add `hooks` section under per-adapter `managed_keys`

The lockfile's existing `managed_keys` section (introduced for MCP reconciliation in v0.4) gains a `hooks` key per hook-registering adapter:

```json
{
  "managed_keys": {
    "claude-code": {
      "mcp_servers": ["atlassian", "slack"],
      "hooks": {
        "PreToolUse": ["/Users/X/.claude/hooks/never-push-to-develop.sh", ...],
        "PostToolUse": [...],
        "SessionStart": [...]
      }
    },
    "codex": {
      "mcp_servers": [...],
      "hooks": {...}
    },
    "cursor": {"hooks": {...}},
    "cline": {"hooks": {...}},
    "copilot": {"hooks": {...}}
  }
}
```

Each event maps to the list of absolute hook command paths the adapter registered on the prior install. Per-adapter nesting (rather than a single top-level `managed_hook_commands`) lets each adapter own its own narrow-cleanup scope, mirroring the per-adapter mcp_servers shape. On every install, the adapter passes `prior_managed_keys[<adapter-name>]` to itself (matching the MCP reconciliation pattern) and computes:

- `to_drop = prior - new`: hook command paths the playbook owned last time but doesn't reference in the current profile. These get removed from `settings.json`. User-authored entries (anything NOT in `prior_managed_keys`) are preserved.
- `to_add = new - existing`: new playbook hooks the user does not yet have.

The lockfile updates after a successful install so the next narrow uses the right baseline.

### Both fixes ship together

Reconciliation and matcher generation share the rewrite of the hook-registration code path. Splitting them would mean two passes through `claude_code.py`'s hook block in the same week. Bundling keeps the design coherent: each entry the playbook writes has a known matcher and a known managed status.

## Consequences

### Good

- Hooks fire only when they should; perf cost of unmatched events disappears.
- Profile narrow now prunes hook entries the playbook no longer references, matching the MCP `managed_keys` semantic from v0.4.
- Hook scripts are more readable: the matcher is at the top, not buried in installer code.

### Bad

- Every existing playbook hook needs a `PLAYBOOK-HOOK-MATCHER` header added. The new `hook-metadata` check (`scripts/check_hook_metadata.py` + `scripts/checks/hook_metadata.py`) fails loud if either the event or matcher header is missing, so the requirement is verifiable via `make check`.
- Two header lines per hook (event + matcher) is more frontmatter than some authors will like. The verbosity is the cost of self-documenting hooks; the alternative (a sidecar `hooks/registry.toml`) was rejected for separating data from its consumer.
- Lockfile schema extends each per-adapter `managed_keys` block with a new `hooks` subkey. Old lockfiles (pre-v0.5) without `hooks` are handled as the absence case (empty set), which means the first post-v0.5 install does NOT prune any hooks; subsequent installs use the freshly written `hooks` set and prune correctly.

## Implementation note

The hook registration code lives in `scripts/adapters/claude_code.py`. A small `_resolve_hook_matcher(hook)` helper next to the existing `_resolve_hook_event(hook)` reads the header. `reconcile_managed_hook_commands(settings_path, event, new_commands, prior_commands)` mirrors the existing `reconcile_managed_json_mcp` in shape; lives in `scripts/adapters/_protocol.py` (alongside the MCP reconciler).

The `prior_managed_keys` shape in the Adapter Protocol gains a `"hooks": {event: [path, ...]}` key. Adapters that don't write hook registrations ignore the new key.
