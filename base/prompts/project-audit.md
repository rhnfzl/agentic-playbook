# Prompt: Project-Level Audit

Paste the prompt below into your coding agent (Claude Code, Codex CLI, Cursor, Windsurf) **from the root of the project you want to bind to the playbook**. The agent walks the project tree, identifies what the project is (language, framework, agent surface already present), and proposes project-level playbook content: `AGENTS.md`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, project-scoped hooks, project-scoped MCP config.

Different from `global-audit.md` (which proposes user-level installs) and from `make init TARGET=<path>` (which scaffolds a single pre-chosen profile). This prompt is for the "what playbook content fits THIS specific project" decision.

---

## The prompt

```
I want you to audit THIS project and propose project-level agentic-playbook content
(an AGENTS.md, per-tool rule files, project hooks, project MCP config, project-scoped
skills if any) that would land in the working directory and apply to anyone working
on this project.

Constraints before you start:

  1. Do NOT install or write any files in this pass. Planning only.
  2. Propose changes in a single phased list: Phase 1 (uncontroversial, ship now),
     Phase 2 (worth discussing with the team).
  3. For every proposed file, show the exact path (relative to repo root) and a 3-line
     preview of the content I'd write. I'll decide whether to land it.
  4. Honor existing conventions. If the project already has an AGENTS.md, .cursorrules,
     .windsurfrules, .github/copilot-instructions.md, etc., propose additions or edits,
     not replacements.
  5. Detect the project's language and framework (package.json, pyproject.toml, go.mod,
     Cargo.toml, etc.) and pick playbook content that fits.

Walk in this order:

  Step 1 -- Identify the project.
    a) Read package.json / pyproject.toml / go.mod / Cargo.toml / Gemfile / pom.xml
       (whichever exists) and name the primary language + framework.
    b) Read any existing AGENTS.md, .cursorrules, .windsurfrules,
       .github/copilot-instructions.md, .clinerules, .agents-md-ignore. Summarize what
       conventions are already enforced.
    c) Read README.md, CONTRIBUTING.md, docs/ (if present) to understand the project's
       development conventions (commit-message shape, branch naming, code-review
       process, test discipline).
    d) Read recent git log (last 50 commits) to identify recurring patterns: do they
       use Conventional Commits? Do PR descriptions follow a template?

  Step 2 -- Inventory the playbook's project-applicable content.
    a) Walk base/rules/. List every rule with a one-line description.
    b) Walk base/hooks/. List hooks that make sense at the project level (lint-guard,
       never-push-to-develop, sonar-advisory) vs hooks that are user-level only.
    c) Walk base/mcp/. Identify any MCP server configs that would help THIS project
       (e.g. error-tracking MCP for a project with Sentry; Atlassian MCP for a project
       with Jira issues referenced in commits).
    d) Walk profiles/. Identify which role profile best matches this project's primary
       workflow.

  Step 3 -- Propose project-level files.
    For each proposed file, specify:
      - Exact path relative to repo root.
      - Whether it's a new file or an edit to an existing one.
      - The content (or, for managed-block edits, the content between the markers).
      - One sentence on WHY this fits this project specifically.

    Common proposals to consider:
      - AGENTS.md at repo root (or edit if it exists) with managed-block content for
        the rules in `base/rules/` that apply.
      - .cursor/rules/<rule>.mdc files (one per relevant rule) with alwaysApply: true.
      - .github/copilot-instructions.md (concatenation of relevant rules + project
        conventions).
      - .windsurfrules (managed block).
      - .clinerules (managed block).
      - .github/hooks/<hook>.sh + .github/hooks.json for any Copilot hooks that fit.
      - .cursor/hooks/<hook>.sh + .cursor/hooks.json for project-scoped Cursor hooks.
      - .cursor/mcp.json or .windsurf/mcp.json for project-scoped MCP servers.
      - .playbook-config.yaml at repo root that records which profile this project is
        bound to (so `make update TARGET=$(pwd)` knows what to refresh).

  Step 4 -- Show me the `make` command.
    After the audit, name the single `make init TARGET=$(pwd) --profile <best-fit>`
    command that would do Phase 1 in one step, and the per-file diffs that Phase 2
    would add on top.

Output format:

  - Markdown.
  - One H2 for each proposed file (or edit).
  - Each H2 contains: path, new-or-edit, 3-line preview, why-this-fits, phase.
  - End with "What I'm NOT proposing and why."
  - End with the single `make init ...` command for Phase 1.

After producing the audit, stop and wait for me to approve before doing anything.
```

---

## What this prompt produces

A markdown plan of 800-2000 words that names:

- Every file the playbook would add or edit at the project level.
- A 3-line preview of each file so you don't have to open it to know what's coming.
- One `make init` command that bundles Phase 1 (so you can land it atomically).
- An explicit list of files NOT being proposed, with reasons.

## When to use it

- New project that doesn't yet have agent conventions in place.
- Existing project where the team is debating which agent rules to formalize.
- Project where multiple teammates use different coding agents and you want one source of truth (`AGENTS.md`) that all of them respect.

## When NOT to use it

- You want user-level installs (apply across every project on this machine). Use `global-audit.md` instead.
- The project already has a thorough agent surface and you only want to update the playbook content. Use `make update TARGET=<path>` directly.
- A new skill or rule is missing; first add it to the playbook (`make new SKILL=<name>`), then re-run this prompt.

## Iteration

After Phase 1 lands:

1. Work in the project for a week with the new project-level files in place.
2. Re-run this prompt with "I've used the Phase 1 setup for a week; reconsider Phase 2 against what I actually did."
3. The agent grades Phase 2 items against observed workflow rather than initial guesses.
