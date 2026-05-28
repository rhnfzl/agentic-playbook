# trajectories/

Cross-adapter trajectory specs for the trajectory harness (ADR-0044).

A trajectory binds one (skill, scenario) pair to:

1. A set of user-prompt phrasings (typically 5, per Anthropic guidance).
2. DSL assertions over the resulting tool-call trace (must-call, must-not-call,
   call_order, artifact-path, total-call bounds).
3. An LLM-judge rubric scored in `[0, 1]` against a per-trajectory threshold.

The harness (`scripts/trajectory_harness.py`, lands in Phase 1) consumes
trajectories and replays them across each adapter listed in
`adapter_scope`. Phase 0 (current) ships the content type, the loader, the
linter, the decay check, the scaffolder, and one canary fixture.

## Layout

```
base/trajectories/
  <skill-name>/
    <scenario>.yaml
  trajectory-canary/
    canary.yaml          # smoke fixture used by the harness self-tests
```

The `<skill-name>` directory must match a skill at
`base/skills/<category>/<skill-name>/SKILL.md`. Each `<scenario>.yaml`
file represents one independently-scored trajectory.

## Adding a trajectory

```bash
make new TRAJECTORY=<skill>:<scenario>
```

This scaffolds `base/trajectories/<skill>/<scenario>.yaml` with the right
frontmatter and TODO markers. Replace the markers, then `make check` to
validate.

## Authoring discipline

- **Five phrasings.** Anthropic's guidance: if a skill doesn't load
  consistently across five paraphrasings of the same intent, the
  description needs work. The linter warns below five.
- **DSL first, LLM judge second.** Put deterministic checks in
  `assertions:`; reserve `llm_judge.rubric:` for intent and quality.
- **Pin the model.** `model_pinned` records the model the reference was
  captured against. When you re-record after a model upgrade, bump this
  field and re-review the diff.
- **60-day decay.** Trajectories rot faster than skills because they're
  model-coupled. Refresh `last_reviewed` whenever you confirm the
  trajectory still passes.

## Related ADRs

- ADR-0044: trajectories as the 8th content type
- ADR-0045: cross-adapter trace contract (Phase 1)
- ADR-0046: hybrid DSL + LLM-judge match semantics (Phase 1)
