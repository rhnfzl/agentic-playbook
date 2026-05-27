# 0006. Open PR contribution model with owner per skill

## Status
Accepted (2026-05-24)

## Context

The playbook is meant to be team-shared. Three contribution models were considered:

1. **Solo curation**: only Rehan merges. Highest quality, lowest buy-in.
2. **Open PR + owner per skill** (chosen): anyone PRs, each artifact has an owner.
3. **Open monorepo, anyone pushes**: maximum velocity, no quality bar.

## Decision

Anyone on the team team can submit a skill, rule, hook, MCP config, or profile via VCS PR. Each artifact has an `owner:` field in frontmatter (defaults to the creator). Owner is responsible for upkeep.

Initial reviewer pool: Rehan, the AI Backend collaborator. As the system grows, domain reviewers (frontend lead for frontend skills, etc.) are added.

A PR needs 1 reviewer approval to merge. Skill changes need approval from the owner OR a reviewer if the owner is unavailable.

## Consequences

- Low friction for contribution (no Slack-and-wait, no Rehan-bottleneck).
- Owner accountability prevents the orphan-skill failure mode (someone adds a skill, moves on, nobody maintains it).
- Decay prevention via `last_reviewed` frontmatter + CI check (`make check` warns at 90d, blocks at 180d) keeps owners engaged.

## Why we did not pick solo curation

The playbook is meant to encode the team's collective knowledge, not just Rehan's. If only Rehan adds skills, frontend / QA / research perspectives never make it in. The repo becomes "Rehan's stuff" instead of "our stuff," and adoption stalls.

## Why we did not pick open monorepo

No quality bar means orphan skills, broken frontmatter, contradictory rules, and decay invisible until someone notices the catalog has rotted. For a small team (10 engineers) the PR overhead is acceptable; for larger scale the model could relax.

## Source

- Microsoft `code-with-engineering-playbook` (PR-based, owner-attribution).
- Airbnb `knowledge-repo` (peer review via git).
- Block/Goose (owner accountability at 5,000-engineer scale).
- See `docs/research/2026-05-24-research-brief-v2.md` ("Governance and Contribution Patterns").

## Open question (revisit at v0.2)

Should reviews require approval from the owner specifically when their skill is being changed? Or is a generalist reviewer's approval enough? Current default: generalist reviewer can approve any change; owner has implicit veto via VCS comment.
