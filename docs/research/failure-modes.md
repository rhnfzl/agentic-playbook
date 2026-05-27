# Failure Modes

Documented failure modes for team-shared coding-agent rule libraries, with primary sources. Each failure mode in this catalog is one we have actively designed against in the playbook.

The point: if you skip a design decision in the playbook, this is the failure mode you accept.

## #1, Global rules degrade agent performance

**Source:** Stripe Minions writeup (ByteByteGo, 2026). "How Stripe's Minions ship 1300 PRs."

**The failure:** A team writes a comprehensive rules file. The rules are loaded at every agent request. Context window fills up before the agent starts work. Performance degrades silently. Developers learn to ignore rule violations as "normal."

**Why it happens:** Rules feel cheap to add but are expensive at the per-request level. A 300-line CLAUDE.md eats 4-6k tokens of every conversation's context, even when only 3 of those 300 lines are relevant to the current task.

**How we prevent it:**
- Per-subproject AGENTS.md (ADR 0002): each subproject sees only its own rules.
- Workspace-level rules stay minimal.
- Rules vs. skills separation (ADR 0007): skills are invoked by name, not loaded ambient.

**What you accept if you skip this:** Slower, less attentive agent responses. The cost is invisible: there is no error, just steadily degrading quality.

## #2, Monolithic CLAUDE.md or AGENTS.md hurt performance

**Source:** ETH Zurich study, 2025 (cited in termdock.com).

**The failure:** A team writes a "comprehensive" 300+ line CLAUDE.md combining coding standards, architecture docs, workflow instructions, and style guides. Agent performance is measurably worse than with a 50-line focused file. Agents follow some instructions, ignore others.

**Why it happens:** Longer files are not better files. After a certain length, agent attention degrades. The "I'll add one more rule" instinct accumulates into context bloat.

**How we prevent it:**
- One rule per file in `rules/`. The installer concatenates only selected rules.
- Profiles select rule subsets per role.
- `make check` could be extended to warn when the generated AGENTS.md exceeds a threshold.

**What you accept if you skip this:** Inconsistent rule adherence. Agents follow some rules, miss others, with no visibility into why.

## #3, LLM-generated context files backfire

**Source:** ETH Zurich study, 2025.

**The failure:** A team asks Claude to "generate our CLAUDE.md from the codebase." The output is verbose, generic, and restates information the agent can already see. Agent performance is worse than with a hand-written file.

**Why it happens:** LLM-generated rules tend to be exhaustive (low signal-to-noise) and generic (no team-specific judgment). Hand-written rules reflect actual observed failures and team-specific conventions.

**How we prevent it:**
- Rules are extracted from feedback memories (real observed failures), not auto-generated.
- The `extract-rules-from-codebase` prompt asks the agent to surface candidates from memory + commit history, not to invent rules.

**What you accept if you skip this:** A bloated, generic ruleset that the team will ignore because none of it feels like THEIR conventions.

## #4, Rules without model-tier awareness

**Source:** Cursor community forum, December 2025 (8-engineer team thread).

**The failure:** Rules work with Claude Sonnet/Opus or GPT-5 reasoning models. They are silently ignored by cheaper "Auto" mode or smaller models. A team where developers use different model tiers gets inconsistent rule adherence with no visibility into why.

**Why it happens:** Rule attention is a function of model capability. Smaller/cheaper models do not surface "I noticed the rule but chose to ignore it"; they just skip it.

**How we prevent it:**
- Document this limitation in per-agent docs (`docs/tools/cursor.md`).
- Cannot fully prevent. Recommendation: enforce a minimum model tier org-wide where possible.
- Cursor Enterprise has model controls; consider adopting if the team grows past 5 Cursor users.

**What you accept if you skip this:** Inconsistent rule adherence across the team, correlated with developer-chosen model tier.

## #5, One-size-fits-all org rules

**Source:** Packmind research, January 2026 ("Error #3"). Cited: 48% of companies run 2+ AI coding tools in parallel.

**The failure:** A single AGENTS.md for a frontend React team and a backend Go microservices team is either too generic (ignored as useless) or too specific to one team (actively wrong for the other). Both teams end up worse off than with no shared rules at all.

**Why it happens:** Teams have different vocabularies, different priorities, different conventions. Forcing a shared rules file across heterogeneous teams forces compromises that satisfy nobody.

**How we prevent it:**
- Per-subproject AGENTS.md (ADR 0002).
- Profiles per role (backend-developer, frontend-developer, qa, tech-lead).
- Workspace-level rules stay TRULY universal (no em dashes, VCS-not-GitHub, label policy).

**What you accept if you skip this:** Both teams ignore the rules. The shared file becomes dead weight.

## #6, Rules without validation / decay prevention

