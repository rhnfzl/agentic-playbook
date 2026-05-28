# 0043. trajectories/ as 8th content type

## Status
Accepted (2026-05-28)

## Context

ADR-0010 fixed the seven content types (skills, rules, hooks, mcp, agents, commands, prompts). All seven describe what the agent should do. None describe what doing it correctly looks like.

The playbook ships portable skills to four Tier-1 agents (Claude Code, Codex, Cursor, Windsurf). Portability is the central product claim. Until this ADR, the claim was untested in CI. There was no machine-verifiable artifact that asserted "this skill behaves the same in Claude Code as in Cursor," and no automated check that a skill's description loaded consistently across paraphrasings of the same user intent.

Two pieces of external evidence shaped the decision:

- **Anthropic's own guidance** (resources.anthropic.com Complete Guide to Building Skills) recommends "ask 5 different phrasings of the same request, and improve the description if the skill does not load consistently." This is a documented best practice that the playbook did not operationalize.
- **Vercel's eval data** (vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals) measured a 53-to-79 percent pass-rate delta from explicit `AGENTS.md` instructions. The playbook had no equivalent measurement of its own skills.

The DevAI benchmark (Zhuge et al. 2025, "Agent-as-a-Judge: Evaluate Agents with Agents") demonstrated that trajectory-level evaluation matches human reliability on code tasks where final-output evaluation does not. The eval research community is converging on per-step trajectory data as the unit of agent assessment; the playbook needs the artifact that lets it participate.

## Decision

A new top-level content type, `base/trajectories/<skill-name>/<scenario>.yaml`. Each trajectory file declares:

1. An input prompt with five paraphrasings (the operationalization of Anthropic's guidance).
2. A set of DSL assertions over the resulting tool-call trace.
3. An LLM-judge rubric with a numeric threshold.

The schema is validated by `scripts/checks/trajectory.py` (a self-contained check; see ADR-0024 for the sibling pattern). The reader is `scripts/adapters/_reader.py:load_trajectories()` (ADR-0031). The `PlaybookContent` namedtuple gains a `trajectories: list[Trajectory]` field; the dispatcher loads all eight content types once and passes through.

The decay window is 60 days (vs 90 for skills). Trajectories are model-version-coupled (a `model_pinned` frontmatter field records the model the reference was captured against), so they rot faster.

Authors scaffold a new trajectory with `make new TRAJECTORY=<skill>:<scenario>`. The harness (lands in Phase 1, future ADR-0044) consumes trajectories and replays them across each adapter in `adapter_scope`.

## Reject if

Authoring cost outweighs signal, measured by either:

- (trajectories committed / skills shipped) staying below 0.5 for two consecutive releases, OR
- cross-adapter divergences turning out to be uninteresting in practice (the matrix is mostly all-pass or all-fail for non-skill reasons).

Watch for: authors silently dropping trajectories from their PRs, repeated `adapter_scope: [claude-code]` opt-outs, or the trajectory linter accumulating warnings the team stops reading.

## Consequences

- Eight buckets instead of seven; the diagram in `CONTEXT.md` regenerates.
- `scripts/adapters/_reader.py` gains a fifth load method (`load_trajectories`); `_protocol.py` adds the `Trajectory` NamedTuple and extends `PlaybookContent`.
- New `make` targets: `make new TRAJECTORY=<skill>:<scenario>` today; `make record-trajectory`, `make verify-trajectory`, `make trajectory-check` land in Phase 1.
- New decay-check class (60-day window) for trajectories.
- New `make check` gate (`trajectory`) enforces frontmatter and shape rules.
- Authoring discipline grows: a skill change that breaks behavior is caught at trajectory time, not in production.

## Source

- Anthropic. The Complete Guide to Building Skills for Claude. https://resources.anthropic.com/hubfs/The-Complete-Guide-to-Building-Skill-for-Claude.pdf
- Vercel. AGENTS.md outperforms Skills in our agent evals. https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
- Zhuge et al. Agent-as-a-Judge: Evaluate Agents with Agents. https://proceedings.mlr.press/v267/zhuge25a.html
- LangChain. Trajectory evaluations (agentevals). https://docs.langchain.com/langsmith/trajectory-evals
- Internal design doc: `docs/superpowers/specs/2026-05-27-cross-adapter-trajectory-harness-design.md` (gitignored draft)
