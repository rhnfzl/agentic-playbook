# Customizing script templates

This directory holds longer-form Python and shell tools that depend on workspace-specific layout. Each `*.template` file shows the constants you must replace; rename to drop the `.template` suffix and edit them in place.

## Available templates

| Template | What it does for the user | Sentinels |
|---|---|---|
| `workspace_status.py.template` | Single-command dashboard that aggregates 7 health signals (read-only checkout freshness, docs drift, meetings index, conversation log age, agents-md lifecycle, launchd agents, env keys). Tells you "is this workspace healthy enough to work in?" with one command. | `{{WORKSPACE_ROOT}}`, `{{LAUNCHD_LABEL_1/2}}`, `{{ENV_KEY_1/2}}` |
| `upstream_drift_report.py.template` | Reports drift in read-only checkouts you mirror from upstream repos. Surfaces both forward-drift (your local is behind upstream) and reverse-drift (upstream changed since you last synced). Stays read-only on the mirrored tree. | `{{UPSTREAM_DIR_NAME}}`, `{{REPO_ALIAS_*}}`, `{{REPO_DIR_*}}`, `{{CRAWL_DIR_NAME}}` |
| `install_launchd_agents.sh.template` | Installs / uninstalls / inspects a macOS launchd agent for periodic workspace maintenance (refresh memory bridge, refresh code-review-graph, audit AGENTS.md lifecycle, etc.). | `{{WORKSPACE_ROOT}}`, `{{LAUNCHD_LABEL}}`, `{{LAUNCHD_PATH}}` (plus body edits for what the agent does) |

## How to customize

1. Copy the template, dropping the `.template` extension:
   ```bash
   cp scripts/templates/workspace_status.py.template scripts/workspace_status.py
   ```
2. Open the new file and replace every `{{SENTINEL}}` with a concrete value.
3. Read the original docstring (preserved verbatim). It tells you which probes exist, which env vars they expect, and how the exit codes work.
4. For `workspace_status.py`: edit individual probe functions if your workspace lacks a probe's prerequisite (e.g. no meetings dir = remove `probe_meetings_index`).
5. For `upstream_drift_report.py`: edit `REPOS` map to one entry per upstream repo you mirror. Set `CRAWL_DIRS = []` if you don't have dated capture directories.
6. For `install_launchd_agents.sh`: edit the body of `install_agent()` to call your own maintenance script(s) instead of the upstream's `agent_instruction_sync.py` / `agent_memory_bridge.py`.
7. Run the em-dash lint after editing: `python3 scripts/check_em_dashes.py`.
8. Run any local syntax check (`bash -n` for shell, `python3 -m py_compile` for Python).

## When NOT to use these templates

- You don't run a workspace with multiple agent-harness signals to monitor (the `workspace_status.py` dashboard wins when there are 4+ moving parts).
- You don't mirror upstream code via read-only checkouts (`upstream_drift_report.py` is only useful when you have the mirror pattern).
- You don't use launchd for periodic tasks (cron or systemd users should adapt the patterns to their scheduler).

## Provenance

All three templates were distilled from the user's `team_LLM_Systems/scripts/` directory during the v0.2 harness import pass. The original scripts run today on the author's machine; the templates strip workspace-IP-specific values so other teams can adopt the patterns.
