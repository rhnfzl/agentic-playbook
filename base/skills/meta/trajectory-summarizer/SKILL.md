---
name: trajectory-summarizer
description: Use when an author has captured a Claude Code session as a trajectory fixture (via `make record-trajectory`) and wants help turning the recorded trace into a publishable trajectory YAML — picking good paraphrasings, tightening DSL assertions, and drafting a rubric that the calibration check will accept.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-28
tags: [meta, trajectory, authoring]
scope: [any]
---

# Trajectory Summarizer

A workflow for turning a recorded Claude Code trace into a publishable
trajectory YAML. The recorder (`scripts/trajectory_record.py`) already
writes a `.draft` file with the structural pieces filled in; this skill
helps the author finish the cognitive pieces (paraphrasings, rubric,
which assertions to keep).

## When to use

After running:

```bash
make record-trajectory SKILL=<name> SCENARIO=<name> PROMPT="<prompt>"
```

You will have:

- `base/trajectories/<skill>/fixtures/<scenario>-pass.jsonl` — the
  recorded trace.
- `base/trajectories/<skill>/<scenario>.yaml.draft` — the starter YAML
  with TODO placeholders.

Open both, then walk through this skill.

## Steps

### 1. Read the recorded trace

Open the JSONL fixture and look at the tool-call sequence. Ask:

- Did the agent do what the prompt asked, or did it veer off?
- Are there tool calls you didn't expect (e.g. Read before Write)?
- Did the agent stop at the right moment, or did it keep going?

If the trace itself is wrong (agent veered off), don't write a
trajectory around it. Re-record with a tighter prompt.

### 2. Paraphrase the prompt (phrasings 2-5)

The recorder seeds phrasing 1 with the user's verbatim prompt. The
other four should be paraphrases that an alternative human user might
write to express the same intent. The Anthropic guidance: if the skill
does not load consistently across five phrasings, the description
needs work.

Good paraphrasings vary along these dimensions:

- **Tone**: terse vs verbose; formal vs casual.
- **Structure**: imperative vs question; first-person vs third-person.
- **Tools the user mentions**: "use the to-prd flow" vs implicit.
- **Edge wording**: synonyms for the key nouns (PRD, spec, doc, plan).

Bad paraphrasings re-use the same lexical anchors (every phrasing
mentions "PRD" verbatim, so the description is just memorizing that
token).

### 3. Trim the assertions

The recorder generates one `must_invoke_tool` for every distinct tool
that appeared in the trace. Some of those are essential to the
trajectory's intent; others are incidental (the agent happened to
Read a file before Writing it, but a future run might Glob first).

For each assertion the recorder generated, ask:

- **Is this tool ALWAYS needed?** Keep `must_invoke_tool`.
- **Is this tool SOMETIMES needed?** Remove the assertion; the rubric
  can grade it.
- **Should the tool order matter?** Add `call_order: [{tool: X, before: Y}]`.
- **Should the agent NEVER use a tool here?** Add
  `must_not_invoke_tool: Bash`.

### 4. Write the rubric

The LLM-judge rubric is what makes the difference between
"the agent did the steps" and "the agent did the steps WELL." A good
rubric scores 2-4 specific behaviors out of 1.0 total. Avoid one
giant subjective bullet ("did the agent do a good job?") because the
calibration check (Phase 2C-β) will flag it as too noisy.

Template:

```yaml
llm_judge:
  threshold: 0.7
  rubric: |
    Score the trajectory on:
    1. <Specific behavior #1> (0-0.4)
    2. <Specific behavior #2> (0-0.3)
    3. <Specific behavior #3> (0-0.3)
  model: claude-sonnet-4-6
```

Keep each bullet narrow enough that two humans would assign similar
scores; if you can't, drop the bullet.

### 5. Verify against the fixture

Before committing:

```bash
mv base/trajectories/<skill>/<scenario>.yaml.draft \
   base/trajectories/<skill>/<scenario>.yaml

make verify-trajectory \
  SKILL=<skill> SCENARIO=<scenario> \
  FIXTURE=base/trajectories/<skill>/fixtures/<scenario>-pass.jsonl

make trajectory-calibrate \
  SKILL=<skill> SCENARIO=<scenario>
```

Both commands should pass. If `make verify-trajectory` fails, the
DSL assertions are tighter than the trace supports; loosen them.
If `make trajectory-calibrate` flags the rubric as noisy
(`is_noisy: True`, variance > 0.1), the rubric is too subjective;
tighten or split it.

### 6. Commit

Once both checks pass:

```bash
make check                  # full lint pass
git add base/trajectories/<skill>/
git commit
```

## When NOT to use this skill

- The recorded trace is wrong (agent did the wrong thing). Re-record.
- The skill itself is broken (the agent crashed or refused). Fix the
  skill before authoring a trajectory for it.
- You want a trajectory for behavior the agent does NOT do today.
  Trajectories are tests, not aspirations; record what is real.

## Output shape

A polished `<scenario>.yaml` ready to commit. Companion fixture stays
under `fixtures/`. The pair feeds three downstream surfaces:
`make trajectory-check` (matrix), `make verify-trajectory` (single
trajectory inner loop), and `make trajectory-calibrate` (rubric
noise check).
