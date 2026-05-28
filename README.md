# agentic-playbook

A tool-agnostic, shareable system for working with coding agents. One canonical repo holds the skills, rules, hooks, MCP server configs, subagents, slash commands, and prompt templates; one `make install` materializes them as native files in whichever coding agent you use (Claude Code, Codex CLI, Cursor IDE + CLI, Windsurf, Pi, plus 20+ more via Tier 3 adapters).

This is also a teaching project. Clone it, study the ADRs, copy the patterns, build your own playbook with whatever conventions fit your team.

## What it is (8 content types)

- **Skills** (`base/skills/`): workflow orchestration ("how to scaffold a PRD", "how to review a PR with our conventions", "how to triage a CI failure")
- **Rules** (`base/rules/`): behavioral constraints distributed as `AGENTS.md` fragments ("never use em dashes", "feature branch only, never push to default")
- **Hooks** (`base/hooks/`): shell scripts that fire on agent lifecycle events (pre-tool, post-tool, session-start, etc.); examples: lint guard, human-html auto-index, memory-curator
- **MCP configs** (`base/mcp/`): shareable Model Context Protocol server definitions (agent-memory bridge, code-review graph, anchored filesystem); the installer registers them with every supported adapter
- **Subagents** (`base/agents/`): specialized AI assistants with their own context window; markdown source converts to the right native format per adapter
- **Slash commands** (`base/commands/`): user-triggered actions ("/handoff", "/diagnose", "/playbook-promote") for Cursor + Claude Code
- **Prompt templates** (`base/prompts/`): reusable `/name` expansion templates (Pi-flavored), plus onboarding docs
- **Trajectories** (`base/trajectories/`): cross-adapter behavior assertions, one per (skill, scenario). Declare input phrasings, DSL assertions over the tool-call trace, and an LLM-judge rubric. Consumed by the trajectory harness (`make trajectory-check`), not materialized to adapters. Per ADR-0044.

Profiles (`profiles/`) compose the 7 content types into per-role bundles: `tech-lead`, `engineering`, `devops`, `qa`, `research`, `product-manager`, `backend-developer`, `frontend-developer`. Each profile's TOML lists which skills, rules, hooks, and MCPs to install.

The installer detects which agents are present on your machine, pre-selects them, and lets you toggle. Each agent gets the native files it expects: SKILL.md for Claude Code, .mdc for Cursor, `.windsurf/skills/` for Windsurf, TOML subagents for Codex, `~/.pi/agent/skills/` for Pi, `AGENTS.md` for the 20+ tools that read it natively.

## Why this exists

Most playbooks are utilitarian: they exist to be consumed, not learned from. This one is deliberately built as a teaching project.

- `docs/adr/` explains **why** each decision was made. 40+ ADRs covering content shape, install model, governance, lifecycle, hooks contract, MCP boundary, profile semantics, version policy, content tiering, sync infrastructure.
- `docs/research/` shows the **evidence** behind those decisions.
- `base/prompts/` contains pre-built scaffolding prompts you can paste into your coding agent to bootstrap a version of this playbook for your own team or project.

The point isn't to make you use these skills. It's to make it easy to build yours.

## Inspirations

Two precedents shaped this directly:

- **Microsoft's [code-with-engineering-playbook](https://github.com/microsoft/code-with-engineering-playbook)** proved that the rationale IS the value. A playbook full of "here's why" is more useful than a playbook full of "here's what."
- **Airbnb's [knowledge-repo](https://github.com/airbnb/knowledge-repo)** proved that methodology shipped alongside content beats either alone.

Additional precedents the design rests on:

- **Block / Goose** (5,000 employees, donated to Linux Foundation) validates the rules-vs-recipes separation at company scale.
- **Stripe Minions** validates the directory-scoped rules architecture (per-subproject `AGENTS.md` instead of monolithic).
- **mattpocock/skills** validates the SKILL.md format and the skill-bucket organization.
- **Spotify Golden Path** validates the blessed-path-per-discipline framing.

See `docs/research/` for the evidence base and `docs/adr/` for how each piece informed a specific design decision.

## Quick start

Different entry points for different things you want to do.

### I just want the playbook installed for my agents

