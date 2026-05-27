# agentic-playbook

A curated playbook for coding agents. Skills, rules, hooks, MCP configs, agent profiles, and a lifecycle installer that lays them down for Claude Code, Cursor, Codex, and the other adapters listed under `scripts/adapters/`.

## What this is

If you work with a coding agent regularly, you accumulate patterns: shortcuts for the recurring questions you ask, rules you wish the agent would remember between sessions, hooks that catch the failure modes you have seen twice. This repo packages a year of those patterns into a portable installer.

- **Skills** under `base/skills/` are workflows the agent can invoke by name (write a tdd test, draft a prd, run a retrospective, audit a skill, harden a pipeline).
- **Rules** under `base/rules/` are durable instructions that flow into `AGENTS.md` (writing style, no em dashes, no ticket IDs in code, feature-branch-only).
- **Hooks** under `base/hooks/` are pre and post-tool gates (lint guard, never push to main without review, AGENTS.md auto-index, anchored-edit pre-flight).
- **MCP configs** under `base/mcp/` are bundled server definitions (anchored filesystem, agent-memory bridge, code-review graph) that the installer registers with every supported adapter.
- **Agent profiles** under `base/agents/` are role-specific bundles (devops, tech-lead, qa, research, product-manager) that pick a curated subset of the above.
- **Lifecycle tooling** under `scripts/` handles install, update, status, doctor, materialization, lockfile, scope auto-detect, and a CI harness that keeps the content honest (frontmatter lint, decay check, size policy, em-dash sweep, scope boundaries).

## Quick start

```bash
git clone https://github.com/rhnfzl/agentic-playbook.git
cd agentic-playbook
make install TARGET=/path/to/your/project
```

The installer detects which coding agents you have configured locally, picks a profile, and lays the matching skills / rules / hooks / MCPs into your project. Re-run `make update` after pulling new content.

## Adapters supported

Anchored to the adapters listed in `scripts/adapters/`. The exact set evolves; check that directory for the current list. Notable ones:

- **Claude Code** (`.claude/`)
- **Cursor** (`.cursor/`)
- **Codex** (`.codex/`)
- **Gemini CLI** (`.gemini/`)
- **Pi** (`pi.dev`)

Each adapter reads from the same source content; the installer translates skill / rule / hook bodies into the adapter's native format. Adding a new adapter is a single file under `scripts/adapters/` plus an entry in the dispatch table.

## Profiles

The five built-in profiles are starting points, not commitments. Pass `--profile a,b,c` to install multiple roles' content alongside; the union is materialized.

| Profile | What it bundles |
|---|---|
| `tech-lead` | engineering + meta + observability skills with the full hook set |
| `engineering` | engineering + meta skills with the lint and review hooks |
| `devops` | observability skills + infra-focused hooks |
| `qa` | testing skills + bug-triage + review hooks |
| `research` | research skills (interview, market sizing, sentiment) + handoff |
| `product-manager` | PM-execution skills (PRD, sprint plan, retro, prioritization) + research |

## Conventions

The playbook is opinionated. Some of those opinions:

- **AGENTS.md as the canonical instruction file.** Every supported adapter reads `AGENTS.md` natively or via `@-import`; the playbook installs into `AGENTS.md` rather than into per-agent files like `CLAUDE.md` or `.cursor/rules`.
- **Skills are SKILL.md files.** Anthropic-style YAML frontmatter (name, description, version, owner, last_reviewed, tags, scope) plus a markdown body. The same file works across adapters.
- **Profiles are TOML.** Each profile's `[skills].include`, `[rules].include`, `[hooks].include`, `[mcp].include` lists drive what the installer materializes.
- **Lockfile, not git as source-of-truth.** The installer writes `.playbook-lock.json` to each target; subsequent updates reconcile against the lockfile, not against `git diff`.
- **Vendored content is pinned.** Imports from upstream skill repos are pinned to a SHA via `SOURCES.toml`; `make sync-curated-skills` re-fetches and verifies.

## Contributing

Issues and PRs welcome. The repo's own AGENTS.md describes the contribution conventions the installer uses internally; the same conventions apply to external contributors.

## License

MIT. See [LICENSE](LICENSE).
