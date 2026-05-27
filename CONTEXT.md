# Shared Language

A short glossary of terms used in this repo. Borrowed from mattpocock's CONTEXT.md pattern (ubiquitous language).

This file is meant to grow. Add new terms as they emerge in skills, rules, and discussions.

## Core terms (the seven content types per ADR-0010)

- **Skill**, A workflow orchestration. A "how to do X" recipe with deterministic steps. Agent-decided invocation: the agent loads the skill when its description matches the user's task. Lives in `skills/<category>/<name>/SKILL.md`. Examples: `VCS-pr-review`, `grill-me`.
- **Rule**, A behavioral constraint. A "always/never do X" directive. Lives in `rules/<name>.md`. Examples: `no-em-dashes`, `label-policy`.
- **Hook**, A shell script that fires on a coding-agent event (PreToolUse, PostToolUse, SessionStart, Stop). Lives in `hooks/`.
- **MCP**, A Model Context Protocol server config. Two shapes: flat `mcp/<name>.json` for hosted / npx servers; directory `mcp/<name>/{server.json, *.py, README.md}` for locally-hosted Python servers (the installer symlinks the source into `~/.config/agent-shared/mcp_servers/<name>/`).
- **Agent**, A subagent with its own context window, invoked by name. Per ADR-0009; lives in `agents/<name>.md` (markdown + YAML frontmatter, converted to TOML for Codex on install).
- **Command**, A user-triggered slash action. Per ADR-0010; lives in `commands/<name>.md`. When the user types `/<name>`, the body becomes the prompt sent to the agent. Examples: `playbook-promote`, `human-html`.
- **Prompt**, A reusable runtime template that expands inline (Pi-style `/name` expansion). Per ADR-0010; lives in `prompts/<name>.md` with YAML frontmatter (distinguishes runtime templates from setup / onboarding docs that share the directory).
- **Adapter**, A per-tool translator that materializes the seven canonical content types into the format a specific coding agent expects. Lives in `scripts/adapters/<tool>.py`.
- **Profile**, A per-role bundle that selects a subset of content types for a specific developer role. Lives in `profiles/<role>.toml`.
- **Playbook**, The repo as a whole.
- **Project**, PM-facing alias for **Playbook** / repo / directory used by the AGENTS.md curator, profile documentation, and PM-oriented README sections (v0.10 layered-rename convention). Engineers see "repo" in internal docs (ADRs, scripts/README.md, code comments); PMs and onboarding surfaces see "project" so the playbook reads naturally to a non-engineer. Same underlying thing, two vocabularies by audience.

## Distinctions

- **Skill vs Command vs Prompt.** Skills are agent-decided (the agent loads the skill when its description matches). Commands are user-triggered (the user types `/cmd-name`). Prompts are templates that expand inline (like a macro). Per ADR-0010.
- **Skill vs Rule.** A skill is "do these steps in this order." A rule is "always/never do this." If your contribution is a sequence of steps, it is a skill. If it is a single constraint, it is a rule.
- **Rule vs Hook.** A rule is content that the agent reads. A hook is an executable that fires automatically (the agent does not choose to run it). If a constraint needs the agent's cooperation, it is a rule. If it can be enforced without the agent's involvement, it is a hook.
- **Adapter vs Installer.** The installer is the user-facing CLI that orchestrates adapters. Adapters are the per-tool translation logic. Users invoke the installer; the installer dispatches to adapters.

## Tiers

- **Tier 1**, Full custom adapter. Currently: Claude Code, Codex, Cursor, Windsurf. Adapter coverage of the seven content types varies (see seven-bucket diagram below); only Claude Code and Cursor materialize the `commands/` surface natively.
- **Tier 2**, Lighter adapter, surface varies. Currently: GitHub Copilot, Gemini CLI, Aider, Cline, Pi. (Pi materializes skills + rules + prompts to `~/.pi/agent/`; the others materialize skills + rules only via `AGENTS.md`.)
- **Tier 3**, AGENTS.md only (generated). All other agents that read AGENTS.md natively. 20 named tools currently registered: Kiro, Goose, Junie, Zed, Amp, Augment, OpenCode, Aide, Droid, Jules, Qodo, Q-Developer, SWE-Agent, Devon, Claude-Flow, Kilo, Continue, Tabnine, Cline-CLI, Supermaven.

## Seven-bucket diagram (ADR-0010 consequence)

The playbook ships seven content types. Each adapter materializes a subset of the seven into that tool's native surface. `Y` = adapter materializes; `.` = adapter skips this type.

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
- Hook support was generalized across adapters in v0.5 and v0.6 (per the multi-agent hook gap analysis). Each adapter shape: Claude/Codex/Cline/Copilot use PascalCase events (Claude-shaped `settings.json` schema); Cursor uses camelCase events + flat per-entry shape + snake_case JSON stdout responses (`hooks.json`); Windsurf uses snake_case 12-event Cascade names + `tool_info` stdin (per-hook translator wrapper bridges to Claude-shaped stdin so playbook hooks run unchanged).
- Codex's PreToolUse reliably intercepts only Bash; PreToolUse + non-Bash matcher auto-promotes to PostToolUse at install time so Edit/Write hooks still fire (per ADR-0034).
- Cursor PreToolUse advisory output uses snake_case JSON (`{permission, agent_message}`) per Cursor 2.0.64+. The playbook ships `human-html-advisory-cursor.sh` as a Cursor-only wrapper for the stderr-based advisory.
- Codex skips `commands/` because Codex's slash UX is description-matched skills, not separate command files.
- Windsurf skips `commands/` because the Windsurf surface does not have a native commands directory the installer can target.
- Gemini CLI / Aider / Pi do not expose a documented general shell-hook contract; hooks support is omitted by design.
- Pi only ships skills + rules (via parent-dir AGENTS.md walk) + prompts to `~/.pi/agent/prompts/`; Pi has no MCP, subagent, hook, or command surface today.

## Flagged ambiguities

- "agent rules" sometimes means SKILL.md (Claude Code) and sometimes means AGENTS.md (Codex). In this repo, "rule" always means an AGENTS.md fragment in `rules/`. SKILL.md is always called a "skill."
- "MCP" sometimes refers to Anthropic's Model Context Protocol generally, and sometimes to the team MCP repo specifically. In this repo, lowercase "mcp/" directory holds MCP server configs (the protocol). The team MCP repo is referenced as "team_mcp" or "MCP repo."
