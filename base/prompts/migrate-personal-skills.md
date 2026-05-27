# Prompt: Migrate Personal Skills

Use this when you have a personal skill library (`~/.agents/skills/`, `~/.claude/skills/`, or similar) and want to lift the team-relevant skills into a shared playbook.

---

## The prompt

```
I have personal skills in ~/.agents/skills/ (or ~/.claude/skills/ as symlinks).
I want to migrate the team-relevant ones into the coding-agents-playbook.

First, inventory my personal skills:

  ls ~/.agents/skills/

For each skill, classify:

  TEAM-WORTHY: Encodes a workflow my teammates also do. Examples: PR review,
    CI triage, ticket grounding, scenario debugging, k8s state sweep.

  PERSONAL ONLY: Encodes a workflow only I do or that depends on my specific
    setup. Examples: homelab alerts, personal note management.

  REDUNDANT: Covered by an existing playbook skill or a mattpocock-style skill
    library. Examples: tdd, diagnose, write-a-skill if the playbook already
    has equivalents.

Report the classification as a table:

| Skill | Classification | Suggested category | Notes |
|---|---|---|---|
| code-review | TEAM-WORTHY | engineering | Lift |
| ha-alert-triage | PERSONAL ONLY | -- | Skip |
| tdd | REDUNDANT | -- | Skip (mattpocock has it) |

Ask me to confirm the table BEFORE moving anything.

After confirmation, for each TEAM-WORTHY skill:

  1. Read ~/.agents/skills/<source-name>/SKILL.md
  2. De-prefix the name (drop any team-specific prefix like "team-")
  3. Rewrite the frontmatter to match the playbook's schema:
       name, description, version (0.1.0), owner (default: me),
       last_reviewed (today), tags, scope
  4. Tighten the body if it's >150 lines.
  5. Add a "When NOT to use this skill" section if missing.
  6. Write to <playbook>/skills/<category>/<de-prefixed-slug>/SKILL.md.

Run `make check` after the migration to confirm all frontmatter is valid.

Important:
- No em dashes anywhere.
- No ticket IDs (R8-*, MATCH-*) in skill bodies.
- Default owner is my VCS handle. Ask me what to use.
```

---

## After the prompt

Once your agent finishes:

- The team-worthy subset of your personal skills is now in the playbook.
- `make check` passes.
- You have a clean PR with one commit per skill (or one bundled commit, your call).

## What NOT to migrate

- **Homelab / personal automation skills.** They are not workflows your team does.
- **One-off skills built for a single ticket.** Not enough repetition to justify packaging.
- **Skills that are exact copies of mattpocock or other established libraries.** Use the original; don't fork.
- **Skills you have not used in 90+ days.** They are dead weight; the team won't benefit.

## What to migrate

- Skills you invoke at least once a week.
- Skills that encode team-specific (or team-specific) conventions.
- Skills that 2+ teammates would also use if they knew about them.
- Setup / meta skills that help new contributors (write-a-skill, audit-docs).
