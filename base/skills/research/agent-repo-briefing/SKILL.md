---
name: agent-repo-briefing
description: Use when starting a fresh coding-agent session on a research repo the agent has never seen (read the README and AGENTS.md, list datasets, summarize past experiments, identify the next sensible step) before any code is changed.
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, onboarding, context, agent]
scope: [research]
---

# Agent Repo Briefing

What this gets you: a one-page brief that a coding agent (Cursor CLI, Pi, Codex, Claude Code) can read in its first turn to understand the repo before being asked to modify anything. Lists what the repo does, what the data looks like, what experiments have been run, and what the next sensible step appears to be. The agent then has the context to ask informed questions instead of generic ones.

The point is to compress the cost of cold-starting an agent on a research codebase. Without a briefing, the first three turns of every session are the agent re-discovering the repo from scratch. With a briefing, the agent starts at turn four equivalents.

## When NOT to use this skill

- The agent already has context (continuing a session, or working in a repo it just modified). Briefing again wastes tokens.
- The repo has no datasets and no experiments (it is a fresh scaffold). The README plus AGENTS.md is enough.
- The user is asking the agent a focused, surgical question that does not need full repo context ("fix this typo in this file"). Skip the briefing and answer.
- The repo is greater than 1000 files and a full sweep would blow the context window. Brief only the relevant subtree.

## Inputs you need from the user

Usually just the repo path. Optionally:

1. **The task the user wants the agent to do** (if known, briefs the relevant subtree first).
2. **Whether the user wants the brief in the chat or as a file** (default: file at `docs/agent-brief.md` so future sessions can read it).
3. **Time budget** (the full sweep is 5 to 10 minutes; a fast brief is 2 minutes; ask if the user has a preference).

## Workflow

### Step 1: Read the doorways

The first reads should be the files designed to onboard a reader:

1. `README.md` (the human-facing summary)
2. `AGENTS.md` or `CLAUDE.md` or `.cursor/rules/*.md` (the agent-facing rules)
3. `pyproject.toml` / `package.json` / `Cargo.toml` (the dependency manifest, tells you the language and the package layout)
4. `docs/` index (if it exists; check `docs/README.md` or just list the directory)
5. `Makefile` / `justfile` / `scripts/` (the entry points the maintainers expect you to use)

If `AGENTS.md` exists, read it carefully. It is the contract the team has chosen for any agent working in this repo. Treat its rules as non-negotiable for this session unless the user overrides explicitly.

### Step 2: Map the directory structure

Walk the top three levels of the repo (no deeper unless the user asks). Note:

- The data directory (`data/`, `datasets/`, `corpora/`).
- The source directory (`src/`, `lib/`, the package directory).
- The notebook directory (`notebooks/`, `analyses/`).
- The reports directory (`reports/`, `results/`).
- The experiment directory (`experiments/`, `runs/`, `mlruns/`).
- The test directory (`tests/`).

For research repos, the cookiecutter-data-science layout is common. If the layout is non-standard, ask what convention the team uses.

### Step 3: Inventory the datasets

In `data/` (or wherever the data lives), for each subdirectory or file, capture:

```
data/raw/customers.parquet     487k rows, schema: 24 cols, last modified 2026-04-12
data/raw/transactions.csv      1.2M rows, schema: 14 cols, last modified 2026-04-18
data/processed/training.pkl    340k rows, last modified 2026-05-02 (newer than raw, derived)
data/external/zip_codes.csv    42k rows, 2025-09 snapshot
```

Use `ls -la` for filesystem metadata; for parquet, `pq.read_schema()` is cheap and reveals dtypes without loading data; for CSV, read the first 5 rows.

Flag anomalies:

- A processed file older than the raw file it derives from (probably stale).
- A "data/" directory that is empty (probably gitignored; ask the user where the data lives).
- A file with no schema documentation (ask the user or list the columns inline).

### Step 4: Read the experiment log

Most research repos track experiments somewhere. Look for, in this order:

- An `experiments/` directory with named runs.
- An MLflow `mlruns/` or DVC `.dvc/` directory.
- An `experiments.md` or `runs.md` notes file.
- Git commit log filtered to "experiment" / "run" / "eval" messages (`git log --oneline --grep "exp"`).
- Closed issues or PRs tagged `experiment`.
- Notebooks named with dates and descriptions (`2026-04-experiments-with-prompt-v3.ipynb`).

Summarize the last 3 to 5 experiments:

