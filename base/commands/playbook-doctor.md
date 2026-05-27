---
name: playbook-doctor
description: Diagnose installer state on the current machine, showing which coding agents are detected and (with --verify) whether the playbook is actually wired into each agent's runtime config.
version: 1.1.0
owner: playbook-core
last_reviewed: 2026-05-25
tags: [doctor, install, diagnostics, adapters, playbook]
---

# Diagnose the playbook installer on this machine

When the user wants to know which coding agents the playbook installer can detect on this machine, which ones are missing, and what to do about it, this command runs the diagnostic and interprets the output.

## When to use

- A teammate just cloned the playbook and wants to know what will work out of the box.
- Install ran but skipped an agent the user expected. They want to know why.
- The user added a new agent locally (Cursor, Codex, Gemini CLI, etc.) and wants to confirm the playbook will pick it up on the next install.
- A `make install` run failed for one or more adapters and the user wants a clean detection map.
- After install, the user wants to confirm hooks fire and skills load (run with `make doctor-verify`, ADR-0036 layer-3).

## When NOT to use

- The user actually wants to install (use `make install` or `/playbook-new-skill`).
- The user wants to run validation gates on playbook content (use `/playbook-check`).
- The user wants to author a new skill (use `/playbook-new-skill`).

## Your job

You run `make doctor`, parse its output, and translate it into actionable next steps. Detection is per-tier:

- **Tier 1**: full adapter (skills, rules, hooks, MCP). Agents: claude-code, codex, cursor, windsurf.
- **Tier 2**: skills and rules only. Agents: copilot, gemini-cli, aider, cline, pi.
- **Tier 3**: AGENTS.md only (auto-generated). Agents: kiro, goose, junie, zed, amp, augment, opencode, aide, droid, jules, qodo, q-developer, swe-agent, devon, claude-flow, kilo, continue, tabnine, cline-cli, supermaven.

## Workflow

1. **Run the diagnostic.** From the playbook root:
   ```bash
   make doctor                # detection map (which agents are on this box)
   make doctor-verify         # ADR-0036 layer-3: lockfile vs native config vs on-disk
   ```
   `make doctor` invokes `python3 scripts/install.py --diagnose` and prints the full detection report. `make doctor-verify` invokes `python3 scripts/install.py --verify` and audits the installed adapters: for each, the file count in the lockfile, the hook count in the native config (`settings.json` / `hooks.json`), the on-disk script existence, and the `.playbook-owned` marker on installed skill directories. Use `make doctor-verify TARGET=/path/to/project` when you installed to a non-$HOME target.

2. **Group results by tier.** Walk the output and bucket each agent into:
   - detected and Tier 1
   - detected and Tier 2
   - detected and Tier 3
   - not detected at all

3. **Interpret the detection logic.** The detector checks one of:
   - A config directory exists (`~/.claude`, `~/.codex`, `~/.cursor`, `~/.gemini`, etc.).
   - A binary is on PATH (`gemini`, `aider`, `goose`, `opencode`, etc.).
   - A VS Code extension folder exists under `~/.vscode/extensions/<ext-id>*`.
   - For some agents, an installed app exists at `/Applications/<App>.app`.

   The source of truth for detection is the `AGENTS` registry in `scripts/install.py`.

4. **Explain missing agents** to the user. For each not-detected agent the user cares about, surface:
   - What the detector is looking for (config dir, binary, or extension).
   - The minimal install step (e.g., "install the Cursor app from cursor.com, then re-run doctor").
   - Whether the agent is Tier 1, 2, or 3 (so the user knows what they would get out of installing it).

5. **Recommend next action.** Pick one based on what the doctor showed:
   - If everything detected matches what the user expects, suggest `make install AGENTS=auto TARGET=<path>` for a non-interactive sync.
   - If something is missing that the user wants, give the concrete install command and tell them to re-run `make doctor` after.
   - If a Tier 1 agent failed detection but should be there, suggest checking the config dir path on disk and falling back to `python3 scripts/install.py --diagnose` for raw output.

## Output

The user sees:

- A grouped detection summary (detected per tier, then not-detected).
- For each missing agent the user mentions, a one-line install hint.
- A recommended next command (one of `make install`, `make install AGENTS=auto`, or a concrete install step for the missing tool).

## Verify workflow (ADR-0036)

After install, run `make doctor-verify` to confirm the three-layer chain is intact for every detected adapter:

1. **Layer 1 (canonical source)** is enforced by `make check` (the `hook-source-unification` gate).
2. **Layer 2 (materialization)** is recorded in the lockfile.
3. **Layer 3 (runtime discovery)** is what `--verify` actually walks: the adapter's native config file (`~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.cursor/hooks.json`, `~/.cline/hooks.json`, `~/.codeium/windsurf/hooks.json`, project `.github/hooks.json`) must contain entries for every hook the lockfile recorded.

When `--verify` reports a FAIL:

- "lockfile entry missing on disk": the materialized file was deleted or moved. Re-run `make install` (or `make update`).
- "lockfile registered <event>=<path> but <config> does not contain it": the native config drifted (manual edit, partial install). Re-run `make install` to re-register, then re-verify.
- "skill ... has no .playbook-owned marker": the skill dir exists but isn't claimed by the playbook (next install will skip it as user-owned). Either move the dir aside or re-run `make install` with the skill in the active profile.

## Reference

The detection registry lives in `scripts/install.py` under the `AGENTS` dict. The diagnose entrypoint is `make doctor` (equivalent to `python3 scripts/install.py --diagnose`); the verify entrypoint is `make doctor-verify` (equivalent to `python3 scripts/install.py --verify`). Adapter modules live under `scripts/adapters/<agent>.py`; if an adapter is missing for a detected Tier 1 or 2 agent, that is a bug worth reporting. ADR-0036 (three-layer content contract) is the design rule the verify pass enforces.
