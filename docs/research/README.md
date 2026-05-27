# Research evidence for the coding-agents-playbook

What the playbook design is grounded in. Each document here is dated and scope-stamped so design decisions remain traceable when the agent landscape shifts.

## How to use this directory

- Read `inspirations.md` first for the inspiration map (mattpocock/skills, Block/Goose, Stripe Minions, Shopify Toolkit, Anthropic skills bundle).
- Then `failure-modes.md` for the catalog of what goes wrong (silent skill drift, agent name explosion, doc rot) and how the playbook's gates address each.
- Then `upcoming-adapters.md` for the Tier 3 expansion candidates and the criteria they need to clear.
- Reach for the dated `research-brief-*.md` files when you need source attribution for a design decision; they are the depth-research that informed `inspirations.md`.

## Index

| Document | Purpose | When to consult |
|---|---|---|
| `inspirations.md` | Map of patterns the playbook borrowed, with attribution. Stays evergreen as new sources surface. | Always: it is the canonical "what is this design based on" doc. |
| `failure-modes.md` | Catalog of agentic-coding failure modes and the playbook gate that addresses each. | When proposing a new gate or skill, to confirm it addresses a real failure mode rather than a hypothetical one. |
| `upcoming-adapters.md` | Tier 3 expansion list and promotion criteria (Tier 2 / Tier 1). | When weighing whether to add a new adapter or promote an existing one. |
| `cursor-team-rules-limitation.md` | Why the Cursor Team Rules dashboard cannot be a distribution surface (no API as of May 2026). | When someone asks "why don't we just push rules through the Cursor dashboard." |
| `2026-05-24-research-brief-v1.md` | Initial deep-read of `mattpocock/skills` (the foundational inspiration corpus). | When tracing the origin of an early design decision; archived but not deleted. |
| `2026-05-24-research-brief-v2.md` | Extends v1 with company-scale evidence (Shopify, Stripe, Block, Anthropic) and the broader agent landscape beyond Claude / Codex / Cursor / Windsurf. | When designing a Tier 2 or Tier 3 expansion; when justifying a "team-shared rules" design choice against published precedent. |

## Editing policy

- Dated briefs (`YYYY-MM-DD-*.md`) are append-only artifacts of a specific research session. Do not edit them in place; supersede with a new dated brief and link back if findings change.
- Undated docs (`inspirations.md`, `failure-modes.md`, `upcoming-adapters.md`) are living; update them when new evidence or patterns surface, with a Source row added at the bottom.

## Where research becomes design

- Patterns from `inspirations.md` land in `docs/adr/*.md` as Architecture Decision Records.
- Failure modes from `failure-modes.md` land in `scripts/check_em_dashes.py`, `scripts/decay_check.py`, `scripts/frontmatter_lint.py` as enforced gates.
- Adapter candidates from `upcoming-adapters.md` land in `scripts/install.py` under their tier when promoted.
