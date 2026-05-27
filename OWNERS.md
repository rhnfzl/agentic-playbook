# OWNERS Registry

This file maps team aliases used in skill / rule / agent frontmatter `owner:`
fields to the humans who maintain them. Per Q13 v0.2 lock, owner aliases let
ownership scale with the team without forcing every artifact to name a single
individual.

## Aliases

| Alias            | Members                | Scope |
|------------------|------------------------|-------|
| `research-team`  | Rehan, +TBD            | Research workflows: data profiling, experiments, papers, RAG eval |
| `backend-team`   | Rehan, the AI Backend collaborator           | AI Backend + MCP engineering |
| `ai-platform`    | Rehan, the AI Backend collaborator           | Cross-cutting AI platform work (skills, prompts, evals) |
| `playbook-core`  | Rehan, the AI Backend collaborator           | This playbook repo itself; reviewer for all PRs |

## Individual handles

| Handle           | Name                   | VCS username |
|------------------|------------------------|--------------------|
| `rehan-8v`       | Rehan Fazal            | rehan-8v |
| `the AI Backend collaborator-8v`       | the AI Backend collaborator (TBD)            | the AI Backend collaborator-8v |

## Adding an alias

1. Edit this file: add a row to the Aliases table.
2. PR review per the standard contribution flow.
3. Once merged, skills / rules / agents can use `owner: <alias>` in frontmatter.

## Adding a member

1. Add their handle + name to the Individual handles table.
2. Add their handle to relevant alias rows.
3. PR review.

## What `owner:` means in practice

- The owner (alias or individual) is the maintainer of last resort for that artifact.
- `last_reviewed:` decay warnings ping the owner first.
- Per CONTRIBUTING.md, PRs that change a skill/rule should be approved by the owner
  OR by a generalist reviewer (with the owner getting tagged).
- If an alias-owned artifact has no responding member, the playbook-core team
  inherits it until reassigned.

## Auto-validation

The frontmatter linter (`scripts/frontmatter_lint.py`) verifies that any `owner:`
value listed in skill frontmatter exists in either the Aliases or Individual
handles tables above. (Validation extension is in v0.2.1; for v0.2 this
registry is human-curated only.)
