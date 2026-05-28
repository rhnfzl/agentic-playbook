# Glossary (CONTEXT.md)

Canonical vocabulary for this repo. When code, docs, or PRs talk about a term, they use the meaning given here. New terms get added as they're resolved during grill sessions (see `base/skills/productivity/grill-with-docs/`).

## Core terms (the seven content types per ADR-0010)

- **Skill**: a workflow orchestration. A "how to do X" recipe with deterministic steps. Agent-decided invocation: the agent loads the skill when its description matches the user's task. Lives in `base/skills/<category>/<name>/SKILL.md`.
- **Rule**: a behavioral constraint. An "always / never do X" directive. Lives in `base/rules/<name>.md`. The installer concatenates selected rules into per-project `AGENTS.md`.
- **Hook**: a shell script that fires on a coding-agent event (PreToolUse, PostToolUse, SessionStart, Stop). Lives in `base/hooks/`.
- **MCP**: a Model Context Protocol server config. Two shapes: flat `base/mcp/<name>.json` for hosted / npx servers; directory `base/mcp/<name>/{server.json, *.py, README.md}` for locally-hosted Python servers (the installer symlinks the source into `~/.config/agent-shared/mcp_servers/<name>/`).
- **Agent**: a subagent with its own context window, invoked by name. Per ADR-0009; lives in `base/agents/<name>.md` (markdown + YAML frontmatter, converted to TOML for Codex on install).
- **Command**: a user-triggered slash action. Per ADR-0010; lives in `base/commands/<name>.md`. When the user types `/<name>`, the body becomes the prompt sent to the agent.
- **Prompt**: a reusable runtime template that expands inline (Pi-style `/name` expansion). Per ADR-0010; lives in `base/prompts/<name>.md` with YAML frontmatter (distinguishes runtime templates from setup / onboarding docs that share the directory).
- **Trajectory**: a cross-adapter behavior assertion for one (skill, scenario) pair. Per ADR-0044; lives in `base/trajectories/<skill>/<scenario>.yaml`. Declares input phrasings, DSL assertions over the tool-call trace, and an LLM-judge rubric. Consumed by the trajectory harness (`scripts/trajectory_harness.py`, lands in Phase 1), not by adapters.
- **Adapter**: a per-tool translator that materializes the canonical content types into the format a specific coding agent expects. Lives in `scripts/adapters/<tool>.py`. Trajectories are NOT materialized by adapters; they're read by the harness.
- **Profile**: a per-role bundle that selects a subset of content types for a specific developer role. Lives in `profiles/<role>.toml`.
- **Playbook**: the repo as a whole.
- **Project**: PM-facing alias for **Playbook** / repo / directory used by the AGENTS.md curator, profile documentation, and PM-oriented README sections. Engineers see "repo" in internal docs (ADRs, scripts/README.md, code comments); PMs and onboarding surfaces see "project" so the playbook reads naturally to a non-engineer. Same underlying thing, two vocabularies by audience.

## Distinctions

