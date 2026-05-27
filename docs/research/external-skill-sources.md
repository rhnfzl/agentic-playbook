# External Skill Sources Catalog

Owner: Rehan
last_reviewed: 2026-05-25

This catalog tracks every external source the playbook references, vendors, or has evaluated. Each entry follows the schema in ADR-0014:

- **source**: upstream repo / package URL
- **pin**: commit SHA, tag, or release reviewed at vendor time
- **license**: legal reuse signal
- **skills**: specific skills approved or referenced (or "all" if the whole repo)
- **status**: `recommended` / `refer-only` / `audit-needed` / `rejected`
- **risk_class**: `docs-only` / `scripts` / `network` / `credentials`
- **reviewer**: human owner for the approval
- **last_reviewed**: review freshness (YYYY-MM-DD)
- **notes**: when to use and when not to use

Status definitions:

- `recommended`: vendored into the playbook, audit clean, ready for teammate use
- `refer-only`: catalog reference; do not vendor (legal or strategic reason captured in notes)
- `audit-needed`: candidate for vendoring once audit + review complete
- `rejected`: evaluated and not adopted, with reason captured

## Vendored sources (status: recommended)

### mattpocock/skills

- **source**: https://github.com/mattpocock/skills
- **pin**: `b8be62ffacb0118fa3eaa29a0923c87c8c11985c` (matches skills/imported/mattpocock/PROVENANCE.md)
- **license**: MIT
- **skills**: all (engineering/, productivity/, misc/ subtrees)
- **status**: recommended
- **risk_class**: docs-only (skills/, no scripts that touch credentials or network)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Foundational mattpocock skill library, format-aligned with playbook. Vendored as snapshot. Sync via `make sync-mattpocock` (monthly). Catalog status: recommended for all teams.

### jamiemill/layers-skills

- **source**: https://github.com/jamiemill/layers-skills
- **pin**: `0e5d49b5840a542fd59c0a64f4ba0013c30160fe` (matches skills/imported/<source>/PROVENANCE.md)
- **license**: MIT
- **skills**: all
- **status**: recommended
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Seven-layer product design model. Use BEFORE implementation, especially for onboarding / search / matching / recruiter flow design. Companion to Impeccable.

### pbakaus/impeccable

- **source**: https://github.com/pbakaus/impeccable
- **pin**: `84135db0e6bdd58d22828f7bc8331cae7bde3e7f` (matches skills/imported/<source>/PROVENANCE.md)
- **license**: Apache 2.0
- **skills**: all
- **status**: recommended
- **risk_class**: network (scripts/live-server.mjs runs a local HTTP server for live-mode preview; scripts/live-* use fetch + http.createServer)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Design vocabulary for AI harnesses (audit / critique / polish / animation / hardening / performance / design-system extraction / live-mode). Use AFTER an interface exists.

### Leonxlnx/taste-skill

- **source**: https://github.com/Leonxlnx/taste-skill
- **pin**: `c8075169cd63d1430bbf492dd4ddd478ea9fa4da` (matches skills/imported/<source>/PROVENANCE.md)
- **license**: MIT
- **skills**: all
- **status**: recommended
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Layout, typography, motion, spacing, reference-board generation. Intentionally opinionated; pair with team SaaS dashboard constraints (restrained operational interface, not flashy).

### anchored-fs (now upstream-in-playbook)

- **source**: mcp/anchored-fs/ (playbook is the canonical upstream per ADR-0018)
- **pin**: n/a (canonical here)
- **license**: MIT (added at vendor time)
- **skills**: n/a (this is an MCP server, not a skill)
- **status**: recommended
- **risk_class**: scripts (FastMCP server with file-system write)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Globally-installed MCP filesystem server with `prefix[upto]suffix` anchored-edit support. Future development goes through playbook PRs. Users with an existing real-dir install at `~/.config/agent-shared/mcp_servers/anchored-fs/` rename to `.bak` before re-running `make install`.

## Refer-only sources (status: refer-only)

### anthropics/skills (frontend-design)

- **source**: https://github.com/anthropics/skills/tree/main/skills/frontend-design
- **license**: Apache 2.0 (LICENSE.txt in skill dir)
- **status**: refer-only
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Originally targeted for v0.3 vendoring, then dropped after evaluation. The skill is prose-only design-aesthetic guidance ("be bold, pick distinctive fonts, use motion, avoid generic AI slop"). The team frontend lane is better served by MCP-connected approaches (chrome-devtools-mcp for live preview, design-system MCPs, v0 MCP), and the design framing is already covered by Layers + Impeccable + Taste Skill. Catalog entry kept so the reasoning is recoverable.

### gnurio/refactoring-ui-plugin

- **source**: https://github.com/gnurio/refactoring-ui-plugin
- **license**: all rights reserved (no explicit OSS license)
- **status**: refer-only
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Useful review checklist shape (10 Refactoring UI principles), but the license text says all rights reserved. Cannot legally redistribute without explicit permission. Teammates may READ upstream for inspiration; do not copy any code or skill text into our repo.

### vercel-labs/agent-skills web-design-guidelines

- **source**: https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines
- **license**: presumed MIT (verify on each visit)
- **status**: refer-only
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Complements Impeccable as a rules-based review pass. Deferred from v0.3 vendoring; reconsider for v0.4 after Impeccable use proves the gap.

### alexgreensh/token-optimizer

