# Inspirations

This file catalogs the precedents that shaped the coding-agents-playbook. Each entry covers: who they are, what we borrowed, what we changed, and why.

The point of this document is the framing of the playbook itself. It is an inspiration repo. The same way mattpocock's skills, Block's Goose, Stripe's Minions, and Microsoft's code-with-engineering-playbook are inspirations to us, this repo is meant to be an inspiration to the next team.

## mattpocock/skills

**URL:** https://github.com/mattpocock/skills
**License:** MIT
**Scope:** Personal Claude Code skill library, distributed via skills.sh npm CLI.

**What we borrowed:**
- SKILL.md format with YAML frontmatter (name, description, version) as the canonical skill unit.
- Category folders inside `skills/`: engineering, productivity, misc (we use engineering / productivity / observability / meta).
- CONTEXT.md as a shared-language file (mattpocock's ubiquitous-language pattern).
- docs/adr/ for design-decision records.
- A `setup-*` skill that configures per-repo state (we have a similar shape via profiles).
- The skills.sh-style install UX: detect installed agents, pre-select, let user toggle.

**What we changed:**
- Multi-author (team-shared, not personal): every skill has an `owner:` field.
- Cross-tool: 28 agents supported via tiered adapters, not Claude-Code-only.
- `last_reviewed:` frontmatter + CI decay check (warn 90d, block 180d).
- Added harness layer (hooks, MCP configs, profiles) that his repo does not have.

**Key quote from his README:** *"These skills are designed to be small, easy to adapt, and composable. They work with any model. They are based on decades of engineering experience. Hack around with them. Make them your own. Enjoy."*

## Block / Goose

**URL:** https://github.com/block/goose
**License:** Apache 2.0 (donated to Linux Foundation, December 2025)
**Scope:** Open-source AI coding agent. Used by 5,000 Block employees weekly. The only published example of a company running team-shared agentic workflows at scale.

**What we borrowed:**
- The strict separation between Rules (behavioral constraints) and Recipes (workflow orchestration). This separation is documented as load-bearing; conflating them is a failure mode.
- Owner accountability per artifact (Block uses session ownership; we use SKILL.md `owner:` frontmatter).
- 5,000-engineer-scale validation that a Recipes-style approach works.

**What we changed:**
- Recipes are JSON-exported with pinned MCP extensions; we use SKILL.md markdown for git-friendliness and human readability.
- No Block-specific platform binding: our adapters must work in Cursor, Windsurf, Codex too.

**Key insight:** Block's Recipes architecture survives 5,000-engineer scale specifically because Rules and Recipes are separate. Mixing them is the single biggest failure mode at team-shared scale.

## Stripe Minions

**URL:** https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents
**Companion writeup:** https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs
**Scope:** Stripe's internal coding-agent system, shipping 1300+ PRs in production.

**What we borrowed:**
- Directory-scoped rules (per-subproject AGENTS.md). The single most consequential design move in v2.
- "Rules used very judiciously" globally. Most rules co-locate with the code they govern.
- MCP via internal toolshed pattern (~500 Stripe tools). Our `mcp/` directory follows the same per-config-file pattern.

**What we changed:**
- Open source (Stripe's is internal).
- Per-team profiles (Stripe is one team; we are four roles).

**Key quote:** *"Rules are used very judiciously globally because loading all rules globally fills the context window before the agent starts work."*

This is documented in our `docs/research/failure-modes.md` as failure mode #1.

## Microsoft code-with-engineering-playbook

**URL:** https://github.com/microsoft/code-with-engineering-playbook
**License:** MIT
**Scope:** Microsoft Commercial Software Engineering (CSE) org's six-year-distilled engineering playbook. Built across hundreds of real production engagements.

**What we borrowed:**
- PR-based contribution with explicit reviewer pool.
- ADRs alongside artifacts (the rationale lives with the code).
- The "rationale IS the value" framing: a playbook full of "here's why" is more useful than a playbook full of "here's what."
- Focused scope kept small (their scope: code review; ours: coding-agent workflows).

**What we changed:**
- Coding-agent-specific (their playbook is general engineering).
- Smaller team scope (10 engineers vs. hundreds).
- Markdown source format compiles to per-agent native files; their playbook is read-only documentation.

**Key insight:** Microsoft's playbook is six years old and still active. The structural reason: contributors update it when they learn something on a real engagement. The rationale lives alongside the practice, so contributors understand why the practice exists.

## Airbnb knowledge-repo

**URL:** https://github.com/airbnb/knowledge-repo
**License:** Apache 2.0
**Scope:** Git-backed knowledge sharing platform open-sourced in 2016.

**What we borrowed:**
- Methodology lives alongside content. Each knowledge post includes the analysis and decisions, not just conclusions.
- Peer review via git pull requests. Knowledge is treated as code.
- Versioned, owned, searchable.

**What we changed:**
- Skills and rules instead of analytical posts (we are coding-agent-specific, not data-science).
- Agent-consumable, not human-only.

**Key insight:** Airbnb's repo proved that knowledge artifacts work when you treat them like code (PR review, ownership, version control). That same model works for skills, rules, and ADRs.

## Spotify Golden Path / Backstage

**URL:** https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem
**Scope:** Spotify's "blessed and supported" path for building each kind of service, integrated with Backstage developer portal.

**What we borrowed:**
- "Blessed path per discipline" framing. Backend developers, frontend developers, QA, and tech leads each get a profile.
- Onboarding-first: the Golden Path tutorial is the most-read documentation at Spotify and the first thing new engineers see. Our `onboard-a-new-teammate` prompt parallels this.
- Treat the playbook as load-bearing: if you only have time to update one thing, update the Golden Path.

**What we changed:**
- Profiles (TOML files) instead of Backstage TechDocs portal (lighter weight).
- No web app required.

**Key insight:** Spotify's lesson is institutional. The Golden Path works because Spotify treats it as infrastructure, not documentation. Owners are tasked with maintaining it above all other documentation.

## Ruler CLI (intellectronica)

**URL:** https://github.com/intellectronica/ruler
**License:** MIT
**Scope:** CLI that reads `.ruler/*.md` and writes agent-specific config files for 20+ tools, including MCP config distribution.

**What we borrowed:**
- The per-tool adapter abstraction. Each adapter is small (~100-200 lines) and focused.
- Nested rule loading for monorepos.
- MCP config distribution alongside rules.
- The 20+ agent target list (we extend with our own additions).

**What we changed:**
- We do not depend on Ruler at runtime (see ADR 0003: foundational infrastructure shouldn't depend on third-party).
- Custom UX layer (skills.sh-style detection); Ruler's UX is more CLI-flag-driven.

**Key insight:** Ruler is technically excellent OSS but it is single-author. For team-foundation infrastructure, owning the engine is worth the extra ~600 lines of code.

## Packmind

**URL:** https://packmind.com
**Scope:** Commercial ContextOps platform: enterprise governance, drift detection, multi-repo distribution.

**What we borrowed:**
- Drift detection categories: pattern violation, architectural drift, staleness, inter-agent inconsistency. All four are documented in our `failure-modes.md`.
- `last_reviewed:` pattern + lint-the-rules approach.
- The framing that rules without governance decay silently.

**What we changed:**
- Not SaaS. Lightweight CI checks instead of enterprise governance platform.
- Open source instead of commercial.

**Key insight:** Packmind's research validated that drift is the #1 long-term risk for shared rules. Even the smallest CI check (`last_reviewed > 90d?`) is much better than nothing.

## skills.sh

**URL:** https://skills.sh
**Scope:** Distribution platform for Claude Code skills, used by mattpocock and others.

**What we borrowed:**
- The install-time UX pattern: `npx skills@latest add <repo>` prompts for which agents to install into, pre-selects detected ones.

**What we changed:**
- We have our own installer (`make install`) instead of running through skills.sh's runtime. This keeps the dependency surface smaller and matches our "own the engine" principle from ADR 0003.

## Lineage Summary

Each design decision in this playbook traces back to at least one precedent:

| Design decision | Inspired by |
|---|---|
| SKILL.md as canonical | mattpocock/skills |
| Categories inside skills/ | mattpocock/skills |
| CONTEXT.md shared language | mattpocock/skills |
| docs/adr/ | mattpocock + Microsoft |
| Per-subproject AGENTS.md | Stripe Minions |
| Rules vs Skills separation | Block/Goose |
| Owner per artifact | Block/Goose + Microsoft |
| PR-based contribution | Microsoft + Airbnb |
| Methodology beside content | Airbnb + Microsoft |
| Profiles per role | Spotify Golden Path |
| Per-tool adapter pattern | Ruler CLI |
| Install-time agent detection | skills.sh |
| Decay tracking | Packmind |
| Inspiration-repo framing | Microsoft (rationale IS the value) |

This is how the playbook came to be. Use any of these precedents as your starting point when building your own.
