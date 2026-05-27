# Prompt: Extract Rules From Codebase

Use this when bootstrapping a playbook for a new team. The prompt below asks your coding agent to mine your codebase + existing agent memory for behavioral rules worth lifting into the shared playbook.

---

## The prompt

```
I want to extract behavioral rules from my codebase and existing agent memory.
The rules will live in rules/*.md and be distributed to every teammate via the
coding-agents-playbook installer.

Search these locations for repeated patterns that could be lifted as rules:

  1. ~/.claude/projects/<this-workspace>/memory/feedback_*.md
     (Claude's accumulated feedback memories)
  2. ~/.codex/memory/*.md
     (Codex's accumulated feedback memories, if applicable)
  3. The workspace's AGENTS.md or CLAUDE.md
  4. Any CONTRIBUTING.md, STYLE_GUIDE.md, or README in the project root
  5. Slack pin/canvas references if mentioned in memory
  6. Existing .cursorrules, .windsurfrules, or .github/copilot-instructions.md

For each pattern you find, evaluate:

  - Is this a BEHAVIORAL CONSTRAINT (rule)? Examples: "Never use em dashes,"
    "Always use VCS not GitHub," "Use P0-P4 priority not Low/Med/High."
  - Is this a WORKFLOW (skill)? Examples: "Review a VCS PR," "Triage a CI failure."
  - Is this PROJECT-SPECIFIC NOISE that should NOT be a rule? Examples: a one-time
    workaround, a personal preference unrelated to the team.

For each rule candidate, produce a draft:

  Filename: rules/<kebab-case-slug>.md (NO team/team prefix in the filename)
  Body shape:
    # <Title>
    <The rule itself, 1-2 sentences>

    ## Use instead / Why / Specific anti-patterns (as appropriate)
    <2-3 paragraphs of context>

  Constraints:
    - No em dashes
    - No ticket IDs in code or descriptions
    - Plain-language first; technical detail second
    - 30-80 lines per rule file

Report back as a table:

| Source | Pattern | Recommendation | Filename |
|---|---|---|---|
| feedback_no_em_dashes.md | "Never use em dashes" | Lift as rule | rules/no-em-dashes.md |
| feedback_bitbucket_not_github.md | "Use VCS not GitHub" | Lift as rule | rules/vcs-not-github.md |
| (one-off workaround) | "Set FOO_BAR=1 for X" | Skip (project-specific noise) | -- |

Ask me to confirm the table BEFORE writing any rule files. I want to review the
list and remove anything I do not want lifted.

After confirmation, write the approved rules to rules/<slug>.md in the playbook.
```

---

## After the prompt

Once your agent finishes, you should have:

- A table of candidate rules with recommendations.
- After confirmation, the approved rule files written.
- Ready-to-PR changes for v0.1 seed content.

## What to expect

The agent will surface patterns you may not realize you have. Some will be obvious lifts (writing style, never-push-to-develop). Some will be borderline (preferences that aren't quite team-wide). You're the filter: only lift what the team actually shares.

## Anti-pattern to watch for

Do NOT let the agent generate rules from scratch ("Here are 10 common engineering rules"). Generic rules dilute the playbook. The point is to capture YOUR TEAM's shared knowledge, not generic best practices.