```bash
git clone https://github.com/rhnfzl/agentic-playbook.git
cd agentic-playbook
make install
```

The installer detects which coding agents you have on this machine, lets you toggle them, and materializes the right files for each. Re-run anytime to sync updates.

### I want to use the playbook in a specific project

```bash
make init TARGET=/path/to/my-project
```

Scaffolds the target project with an `AGENTS.md` (pointer back to the playbook plus a fillable 8-section template) and a `.playbook-config.yaml` that records the profile. Pick from any installed profile or compose your own with `--profile a,b,c`.

### I want my coding agent to read this playbook and integrate what fits

You have an existing setup. You don't want to blindly run `make install`; you want a thinking pass that picks the right pieces for your machine or your project, explains the tradeoffs, and proposes a phased rollout you can review before any file lands.

That pass is a prompt you paste into your coding agent of choice (Claude Code, Codex, Cursor, Windsurf) after cloning this playbook. The agent walks the playbook, walks your current setup, and proposes a plan. Two flavors:

**Globally (entire machine)**: audit `~/.claude`, `~/.codex`, `~/.cursor`, `~/.codeium/windsurf/`, etc., and propose what to install for every project you work on. The exact prompt template lives in `base/prompts/global-audit.md`.

**For one specific project**: audit the current working directory and propose project-level files (`AGENTS.md`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, project hooks). Prompt template at `base/prompts/project-audit.md`.

Both share the same shape: read the playbook, read your current setup, propose a phased plan with concrete commands. The agent does the matching; you keep the review and approval.

### I want to add a new skill

```bash
make new SKILL=my-workflow CATEGORY=engineering
```

Scaffolds `base/skills/engineering/my-workflow/SKILL.md` with the right frontmatter. Edit, then `make check`, commit, PR.

### I want to manage what is installed

```bash
make list           # show installed playbook content per adapter
make status         # compare installed vs lockfile, report drift
make update         # re-materialize content + refresh lockfile
make remove         # remove materialized files per lockfile (skips managed-block + user-edited)
make doctor         # diagnose setup issues
```

### I want to verify the project is healthy

```bash
make check          # full pipeline: frontmatter, AGENTS.md governance, audit, size, decay, em-dash, evals
make test           # adapter smoke tests
make audit          # external-skill security audit (block-by-default)
make sync-mattpocock        # pull upstream mattpocock/skills updates
make sync-curated-skills    # pull curated PM/research skill sets
make doctor-verify          # layer-3: lockfile vs native config + MCP runtime initialize handshake
```

### I want to see every project this machine has the playbook bound to

```bash
make targets-list             # table of every project that ran `make init`
make targets-doctor           # report registry state (read-only by default)
make targets-doctor PRUNE=1   # opt in to pruning entries pointing at missing dirs
```

Multi-target registry lives at `~/.coding-agents-playbook-targets.json` and is refreshed by every successful `make init` and `make update`. `make targets-doctor` is report-only by default so a temporarily unmounted workspace or transient permissions issue doesn't silently drop metadata; explicit `PRUNE=1` opts into destruction. Per ADR-0038.

## Keeping the playbook updated

The playbook gets stale unless there is a mechanism to capture new patterns as they emerge during real coding work. Two skills handle this; both are installed by `make install` so they work from any working directory.

