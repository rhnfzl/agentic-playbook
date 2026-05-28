# imported/impeccable/

Single vendored skill bundle providing an "impeccable" execution discipline: when invoked, the agent commits to a higher rigor bar (assumption tracking, explicit confound naming, no shortcuts, full verification) for the rest of the session.

## What ships here

This directory is one skill, not a collection. The bundled files are:

- `SKILL.md`: the skill itself.
- `PROVENANCE.md`: upstream attribution.
- `agents/`: helper subagent definitions the skill spawns.
- `reference/`: reference material the skill body links to.
- `scripts/`: helper scripts the skill invokes.

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md) for the upstream URL, license, and pin SHA.

This skill is **vendored** (per ADR-0014 + ADR-0018): the playbook copies the bundle locally.

## When to consume

- When a session involves a high-stakes deliverable (a public release, an external commitment, a security-sensitive change) and the default rigor isn't enough.
- When the agent has been cutting corners and you want a structural reset to "no shortcuts."

## When to NOT consume

- Routine work. The impeccable discipline is heavy; using it everywhere dulls its signal.
- Time-boxed exploration. Impeccable favors verification over speed; if you're spiking, use a lighter skill.

## Related

- [`PROVENANCE.md`](PROVENANCE.md) for upstream attribution.
- `base/skills/meta/zoom-out/` (sibling pattern: step back when stuck).
- `base/skills/productivity/grill-me/` (sibling pattern: interview-style rigor).
