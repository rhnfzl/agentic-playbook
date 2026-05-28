# Enhancement Backlog (Tavily-driven, 2026-05-28)

This file captures the seven enhancement candidates surfaced during the
recursive Tavily research session on 2026-05-27. Two were picked and
landed; five are unbuilt and queued for future sessions to consider.

Treat this as the durable record of "what we considered, why, what we
chose, what's left." If a later session wants to extend the playbook,
start here rather than re-running the research.

## Methodology recap

The research was two Tavily waves (May 27, 2026):

- **Wave 1** (broad reconnaissance, parallel): Anthropic Skills ecosystem
  trends, competing playbook repos, agent eval frameworks, MCP marketplace
  state, observability stacks.
- **Wave 2** (deep dives): trigger-reliability tooling (via `tavily_research
  --pro`), tool-poisoning + supply chain audit, Agent-as-a-Judge
  implementations, Claude Code OTel emission, obra/superpowers competitive
  analysis.

The full citations live in the research transcript. Highlights of the
external evidence base used to rank these ideas:

- Snyk ToxicSkills (Feb 2026): 36.8% of 3,984 public skills have security
  flaws, 13.4% critical. https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub
- Vercel agent eval: AGENTS.md explicit instructions moved trigger rate
  >95% and pass-rate 53->79%.
  https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals
- Agent-as-a-Judge (Zhuge et al. 2025): LLM-judge disagreement with
  human majority dropped from 31% to 0.3% on code tasks using DevAI.
  https://proceedings.mlr.press/v267/zhuge25a.html
- Claude Code monitoring docs: native `gen_ai.*` OTel emission,
  one env var away. https://code.claude.com/docs/en/monitoring-usage

## Idea 1: Cross-Adapter Trigger Reliability Harness  STATUS: BUILT

Tests that the same skill loads consistently across Claude Code, Codex,
Cursor, Windsurf via 5 paraphrasings per intent (Anthropic's "5 phrasings"
guidance, operationalized). First public Skill Portability Index.

**Status:** built across Phase 0 (skeleton, ADR-0044) and Phase 1
(TraceRecord + matcher + Claude Code OTel shim + harness CLI +
verify-trajectory). Phase 2+ (live LLM spawn, LLM judge, Codex / Cursor /
Windsurf shims) is queued.

**Outputs landed:**
- `base/trajectories/` content type (ADR-0044)
- `scripts/checks/trajectory.py` lint gate
- `scripts/trajectory_matcher.py` DSL evaluator
- `scripts/adapters/claude_code_trace.py` OTel shim
- `scripts/trajectory_harness.py` matrix runner
- `scripts/trajectory_verify.py` author inner-loop tool
- `make trajectory-check`, `make verify-trajectory`, `make new TRAJECTORY=`

## Idea 5: Reference Trajectory as 8th Content Type  STATUS: BUILT (folded into Idea 1)

Originally listed as a separate idea: add trajectory as a first-class
canonical content type alongside skills/rules/hooks/MCP/agents/commands/prompts.

**Status:** folded into Idea 1's implementation; trajectories ARE the 8th
content type per ADR-0044. No separate work remaining.

## Idea 2: Skill Supply-Chain Security Gate  STATUS: NOT BUILT

Today `make audit` blocks new external skill sources by default but does
not actually scan the content of imported SKILL.md files. Snyk ToxicSkills
shows 36.8% of public skills have security flaws and 13.4% are critical;
the playbook explicitly imports from upstreams (mattpocock, others).

**What to build:**

- Wrap Snyk's `mcp-scan` (`uvx mcp-scan@latest --skills`) as a check gate.
- Wrap the `agent-skill-evaluator` PyPI package ("npm audit for SKILL.md").
- Add a DDIPE detector (Document-Driven Implicit Payload Execution): scan
  fenced code blocks in SKILL.md bodies for shell / curl / eval patterns
  that the agent might reproduce as a "reference implementation."
