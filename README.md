# agentic-playbook

[![License: MIT](https://img.shields.io/github/license/rhnfzl/agentic-playbook?color=blue)](LICENSE)
[![Stars](https://img.shields.io/github/stars/rhnfzl/agentic-playbook?style=flat&logo=github)](https://github.com/rhnfzl/agentic-playbook/stargazers)
[![Forks](https://img.shields.io/github/forks/rhnfzl/agentic-playbook?style=flat&logo=github)](https://github.com/rhnfzl/agentic-playbook/network/members)
[![Last commit](https://img.shields.io/github/last-commit/rhnfzl/agentic-playbook?logo=git&color=informational)](https://github.com/rhnfzl/agentic-playbook/commits/main)
[![Contributors](https://img.shields.io/github/contributors/rhnfzl/agentic-playbook)](https://github.com/rhnfzl/agentic-playbook/graphs/contributors)
[![Top language](https://img.shields.io/github/languages/top/rhnfzl/agentic-playbook?logo=python)](https://github.com/rhnfzl/agentic-playbook)
[![Issues](https://img.shields.io/github/issues/rhnfzl/agentic-playbook?logo=github)](https://github.com/rhnfzl/agentic-playbook/issues)
[![Pull requests](https://img.shields.io/github/issues-pr/rhnfzl/agentic-playbook?logo=github)](https://github.com/rhnfzl/agentic-playbook/pulls)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-yellow?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![AI Bill of Materials](https://img.shields.io/badge/AI--BOM-published-brightgreen)](docs/security/ai-bom.json)
[![Made for Claude Code · Cursor · Codex · Windsurf](https://img.shields.io/badge/agents-Claude%20Code%20%C2%B7%20Cursor%20%C2%B7%20Codex%20%C2%B7%20Windsurf%20%2B16-orange)](#what-it-is-8-content-types)

> **agentic-playbook is a tool-agnostic, shareable repository of skills, rules, hooks, MCP server configs, subagents, slash commands, prompt templates, and behavior trajectories that installs natively into Claude Code, Cursor, Windsurf, Codex CLI, GitHub Copilot, Cline, Aider, Pi, Gemini CLI, and 20+ more coding agents through a single `make install`.**

It is also a deliberately-built teaching project. The 49 Architecture Decision Records under `docs/adr/` explain why each design choice exists; the research under `docs/research/` shows the evidence. Clone it, study the ADRs, copy the patterns, and build your own playbook with whatever conventions fit your team.

## Who this is for

- **Tech leads and engineering managers** who want one canonical, versioned set of agent rules and skills that lands consistently on every teammate's machine, regardless of which coding agent each person prefers.
- **Individual engineers** running Claude Code, Cursor, Codex CLI, Windsurf, GitHub Copilot, Cline, Aider, or Gemini CLI who want a tested baseline of skills and rules without authoring everything from scratch.
- **Product managers, researchers, QA engineers, and DevOps engineers** who use the same coding agents as the engineers and want a role-specific bundle (`product-manager`, `research`, `qa`, `devops` profiles) tuned to their workflow.
- **Open-source maintainers and platform teams** building their own agent playbook who want a worked reference for skill format (SKILL.md), rule shape, hook lifecycle, multi-adapter install, decay tracking, supply-chain security, and per-skill telemetry.

## What you get in 60 seconds

One `git clone` followed by one `make install` gives you:

- **150+ skills, rules, hooks, MCP server configs, subagents, commands, prompts, and trajectories** materialized natively into every coding agent installed on your machine.
- **Detection-and-preselect**: the installer probes `~/.claude/`, `~/.codex/`, `~/.cursor/`, `~/.codeium/windsurf/`, and others, then pre-selects the agents it found.
- **Role profiles** that filter the firehose to the 15-30 items that matter for your specific role (`tech-lead`, `backend-developer`, `frontend-developer`, `qa`, `research`, `product-manager`, `devops`).
- **A lockfile that records every materialized path**, so `make remove` cleanly uninstalls without touching anything you authored by hand.
- **`make check` quality gates** that catch frontmatter drift, decay, em-dashes, AGENTS.md governance violations, content-tier breaches, and 7 other failure modes before you commit.

## What it is (8 content types)

- **Skills** (`base/skills/`): workflow orchestration ("how to scaffold a PRD", "how to review a PR with our conventions", "how to triage a CI failure")
- **Rules** (`base/rules/`): behavioral constraints distributed as `AGENTS.md` fragments ("never use em dashes", "feature branch only, never push to default")
- **Hooks** (`base/hooks/`): shell scripts that fire on agent lifecycle events (pre-tool, post-tool, session-start, etc.); examples: lint guard, human-html auto-index, memory-curator
- **MCP configs** (`base/mcp/`): shareable Model Context Protocol server definitions (agent-memory bridge, code-review graph, anchored filesystem); the installer registers them with every supported adapter
- **Subagents** (`base/agents/`): specialized AI assistants with their own context window; markdown source converts to the right native format per adapter
- **Slash commands** (`base/commands/`): user-triggered actions ("/handoff", "/diagnose", "/playbook-promote") for Cursor + Claude Code
- **Prompt templates** (`base/prompts/`): reusable `/name` expansion templates (Pi-flavored), plus onboarding docs
- **Trajectories** (`base/trajectories/`): cross-adapter behavior assertions, one per (skill, scenario). Declare input phrasings, DSL assertions over the tool-call trace, and an LLM-judge rubric. Consumed by the trajectory harness (`make trajectory-check`), not materialized to adapters. Per ADR-0044.

Profiles (`profiles/`) compose the 8 content types into per-role bundles: `tech-lead`, `backend-developer`, `frontend-developer`, `qa`, `research`, `product-manager`, `devops`. Each profile's TOML lists which skills, rules, hooks, and MCPs to install.

Plugins (`plugins/`) are pre-built marketplace bundles (per ADR-0043) that mirror each profile but install through `/plugin install <pack>@8v-coding-agents-playbook` inside Claude Code or Cursor instead of through `make install`. Use plugins when you want a single-pack install with no Make tooling on the target machine; use profiles when you want the full `make install` lifecycle with lockfile + decay tracking. Both paths land equivalent content.

The installer detects which agents are present on your machine, pre-selects them, and lets you toggle. Each agent gets the native files it expects: SKILL.md for Claude Code, .mdc for Cursor, `.windsurf/skills/` for Windsurf, TOML subagents for Codex, `~/.pi/agent/skills/` for Pi, `AGENTS.md` for the 20+ tools that read it natively.

## Why this exists

Most playbooks are utilitarian: they exist to be consumed, not learned from. This one is deliberately built as a teaching project.

- `docs/adr/` explains **why** each decision was made. 49 ADRs covering content shape, install model, governance, lifecycle, hooks contract, MCP boundary, profile semantics, version policy, content tiering, sync infrastructure, supply-chain security gate, telemetry privacy, atlas knowledge graph.
- `docs/atlas/` is an auto-generated, browseable knowledge graph of every ADR, skill, and trajectory in the repo, plus the cross-references between them. Run `make atlas` to rebuild; open `docs/atlas/index.html` in a browser to explore.
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
make init TARGET=<path-to-your-project>
```

Scaffolds the target project with an `AGENTS.md` (pointer back to the playbook plus a fillable 8-section template) and a `.playbook-config.yaml` that records the profile. Pick from any installed profile (`backend-developer`, `frontend-developer`, `qa`, `research`, `product-manager`, `devops`, `tech-lead`) or compose your own with `--profile <profile1>,<profile2>,<profile3>`.

### I want my coding agent to read this playbook and integrate what fits

You have an existing setup. You don't want to blindly run `make install`; you want a thinking pass that picks the right pieces for your machine or your project, explains the tradeoffs, and proposes a phased rollout you can review before any file lands.

That pass is a prompt you paste into your coding agent of choice (Claude Code, Codex CLI, Cursor, Windsurf) after cloning this playbook. The agent walks the playbook, walks your current setup, and proposes a plan. Two flavors:

**Globally (entire machine)**: audit `~/.claude/`, `~/.codex/`, `~/.cursor/`, `~/.codeium/windsurf/`, etc., and propose what to install for every project you work on. Paste prompt: [`base/prompts/global-audit.md`](base/prompts/global-audit.md).

**For one specific project**: audit the current working directory and propose project-level files (`AGENTS.md`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, project hooks). Paste prompt: [`base/prompts/project-audit.md`](base/prompts/project-audit.md).

Both share the same shape: read the playbook, read your current setup, propose a phased plan with concrete commands. The agent does the matching; you keep the review and approval.

### I want to install via the Claude Code or Cursor plugin marketplace

```text
/plugin install backend-developer@8v-coding-agents-playbook
```

Picks a role-specific bundle from `plugins/` (per ADR-0043) and installs it through your IDE's native plugin marketplace instead of `make install`. No Make tooling required on the target machine. Available packs mirror the profiles: `backend-developer`, `frontend-developer`, `qa`, `research`, `product-manager`, `devops`, `tech-lead`, and `meta` (the playbook-management pack).

### I want to add a new skill

```bash
make new SKILL=<skill-slug> CATEGORY=<category>
```

Where `<category>` is one of `engineering`, `productivity`, `observability`, `research`, `meta`. Scaffolds `base/skills/<category>/<skill-slug>/SKILL.md` with the right frontmatter. Edit, then `make check`, commit, PR.

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
make check                  # full pipeline: frontmatter, AGENTS.md governance, audit, size, decay, em-dash, content tiering
make test                   # adapter smoke tests
make audit                  # external-skill security audit (block-by-default)
make eval                   # LLM-judge eval suites per skill (slower; split from make check)
make trajectory-check       # cross-adapter behavior assertions (Claude / Codex / Cursor / Windsurf) per ADR-0044
make telemetry-report       # per-skill triggers / latency / token usage from opt-in OTel collector (ADR-0048)
make atlas                  # rebuild the docs/atlas/ knowledge graph (ADR-0049)
make sync-mattpocock        # pull upstream mattpocock/skills updates
make sync-curated-skills    # pull curated PM / research skill sets
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
│   │   └── imported/                    curated upstream skills (mattpocock, pm-curated, layers, impeccable, research-curated, taste-skill)
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
├── profiles/                            per-role install bundles (make install)
├── plugins/                             pre-built marketplace bundles (/plugin install, ADR-0043)
├── scripts/                             installer + lint + decay checks + bulk import
│   ├── adapters/                        per-agent install adapters (claude, codex, cursor, windsurf, pi, ...)
│   ├── checks/                          make check gates (frontmatter, decay, em-dash, content tiering, ...)
│   ├── security/                        supply-chain gate + AI BOM emitter (ADR-0047)
│   ├── telemetry/                       OTel collector + per-skill report (ADR-0048)
│   ├── atlas/                           knowledge-graph builder (ADR-0049)
│   ├── templates/                       new-skill/new-command scaffolds + cron / sync templates
│   └── sync_distribution.py             manifest-driven content distribution (ADR-0042)
├── tests/                               lifecycle + atlas + security + telemetry pytest suite (480+ tests)
├── docs/
│   ├── adr/                             design decisions (0001+); start with 0036 (three-layer content contract)
│   ├── research/                        evidence base + upcoming-adapters tracking
│   ├── atlas/                           auto-generated knowledge graph (open index.html in a browser)
│   ├── security/                        AI Bill of Materials, supply-chain audit output
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

## Frequently asked questions

### What is agentic-playbook in one sentence?

agentic-playbook is an open-source, tool-agnostic library of skills, rules, hooks, MCP server configs, subagents, slash commands, prompt templates, and behavior trajectories that installs natively into 20+ coding agents (Claude Code, Cursor, Windsurf, Codex CLI, GitHub Copilot, Cline, Aider, Pi, Gemini CLI, and more) through a single `make install` or `/plugin install` command.

### Who is agentic-playbook for?

It is for engineering tech leads, individual engineers, product managers, researchers, QA engineers, and DevOps engineers who use AI coding agents (Claude Code, Cursor, Windsurf, Codex CLI, GitHub Copilot, Cline, Aider, Pi, or Gemini CLI) and want a tested, role-specific baseline of skills and rules without authoring everything from scratch. It is also for open-source maintainers and platform teams building their own internal agent playbook who want a worked reference for skill format, multi-adapter install, decay tracking, supply-chain security, and per-skill telemetry.

### Which coding agents does agentic-playbook support?

Tier 1 (full adapter, hook-capable): Claude Code, Cursor IDE + CLI, Codex CLI, Windsurf, Cline, GitHub Copilot. Tier 2 (rules + skills only, no hook surface): Aider, Gemini CLI, Pi. Tier 3 (AGENTS.md-only, declarative TOML): 16 long-tail agents including Goose, Junie, Kiro, Zed, Amp, RooCode, and others. See `docs/adr/0030-tier-3-declarative-registry.md` for the full Tier 3 list.

### How is agentic-playbook different from anthropics/skills or awesome-agent-skills?

`anthropics/skills` is a curated bundle of skills from Anthropic. `awesome-agent-skills` (heilcheng, VoltAgent) is a curated index of external skill repositories. agentic-playbook is a **distribution-and-governance system**: it ships seven other content types (rules, hooks, MCP server configs, subagents, slash commands, prompt templates, behavior trajectories) alongside skills, with a multi-adapter installer, a 13-gate `make check` quality pipeline, a supply-chain security gate (`make audit`), opt-in OTel telemetry per skill (`make telemetry-report`), and an auto-generated knowledge graph (`make atlas`). It is a teaching project as much as a content library: 49 Architecture Decision Records explain why each choice was made.

### Is it safe to clone and install on my machine?

The installer is dry-run by default in all destructive operations, writes lockfiles for every materialized path, and `make remove` cleanly uninstalls. External skills imported via `make sync-mattpocock` and `make sync-curated-skills` pass through a block-by-default security audit (`make audit`, ADR-0047) before they land in the playbook. The opt-in OpenTelemetry collector (ADR-0048) is off by default and records metadata only (skill name, latency, token counts); prompt bodies and response bodies are never stored. See `docs/security/ai-bom.json` for the current AI Bill of Materials.

### How do I uninstall agentic-playbook cleanly?

```bash
make remove                 # remove materialized files per lockfile; skips managed-block + user-edited
make remove TARGET=<path>   # remove from a specific project the playbook was bound to
```

The lockfile records every file the installer wrote. `make remove` only deletes files in the lockfile; anything you hand-authored outside the `<!-- coding-agents-playbook BEGIN/END -->` markers is preserved.

### Can I install just one skill or rule without taking the whole playbook?

Yes, three ways. (1) Use a role profile: `make install PROFILE=<role>` filters the install to the 15-30 items that role needs. (2) Use a plugin pack: `/plugin install <pack>@8v-coding-agents-playbook` inside Claude Code or Cursor installs just that pack. (3) Copy the SKILL.md or rule file directly into your own playbook; the format is documented in `base/skills/README.md` and `base/rules/README.md`.

### Does agentic-playbook require GitHub?

No. The installer and the `make` pipeline work against a local checkout regardless of where it came from. GitHub is the public distribution point (`https://github.com/rhnfzl/agentic-playbook`) but you can also clone via HTTPS, mirror to your own forge, or download a tarball.

### Where do my hand-edits go on re-install?

Anywhere outside the `<!-- coding-agents-playbook BEGIN/END -->` managed-block markers is preserved across `make update` and `make install`. The installer rewrites only the content inside the markers and records the file in the lockfile. For SKILL.md and rule files materialized into agent directories, the installer detects user-edits via mtime + content hash and prompts before overwriting.

### How do I track adoption of the playbook?

GitHub Insights → Traffic (admin-only) shows clones and views in 14-day windows. Stars, forks, contributors, and dependents are public and shown in the badge row at the top of this README. For per-skill usage on your own install, run `make telemetry-report` after enabling the opt-in OTel collector (per ADR-0048). The repo deliberately does not collect or aggregate cross-installation telemetry; that is out of scope for an open-source content library.

## Star history

[![Star History Chart](https://api.star-history.com/svg?repos=rhnfzl/agentic-playbook&type=Date)](https://star-history.com/#rhnfzl/agentic-playbook&Date)

## Related reading inside this repo

- [`base/skills/README.md`](base/skills/README.md), [`base/rules/README.md`](base/rules/README.md), [`base/hooks/README.md`](base/hooks/README.md), [`base/mcp/README.md`](base/mcp/README.md) for the four core content types.
- [`base/agents/README.md`](base/agents/README.md), [`base/commands/README.md`](base/commands/README.md), [`base/prompts/README.md`](base/prompts/README.md), [`base/trajectories/README.md`](base/trajectories/README.md) for the four newer content types.
- [`profiles/README.md`](profiles/README.md) for the per-role install bundles.
- [`plugins/README.md`](plugins/README.md) for the marketplace plugin packs (Claude Code + Cursor).
- [`evals/README.md`](evals/README.md) for the LLM-judge eval suites that gate skill quality.
- [`scripts/README.md`](scripts/README.md) for the installer + 13-gate `make check` pipeline.
- [`docs/README.md`](docs/README.md), [`docs/adr/README.md`](docs/adr/README.md), [`docs/research/README.md`](docs/research/README.md), [`docs/atlas/README.md`](docs/atlas/README.md), [`docs/security/README.md`](docs/security/README.md) for the docs hub.
- [`CONTRIBUTING.md`](CONTRIBUTING.md), [`AGENTS.md`](AGENTS.md), [`CONTEXT.md`](CONTEXT.md), [`CHANGELOG.md`](CHANGELOG.md), [`RELEASING.md`](RELEASING.md), [`TOOLS.md`](TOOLS.md), [`OWNERS.md`](OWNERS.md) for governance and process.

## License

MIT. See [LICENSE](LICENSE).