- **Skill vs Command vs Prompt.** Skills are agent-decided (the agent loads the skill when its description matches). Commands are user-triggered (the user types `/cmd-name`). Prompts are templates that expand inline (like a macro). Per ADR-0010.
- **Skill vs Rule.** A skill is "do these steps in this order." A rule is "always / never do this." If your contribution is a sequence of steps, it's a skill. If it's a single constraint, it's a rule.
- **Rule vs Hook.** A rule is content that the agent reads. A hook is an executable that fires automatically (the agent doesn't choose to run it). If a constraint needs the agent's cooperation, it's a rule. If it can be enforced without the agent's involvement, it's a hook.
- **Adapter vs Installer.** The installer is the user-facing CLI that orchestrates adapters. Adapters are the per-tool translation logic. Users invoke the installer; the installer dispatches to adapters.

## Tiers

- **Tier 1**: full custom adapter. Currently: Claude Code, Codex, Cursor, Windsurf. Adapter coverage of the seven content types varies; only Claude Code and Cursor materialize the `commands/` surface natively.
- **Tier 2**: lighter adapter, surface varies. Currently: GitHub Copilot, Gemini CLI, Aider, Cline, Pi. (Pi materializes skills + rules + prompts to `~/.pi/agent/`; the others materialize skills + rules only via `AGENTS.md`.)
- **Tier 3**: AGENTS.md only (generated). All other agents that read AGENTS.md natively. 20 named tools currently registered: Kiro, Goose, Junie, Zed, Amp, Augment, OpenCode, Aide, Droid, Jules, Qodo, Q-Developer, SWE-Agent, Devon, Claude-Flow, Kilo, Continue, Tabnine, Cline-CLI, Supermaven.

## Eight-bucket diagram (ADR-0010 + ADR-0044)

The playbook ships eight content types. Seven of them get materialized by adapters into the tool's native surface (`Y` = materialize; `.` = skip). The eighth, **trajectories**, is consumed by the harness rather than materialized into any adapter, so the columns below cover only the materialized seven.

```
                                  skill   rule   hook   mcp   agent  command  prompt
                                  -----   ----   ----   ---   -----  -------  ------
Tier 1
  Claude Code                       Y      Y      Y     Y      Y       Y        .
  Codex                             Y      Y      Y     Y      Y       .        .
  Cursor                            Y      Y      Y     Y      Y       Y        .
  Windsurf                          Y      Y      Y     Y      Y       .        .

Tier 2
  Copilot                           .      Y      Y     .      .       .        .
  Gemini CLI                        .      Y      .     .      .       .        .
  Aider                             .      Y      .     .      .       .        .
  Cline                             .      Y      Y     .      .       .        .
  Pi                                Y      Y      .     .      .       .        Y

Tier 3 (20 named tools)             .      Y      .     .      .       .        .
```

Notes:

- "Rule" lands as AGENTS.md content for every tool that reads AGENTS.md natively (Tier 2 / 3 fallback); Cursor adds `.cursor/rules/*.mdc`, Cline adds `.clinerules`, Windsurf adds `~/.codeium/windsurf/memories/global_rules.md`.
- Hook support was generalized across adapters in v0.5 and v0.6 (per the multi-agent hook gap analysis). Each adapter shape: Claude / Codex / Cline / Copilot use PascalCase events (Claude-shaped `settings.json` schema); Cursor uses camelCase events + flat per-entry shape + snake_case JSON stdout responses (`hooks.json`); Windsurf uses snake_case 12-event Cascade names + `tool_info` stdin (per-hook translator wrapper bridges to Claude-shaped stdin so playbook hooks run unchanged).
- Codex's PreToolUse reliably intercepts only Bash; PreToolUse + non-Bash matcher auto-promotes to PostToolUse at install time so Edit / Write hooks still fire (per ADR-0034).
- Cursor PreToolUse advisory output uses snake_case JSON (`{permission, agent_message}`) per Cursor 2.0.64+. The playbook ships `human-html-advisory-cursor.sh` as a Cursor-only wrapper for the stderr-based advisory.
- Codex skips `commands/` because Codex's slash UX is description-matched skills, not separate command files.
- Windsurf skips `commands/` because the Windsurf surface has no native commands directory the installer can target.
- Gemini CLI / Aider / Pi do not expose a documented general shell-hook contract; hooks support is omitted by design.
- Pi only ships skills + rules (via parent-dir AGENTS.md walk) + prompts to `~/.pi/agent/prompts/`; Pi has no MCP, subagent, hook, or command surface today.

## Lifecycle terms

- **Install**: materializing playbook content as native files in a coding agent's expected location.
- **Materialize**: the act of writing the right native file for an adapter from the source markdown / TOML / JSON.
- **Lockfile**: `.playbook-lock.json` at the target project root. Records exactly what was materialized so `make update` can reconcile drift and `make remove` can clean up.
- **Managed block**: the `<!-- AGENTS-MD-CURATOR BEGIN -->...END` markers in installed `AGENTS.md` files. Content inside is rewritten by the installer; content outside is preserved.
- **Scope**: which content layers apply to an install. Auto-detected from the target project's git remote URL; overridable via `--scope`.
- **Content tiering**: the base / overlay split (ADR-0040). `base/` ships portable content; overlays add workspace-specific extensions.

## Governance terms

- **ADR**: Architecture Decision Record under `docs/adr/NNNN-title.md`. Short, dated, immutable. New decisions get new ADRs; superseded ADRs are marked, not deleted.
- **Frontmatter**: the `---` YAML block at the top of a SKILL.md (or any other markdown content type). Required fields are validated by `scripts/frontmatter_lint.py`.
- **Decay**: a skill / rule / hook is "decaying" when its `last_reviewed` date is older than the threshold (90d default, 180d for docs-like dirs). The `decay_check.py` gate warns or blocks.
- **Vendored**: content imported from upstream with a pinned SHA via `SOURCES.toml`. Lives under `base/skills/imported/` or `base/mcp/anchored-fs/`. Marked `linguist-vendored=true` in `.gitattributes`.