- Generate an AI-BOM (Bill of Materials) per install listing every
  external skill source, vendored MCP, and pinned SHA.

**Effort:** ~2-3 days. Most work is integration wrapping; mcp-scan and
agent-skill-evaluator do the heavy lifting.

**Interesting because:** first explicit trust model for vendored skills.
Frames a per-source threat surface and lets the playbook publish a
"vetted as of" annotation in `base/skills/imported/<source>/`.

**Evidence:**
- Snyk ToxicSkills audit: https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub
- OWASP Agentic Skills Top 10 (April 2026; see related blog posts)
- CVE-2025-6514 (mcp-remote): 437K environments affected by an OS
  command injection.

**ADR slot:** next free number after 0044 (currently 0045 / 0046 reserved
for trajectory work, so this would be 0047+).

## Idea 3: Agent-as-a-Judge Eval Layer  STATUS: PARTIALLY UNBLOCKED

DevAI showed Agent-as-a-Judge matches human reliability on code tasks
where final-output LLM-as-judge does not (31% disagreement -> 0.3%).
The playbook's `evals/` directory is sparse (one skill suite) and uses
static assertions, not trajectory-level evaluation.

**What this looks like now that Idea 1 is built:** the trajectory harness
ALREADY does trajectory-level DSL matching. Idea 3 is the **LLM-judge
half** of the trajectory contract (ADR-0046's `llm_judge.rubric` field).

**What to build:**

- Wire LangChain's `agentevals` package (or MLflow's Agent GPA scorers)
  as the LLM-judge implementation in the harness.
- Add `temperature=0` calibration check: each rubric runs 3x; if judge
  scores vary by more than 0.1, flag the rubric as too subjective.
- Surface judge scores per trajectory in the matrix report.

**Effort:** ~3-5 days. Mostly the calibration check is novel work;
the judge call itself is a small wrapper.

**Interesting because:** turns the trajectory harness from "did the
agent do the prescribed steps" into "did the agent do the steps WELL."
Per ADR-0046, the contract is hybrid (DSL gate first, then judge for
quality).

**Dependency:** Idea 1 must be in place. Now it is. Phase 2 of the
trajectory harness work is the right slot for this.

**Evidence:**
- Zhuge et al. https://proceedings.mlr.press/v267/zhuge25a.html
- LangChain agentevals https://docs.langchain.com/langsmith/trajectory-evals
- MLflow Agent GPA https://mlflow.org/llm-evaluation

## Idea 4: Skill Telemetry via OTel gen_ai Conventions  STATUS: NOT BUILT

