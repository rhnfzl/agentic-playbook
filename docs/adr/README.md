# ADRs

**ADR stands for Architecture Decision Record.** Short documents that capture a single architectural decision plus the context that made it necessary and the consequences (good, bad, and open risks). ADRs are numbered sequentially (`ADR-0001`, `ADR-0002`, ...) and kept in the repo so future contributors can see why the architecture looks the way it does, not just what it is.

Each file in this directory follows the format `NNNN-kebab-case-slug.md` and ships four sections:

- **Status** -- Accepted / Superseded / Deprecated, plus the date.
- **Context** -- the problem the decision is solving.
- **Decision** -- what we decided.
- **Consequences** -- what is now better, what is worse, what risks are open.

## When to write one

- A choice is **hard to reverse** (rewriting the lockfile format, choosing an installer pattern, picking a hook canonical-source rule).
- A choice would be **surprising without context** (a future reader asks "why this?" and the reason is non-obvious from the code).
- A choice is **the result of a real trade-off** (there were genuine alternatives and we picked one for specific reasons).

If any of the three is missing, skip the ADR. Use a code comment or a PR description instead.

## When to NOT write one

- The decision is fully captured by the code's shape and well-named identifiers.
- The decision is reversible at any time without coordination (e.g. a one-off helper function name).
- The decision is short-term scaffolding that will go away in a few weeks.

## Numbering

ADRs are append-only. To add a new one: look at the highest-numbered file in this directory, add 1, and use that as your number. Never reuse a number, never renumber.

## Superseding

When a later ADR replaces an earlier one, set the earlier ADR's status to `Superseded by ADR-NNNN` and add a one-paragraph note pointing forward. The earlier ADR stays in the repo for the historical record.

## Index

The ADR list below is hand-maintained for now; future automation may generate it. See each file for its full status.

- ADR-0001 SKILL.md canonical (skill content type lives in `skills/<cat>/<name>/SKILL.md`).
- ADR-0007 Three buckets: rules / skills / hooks.
- ADR-0010 Commands and prompts as 5th and 6th content types.
- ADR-0024 Adapter Protocol + Install Manifest.
- ADR-0027 AGENTS.md document type + hook event metadata.
- ADR-0029 Hook reconciliation + matcher header.
- ADR-0030 Tier-3 declarative TOML registry.
- ADR-0031 Four-file loader split (`_protocol`, `_reader`, `_writer`, `_detect`).
- ADR-0034 Cross-agent hook contract.
- ADR-0035 Canonical hook source unification (skill-owned vs root).
- ADR-0036 Three-layer content contract (canonical / materialization / runtime).