- **source**: https://github.com/alexgreensh/token-optimizer
- **license**: PolyForm Noncommercial
- **status**: refer-only
- **risk_class**: scripts (smart compaction, lifecycle hooks)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: team is commercial; PolyForm Noncommercial license forbids vendoring or production use. Overlaps with RTK (`rtk-ai/rtk`) which is already in use. Read upstream for ideas; do not vendor.

### rtk-ai/rtk (RTK, Rust Token Killer)

- **source**: https://github.com/rtk-ai/rtk
- **license**: Apache 2.0
- **status**: refer-only (CLI tool, listed in TOOLS.md, not a skill source)
- **risk_class**: scripts (CLI proxy + Claude Code hook auto-rewrites)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Canonical RTK home. Installs via `brew install rtk`. The `reachingforthejack/tap/rtk` formula is a different tool (Rust Type Kit) and should not be confused with this one. RTK proxies dev CLI commands (git/find/grep/etc.) to reduce token cost 60-90% in agent sessions. Used company-wide; entry here documents the upstream pin + license rather than vendoring code.

### nickwinder/synthteam

- **source**: https://github.com/nickwinder/synthteam
- **license**: no LICENSE file
- **status**: refer-only
- **risk_class**: scripts (Slack persona ingestion, multi-agent panel deliberation)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Novel persona-distillation pattern (3 skills: distill-slack-persona, ask-colleague, ask-team). No LICENSE means no redistribution right. If upstream relicenses MIT/Apache, revisit for v0.4.

### multica-ai/andrej-karpathy-skills

- **source**: https://github.com/multica-ai/andrej-karpathy-skills
- **license**: no LICENSE file
- **status**: refer-only
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Karpathy-inspired CLAUDE.md guidelines (4 principles addressing LLM coding pitfalls). Worth referencing as inspiration for our writing-style rule. No LICENSE means no redistribution.

### microsoft/AI-Engineering-Coach

- **source**: https://github.com/microsoft/AI-Engineering-Coach
- **license**: MIT
- **status**: refer-only (catalogued in TOOLS.md, not skills/imported/)
- **risk_class**: scripts (VS Code extension reading local AI session logs)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: VS Code extension that reads local AI session logs and renders insights. Observability tool, not a skill source. Listed in TOOLS.md for teammates who want a usage dashboard.

### steipete/agent-scripts

- **source**: https://github.com/steipete/agent-scripts
- **license**: MIT
- **status**: refer-only (benchmark, patterns absorbed)
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Comparable shared agent operating system: shared AGENTS.MD, skills, scripts, hooks, global symlink setup, validation, CHANGELOG, RELEASING. Used as a structural benchmark; the playbook absorbs `validate-skills`, `tools.md`, `CHANGELOG.md`, and `RELEASING.md` patterns. Do not vendor whole.

### microsoft/apm

- **source**: https://github.com/microsoft/apm
- **license**: MIT
- **status**: refer-only (concepts borrowed)
- **risk_class**: scripts (manifest + lockfile + drift)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Best observed model for agent package manifests, lockfiles, policy, audit, source hashes, drift management. Playbook borrows lockfile + drift + status concepts without adopting the full APM schema. Cross-tool interop deferred (per ADR-0014, optional Phase 5).

### microsoft/azure-skills

- **source**: https://github.com/microsoft/azure-skills
- **license**: MIT
- **status**: refer-only (conditional)
- **risk_class**: scripts (Azure CLI / SDK)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Azure-focused skills. Relevant only if team picks up Azure workflows as a common agent surface. Currently no production use.

### supabase/agent-skills

- **source**: https://github.com/supabase/agent-skills
- **license**: MIT
- **status**: refer-only (conditional)
- **risk_class**: scripts (database access)
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Focused Postgres / Supabase guidance. Relevant only when the target project actually uses Supabase or compatible Postgres workflows.

### github/awesome-copilot

- **source**: https://github.com/github/awesome-copilot
- **license**: per upstream README
- **status**: refer-only (catalog source)
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Catalog of Copilot instructions, prompts, custom agents. Reference for Tier 2 / Tier 3 adapter research; not a direct installer target.

### intellectronica/ruler

- **source**: https://github.com/intellectronica/ruler
- **license**: per upstream
- **status**: refer-only (adapter reference)
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Multi-agent rule distributor. Used to compare adapter paths and target shapes. ADR-0003 records the decision to own the playbook installer rather than depend on Ruler.

### agentsmd/agents.md

- **source**: https://github.com/agentsmd/agents.md
- **license**: MIT
- **status**: refer-only (align and contribute)
- **risk_class**: docs-only
- **reviewer**: Rehan
- **last_reviewed**: 2026-05-25
- **notes**: Upstream AGENTS.md format project. Playbook aligns the AGENTS.md governance harness (ADR-0013) with this format. Post-v0.3, file PRs upstream with nested-coverage examples, size budgets, and harness check patterns.

## Schema notes

This catalog is the canonical source. Per-skill provenance is also recorded in `skills/imported/<source>/PROVENANCE.md` at vendor time. When refreshing a vendored skill:

1. Update the entry's `last_reviewed` here.
2. Update the `pin` here and in PROVENANCE.md.
3. Re-run the external-skill audit script (`make audit`).

When adding a new external source:

1. Add an entry to the right section.
2. If vendoring: create `skills/imported/<name>/` and run `make audit`.
3. Reference the entry in the relevant ADR (0019 for imports, 0020 for refer-only justifications).