Claude Code already emits `gen_ai.*` traces (model, agent_id, query_source,
input_tokens, etc.) when `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set. The
playbook has zero production telemetry today; `decay_check.py` warns by
date, not by actual usage.

**What to build:**

- Local OTLP collector recipe (Docker compose, or just `otel-collector` +
  a config) that writes to a JSONL file in `~/.coding-agents-playbook/telemetry/`.
- `scripts/skill_telemetry_report.py` that ingests the JSONL and prints:
  per-skill trigger count (last 30d), p50/p95 latency, total input/output
  tokens, last-fired timestamp.
- Upgrade decay check: a skill not fired in 60 days is decaying, regardless
  of `last_reviewed` date.
- Privacy: local-first; opt-in for sharing aggregates upstream.

**Effort:** ~1-2 weeks. The collector setup is straightforward; the
aggregation logic and the privacy review (no prompt content leaks) is
the real work.

**Interesting because:** turns every claim in the repo ("skills decay",
"trigger reliability is leverage") from date-based vibes into actual
data. The Vercel 53->79% number is exactly the kind of stat this would
let the playbook produce for its own skills.

**Evidence:**
- Claude Code monitoring docs: https://code.claude.com/docs/en/monitoring-usage
- OTel gen_ai semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Dash0 / Coralogix / Sentry agent observability writeups
- Augment Code's 4-dimension instrumentation guide
  https://www.augmentcode.com/guides/agent-observability-for-ai-coding

**Connection to Idea 1:** trajectory traces (the harness output) are a
specific subset of what an OTel telemetry layer would capture. Building
Idea 4 generalizes the trajectory shim to "all skill execution," not
just harness runs.

## Idea 6: Interactive ADR + Skill Browser ("Why Atlas")  STATUS: NOT BUILT

The teaching-playbook pitch is "rationale IS the value" with 44 ADRs.
Reading 44 markdown files is friction. mattpocock/skills and
obra/superpowers don't have an equivalent because they don't have the
ADR corpus.

**What to build:**

- Static-site generator that walks `docs/adr/` + `base/skills/` + 
  `base/trajectories/` and produces a navigable D3 graph: each skill
  page shows which ADRs justified its existence, related skills,
  decay status, and (if Idea 4 lands) trigger telemetry.
- Hostable on GitHub Pages with no JS dependency beyond what D3 needs.
- Lives at `docs/atlas/` after generation; source generator at
  `scripts/build_atlas.py`.

**Effort:** ~1 week. The crawl + render is straightforward; choosing
the graph layout that doesn't visually overflow at 100+ nodes is the
real design problem.

**Interesting because:** highest-visibility, lowest-engineering-risk
item on the list. Turns the ADR corpus from "read these 44 files" into
"explore the decision graph." Distinguishes the playbook from competing
projects that can't easily ship this because they have no ADRs.

**Evidence:** internal to the playbook's positioning; no Tavily
external citations apply directly.

## Idea 7: Bidirectional Skill Contribution Model  STATUS: NOT BUILT

Today `make sync-mattpocock` is one-way pull. With 490K+ public skills
across SkillsMP / Skills.sh / ClawHub, discovery and contribution are
the next bottleneck for a playbook that aims to be a living standard.

**What to build:**

- `make propose SKILL=<name>` flow: takes an internal skill, runs
  `playbook-promote`'s grill, then opens an upstream PR automatically
  (Bitbucket REST API or `gh` for github-hosted upstreams).
- Skill-card spec (`.well-known/skills.json`) for external repos
  modeled on the MCP Server Cards proposal. Lets crawlers discover
  capabilities without cloning.
- Discovery surface: a script that crawls registered skill repos and
  publishes a curated index.

**Effort:** ~1-2 weeks. The PR automation is well-trodden; the skill-card
spec is the novel piece.

**Interesting because:** this is the only idea that grows the *community*
not the *capability*. Lower technical risk, higher social risk: requires
upstream maintainers to agree to a contribution shape.

**Evidence:**
- Official MCP Registry (Linux Foundation): https://registry.modelcontextprotocol.io
- MCP Server Cards proposal in the 2026-07-28 spec release candidate.
- Public ecosystem numbers (Anthropic 10K+ servers, GitHub 15,926
  mcp-server topic repos, etc.) per
  https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol

## Recommended pick-order for future sessions

When picking the next item, the natural order is:

1. **Phase 2 of trajectory harness** (Idea 3 + live Claude Code spawner)
   completes the work in flight. Highest unblocked value-per-effort.
2. **Idea 2 (supply-chain security)** is small, defensive, and addresses
   a real public threat. Low risk to land.
3. **Idea 6 (Why Atlas)** is small, high-visibility, and reinforces
   the teaching-playbook moat. Good "ship something visible" pick.
4. **Idea 4 (telemetry)** is the biggest, most data-changing piece.
   Builds on the Claude Code OTel shim already in place.
5. **Idea 7 (bidirectional contribution)** is socially the hardest;
   needs upstream coordination. Last in the queue.

## Provenance

- Generated as part of a recursive Tavily research session, 2026-05-27.
- Internal design doc (gitignored): `docs/superpowers/specs/2026-05-27-cross-adapter-trajectory-harness-design.md`
- ADR landed: `docs/adr/0044-trajectories-as-eighth-content-type.md`
- Branch where Idea 1+5 shipped: `feat/trajectory-harness-phase0`