- What was the question?
- What was the result?
- What did the team decide?

If you cannot tell what an experiment was for, that itself is a finding (the experiment is undocumented). Surface it.

### Step 5: Read the most recent notebooks

The latest 2 to 3 notebooks (by modification date) are usually the active work. Read each:

- What is the notebook trying to learn?
- What is the current state (in progress, abandoned, ready to refactor)?
- Are there visible TODOs or open questions in markdown cells?

This is the highest-signal step. The active notebooks tell you where the team's attention is.

### Step 6: Read the open TODOs and issues

Sources of open work:

- `TODO.md` or `BACKLOG.md` if it exists.
- Comments in code: `git grep -nE "TODO|FIXME|XXX|HACK"` (limit to recent files).
- Open issues in the issue tracker (Jira, Linear, VCS, GitHub).
- Comments in the recent notebooks.

Summarize the top 3 to 5 by what looks active. Skip stale TODOs (greater than 6 months old, no movement).

### Step 7: Identify the next sensible step

Based on Steps 4 to 6, propose what the next session should focus on. Three to five suggestions, ordered by what looks ripe:

1. **Highest priority**: an in-progress notebook with an open question.
2. **Quick win**: a TODO that looks like a small refactor.
3. **Important but larger**: an experiment that has been mentioned but not run.
4. **Maintenance**: a stale file, an old data version, a failing test.

The agent (or the human) picks one. The briefing surfaces options, not commands.

### Step 8: Write the brief

Output structure:

```markdown
# Repo brief: my-research-project

Generated: 2026-05-24 by agent-repo-briefing skill
Repo: /Users/rehan/work/my-research-project
Branch: develop (clean)

## What this repo does
One-paragraph plain-language summary (from README), with the key product / research framing.

## House rules (from AGENTS.md)
- 3 to 5 bullets of the hard rules the agent must follow in this repo.

## Layout
- src/my_project/: package code
- notebooks/: 12 notebooks; latest is 2026-05-22-prompt-v4.ipynb
- data/raw/: 3 datasets (largest: transactions.csv, 1.2M rows)
- data/processed/: training.pkl (derived from raw)
- experiments/: 8 runs logged in MLflow

## Recent experiments
1. exp-2026-05-12-prompt-v3: tested new prompt on 200-query eval, +0.04 accuracy (CI [0.01, 0.07]), shipped.
2. exp-2026-05-08-reranker: added cross-encoder reranker, +0.02 NDCG, did not ship (latency cost).
3. exp-2026-04-30-rechunking: tried 1024-token chunks vs 512, no difference, kept 512.

## Active work
- notebooks/2026-05-22-prompt-v4.ipynb: in progress, exploring chain-of-thought variants.
  Open question (markdown cell): "is the COT win on benchmark X coming from leakage?"
- TODO in src/my_project/features.py:127: "refactor the date parsing once we standardize on UTC"

## Suggested next steps for this session
1. (Highest): Help the user resolve the COT-leakage question in prompt-v4 notebook.
2. (Quick win): Refactor the date parsing TODO (small, isolated).
3. (Larger): Run the rechunking experiment again with the new prompt; previous result may not generalize.

## Things to ask the user
- Is the prompt-v4 notebook ready to merge or still mid-exploration?
- Should the next experiment use the v3 eval set or the new v4 one?

## Reference files for context
- README.md (project framing)
- AGENTS.md (rules)
- docs/research/methods.md (eval methodology)
- experiments/exp-2026-05-12-prompt-v3.md (most recent shipped result)
```

The brief is a working document. Update the `last generated` line each time it is regenerated. Older briefs in the repo become a low-cost history of the project's evolution.

### Step 9: Check what is missing

The brief reveals gaps in the repo's onboarding material itself. If the brief had to ask the user multiple basic questions (where is the data, what does this experiment do, what is the convention for X), surface those as documentation TODOs:

- Add a section to README describing the data sources.
- Add an experiment-log template if there is no consistent format.
- Add an AGENTS.md if none exists and the team works with multiple agents.

This is optional but high-value. Many research repos lack any onboarding material because the original author has it all in their head.

### Step 10: Hand off to the agent or the user

The brief is now ready to drop into the agent's context. Two patterns:

- **Inline**: paste the brief as the agent's first message. Works for short briefs and short sessions.
- **File reference**: save the brief to `docs/agent-brief.md` and tell the agent (or the user) to read it. Works for longer briefs and recurring sessions.

