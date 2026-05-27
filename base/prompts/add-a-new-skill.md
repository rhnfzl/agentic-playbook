# Prompt: Add a New Skill

Use this when you have a workflow you find yourself repeating and want to package it as a skill in the playbook. Paste the prompt below into your coding agent from the root of the coding-agents-playbook repo.

---

## The prompt

```
I want to add a new skill to the coding-agents-playbook. Walk me through it.

The workflow I want to package:
[ONE-PARAGRAPH DESCRIPTION OF THE WORKFLOW]

Approximate frequency:
[WEEKLY / DAILY / OCCASIONAL]

What triggers me to do this workflow:
[E.G. "When the user pastes a VCS PR URL"]
[E.G. "When I see a code-quality PR-mode gate failure"]

What category does this fit?
[engineering / productivity / observability / meta]

Please do the following:

1. Confirm whether this workflow actually meets the quality bar in CONTRIBUTING.md:
   - Does it repeat? (If only done once, suggest waiting.)
   - Is it not already covered? (Search skills/ for similar.)
   - Is the description specific enough? ("Use when X" phrasing.)
   - Would I commit to upkeep?

2. If it passes, scaffold the skill:
   `python3 scripts/new_skill.py --name <slug> --category <category>`
   This creates skills/<category>/<slug>/SKILL.md with frontmatter.

3. Walk me through the SKILL.md body:
   - Trigger ("Use when ...")
   - Steps (procedural, ordered)
   - Output shape (what does it produce)
   - When NOT to use this skill

4. Validate: run `make check` and confirm frontmatter is complete.

5. Suggest the first PR commit message and which reviewer to request
   (default: rehan, the AI Backend collaborator).

Important constraints:
- No team prefix in the skill name.
- No em dashes anywhere in the body.
- No ticket IDs (R8-*, MATCH-*) in skill descriptions or body.
- The description field must start with "Use when ..." (third-person, agent-readable).
- last_reviewed must be today's date.
- Body should be 50-150 lines. If shorter, the skill may be too simple to justify
  packaging. If longer, consider splitting into two skills.

After scaffolding, ask me to read through the body together and refine it.
```

---

## After the prompt

Once your agent finishes, you should have:

- `skills/<category>/<slug>/SKILL.md` with a complete frontmatter and a body skeleton.
- A working `make check` that doesn't complain about the new skill.
- A commit-ready change.

Open a PR with `feat(skills): add <slug>` and tag rehan/the AI Backend collaborator for review.

## Tips for a successful skill

- **Specific triggers beat broad ones.** "Use when user pastes a VCS PR URL" beats "Use for PR reviews."
- **Procedural body beats philosophy.** Steps the agent can execute beat prose about why this matters.
- **A short skill that does one thing is better than a long skill that does five.** If your skill has more than 7 steps, split it.
- **The "when NOT to use" section is load-bearing.** Without it, the skill triggers too eagerly and burns context.
