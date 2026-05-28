# 0044. trajectories/ as 8th content type

## Status
Accepted (2026-05-28)

## Context

ADR-0010 fixed the seven content types (skills, rules, hooks, mcp, agents, commands, prompts). All seven describe what the agent should do. None describe what doing it correctly looks like.

The playbook ships portable skills to four Tier-1 agents (Claude Code, Codex, Cursor, Windsurf). Portability is the central product claim. Until this ADR, the claim was untested in CI. There was no machine-verifiable artifact that asserted "this skill behaves the same in Claude Code as in Cursor," and no automated check that a skill's description loaded consistently across paraphrasings of the same user intent.

Two pieces of external evidence shaped the decision:

- **Anthropic's own guidance** (resources.anthropic.com Complete Guide to Building Skills) recommends "ask 5 different phrasings of the same request, and improve the description if the skill does not load consistently." This is a documented best practice that the playbook did not operationalize.
- **Vercel's eval data** (vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) measured a 53-to-79 percent pass-rate delta from explicit `AGENTS.md` instructions. The playbook had no equivalent measurement of its own skills.

The DevAI benchmark (Zhuge et al. 2025, "Agent-as-a-Judge: Evaluate Agents with Agents") demonstrated that trajectory-level evaluation matches human reliability on code tasks where final-output evaluation does not. The eval research community is converging on per-step trajectory data as the unit of agent assessment; the playbook needs the artifact that lets it participate.

## Alternatives considered

Two routes were considered before settling on a new content type.

**Extend the existing `evals/` directory (ADR-0017).** Today's `evals/<skill>/cases.yaml` already captures per-case assertions over a skill's body and frontmatter, scored by `scripts/eval_runner.py`. A `evals/<skill>/trajectory.yaml` sibling could carry the cross-adapter contract without adding a new content type. We rejected this because trajectories carry distinct lifecycle concerns: a per-trajectory `adapter_scope` decides where the harness replays, a `model_pinned` field records the reference model, and the artifact is consumed by a cross-process harness rather than the in-process eval runner. Folding both shapes into `evals/` would make the eval runner load-bearing for two different consumers and blur the eval-vs-harness boundary. The seven existing content types each have a single consumer (or class of consumers); preserving that invariant is part of why ADR-0010's seven-bucket model holds up.

**Sibling repo for trajectories.** A separate `agentic-playbook-trajectories` repo would let trajectories evolve at their own cadence and be community-contributable independently of skills. We rejected this because a skill and its trajectory drift together (a skill change that alters tool-call patterns invalidates the reference); keeping them in the same review unit means a single PR validates both. The cost of a sibling repo is a coordination problem we do not have today.

## Decision

A new top-level content type, `base/trajectories/<skill-name>/<scenario>.yaml`. Each trajectory file declares:

1. An input prompt with five paraphrasings (the operationalization of Anthropic's guidance).
2. A set of DSL assertions over the resulting tool-call trace.
3. An LLM-judge rubric with a numeric threshold.

The schema is validated by `scripts/checks/trajectory.py` (a self-contained check; see ADR-0024 for the sibling pattern). The reader is `scripts/adapters/_reader.py:load_trajectories()` (ADR-0031). The `PlaybookContent` namedtuple gains a `trajectories: list[Trajectory]` field (no default; the field is required so a mutable empty-list default cannot leak across instances). The dispatcher loads all eight content types once and passes through.

The decay window for trajectories matches skills (60/90/180 day notice/warn/block) for v0.2. The design intuition is that trajectories rot faster because they're model-version-coupled, but tightening bands before the Phase 1 harness produces actual drift data would generate noise the team is likely to stop reading. Revisit after Phase 1.

Authors scaffold a new trajectory with `make new TRAJECTORY=<skill>:<scenario>`. The harness (lands in Phase 1, future ADR-0045) consumes trajectories and replays them across each adapter in `adapter_scope`.

## Reject if

Authoring cost outweighs signal, measured by quantitative thresholds. The metrics below are deliberately measurable in tooling we either have today or will have after Phase 1; "warnings the team stops reading" was a vibe-test in the draft and is now replaced.

Phase 0 + Phase 1 (measurable today via `make trajectory-coverage-ratio`, see Consequences):

- (trajectories committed / shipped skills) below 0.5 across two consecutive releases.
- More than 50% of trajectories carry `adapter_scope: [claude-code]` only (silent opt-out from cross-adapter testing).

Phase 1+ (measurable once the harness exists):

- Cross-adapter divergence rate (cells where one adapter passes and another fails) below 5% across the full matrix for three consecutive nightly runs. A matrix that only ever surfaces uniform pass or fail is not earning the cross-adapter overhead.
- Trajectory pass-rate noise (same trajectory run twice in 24h producing different verdicts) above 10%. Noise above this floor means the harness is not deterministic enough to gate CI on.

Unwind action if a reject criterion triggers: move trajectories under `evals/` as the alternative considered above, delete `scripts/checks/trajectory.py` and `scripts/new_trajectory.py`, and convert the content-type docs back to seven buckets. A retrospective ADR documents the empirical reason.

## Consequences

- Eight buckets instead of seven; the diagram in `CONTEXT.md` regenerates.
- `scripts/adapters/_reader.py` gains a fifth load method (`load_trajectories`); `_protocol.py` adds the `Trajectory` NamedTuple and extends `PlaybookContent`.
- New `make` targets: `make new TRAJECTORY=<skill>:<scenario>` today; `make record-trajectory`, `make verify-trajectory`, `make trajectory-check` land in Phase 1.
- New decay-check class for trajectories (currently shares skill bands; revisit after Phase 1).
- New `make check` gate (`trajectory`) enforces frontmatter and shape rules: required fields, TODO-placeholder rejection, non-empty `adapter_scope`, non-empty `assertions`, complete `llm_judge` (threshold + rubric + model), and threshold in `[0, 1]`.
- Future work: `make trajectory-coverage-ratio` prints (trajectory count / shipped-skill count) as the release-gate metric named in the reject-if criteria.
- Authoring discipline grows: a skill change that breaks behavior is caught at trajectory time, not in production.

## Source

- Anthropic. The Complete Guide to Building Skills for Claude. https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf
- Vercel. AGENTS.md outperforms Skills in our agent evals. https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
- Zhuge et al. Agent-as-a-Judge: Evaluate Agents with Agents. https://proceedings.mlr.press/v267/zhuge25a.html
- LangChain. Trajectory evaluations (agentevals). https://docs.langchain.com/langsmith/trajectory-evals
- Internal design doc: `docs/superpowers/specs/2026-05-27-cross-adapter-trajectory-harness-design.md` (gitignored draft)
