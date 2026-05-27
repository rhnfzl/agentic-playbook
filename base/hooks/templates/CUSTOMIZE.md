# Customizing hook templates

This directory holds hook templates that need workspace-specific values before they can be wired into Claude Code or Codex. Each `*.template` file lists its required sentinels in a header comment; fill them in and rename to `*.sh`, then drop into `hooks/` proper.

## Available templates

| Template | What it does | Sentinels |
|---|---|---|
| `deny-edits-in-readonly-dir.sh.template` | Denies Edit / Write / MultiEdit / NotebookEdit on a sync-from-elsewhere directory inside your workspace, so local edits cannot be silently overwritten by the next sync. | `{{WORKSPACE_ROOT}}`, `{{READONLY_DIR_NAME}}`, `{{READONLY_DIR_REASON}}`, `{{ALTERNATIVE_LOCATIONS}}` |

## How to customize

1. Copy the template, dropping the `.template` extension:
   ```bash
   cp hooks/templates/deny-edits-in-readonly-dir.sh.template \
      hooks/deny-edits-in-myreadonly.sh
   ```
2. Open the new file and replace every `{{SENTINEL}}` with a concrete value:
   - `{{WORKSPACE_ROOT}}`: absolute path to your workspace (the dir that contains the read-only subdir).
   - `{{READONLY_DIR_NAME}}`: the subdirectory name (e.g. `platform`, `vendored`, `upstream`).
   - `{{READONLY_DIR_REASON}}`: a one-paragraph explanation the agent will see when the deny fires (why this dir is read-only, who manages it, how often it syncs).
   - `{{ALTERNATIVE_LOCATIONS}}`: bullet list of where the equivalent edit should go instead.
3. Make it executable: `chmod +x hooks/deny-edits-in-myreadonly.sh`.
4. Run the em-dash lint to confirm no banned characters slipped in: `python3 scripts/check_em_dashes.py`.
5. Re-run `make install` to register it with each adapter's hook settings.

## When NOT to use these templates

If your read-only subdir is already excluded by `.gitignore` and you never mean to edit it, you do not need this hook. The hook earns its keep when:
- The directory is committed (so it appears editable).
- Multiple agents (Claude Code, Codex, Cursor) work in the same workspace.
- The cost of an accidental edit being silently overwritten is high (loss of work, incorrect code in PRs).

## Provenance

The `deny-edits-in-readonly-dir.sh.template` template was distilled from `block-platform-writes.sh` in the user's `team_LLM_Systems` workspace, where it guards a `platform/` directory containing read-only checkouts of upstream team repos that sync hourly via launchd.