**Source:** Packmind drift-detection research, January 2026.

**The failure:** Rules are written once and forgotten. Four drift symptoms compound silently over months:

1. **Pattern violation**, agents suggest deprecated APIs the rules no longer reflect.
2. **Architectural drift**, locally coherent decisions become globally inconsistent.
3. **Staleness**, instructions no longer match the actual codebase.
4. **Inter-agent inconsistency**, different tools (Claude vs Cursor) produce conflicting code because their rules diverged.

**Why it happens:** Without a review cadence, rules decay invisibly. Nobody notices until production breaks because of a rule that should have been updated months ago.

**How we prevent it:**
- `last_reviewed:` frontmatter required.
- `make check` warns at 90 days, blocks at 180 days.
- Owners are responsible for refreshing the date.

**What you accept if you skip this:** Slow rot. Six months in, rules are still being applied but they no longer match the codebase. Agent output gets worse but it's hard to attribute to the rules.

## #7, Cursor Team Rules dashboard has no API

**Source:** Cursor community forum, 2026.

**The failure:** A team adopts Cursor Enterprise expecting to manage shared rules programmatically. They discover Team Rules are dashboard-managed only. Changes don't propagate via git. Project-level `.cursor/rules/*.mdc` and dashboard Team Rules can diverge silently.

**Why it happens:** Cursor's Team Rules feature is dashboard-first by design. The dashboard provides RBAC and audit logs that an API would complicate.

**How we prevent it:**
- We do not rely on Cursor Team Rules dashboard.
- Project-level `.cursor/rules/*.mdc` is what our installer materializes (committed to the project repo).
- Document this limitation in `docs/tools/cursor.md`.

**What you accept if you skip this:** Two systems of rules (committed vs dashboard) that diverge. Confusion about which is canonical.

## #8, Rules not following tool upgrades

**Source:** Cursor community forum, December 2025.

**The failure:** Rule syntax that works in one version of Cursor (or Windsurf, or any agent) breaks silently in the next. Rules written against `.cursorrules` (deprecated) vs `.cursor/rules/*.mdc` (current) show this lifecycle problem.

**Why it happens:** Each agent's config format evolves. Teams that do not own their rule format proactively fall behind tool upgrades.

**How we prevent it:**
- The playbook's canonical source format (SKILL.md + rules/*.md) is independent of per-agent config formats.
- Per-agent adapters translate from canonical to native. When an agent upgrades its format, only one adapter file changes.

**What you accept if you skip this:** Each agent upgrade is a fire-drill: which rules still work? Which silently broke?

## #9, Team coordination problems amplified by AI tools

**Source:** LinkedIn post citing a real team failure (ShriKant Vashishtha, 2026).

**The failure:** A team gets AI coding tools for every developer. Leadership is excited. Sprint 1 ends. Not a single story is done.

**Why it happens:** The team had pre-existing coordination problems (siloed developers, testing as a separate downstream activity). AI tools amplify the existing dysfunction, they do not fix it.

**How we prevent it:**
- Rules and skills do not fix team process debt.
- The playbook helps a coordinated team move faster. It does not turn a disorganized team into a coordinated one.
- Onboarding (the `onboard-a-new-teammate` prompt) explicitly emphasizes team conventions, not just tooling.

**What you accept if you skip this:** Tools accelerate dysfunction. AI agents make broken process worse, faster.

## #10, Format fragmentation despite AGENTS.md convergence

**Source:** Direct observation, 2026 (cross-tool format matrix in research v2 brief).

**The failure:** Even with ~28 tools reading AGENTS.md natively, tool-specific features still vary: Cursor's MDC frontmatter (description, globs, alwaysApply), Windsurf's 6,000-char global rules limit, GitHub Copilot's `.github/copilot-instructions.md` alongside AGENTS.md, Kiro's inclusion modes (always/conditional/manual).

**Why it happens:** AGENTS.md is the lowest common denominator. Each agent layers tool-specific features on top.

**How we prevent it:**
- Per-agent adapters handle tool-specific features (Tier 1 + Tier 2).
- Tier 3 (AGENTS.md only) accepts a degraded experience for the long-tail of less-used agents.

**What you accept if you skip this:** Either you write everything in lowest-common-denominator markdown (losing native features) or you maintain per-agent files manually (drift between them).

## Summary

A team-shared coding-agents-playbook that ignores all 10 failure modes:

- Degrades performance (1, 2)
- Becomes generic and ignored (3)
- Has inconsistent adherence (4, 5)
- Decays silently (6)
- Diverges between systems (7, 10)
- Breaks on tool upgrades (8)
- Amplifies team dysfunction (9)

Each of the 7 ADRs in `docs/adr/` is a deliberate defense against one or more of these failure modes.
