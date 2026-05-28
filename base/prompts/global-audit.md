# Prompt: Global Machine Audit

Paste the prompt below into your coding agent (Claude Code, Codex CLI, Cursor, Windsurf) **after cloning the agentic-playbook**. The agent walks your user-level agent directories and the playbook in parallel, then proposes a phased rollout of which skills, rules, hooks, MCP server configs, subagents, slash commands, and prompt templates to install across every project you work on.

Different from `make install` (which materializes the whole opinionated set) and from `project-audit.md` (which proposes project-level files for one specific directory). This prompt is for the "globally on this machine" decision.

---

## The prompt

```
I want you to audit my coding-agent setup across this entire machine and propose a phased
rollout of agentic-playbook content (skills, rules, hooks, MCP server configs, subagents,
slash commands, prompt templates, behavior trajectories) that would land at the user level
and apply to every project I work on.

Constraints before you start:

  1. Do NOT install or write any files in this pass. This is a planning pass only.
  2. Propose changes in a phased rollout (Phase 1 high-confidence, Phase 2 worth trying,
     Phase 3 worth discussing). I want to review each phase before anything lands.
  3. For every proposed addition, name (a) the specific playbook artifact (slug + path),
     (b) the agent surface it would land on (~/.claude/skills/, ~/.codex/hooks/,
     ~/.cursor/rules/, ~/.codeium/windsurf/, ~/.pi/agent/, etc.), and (c) one sentence
     on why it fits MY setup, not the generic case.
  4. Never propose something that would overwrite a hand-authored file. The installer
     materializes content under managed-block markers and the lockfile records every
     materialized path; before proposing, walk the lockfile (if present at the target)
     and check whether the path is already managed or hand-authored. Anything outside
     the managed-block markers is operator-owned and must not be overwritten.

Walk in this order:

  Step 1 -- Inventory my current setup.
    a) Read ~/.claude/, ~/.codex/, ~/.cursor/, ~/.codeium/windsurf/, ~/.pi/agent/,
       ~/.aider/, ~/.gemini/, ~/.cline/, ~/.config/agent-shared/ (if present).
    b) For each agent directory, list which content types are populated (skills/,
       rules/, hooks/, agents/, commands/, prompts/, mcp config) and how many entries
       each has.
    c) Read ~/AGENTS.md and ~/.claude/CLAUDE.md (if present); identify which rules I
       already have at the user level.
    d) Read any global memory / context files (~/.claude/projects/*/memory/MEMORY.md
       if present) and summarize the persistent context I've accumulated.

  Step 2 -- Inventory the playbook.
    a) Walk base/skills/, base/rules/, base/hooks/, base/mcp/, base/agents/,
       base/commands/, base/prompts/, base/trajectories/ in the cloned playbook.
    b) For each content type, list every artifact with its slug + one-line description
       (from the SKILL.md frontmatter or h1).
    c) Cross-reference profiles/ to identify which artifacts are bundled into which
       role profile (tech-lead, backend-developer, frontend-developer, qa, research,
       product-manager, devops).

  Step 3 -- Match.
    a) For each playbook artifact, decide:
       - HAVE: I already have an equivalent (named differently). Note both names.
       - GAP: I would benefit; propose for Phase 1, 2, or 3.
       - SKIP: not relevant to my setup (justify in one sentence).
    b) For each HAVE conflict, name which version is better (mine or the playbook's)
       and why. If the playbook version is better, propose a migration path that
       preserves the user data hidden in mine.

  Step 4 -- Propose phased rollout.
    Phase 1 (install now, high-confidence): the artifacts that obviously fit. Show me
      the exact `make install PROFILE=<role>` command or the per-artifact copy steps.
      Note: the Makefile reads the profile via `PROFILE=<name>`, not `--profile`;
      `--profile` is the underlying `scripts/install.py` flag and would fail at the
      `make` layer.
    Phase 2 (try for a week, then keep or remove): items that are useful in theory but
      whose value depends on my actual workflow. Propose a one-week trial protocol.
    Phase 3 (worth discussing): items that conflict with my current setup, require a
      workflow change, or have non-obvious tradeoffs. List the tradeoff so I can decide.

Output format:

  - Markdown.
  - One H2 per phase.
  - Inside each phase, one H3 per content type (skills, rules, hooks, MCP, etc.).
  - For each artifact: bullet line in the form
      `<slug>` (`<source path>`) → `<destination path>`: one-sentence why-this-fits.
  - End with a "What I'm NOT proposing and why" section so I can sanity-check the
    selection.

After producing the audit, stop and wait for me to approve which phase to execute.
Do NOT proceed to installation without explicit per-phase approval.
```

---

## What this prompt produces

A markdown audit document, typically 1500-3000 words, that names:

- What you have today across every coding agent installed on this machine.
- What the playbook ships that would help.
- A phased rollout you can execute incrementally with `make install PROFILE=<role>` (Phase 1) followed by per-artifact copies for Phase 2 and 3.
- An explicit "not proposing X because Y" list so the agent's selection logic is visible.

## When to use it

- Before your first `make install` if you already have an established personal agent setup and don't want to blindly overwrite.
- When the playbook ships a major upstream sync (check `.sync-manifest.json` for new content) and you want to know which new artifacts apply to your workflow.
- When onboarding a new team to the playbook and the team wants a per-machine audit before standardizing.

## When NOT to use it

- Fresh machine with no existing agent setup. Just run `make install` directly.
- You want project-level files (`AGENTS.md`, `.cursor/rules/`, project hooks). Use `project-audit.md` instead.
- You only want one specific skill or rule. Copy it directly from the playbook tree; no audit needed.

## Iteration

The audit is a starting point, not a verdict. After Phase 1 lands:

1. Use the playbook for a week with the Phase 1 content.
2. Re-run this prompt with the addendum "I've used the Phase 1 install for a week; now reconsider Phase 2 against what I actually did."
3. The agent will re-grade the Phase 2 items against your observed workflow rather than its initial guess.