For Cursor CLI and Pi, the file approach plays well with `@file` references. For Codex, the brief can live in `AGENTS.md` if it is durable enough. For Claude Code, save to a session-scoped file.

## Common pitfalls

- **Generating the brief and never reading it back**: the brief is for the next session, not for the current one. Make sure it is committed or saved somewhere the agent will find it.
- **Brief too long**: greater than 1500 words and the agent skims. Cut to 500 to 800 words for most repos.
- **Brief too generic**: "this is a Python repo with notebooks" is true but useless. The brief earns its tokens by being specific (named experiments, named datasets, named TODOs).
- **Out of date**: a brief from three months ago is misleading. Re-generate when the repo's state has shifted (new experiments, new datasets, new direction).
- **Pretending to know**: if a section cannot be filled (no experiments logged, no notebooks), say so rather than fabricate. "No experiment log found" is a finding.

## Fast path (2-minute brief)

When the user wants a quick brief, skip Steps 5 (notebook deep-read), 6 (TODOs), and 9 (missing material). Keep:

1. Read README and AGENTS.md.
2. List datasets (filesystem only, no schema reads).
3. List recent experiments (titles only).
4. Suggest one next step.

The 2-minute version is enough to unblock simple tasks. The full version is what you want before significant work.

## Output shape

A markdown file at `docs/agent-brief.md` (or the path the user prefers) plus a chat reply with the suggested next steps section pulled out so the user can pick one. If the brief is being generated for a specific task the user mentioned, weight the suggestion ranking toward files that touch that task.

## Sources

- DrivenData, "Cookiecutter Data Science V2" for the canonical research-repo layout
- Anthropic Claude Code docs on AGENTS.md and CLAUDE.md as agent onboarding files
- The Block / Goose pattern of putting agent rules in a versioned file rather than user-level config

## Pre-flight checklist

Run through these questions before deciding to invoke this skill at all. If any answer is "no", consider whether a smaller skill is the right tool.

1. Is this a research repo (notebooks, datasets, experiments)? If it is a service or library, use a smaller code-tour pattern instead.
2. Will the agent be doing substantive work (greater than 30 minutes of edits), or is this a one-shot question? If one-shot, skip the brief and answer directly.
3. Does the repo have at least one of: a README, an AGENTS.md / CLAUDE.md, a data directory, or an experiments directory? If none of those exist, the brief will be empty and the user should write a README first.
4. Has the user given consent (implicit or explicit) for a 5 to 10 minute discovery phase? If they are in a hurry, switch to the fast-path variant.
5. Is the repo small enough that a full sweep fits in the agent's context window? For monorepos greater than 1000 files, brief a subtree only.

If three or more answers tilt against running the full brief, default to the fast-path (Steps 1, 3, 4, 7, 8 only).

## Second worked example: monorepo with a research subtree

The first walkthrough assumed a clean cookiecutter-style repo. Real life is messier. Imagine the user points the agent at a monorepo that contains a production web service, a shared library, and a `research/` subdirectory where two data scientists do their work.

Phase A: scope the brief. The agent should NOT brief the whole repo. Confirm with the user: "I see this repo also contains a web service and a shared library. Should the brief focus on `research/` only, or should I include the shared library it depends on?" In most cases the answer is `research/` only, plus the top-level `pyproject.toml` and `Makefile` because those govern the dev environment.

Phase B: doorways. The doorways are now nested. Read `research/README.md`, then `research/AGENTS.md` if present, then the top-level `AGENTS.md` for any rules that apply to the whole repo (license, security, dependency policy). If both exist, the research-subtree rules supplement the top-level rules; they do not replace them.

Phase C: dataset inventory inside `research/data/`. Watch for symlinks that point out of the repo (e.g., `research/data/raw -> /shared/datasets/raw`). Note the symlink target in the brief so the next session knows where the actual data lives. If the symlink target is unreadable from the agent's environment, surface that as a setup gap before continuing.

Phase D: experiment log. Monorepos rarely have a clean `experiments/` directory. Look in `research/notebooks/` for date-stamped names, in `research/runs/` for CI artifacts, and in the commit log of `research/` only (`git log --oneline -- research/`). The commit-log filter is the trick. Without it, the agent reads thousands of unrelated commits.

Phase E: recent notebooks. The two most recently modified notebooks in `research/notebooks/` are the active work, regardless of how busy the rest of the repo is. Read those two, then stop. Do not climb into the broader `notebooks/` tree of unrelated teams.

