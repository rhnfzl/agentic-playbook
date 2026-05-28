# imported/layers/

Vendored from [jamiemill/layers-skills](https://github.com/jamiemill/layers-skills) (MIT). A 9-skill set that gives a coding agent a structured "thinking layers" model: orient, intro, surface, observed-behaviour, interaction-flow, user-needs, conceptual-model, domain, product-strategy.

## What ships here

| Skill | What it does (per upstream) |
|---|---|
| `layers-orient/` | Orient yourself in a problem before diving into one layer. |
| `layers-intro/` | Introduce the layers framework to the agent for the rest of the session. |
| `layers-surface/` | Reason at the surface layer (what the user sees / interacts with). |
| `layers-observed-behaviour/` | Reason at the observed-behaviour layer (what the user actually does). |
| `layers-interaction-flow/` | Reason at the interaction-flow layer (the sequence of interactions). |
| `layers-user-needs/` | Reason at the user-needs layer (the goal behind the interactions). |
| `layers-conceptual-model/` | Reason at the conceptual-model layer (the user's mental model). |
| `layers-domain/` | Reason at the domain layer (the underlying domain concepts). |
| `layers-product-strategy/` | Reason at the product-strategy layer (where the product is heading). |

Each layer skill is invoked when the agent (or the human via prompt) wants to think specifically at that level rather than collapsing all layers together.

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md) for the upstream URL, license, pin SHA, and `last_reviewed` date.

These skills are **vendored** (per ADR-0014 + ADR-0018): the playbook copies them locally rather than fetching at install time.

## When to consume

- When you're doing PM, design, or UX work where the "what layer am I reasoning at" question matters.
- When a session is at risk of mixing surface-level (UI) and domain-level (data model) reasoning in a way that produces incoherent design proposals.

The `product-manager` and `research` profiles include some of these skills; check the profile TOML for the exact subset.

## When to NOT consume

Engineering-only sessions where the layer abstraction doesn't add value. The layers model shines when the agent is making product or design decisions, not when it's debugging a regression or writing a unit test.

## Related

- [`PROVENANCE.md`](PROVENANCE.md) for upstream attribution.
- [jamiemill/layers-skills](https://github.com/jamiemill/layers-skills) for the upstream README and the layer model's full theory.
- `base/skills/imported/pm-curated/` for the PM execution surface (which composes well with layers).
