# Prompt: Bootstrap Your Playbook

Paste the prompt below into your coding agent (Claude Code, Cursor, Windsurf, Codex, etc.) inside an empty directory where you want your team's playbook to live. Fill in the bracketed placeholders before pasting.

---

## The prompt

```
I want to create a tool-agnostic, team-shared playbook for working with coding agents,
inspired by the coding-agents-playbook pattern. This will become my team's shared
repository of skills, rules, hooks, and MCP configs that distribute to whichever
coding agent each teammate uses (Claude Code, Cursor, Windsurf, Codex, Copilot, etc.).

Here is the context:

  Team name: [YOUR TEAM NAME]
  Primary coding agent(s) used by the team: [LIST]
  Primary programming language(s): [LIST]
  Project domain: [BRIEF DESCRIPTION]
  Number of engineers on the team: [N]
  Existing convention files (CLAUDE.md, AGENTS.md, .cursorrules, etc.): [LIST OR NONE]

Please scaffold the following directory structure in the current directory:

  README.md         # plain-language intro: what this is, why it isn't team-exclusive,
                    # inspirations (Microsoft eng-playbook, Airbnb knowledge-repo,
                    # Block/Goose, Stripe Minions, mattpocock/skills)
  AGENTS.md         # the playbook's own per-repo agent contract
  CONTEXT.md        # shared vocabulary glossary (skill, rule, hook, adapter, profile)
  CONTRIBUTING.md   # PR + owner-per-skill + review process
  LICENSE           # MIT
  Makefile          # install, check, new, doctor targets
  .gitignore        # Python + secrets

  skills/
    engineering/    # code-focused workflows
    productivity/   # general workflow tools
    observability/  # ops, monitoring, debugging
    meta/           # skills about skills

  rules/            # cross-cutting AGENTS.md fragments
  hooks/            # shareable shell hooks
  mcp/              # MCP server configs
  profiles/         # per-role bundles (one TOML per role)
  prompts/          # pre-built prompts for adoption by other teams

  scripts/
    install.py            # interactive installer
    adapters/             # per-tool adapters
    frontmatter_lint.py   # SKILL.md frontmatter validator
    decay_check.py        # warns when last_reviewed > 90 days
    new_skill.py          # scaffold a new skill
    retrospective.py      # backend for /playbook-retrospective (capture)
    promote_skill.py      # backend for /playbook-promote (graduate draft -> repo)

  docs/
    adr/                  # design decisions (one .md per decision)
    research/             # evidence base
    tools/                # per-agent integration notes
    human-html/           # plans, reviews

Design constraints:

1. SKILL.md is the canonical format (mattpocock convention). Each skill is a directory
   under skills/<category>/<name>/ with a SKILL.md containing YAML frontmatter
   (name, description, version, owner, last_reviewed, tags, scope) and a body
   describing trigger, steps, output, and "when NOT to use."

2. Rules are simple markdown in rules/<name>.md. No frontmatter. A rule is a behavioral
   constraint (always/never do X), distinct from a skill (do these steps in this order).
   The installer concatenates selected rules into AGENTS.md for each agent.

3. Architecture: per-subproject AGENTS.md instead of one monolithic file. If your team
   has multiple subprojects, each one owns its own AGENTS.md. The shared repo holds
   only skills and cross-cutting rules.

4. Agent target list: Tier 1 (full adapter) for the 4 agents the team uses most.
   Tier 2 (skills + rules) for ~4 next-most-likely. Tier 3 (AGENTS.md only) for
   the other ~20 agents that read AGENTS.md natively (Codex, Cursor, Windsurf,
   Copilot, Gemini CLI, Aider, Cline, Kiro, Goose, Junie, etc.).

   Claude Code is a special case: it does NOT natively read AGENTS.md (per
   code.claude.com/docs/en/memory). The Tier 1 Claude Code adapter writes the
   playbook rules into a managed block in ~/AGENTS.md, then expects the user's
   ~/.claude/CLAUDE.md to import that file with `@~/AGENTS.md`. If the user
   does not have that import, the adapter surfaces a one-line install reminder.
   Do NOT list Claude Code as Tier 3 (AGENTS.md-only); rules would silently
   not load.

5. Install UX: interactive, detect-and-preselect (probe ~/.claude/, ~/.codex/,
   .cursor/, ~/.codeium/, etc.). User can toggle per-agent before install.

6. Decay prevention: every SKILL.md has last_reviewed: YYYY-MM-DD in frontmatter.
   `make check` warns at 90 days, blocks at 180 days.

7. Inspiration-repo framing: the README explicitly invites other teams to clone,
   study the ADRs, copy patterns, and build their own. The point isn't to make
   them use OUR skills. It's to make it easy for them to build THEIRS.

8. Three-layer capture system: include two meta skills so the playbook can
   keep itself updated as the team works.
   - skills/meta/playbook-retrospective/SKILL.md: session-end retrospective,
     manual trigger. Reads the session log, drafts proposals into
     ~/.playbook-proposals/ (user-level, gitignored, decoupled from the
     playbook checkout).
   - skills/meta/playbook-promote/SKILL.md: graduates a draft into the repo.
     Runs a grill-me interview, scaffolds via scripts/new_skill.py, creates
     feat/playbook-add-<slug> branch, stops before commit/push.
   - scripts/retrospective.py + scripts/promote_skill.py: backend file IO.
   - docs/adr/0008-three-layer-capture-system.md: design rationale.
   Decoupling drafts from the checkout (via $PLAYBOOK_PROPOSALS_DIR default
   ~/.playbook-proposals/) means the same workflow works for teammates with
   the playbook cloned at different paths.

Start by:

  a) Creating the directory tree (mkdir all the dirs above + .gitkeep in empty ones).
  b) Writing README.md, AGENTS.md, CONTEXT.md, CONTRIBUTING.md, LICENSE,
     .gitignore, Makefile, scripts/install.py skeleton, scripts/frontmatter_lint.py,
     scripts/decay_check.py, scripts/new_skill.py, scripts/retrospective.py,
     scripts/promote_skill.py.
  c) Writing 1-2 sample skills (in skills/engineering/ or skills/productivity/) and
     1-2 sample rules so the structure has working examples.
  d) Writing the two meta skills (skills/meta/playbook-retrospective/SKILL.md and
     skills/meta/playbook-promote/SKILL.md) so the playbook can capture and
     graduate new patterns as the team works.
  e) Writing prompts/README.md and at least one starter prompt in prompts/.
  f) Writing docs/adr/0008-three-layer-capture-system.md documenting the
     capture-and-promote design.

After scaffolding, ask me:
  - Which existing personal skills (in ~/.agents/skills/, ~/.claude/skills/, or wherever
    I have them locally) I want to lift into the shared library as v0.1 seed content.
  - Which workspace conventions / memory entries to extract as rules.
  - Whether to start solo or pilot with a specific teammate before wider rollout.

Optimize for substantive v0.1 (real seed content), not abstract "we can add later"
placeholders. Empty directories signal an unfinished system. Use .gitkeep for the
ones that legitimately need to start empty.
```

---

## What this prompt produces

After your agent runs it, you should have:

- A complete directory tree with homes for everything
- Working README, AGENTS.md, CONTRIBUTING.md, LICENSE, Makefile
- A skeleton installer that detects agents and prompts for selection
- Lint scripts that validate frontmatter and warn on stale skills
- 1-2 sample skills demonstrating the format
- 1-2 sample rules demonstrating the format
- Two meta skills (`playbook-retrospective`, `playbook-promote`) that let your team capture new patterns from real sessions and graduate them into the repo via PR
- A prompts/ directory that lets the NEXT team do the same thing

Adjust the prompt to your stack. The patterns transfer; the specifics don't.

## Iteration

After the initial scaffold lands, run:

```
make check    # validate frontmatter, surface decay warnings
make doctor   # diagnose which agents are detected on your machine
make install  # interactive install for selected agents
```

Then start lifting your own workflows into skills. Aim for 5-10 skills + 5-8 rules
in v0.1, drawn from things you actually do every week.