Phase F: next steps. The suggestions are narrower in a monorepo because the work is more siloed. Propose two to three steps inside `research/`, not across the whole repo.

Phase G: where to write the brief. In a monorepo, `docs/agent-brief.md` at the root could collide with another team's brief. Write to `research/docs/agent-brief.md` instead, so the per-subtree convention is clear.

The deltas from the standard flow are: scope confirmation up front, nested doorway resolution, commit-log filtering, and a subtree-local output path. None of these are exotic, but missing any one of them produces a brief that the next session ignores.

## Edge cases

1. **The repo has no README and no AGENTS.md**: this is common in research-only repos that grew organically. The brief becomes the first onboarding document. After writing it, propose that the user commit a 10-line README that points at the brief, so the next agent session does not have to re-derive the same context from scratch.

2. **The data directory is gitignored and empty on a fresh clone**: do not silently report "no data". Ask the user where the data lives (S3, Snowflake, a shared NFS mount, a colleague's laptop). Capture the answer in the brief so the next agent knows where to look. If access is gated (VPN, credentials), note the access path explicitly.

3. **The experiments directory contains 200 runs with cryptic names**: do not summarize all 200. Sort by modification date, take the top 10, and surface the rest as "200 runs total, 190 older than 6 months, brief covers the 10 most recent". The older runs become a follow-up if the user wants them.

4. **AGENTS.md and CLAUDE.md disagree on a rule**: surface the conflict explicitly rather than picking one. The team needs to know they have drift in their agent rules, and the brief is the right place to flag it.

5. **The latest notebook is broken (cells fail to run, imports missing)**: brief it honestly. "Notebook 2026-05-20-prompt-v5.ipynb appears to be mid-debugging (cell 4 raises ImportError on `from new_module import foo`)." A broken notebook is a finding, not a flaw in the brief.

6. **The repo has a `secrets/` or `credentials/` directory checked in**: stop the brief, do not read those files, surface immediately to the user with the path and a recommendation to rotate the credentials and add the directory to `.gitignore`. This is a security finding that supersedes the brief's normal completion.

## Anti-patterns

1. **Re-running the brief at the start of every session without checking if a recent brief exists**: wastes tokens. Check `docs/agent-brief.md` for the last-generated timestamp; if it is less than a week old and the repo state looks stable, read the existing brief instead.

2. **Generating a brief without committing it**: the brief's whole value is that future sessions can read it. A brief that lives only in the current chat dies when the chat ends.

3. **Reading every file in the repo "to be thorough"**: the brief is a sampling exercise, not a code review. The doorways and the 10 most-recent files are usually enough. Reading 200 files to brief a 1000-file repo is a waste.

4. **Listing files without describing them**: "data/raw/customers.csv exists" is not a finding. "data/raw/customers.csv, 1.2M rows, 24 cols, last refreshed 2026-04-12" is. The schema and the freshness are what change downstream decisions.

5. **Brief lengths greater than 2000 words**: anything that long becomes a skim. Cut aggressively. The brief is a pointer, not the whole story.

## When to chain with

Briefing is the warm-up. The skills that typically run next:

- **data-profiling**: after the brief identifies a dataset, profile it before any modeling discussion. The two skills together get a new agent from cold-start to "ready to talk about features" in under 15 minutes.
- **hypothesis-design**: if the brief surfaces an open research question, design the next experiment around it before writing code.
- **literature-synthesis**: if the brief surfaces a research question that the team has not yet investigated, run a literature sweep before designing the experiment.
- **notebook-to-production**: when the brief reveals a mature notebook that has not been productionized, schedule the refactor.

Briefing is rarely run after another skill. It is the first move, not the cleanup.

## Decision tree

```
Is this a research repo?
  No  -> use a smaller code-tour pattern, not this skill
  Yes -> continue
        |
        v
Does docs/agent-brief.md exist?
  Yes -> Is it less than 7 days old AND has git log been quiet?
            Yes -> read the existing brief, do not regenerate
            No  -> regenerate (continue below)
  No  -> continue below
        |
        v
Will the work take greater than 30 minutes?
  No  -> answer the user directly, skip the brief
  Yes -> continue
        |
        v
Is the repo larger than 1000 files?
  Yes -> ask the user which subtree to brief, then narrow scope
  No  -> brief the whole repo
        |
        v
Run the 10-step workflow (or fast-path if user is time-constrained)
```

## Output schema

The brief is a single markdown file. Default path: `docs/agent-brief.md`. Required sections (in order):

1. `# Repo brief: <project-name>` (H1, project name)
2. `Generated: YYYY-MM-DD by agent-repo-briefing skill` (timestamp metadata)
3. `## What this repo does` (one paragraph)
4. `## House rules (from AGENTS.md)` (3 to 5 bullets, or "no AGENTS.md found")
5. `## Layout` (annotated directory list)
6. `## Recent experiments` (3 to 5 most recent, with outcomes)
7. `## Active work` (the live notebooks and TODOs)
8. `## Suggested next steps for this session` (3 to 5 ranked options)
9. `## Things to ask the user` (open questions)
10. `## Reference files for context` (the doorways for future sessions)

The chat reply that accompanies the file contains, at minimum:

- The path to the brief (`docs/agent-brief.md`).
- The top 3 suggested next steps pulled inline so the user can pick one.
- Any blocking questions that prevented full brief completion (missing data path, missing credentials, etc.).

The brief is plain markdown. No YAML frontmatter (it is not a skill or rule). No HTML (a teammate should be able to read it in any markdown viewer). Word count target: 500 to 1500 words for a typical repo, up to 2500 for a large monorepo subtree.

## Calibration notes

Three patterns worth knowing once you have run this skill on more than a handful of repos.

**Brief length scales with repo activity, not repo size.** A 10000-file repo that has been quiet for a year produces a shorter brief than a 200-file repo where two engineers are landing experiments every day. The activity floor is the experiments log and the recent notebooks; both grow with sprint cadence, not file count.

**The "Things to ask the user" section is usually the highest-signal part.** Engineers tend to skim straight to it. If the brief has nothing to ask the user, either the repo is unusually well-documented or the brief was too shallow. Re-read your own brief; if any "no AGENTS.md found" or "data directory empty" findings hide in the body, lift them to "Things to ask".

**Briefs go stale on a predictable cadence.** Active research repos drift in about 7 to 14 days (the cycle of a feature branch or an experiment). Mature repos drift in about 30 to 60 days. Greenfield prototypes drift in 1 to 3 days. The "is the existing brief still good?" check from the decision tree uses these defaults, but a project-specific tuning may be needed if the team works in unusual cycles.

## Handoff conventions

Briefs are read by other agent sessions as often as by humans. Two conventions make handoff cleaner.

First, the file path. `docs/agent-brief.md` is the default because most agents are configured to look for it. If the project's `AGENTS.md` specifies a different brief location (e.g., `.agent/brief.md` or `docs/onboarding/agent-brief.md`), follow that. Do not invent a new path because the default conflicts with something else; rename the conflicting file or merge the briefs instead.

Second, the regeneration cadence. Add a line at the bottom of the brief: `Regenerate suggested: after 2026-06-05 or when the experiments log gains a new entry`. The next session reads this and decides whether to refresh. The date is a soft cap; the second condition is the harder trigger.

If multiple agents (Claude, Codex, Cursor, Pi) share the same repo, the brief becomes a common artifact. Avoid agent-specific sections. Anything Claude-specific belongs in `CLAUDE.md`; anything Cursor-specific belongs in `.cursor/rules/`. The brief stays agent-neutral so any session can use it.

## Limits

The brief is a context-compression tool, not a substitute for understanding. After reading it, the agent should still ask one or two clarifying questions before making non-trivial changes. The brief earns its tokens by removing the obvious questions, not by removing all questions.

The brief is also not a status report. If the user wants to know "what is the project's progress this sprint?", that is a different question with a different audience. The brief tells a new agent how to get productive; a status report tells a human stakeholder how things are going. The two overlap but they are not the same artifact.

Finally, the brief should be revisited (not necessarily regenerated, but at least re-read) at the start of every long session. A brief from 30 days ago might still be 90% accurate; the 10% that is stale is exactly the part the agent needs to know. Diff the current repo state against the brief's "Recent experiments" and "Active work" sections; flag anything that has changed.

## Quality checks before delivery

Before handing the brief to the next session or to a teammate, walk through:

1. **Are all sections present, including "Things to ask the user"?** A brief with an empty open-questions section is suspicious. Even mature repos have at least one open question worth surfacing.
2. **Are the named items specific?** Named experiments, named datasets, named TODOs. "Several experiments" is not specific. "The 2026-05-12 prompt-v3 experiment" is.
3. **Are the suggested next steps ranked, not just listed?** The whole point is to give the next session a starting move. Without ranking, the brief offloads the decision back onto the user.
4. **Are the suggested steps grounded in the brief's findings?** A suggestion should reference a notebook, a TODO, or an experiment that the brief surfaces. Out-of-thin-air suggestions undermine credibility.
5. **Is the brief commitable?** Check for embedded secrets, internal-only URLs, or paths that depend on a specific developer's machine. The brief should be readable by any teammate.
6. **Is the brief size right for the project size?** 500 to 1500 words for a typical repo, 200 to 500 for a tiny prototype, 1500 to 2500 for a large monorepo subtree. Anything outside these bands is a calibration warning.

If any check fails, fix before committing. A flawed brief misleads more than it helps because the next agent trusts it without re-validating.

## Limits

The brief is a context-compression tool, not a substitute for understanding. After reading it, the agent should still ask one or two clarifying questions before making non-trivial changes. The brief earns its tokens by removing the obvious questions, not by removing all questions.

The brief is also not a status report. If the user wants "what is the project's progress this sprint?", that is a different question with a different audience. The brief tells a new agent how to get productive; a status report tells a human stakeholder how things are going.

The brief depends on the repo being self-describing enough to brief. A repo with no README, no AGENTS.md, no commit history, and undocumented data is hard to brief well; the resulting brief will mostly say "ask the user". That is itself a valuable finding because it tells the user where to invest in onboarding material.

The brief is not authoritative on the repo's correctness. It describes the repo as it appears; if the repo has bugs the brief is not built to find them. Pair the brief with code review or test runs when correctness matters.

## Tooling notes

The skill is mostly read-only and works with any agent's standard tools.

- **Bash** for `ls`, `git log`, `git grep`, `find` (with care; never `find /`).
- **Read** for individual files (README, AGENTS.md, the doorways).
- **Write** to commit the brief at `docs/agent-brief.md`.
- For repos with Jira / Linear / VCS issue trackers, the relevant MCP server can supply open issues for the brief's "Open work" section. Without an issue-tracker MCP, fall back to `git grep "TODO|FIXME"` in the codebase.

Avoid heavy operations: do not load datasets into memory (the brief lists them, does not profile them; profiling is `data-profiling`'s job). Do not run tests (the brief notes whether tests exist, does not run them). Do not modify any code (the brief is read-only on the repo; the only write is the brief file itself).

If the agent has access to a code-graph index (graphify, code search index), use it to find recent changes or active hotspots in the codebase. Without one, the modification-timestamp signal from the filesystem is usually enough.

## Briefing in non-research contexts

The skill was designed for research repos but adapts to two adjacent contexts.

**Service repos**: replace "datasets" with "deployments", "experiments" with "incidents / hotfixes", "notebooks" with "recent feature branches". The structural workflow is the same; the named items are different. The brief becomes "what does this service do, what is in flight, what is the next reasonable change".

**Library repos**: replace "datasets" with "API surfaces", "experiments" with "version migrations", "notebooks" with "examples / docs". The brief becomes "what does this library expose, what is being changed in the API, what is the next release".

For both non-research adaptations, the "House rules" section (from AGENTS.md) is still the most important. The other sections shift but the discipline of compressing the cold-start cost remains.

If the repo is unclassifiable (a mix, a meta-repo, a sandbox), default to the research template and adapt section names as needed.

## Brief lifecycle

A brief is a living document with a predictable lifecycle:

1. **Born**: created by this skill on the first agent session that needs orientation.
2. **Read**: every subsequent session checks the brief before doing other discovery. Reading is the most-common interaction.
3. **Cited**: downstream documents (PRs, ADRs, research syntheses) reference the brief when they need shared context.
4. **Stale**: the repo drifts (new experiments, new datasets, new direction) and the brief no longer reflects reality.
5. **Refreshed**: this skill runs again, the brief is regenerated. Old briefs in git history become a low-cost record of project evolution.

The refresh cadence depends on the project pace. Fast-moving (greater than 5 commits per day): refresh every 1 to 2 weeks. Steady-state (1 to 2 commits per day): every 4 to 6 weeks. Mature / on-the-shelf (less than 1 commit per week): refresh on the rare event that the repo wakes up.

The brief should never be permanent. The phrase "the original brief" is suspect; if no one has touched it in 6 months, either the repo is dormant (in which case the brief is fine) or the brief is stale (in which case refresh).

## Cross-agent compatibility

When multiple agents (Claude Code, Codex, Cursor, Pi, Windsurf) share a repo, the brief becomes shared infrastructure. Two patterns make sharing work:

1. **Agent-neutral content**: the brief avoids agent-specific instructions (no "use the Claude Read tool here"). Agent-specific content belongs in `CLAUDE.md` / `AGENTS.md` / `.cursor/rules/`, not in the brief.

2. **Single source of truth**: one brief per repo (or per subtree in monorepos). Multiple briefs at different paths drift apart. If two briefs already exist, merge them rather than maintain both.

The brief is the warm-start contract; the agent-specific rules files are the operating-procedure contract. Keep them separate.

## Final delivery checklist

Before declaring the brief complete:

1. The file is committed (or scheduled to be committed).
2. The "Suggested next steps" section is ranked, with the top 3 in the chat reply.
3. Every section has named, specific items (no generic "various files").
4. The "Things to ask the user" section is non-empty.
5. The reference files list points to the doorways the next session needs.
6. The word count is within target (500 to 1500 for typical, 200 to 500 for tiny, 1500 to 2500 for monorepo subtrees).
7. No em dashes anywhere in the brief.
8. The timestamp at the top reflects today.

If any item fails, fix before declaring done. A brief that misleads the next session wastes more tokens than no brief at all.

## Failure modes to surface

When the brief cannot complete cleanly, the right move is to surface the failure rather than fabricate around it. Common failures:

1. **No README and no AGENTS.md**: brief proceeds with "No onboarding material found; recommend committing one before next session."
2. **Data directory is empty (gitignored or never populated)**: brief notes "Data directory empty; ask user where data lives and document the access path."
3. **Repo has no commits in greater than 12 months**: brief notes "Repo appears dormant; verify with user whether work has moved elsewhere before continuing."
4. **Repo is too large to brief in scope**: brief asks the user to narrow scope, then briefs the chosen subtree.
5. **Critical access blocked (private submodules, gated data, internal-only URLs)**: brief notes what was inaccessible and what authority would be needed to unblock.

Each of these is a finding worth surfacing in its own right. The brief is most valuable when it tells the truth about what could not be discovered, not when it pads around the gap.

## Sample brief headers for different repo shapes

Three concrete examples of how the header looks depending on what the brief found.

**Standard research repo (healthy state):**

```
# Repo brief: rag-eval-platform

Generated: 2026-05-25 by agent-repo-briefing skill
Repo: /Users/rehan/work/rag-eval-platform
Branch: develop (clean)
Language: Python 3.11 (uv)
Last commit: 2026-05-23 (2 days ago)
House rules: see AGENTS.md (5 rules summarized below)
Brief scope: full repo (442 files, 12 notebooks, 3 datasets)
Regenerate suggested: after 2026-06-25 or when a new experiment lands.
```

**Monorepo with research subtree:**

```
# Repo brief: monorepo/research subtree

Generated: 2026-05-25 by agent-repo-briefing skill
Repo: /Users/rehan/work/monorepo (subtree: research/)
Branch: develop (clean)
Language: Python 3.11 (uv) within research/; rest of repo is JS/TS
Last commit (research/): 2026-05-20 (5 days ago)
House rules: research/AGENTS.md + top-level AGENTS.md (8 rules combined)
Brief scope: research/ subtree only (218 files); shared library mentioned where relevant
Regenerate suggested: after 2026-06-25 or when research/ experiments log gains an entry.
```

**Recently-acquired repo (rough state):**

```
# Repo brief: legacy-customer-analysis

Generated: 2026-05-25 by agent-repo-briefing skill
Repo: /Users/rehan/work/legacy-customer-analysis
Branch: master (clean, no develop branch)
Language: Python 3.9 (requirements.txt, no lock file)
Last commit: 2025-11-12 (6 months ago)
House rules: NONE FOUND (no AGENTS.md, no CLAUDE.md, no .cursor/rules/)
Brief scope: full repo (89 files); data directory empty (user clarification needed)
Findings: 3 documentation TODOs surfaced; recommend establishing AGENTS.md before further work
Regenerate suggested: after any next commit; repo state is stale.
```

The header sets the tone for the rest of the brief. A clear, honest header tells the next session what kind of brief they are about to read.