**At session end**, if anything during the session felt skill-worthy (a recurring pattern, a fix recipe, a workflow you'd do again), invoke `/playbook-retrospective`. It reads the current session log, searches the playbook for existing coverage, and drafts proposals into `~/.playbook-proposals/` (gitignored, user-level, decoupled from the playbook checkout). Manual trigger only; never fires on its own.

**The next day**, review the drafts. Sleep on it. Many "useful patterns" don't survive a second look. The drafts stay private until you decide to graduate them.

**When ready to graduate a draft**, invoke `/playbook-promote <slug>`. It runs a grill-me-style interview (require a 2nd source, articulate "When NOT to use", confirm ownership), scaffolds via `scripts/new_skill.py` (for skills) or writes directly (for rules and hooks), creates a `feat/playbook-add-<slug>` branch, runs `make check`, and stops. Final commit + push + PR are yours.

Drafts live at `$PLAYBOOK_PROPOSALS_DIR` (default `~/.playbook-proposals/`). The promotion command finds the playbook checkout via `$PLAYBOOK_HOME` or by searching common paths.

Full design rationale: `docs/adr/0008-three-layer-capture-system.md`.

## Project structure

Each top-level directory has its own `README.md` with the schema, install rules, and references for that content type.

```
agentic-playbook/
├── base/                                portable content (ADR-0040)
│   ├── skills/                          workflow library
│   │   ├── engineering/                 code review, CI debug, refactor patterns
│   │   ├── productivity/                slide decks, meeting briefs, handoffs
│   │   ├── observability/               k8s sweeps, dashboard interpretation
│   │   ├── research/                    data profiling, lit synthesis, RAG eval
│   │   ├── meta/                        playbook management (write-a-skill, audits)
│   │   └── imported/                    curated upstream skills (mattpocock, phuryn, others)
│   ├── rules/                           always-on behavioral constraints
│   ├── hooks/                           shell hooks fired on agent lifecycle events
│   │   └── templates/                   workspace-specific scaffolds (not installed)
│   ├── mcp/                             MCP server configs (Hub + bundled servers)
│   │   ├── anchored-fs/                 vendored MCP bundle (anchored edit + path resolver)
│   │   ├── agent-memory-bridge/         shared memory MCP for cross-session continuity
│   │   └── code-review-graph.json       graph-aware review MCP
│   ├── agents/                          subagents (markdown frontmatter)
│   ├── commands/                        user-triggered slash commands (Cursor + Claude Code)
│   ├── prompts/                         setup/onboarding + runtime templates
│   └── trajectories/                    cross-adapter behavior assertions (ADR-0044)
├── evals/                               LLM-judge eval suites per skill
├── profiles/                            per-role install bundles
├── scripts/                             installer + lint + decay checks + bulk import
│   ├── adapters/                        per-agent install adapters (claude, codex, cursor, windsurf, pi, ...)
│   ├── checks/                          make check gates (frontmatter, decay, em-dash, content tiering, ...)
│   ├── templates/                       new-skill/new-command scaffolds + cron / sync templates
│   └── sync_distribution.py             manifest-driven content distribution (ADR-0042)
├── tests/                               lifecycle pytest suite (installer regressions, 200+ tests)
├── docs/
│   ├── adr/                             design decisions (0001+); start with 0036 (three-layer content contract)
│   ├── research/                        evidence base + upcoming-adapters tracking
│   └── tools/                           per-agent integration notes
├── AGENTS.md                            project-level rules + writing style
├── CONTRIBUTING.md                      contribution guide
├── OWNERS.md                            owner registry (per-content-type)
├── TOOLS.md                             external tool catalog (refer-only)
├── Makefile                             `make install` / `check` / `test` / `doctor` entrypoints
├── VERSION                              single-source-of-truth semver
└── pyrightconfig.json                   pyright (Python type checker) config
```

## How it stays current

This repo is the downstream mirror of a maintainer's working copy. A manifest-driven sync (`scripts/sync_distribution.py`, ADR-0042) updates this repo whenever the upstream advances; the sync runs daily via cron on the maintainer's machine and applies a scrub-and-copy transform that strips workspace-internal references before publishing.

Implications for downstream users:

- The published content is intentionally a generic subset of what the maintainer uses internally. Skills, rules, and hooks describe portable patterns; workspace-internal examples have been replaced with placeholder tokens.
- The `.sync-manifest.json` at the repo root records the source commit and the scrub-rules hash for the most recent sync. Use it to verify what version of the upstream you're at.
- Direct PRs against this repo are welcome but the maintainer may fold them back into the upstream (which then re-syncs here) rather than landing them directly, to keep the sync direction one-way.

## Contributing

Issues and PRs welcome. The repo's own `AGENTS.md` describes the contribution conventions the installer enforces internally (commit-message shape, branch naming, what `make check` will catch before CI); the same conventions apply to external contributors.

Each content artifact has an `owner:` field in its frontmatter. The owner is responsible for upkeep, deprecation, and answering questions about the skill / rule / hook.

To add or modify content, see `CONTRIBUTING.md` for the full workflow.

## License

MIT. See [LICENSE](LICENSE).
