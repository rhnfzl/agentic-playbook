# team Agentic Coding System: Research Brief
**Date:** 2026-05-24  
**Scope:** Cross-tool, team-shared AI coding skills, agent configs, prompts, harness rules, and hooks  
**Tools in scope:** Claude Code, Codex, Cursor, Windsurf

---

## Inspiration: mattpocock/skills Deep Read

**Repo:** https://github.com/mattpocock/skills (99k stars, 8.8k forks, MIT)  
**Install:** `npx skills@latest add mattpocock/skills`, an npm-based CLI that scaffolds skills into the agent directories you choose.

Matt Pocock's library is structured around solving specific failure modes of coding agents, not around being comprehensive. Every skill answers one of three root problems: "the agent didn't do what I want," "the agent is too verbose," or "the agent is going in circles." The library is organised into named categories (core workflow, engineering, productivity, misc) and each skill is a directory with a `SKILL.md` file.

Key design decisions that make it work:

- **One-shot setup skill.** `/setup-matt-pocock-skills` runs first and configures per-repo context (issue tracker type, triage label vocabulary, doc layout). Other skills consume this config. This is the pattern for onboarding.
- **Progressive disclosure.** Skills trigger via natural language description match, not hardcoded commands. The description field in SKILL.md is the primary routing mechanism, phrased in third person, with explicit "USE WHEN" language.
- **Composability over completeness.** Skills are small, focused, and composed at runtime. `/tdd` does one loop; `/to-issues` does one decomposition. They don't try to do everything.
- **NPM distribution.** The CLI handles multi-agent targeting, you pick which agents to install into during the `npx skills` run. This sidesteps the "which directory" problem without requiring git submodules.

What it does not do: no governance layer, no contribution review process, no versioning scheme, no cross-team distribution (it is explicitly a personal library). It also has no compilation step, the same SKILL.md goes to all agents.

---

## Similar Repos

| Name | URL | Scope | Transferable | Not Transferable |
|---|---|---|---|---|
| mattpocock/skills | github.com/mattpocock/skills | Personal Claude Code skills, npm CLI install | Setup pattern, skill category structure, progressive disclosure descriptions, npm distribution mechanic | No team governance, no cross-tool compile, single author |
| PatrickJS/awesome-cursorrules | github.com/PatrickJS/awesome-cursorrules | Curated .cursorrules files for Cursor, CC0 | Framework-level rule fragments as a starting corpus | No canonical source; just a collection, no runtime distribution |
| buildermethods/agent-os | github.com/buildermethods/agent-os | Tool-agnostic spec-driven dev system (Claude Code, Cursor, Antigravity) | Standards/product/specs three-layer model, modular YAML config, profiles | Not a shared team library; personal or small-team use, no governance |
| intellectronica/ruler | github.com/intellectronica/ruler | CLI that reads `.ruler/*.md` and writes agent-specific config files | Full cross-tool distribution: supports Claude, Cursor, Codex, Windsurf, Copilot, Gemini CLI, Goose, Junie, Warp, and ~12 more. Nested rule loading for monorepos. MCP server config distribution. Explicit skills support. | No governance or quality gates, no team contribution model, no CI integration out of the box |
| PackmindHub/packmind | github.com/PackmindHub/packmind | Full ContextOps lifecycle: build, distribute, govern, maintain playbook across teams | Full CI/CD governance, lint/drift detection, multi-repo distribution, enterprise enforcement. Supports Claude Code, Cursor, Copilot, Junie, Kiro, AGENTS.md | SaaS/commercial enterprise tier for full governance; OSS tier is lighter |
| cursor.directory | cursor.directory | Community Cursor rule fragments | Starting-point rule corpus for framework/language-specific guidance | Purely community aggregate, no structure or governance |
| sanjeed5/awesome-cursor-rules-mdc | github.com/sanjeed5/awesome-cursor-rules-mdc | Cursor-format mdc rules reference | Rule format documentation, glob scoping examples | Cursor-only |
| FireFunGames/agent-rules-sync | VS Code Marketplace | VS Code extension syncing one master rules file to Claude, Cursor, Copilot, Windsurf, Roo | Simple hard-link/sync approach as a proof of concept | Local-only, no CI, no team distribution |

---

## Cross-Tool Format Matrix

