# meta/

Skills about the playbook itself: write-a-skill, audit-docs, decay-check, retrospective, promote, find-skills. Meta skills are how the playbook stays healthy and how new patterns get captured into it without breaking shape.

## What ships here

| Skill | What it does |
|---|---|
| `agents-md-curator/` | Maintain the per-project `AGENTS.md` managed block as rules and conventions evolve. |
| `anchored-edit/` | Use the `prefix[upto]suffix` anchored-edit pattern (per the anchored-fs MCP) for large or fragile rewrites. |
| `audit-docs/` | Audit the repo's docs (READMEs, ADRs, research) for drift, broken refs, and stale claims. |
| `docs-drift/` | Find drift between code and docs (function signatures vs docstrings, config keys vs README examples). |
| `docs-index/` | Maintain an index of where to find what across the docs tree. |
| `find-skills/` | Search the installed skill set by trigger phrase, category, or keyword. |
| `graphify/` | Convert any input into a knowledge graph artifact (skill summaries, ADR maps, codebase structure). |
| `human-html/` | Scaffold + validate HTML artifacts under `docs/human-html/` for human-in-loop review. |
| `playbook-promote/` | Graduate a draft from `~/.playbook-proposals/` into the playbook (one of the three-layer capture system steps, per ADR-0008). |
| `playbook-retrospective/` | At session-end, capture patterns that felt skill-worthy into draft proposals in `~/.playbook-proposals/`. |
| `setup-matt-pocock-skills/` | Bootstrap the mattpocock/skills upstream into the imported tree. |
| `skill-cleaner/` | Audit a skill for shape drift (frontmatter, decay, em-dashes, content tiering) and propose fixes. |
| `trajectory-canary/` | The canary trajectory the harness uses to verify the harness itself, not the playbook content. |
| `trajectory-summarizer/` | Summarize a trajectory run into a human-readable report with pass/fail and divergence per adapter. |
| `write-a-skill/` | Walk the contributor through authoring a new skill: trigger, when-NOT-to-use, workflow, output. |
| `zoom-out/` | Step back from a stuck implementation pass and rethink the approach from first principles. |

## Schema and authoring

Per `base/skills/README.md`. Meta skills are often invoked by `make` targets or slash commands rather than by description-match; they're the substrate other skills run on.

## When to add a meta skill

- The workflow improves or maintains the playbook itself (decay, audit, scaffolding, capture, promote).
- The workflow is reusable across every project the playbook is installed in.
- The workflow has a deterministic shape and a clear stopping condition.

For a workflow specific to one project, use that project's `.cursor/rules/` or `AGENTS.md` rather than a meta skill.

## Related

- `base/skills/README.md` for the skill format and category contract.
- `base/commands/README.md` for slash-command wrappers (e.g. `/playbook-promote`, `/handoff`, `/human-html`) that invoke meta skills.
- ADR-0008 (three-layer capture system) for how `playbook-retrospective` + `playbook-promote` work together.
- ADR-0049 (atlas) for how `docs-index` and atlas overlap.
