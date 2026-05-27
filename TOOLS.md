# Tools catalog

External tools and services referenced by the playbook. This file is informational; the playbook doesn't ship credentials for any of these. Where a tool is used by a skill, hook, or MCP config, that artifact's documentation describes how it's invoked.

Owner: rehan
Last reviewed: 2026-05-27

## CLI

### rtk (Rust Token Killer)

- Upstream: [github.com/rtk-ai/rtk](https://github.com/rtk-ai/rtk) (Apache 2.0)
- Install: `brew install rtk` (homebrew core formula). Not `reachingforthejack/tap/rtk`, which is the unrelated Rust Type Kit.
- Commands: `rtk gain`, `rtk gain --history`, `rtk discover`, `rtk proxy <cmd>`.
- Purpose: token-optimized CLI proxy (60-90% token savings on dev operations).
- Notes: auto-rewrites git / find / grep / etc. via Claude Code hook; transparent to user.

### gh (GitHub CLI)

- Install: `brew install gh`.
- Auth: `gh auth login` once per machine.
- Use for: any GitHub repo operation (this playbook itself, the public skill upstreams, etc.).

### gitleaks

- Install: `brew install gitleaks`.
- Use for: pre-push secret scanning (opt-in via `.pre-commit-config.yaml`; not part of `make check` by default).

## Coding agents (the playbook's targets)

| Agent | Native config location | What the installer writes |
|---|---|---|
| Claude Code | `~/.claude/` | SKILL.md files, settings.json, commands/, agents/, hooks |
| Codex CLI | `~/.codex/` | skills/, hooks, AGENTS.md, config.toml |
| Cursor (IDE + CLI) | `~/.cursor/` | skills/, rules/, hooks.json, mcp.json |
| Windsurf | `~/.codeium/windsurf/` | memories/global_rules.md, hooks.json |
| Pi | `~/.pi/agent/` | skills/, prompts/, hooks/ |
| Cline | `~/.cline/` | hooks, rules |
| Gemini CLI | `~/.gemini/` | skills/, agents/ |

The full list of supported adapters lives at `scripts/adapters/`. Adding a new adapter is one new file in that directory plus an entry in the dispatch table.

## MCP servers shipped with the playbook

| Server | Location | What it provides |
|---|---|---|
| `agent-memory-bridge` | `base/mcp/agent-memory-bridge/` | Cross-session shared memory (search, propose, audit). Configurable display name via `AGENT_MEMORY_MCP_NAME` env var. |
| `anchored-fs` | `base/mcp/anchored-fs/` | Anchored edit + path resolver. Vendored from upstream. |
| `code-review-graph` | `base/mcp/code-review-graph.json` | Graph-aware code review. |
| `slack` | `base/mcp/slack.json` | Hosted MCP server config. The user provides their own auth token. |
| `tavily` | `base/mcp/tavily.json` | Hosted MCP server config. Set `TAVILY_API_KEY` in your shell. |

## External services the skills reference

These are services that some shipped skills know how to talk to. The playbook doesn't include credentials; the skill documents how to configure auth where needed.

- **Atlassian** (Jira, Confluence): some research and PM-execution skills accept Atlassian MCP integration if you have it configured.
- **Slack**: skills for stakeholder updates, distill-slack-persona, and meeting-brief use the Slack MCP if available.
- **Tavily**: research skills (interview-script, competitor-analysis, market-sizing) use Tavily for web search if `TAVILY_API_KEY` is set.
- **GitHub**: PR-review skills know how to fetch PR metadata via `gh` CLI.
- **Generic VCS hosts**: most skills are platform-agnostic and work via standard git commands.

## Pre-commit / CI tools

The playbook's own CI gates (run via `make check`) use:

- **ruff** (lint + format): runs via `uv run ruff check`.
- **pyright**: type-checks the scripts/ directory; the `pyright-zero` gate enforces a 0-error budget.
- **gitleaks**: optional pre-push hook for secret scanning (not built into `make check`; opt-in via `.pre-commit-config.yaml`).

## Cursor plugins (refer-only)

### cursor-team-kit

- Upstream: [github.com/cursor/plugins/tree/main/cursor-team-kit](https://github.com/cursor/plugins/tree/main/cursor-team-kit).
- Marketplace: [cursor.com/marketplace/cursor/cursor-team-kit](https://cursor.com/marketplace/cursor/cursor-team-kit).
- Install: `/add-plugin cursor-team-kit` in Cursor chat, or open the marketplace panel and install from there.
- Purpose: built-in workflows for CI, PR review, shipping, smoke tests, compiler checks, and code cleanup.
- Notes: many skills assume GitHub Actions; if your repo uses a different CI, prefer playbook skills.

### Three-layer caveat (per ADR-0036)

A teammate who runs `make install` expects the workflows they see in chat to be playbook content. A teammate who runs `/add-plugin` in Cursor expects the same. They're not the same surface. Skills in this playbook ship via `~/.agents/skills/` (where Claude / Codex / Cursor agent loaders all walk); only Cursor's plugin loader sees `~/.cursor/plugins/`. Mixing the two routes is the most common reason "I installed the playbook but the skill never shows up" reports surface.

| Surface | Canonical source | Materialization | Runtime discovery |
|---|---|---|---|
| Playbook skill | `base/skills/<cat>/<name>/SKILL.md` | `~/.agents/skills/<name>/` plus per-adapter projections | agent skill loader walks `~/.agents/skills/` (Codex), `~/.claude/skills/` (Claude), `~/.cursor/skills/` (Cursor symlink) |
| Cursor plugin | upstream repo | `~/.cursor/plugins/<id>/` (marketplace loader) | Cursor plugin loader; NOT scanned by `~/.agents/skills/` agents |

Implication: filesystem-copying a marketplace plugin into `~/.cursor/plugins/local/` does not make it visible to Claude Code, Codex, or any non-Cursor agent. Likewise, a playbook skill is invisible to Cursor's plugin loader (Cursor sees it via `~/.cursor/skills/` instead).

## Maintenance

When a tool changes meaningfully (new flag, deprecation, auth shift), update this file and bump `last_reviewed`. When adding a new tool worth surfacing repo-wide, add an entry here rather than scattering it across skill bodies.