| Dimension | Claude Code | Codex (OpenAI) | Cursor | Windsurf |
|---|---|---|---|---|
| **Primary config file** | `CLAUDE.md` (root or subdirs) | `AGENTS.md` (root), `.codex/AGENTS.md`, `AGENTS.override.md` | `.cursor/rules/*.mdc` | `.windsurf/rules/*.md`, legacy `.windsurfrules` |
| **Global/user-level file** | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` | Cursor Settings > User Rules | `~/.codeium/windsurf/memories/global_rules.md` |
| **AGENTS.md support** | Yes (natively read) | Yes (primary format) | Partial (reads AGENTS.md at root as always-on rule per Windsurf/Makerkit report) | Yes, AGENTS.md is processed by the same Rules engine; root-level = always-on, subdir = auto-glob |
| **Skills directory** | `.claude/skills/<name>/SKILL.md` | `.codex/skills/` | `.cursor/skills/` | `.windsurf/skills/` |
| **Activation scoping** | Glob patterns in `.claude/rules/` | Nearest-file precedence (override > root > subdir) | `globs`, `alwaysApply`, `description` frontmatter in .mdc | YAML frontmatter `trigger` field: `always_on`, `manual`, `glob`, `model_decision` |
| **Team/enterprise enforcement** | No dashboard; CODEOWNERS on repo | No dashboard; config precedence in repo | Cursor Team Rules via dashboard (no API); enforce toggle; audit logs (Enterprise) | Windsurf System Rules via IT-deployed OS-level files (Enterprise); read-only for users |
| **Character limits** | None documented | None documented | No per-rule limit documented | 6,000 chars global, 12,000 chars per workspace rule |
| **Hook support** | Yes (PreToolUse, PostToolUse, Stop, Notification) | Limited (Starlark `.rules` for sandbox mode) | Yes (hooks in settings) | Not prominently documented |
| **MCP config** | `.claude.json` / settings.json | `.codex/config.toml` | `.cursor/mcp.json` | `.windsurf/mcp.json` |

**Convergence point:** AGENTS.md is now the lowest-common-denominator cross-tool format. As of 2026, Windsurf (post-Cognition acquisition), Claude Code, Codex, and Cursor all read AGENTS.md at the repo root. A canonical `AGENTS.md` or `CLAUDE.md` in the shared repo, with Ruler or Packmind generating tool-specific derived files, is the recommended cross-tool approach.

**Key incompatibilities to account for:**
- Cursor Team Rules have no API/CLI, they must be set via dashboard. This is the biggest gap for automation.
- Windsurf global rules have a 6,000-character hard limit; Claude Code has none.
- Hook format (PreToolUse/PostToolUse) is Claude Code-specific; Cursor hooks differ; Windsurf has Workflows (separate from Rules).
- Skills directory names differ per tool (`.claude/skills/` vs `.cursor/skills/` vs `.windsurf/skills/`), but Ruler handles this translation.

---

## Lessons from High-Performing Teams

**Spotify / Backstage:** The Golden Path concept, an "opinionated and supported" path for building a service, is their primary knowledge-sharing mechanism. Crucially, the Golden Path tutorial is the most-read documentation at Spotify and is a key onboarding artifact for every new engineer. The lesson: pick one blessed path per discipline (backend, frontend, data), make it the default, document it step-by-step, and treat maintaining it as load-bearing work. Source: https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem

**Airbnb / Knowledge Repository:** Airbnb open-sourced a git-backed knowledge sharing platform in 2016 (github.com/airbnb/knowledge-repo) to solve the "scattered presentations, emails, and Google Docs" problem. The model: knowledge posts (Jupyter notebooks, R Markdown) are peer-reviewed via git pull requests, versioned, and surfaced through a web app. The lesson: treat knowledge artifacts as code, with PR review, ownership, version control, and a searchable index. Source: github.com/airbnb/knowledge-repo

**Google / eng-practices:** Google's public engineering practices (github.com/google/eng-practices, CC-By 3.0) are a curated distillation of internal standards developed over years of production engineering. The key insight: the primary purpose of code review is to make sure overall code health is improving over time. The repo uses a small contributor set, PR review, and a focused scope (code review process). Lesson: keep the scope narrow, quality high, and the review process visible. Source: https://github.com/google/eng-practices

**Microsoft / code-with-engineering-playbook:** microsoft/code-with-engineering-playbook (github.com/microsoft/code-with-engineering-playbook) was built by the Commercial Software Engineering org over six years across hundreds of real production engagements. It is not Microsoft's internal process, it is an amalgamation of working with hundreds of companies. The structure is sprint-cycle-aligned (pre-sprint, sprint structure, fundamentals). Contribution via pull requests, openly maintained by engineers directly. Lesson: anchor the playbook to real engineering workflows (sprints, code review, CI), not abstract principles. Source: https://github.com/microsoft/code-with-engineering-playbook

**Stripe:** Stripe's knowledge sharing infrastructure is custom-built and deeply integrated with workflow tools. Key assets: Trailhead (internal product/documentation system modeled on Stripe's external docs), Compass (internal project management with Slack integration and standup automation), and a dedicated Developer Productivity team that grew to ~12 engineers and focused specifically on reliability of developer tooling. Lesson: invest in dedicated tooling ownership, not just documentation. Source: https://newsletter.pragmaticengineer.com/p/stripe-part-2

**Shopify:** Shopify standardized on one tool per discipline (MySQL, not multiple databases; Figma, not multiple design tools; Cursor, not multiple AI editors) and invested in a custom bootstrapper (`Dev up`) for developer onboarding. They run internal surveys to measure DX satisfaction and use the results to prioritize the Developer Acceleration organization's roadmap. Lesson: standardize aggressively; measure DX; make onboarding a first-class product. Source: https://getdx.com/blog/shopify-developer-experience-survey

---

## Governance and Contribution Patterns

**Quality bar patterns from successful repos:**
- Google eng-practices: small focused scope, CC-By license encouraging sharing, PR review, slow-moving by design.
- Microsoft playbook: CODEOWNERS equivalent (ISE org), PR-based contributions, focused checklist as the entry point.
- mattpocock/skills: effectively single-maintainer quality bar; community forks but upstream is curated.

**Versioning:** No de facto standard exists yet for skill versioning. The most pragmatic approach is semantic versioning in SKILL.md frontmatter (`version: 1.2.0`) with a CHANGELOG per skill. Ruler supports this pattern. Packmind versions the entire playbook via Git.

**Decay prevention:**
- Tessl's approach: pair every rule/spec with a test that asserts agent behavior; run tests in CI. Decay shows up as test failures, not as stale docs.
- Packmind's approach: a linter that detects drift between stated rules and what agents are actually doing; periodic revalidation.
- Spotify's approach: treat golden path docs as load-bearing; if you only have time to update one thing, update the golden path tutorial.
- Practical minimum: add a `last_reviewed` date in frontmatter; add a CI check that warns when skills haven't been reviewed in N days.

**Discovery (how new teammates find the right skill):**
- mattpocock/skills: natural language description matching, Claude finds the skill from conversational context.
- Cursor Team Rules: dashboard listing for enterprise.
- Backstage: TechDocs plugin with full-text search and browse-by-discipline.
- Pragmatic minimum: a root-level SKILLS_INDEX.md with one-line descriptions per skill, generated by CI.

**Contribution model options:**
1. Open PR: anyone can contribute, Rehan + the AI Backend collaborator review. Low friction, moderate quality.
2. Team lead review gate: only Rehan reviews skill additions. High quality, bottlenecked.
3. Draft + pilot: skills start in `drafts/` and must survive 2-week usage before promotion to `stable/`. Used in practice by several teams.
4. Ownership labels: each skill has an `owner:` in frontmatter; only the owner can merge changes to their skill.

---

## Distribution Mechanics Per Tool

| Tool | Idiomatic distribution | Notes |
|---|---|---|
| Claude Code | Symlinks or copies from shared repo to `~/.claude/skills/` and `~/.claude/CLAUDE.md` | Existing team pattern (symlinks from `~/.agents/skills/` to `~/.claude/skills/`); works well |
| Codex | Symlinks or copies to `~/.codex/skills/` and `~/.codex/AGENTS.md` | Same symlink pattern; Codex reads AGENTS.md from project and `~/.codex/` |
| Cursor | Project rules in `.cursor/rules/*.mdc` committed to the shared repo | Cursor reads these automatically; Team Rules require dashboard (no API) |
| Windsurf | Workspace rules in `.windsurf/rules/*.md` committed to shared repo; global rules manually synced | AGENTS.md at repo root is also consumed automatically; global rules require per-machine setup |
| All tools | **Ruler CLI** (`ruler apply`) generates all tool-specific files from `.ruler/*.md` source | Best cross-tool option; supports 20+ agents including all four; handles MCP config distribution too |
| All tools | **Packmind** (OSS or SaaS) generates per-agent files from one playbook | Better governance layer; `packmind-cli init` extracts patterns from existing codebase |
| Hard links | Node script or VS Code extension creating hard links from one canonical file | Simple and tool-agnostic; breaks on some filesystems; lacks CI integration |

**Recommended distribution stack for team:**
1. Canonical source: Git repo (`~/.agents/skills/` extended with an `team-skills` subdirectory, or a dedicated `team-agents` repo)
2. Per-agent materialization: Ruler CLI runs in CI/setup scripts to generate `.cursor/rules/`, `.windsurf/rules/`, `AGENTS.md`
3. Claude Code + Codex: symlinks (existing pattern) remain for fast local iteration
4. Cursor Team Rules: manual sync from generated `.cursor/rules/` to dashboard (accept the automation gap)

---

## Gaps and Opportunities for a Team-Specific Version

1. **No shared corpus yet.** The existing setup (symlinked skills in `~/.agents/skills/`) is Rehan-personal, not team-shared. The key gap is: the AI Backend collaborator, the architect, the TM lead, and the AI Backend collaborator have no access to these skills and no path to contribute.

2. **Windsurf-first team.** Most of the team uses Windsurf today. The existing Claude Code skill structure is invisible to them. A team-shared system needs to prioritize Windsurf as the primary consumption target, not an afterthought.

3. **Domain-specific skills are the highest-value differentiator.** Generic skills (TDD, grill-me, handoff) are already available from mattpocock. What team needs is skills that encode team-specific patterns: the MCP-first boundary rule, the MATCH ticket grounding checklist, the first-principles contract workflow, the integration test runbook, the team API spec access patterns, the approval/HITL flow. These are not available anywhere else.

4. **MCP config distribution is unsolved.** team has a non-trivial MCP setup (code-review-graph, Atlassian, Slack, error-tracking, etc.). Ruler can distribute `mcp.json` alongside rules, this is a significant win for team onboarding that no current tool provides well.

5. **Cursor Team Rules API gap.** Cursor has no API for Team Rules. For an enterprise enforcement layer (e.g., ensuring every Cursor user has the "never push to develop" rule), this is a manual process. Packmind's enterprise linter is the closest automation.

6. **Skills decay tracking.** No current tool enforces a review cadence. An team-specific CI check flagging skills with `last_reviewed` older than 90 days is low-effort but high-signal.

7. **Context-appropriate activation.** The team codebase has two repos (AI Backend, MCP) with different rules. A monorepo-aware skill system (Ruler's nested rule loading) that applies backend-specific skills only when you're editing AI Backend files, and MCP-specific skills only when in `team_mcp/`, is the right architecture.

---

## Recommended Starting Structure

Start with a dedicated `team-agents` private VCS repo that becomes the single source of truth. Structure it in three layers: (1) a `global/` directory with AGENTS.md, CLAUDE.md, and hook configs that apply everywhere, covering commit conventions, branch protection, linting rules, MCP-first boundary, and Jira label policy; (2) a `skills/` directory with one subdirectory per skill, each containing a `SKILL.md` with frontmatter (name, description, version, owner, last_reviewed, tags), an optional `scripts/` directory for companion automation, and an optional `references/` directory for linked docs, skills should cover both team-specific workflows (match-ticket-grounding, api-contract-first, mcp-boundary-check) and team-process workflows (post-iter-review, integration-test-runbook, pr-description-generator); (3) a `profiles/` directory with per-role configurations (backend-dev, frontend-dev, qa) that select and activate different skill subsets. Add a `Makefile` with `make install` (runs Ruler to materialize per-tool configs and creates symlinks to `~/.claude/skills/`, `~/.codex/skills/`) and `make check` (lints skills for frontmatter completeness, warns on stale last_reviewed dates). Onboard the team in one session per person: run `make install`, walk through the three core skills that apply to everyone, and book a 30-minute "skills contribution" session after the first month to capture tacit knowledge that recurred in that period.
