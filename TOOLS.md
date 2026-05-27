# Tools Reference

Owner: Rehan
last_reviewed: 2026-05-25

CLI tools and services agents in this playbook should know about. Listed by category. Steipete-style reference (per ADR-0020 inspired by steipete/agent-scripts tools.md).

## CLI

### rtk (Rust Token Killer)

- Upstream: https://github.com/rtk-ai/rtk (Apache 2.0)
- Install: `brew install rtk` (homebrew core formula); not `reachingforthejack/tap/rtk`, which is the unrelated Rust Type Kit
- Commands: `rtk gain`, `rtk gain --history`, `rtk discover`, `rtk proxy <cmd>`
- Purpose: token-optimized CLI proxy (60-90% token savings on dev operations)
- Notes: auto-rewrites git/find/grep/etc. via Claude Code hook; transparent to user. The catalog entry in `docs/research/external-skill-sources.md` records the upstream pin and license.

### gh (GitHub CLI)

- Location: `brew install gh`
- Auth: `gh auth login` once per machine
- Use for: PUBLIC GitHub repos only (mattpocock/skills, anthropics/skills, etc.)
- DO NOT use for team repos (they live on VCS; use the VCS REST API instead)

## team services

### VCS API

- Endpoint: `https://api.VCS.org/2.0/`
- Auth: API tokens stored at `~/.config/team/VCS-token` (or `$BITBUCKET_TOKEN` env var). Per-engineer location varies; do not hardcode paths in scripts.
- Use for: PR creation, branch management, code review on team repos
- Skill: `/VCS-pr-review` for review workflow

### Direct *.team.com

- Endpoints: `https://app.team.com` (prod), `acc.team.com`, `test.team.com`, `dev.team.com`
- VPN required
- Use `/schema/` (returns YAML, not JSON) for programmatic API spec access

### internal-host fallback

- SSH: `ssh internal-host` for command pass-through when direct access fails
- Stale DNS / cached responses possible; prefer direct unless required

## MCP servers (registered in adapter configs)

### atlassian (Jira + Confluence)

- Registered: see `mcp/atlassian.json`
- Tools: searchJiraIssuesUsingJql, getJiraIssue, createJiraIssue, editJiraIssue, etc.
- Labels: see `rules/label-policy.md`; priority: see `rules/jira-priority-scheme.md`

### error-tracking

- Endpoint: `https://error-tracker.internal/` (VPN required)
- Tools: production-error queries, issue triage
- Token at `SENTRY_ACCESS_TOKEN` env var

### code-quality

- Tools: `sonar_execute_tool`, `sonar_list_categories`, `sonar_get_tool_schema`
- Use for: code-quality quality gate queries before push
- Local pre-push gate: `hooks/sonar-advisory.sh`

### tavily (web search)

- Tools: `tavily_search`, `tavily_extract`, `tavily_crawl`, `tavily_map`, `tavily_research`
- Use as default web search (prefer over WebSearch); see `feedback_tavily_search_patterns` memory

### code-review-graph

- Tools: `query_graph`, `detect_changes`, `get_review_context`, `get_impact_radius`, `semantic_search_nodes`, etc.
- Skill: `/code-review-graph-first` documents the decision tree

### slack

- Tools: `slack_search_public`, `slack_send_message`, `slack_read_thread`, etc.
- Auth: pre-configured for team workspace

### graphify (per-project)

- Started via `python3 -m graphify.serve graphify-out/graph.json` after `/graphify` runs
- Tools: `query_graph`, `get_node`, `get_neighbors`, `god_nodes`, `shortest_path`

### agent-memory-bridge

- Bundle at `mcp/agent-memory-bridge/`
- Tools: search / context / promote / reject / list / status / audit
- Hooks: `memory-curator-postwrite.sh`, `agent-memory-session-brief.sh` (v0.3)

### anchored-fs

- Bundle at `mcp/anchored-fs/` (vendored in v0.3 per ADR-0018)
- Tools: edit_file with `prefix[upto]suffix` anchored-edit, preview_edit_match
- Symlink at `~/.config/agent-shared/mcp_servers/anchored-fs/`

## Cursor plugins (refer-only)

### cursor-team-kit (Cursor Team Kit)

- Upstream: https://github.com/cursor/plugins/tree/main/cursor-team-kit
- Marketplace: https://cursor.com/marketplace/cursor/cursor-team-kit
- Install: `/add-plugin cursor-team-kit` in Cursor chat, or open the marketplace panel and install from there
- Purpose: internal-style workflows for CI, PR review, shipping, smoke tests, compiler checks, and code cleanup
- Notes: many skills assume GitHub (`gh`, GitHub Actions). For team repos on VCS, prefer playbook skills (`VCS-pr-review`, `ci-failure-triage`, `sonar-pr-gate`) for PR/CI workflows. Team Kit is still useful for local checks like `check-compiler-errors`, `deslop`, and `thermo-nuclear-code-quality-review`. If marketplace install does not surface skills after reload, symlink the three local-check skills from the plugin cache into `~/.agents/skills/` (and mirror to `~/.cursor/skills/` + `~/.claude/skills/`).

#### Three-layer caveat (per ADR-0036)

A teammate who runs `make install` expects the workflows they see in chat to be playbook content; a teammate who runs `/add-plugin` in Cursor expects the same. They are not the same surface. Skills in this playbook ship via `~/.agents/skills/` (where Claude / Codex / Cursor agent loaders all walk) and only Cursor's plugin loader sees `~/.cursor/plugins/`. Mixing the two routes is the most common reason "I installed the playbook but the skill never shows up" reports surface. The table below makes the split explicit.

| Surface | Canonical source | Materialization | Runtime discovery |
|---|---|---|---|
| Playbook skill | `skills/<cat>/<name>/SKILL.md` | `~/.agents/skills/<name>/` plus per-adapter projections | agent skill loader walks `~/.agents/skills/` (Codex), `~/.claude/skills/` (Claude), `~/.cursor/skills/` (Cursor symlink) |
| Cursor plugin | upstream repo | `~/.cursor/plugins/<id>/` (marketplace loader) | Cursor plugin loader; NOT scanned by `~/.agents/skills/` agents |

Implication: filesystem-copying a marketplace plugin into `~/.cursor/plugins/local/` does not make it visible to Claude Code, Codex, or any non-Cursor agent. Likewise, a playbook skill is invisible to Cursor's plugin loader (Cursor sees it via `~/.cursor/skills/` instead). For workflows that need to work across agents (PR review, CI gates, code quality), author a playbook skill. For Cursor-only local checks, the marketplace plugin route is fine.

## Observability extensions (refer-only)

### microsoft/AI-Engineering-Coach

- VS Code extension; MIT
- Reads local AI session logs and renders insights ("no data leaves your machine")
- Install: VS Code marketplace
- Not vendored; listed here so teammates know it exists for usage analytics

## Maintenance

When a tool changes meaningfully (new flag, deprecation, auth shift), update this file and bump `last_reviewed`. When adding a new tool worth surfacing repo-wide, add an entry here rather than scattering it across skill bodies.
