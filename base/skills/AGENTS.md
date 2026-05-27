# Skills

Owner: Rehan
last_reviewed: 2026-05-27

## Purpose

The workflow library. Each skill is one directory containing a `SKILL.md` describing a reusable workflow with deterministic steps. Different from a rule (always-on constraint), subagent (delegated specialist), or hook (runs without agent involvement).

## What Lives Here

- `engineering/`, `productivity/`, `observability/`, `meta/`, `research/` category dirs.
- `imported/` for bulk-imported and vendored external skills (mattpocock, layers, impeccable, taste-skill). Imported skills are installed under `imported-<source>-<name>/` slugs to avoid first-party collisions.
- `README.md` enumerates the schema and the quality bar.

## Local Commands

- `make new SKILL=<name> CATEGORY=<cat>` scaffolds a new skill.
- `make check` runs frontmatter lint, size check, decay, em-dash, audit.

## Edit Rules

- One directory per skill, matching the `name:` field in frontmatter (kebab-case).
- Frontmatter: name, description, version, owner, last_reviewed required; tags, scope, allowed-tools, license optional.
- SKILL.md trigger file under 500 lines (warn) / 1000 lines (block, per ADR-0015). Deep content goes to `references/`, helpers to `scripts/`.
- Vendored skills (`imported/`) carry an upstream provenance note plus our owner field.

## Required Checks

- Frontmatter passes spec compliance (name regex, parent-dir match, semver).
- Body under size budget.
- External audit (`make audit`) clean for imported skills.
- `last_reviewed` within 90 days for actively-maintained skills.

## Required Skills

- `/playbook-new-skill` to scaffold.
- `/playbook-promote` to graduate drafts to merged.

## Choosing base vs overlays/<name> (ADR-0040)

Every new skill lands in either `base/skills/<category>/<name>/` (generic, vendor-neutral) or `overlays/<name>/skills/<category>/<name>/` (team-specific). Use the three-bucket policy:

1. **STRICT team** -> `overlays/<name>/skills/`. The skill is tied to internal services (error-tracking, CI, internal Kubernetes), uses team-only tools (VCS via team org, code-quality), or has workflows shaped by team's stack (AI Backend chat, MCP boundary). The `scope_boundary.py` check enforces this.

2. **GENERIC with team examples** -> `base/skills/`. The skill is universal but uses team as an illustrative example. The allowlist at `scripts/checks/scope_boundary_allowlist.toml` records the rationale; growth in the allowlist is a smell.

3. **HYBRID** -> split if practical (extract the team section into `overlays/<name>/skills/`); otherwise classify by PRIMARY AUDIENCE. Decision rule: "if a base-only user gets value from this skill, base; if value is only realized with team context, overlay."

`make new SKILL=<name> SCOPE=team` scaffolds under `overlays/<name>/skills/`; omit `SCOPE` (or `SCOPE=base`) for base.

## Do Not

- Add a skill that duplicates an existing one. Search `base/skills/`, `overlays/<name>/skills/`, `base/rules/`, and `overlays/<name>/rules/` first.
- Author a skill from a one-off task; wait for repetition before packaging.
- Use ticket IDs in skill descriptions or bodies.
- Land an team-specific skill in `base/skills/` without an allowlist entry; `scope_boundary.py` will fail.

## Skill install surfaces (ADR-0036 three-layer contract)

A skill in `base/skills/<cat>/<name>/SKILL.md` (or `overlays/<name>/skills/<cat>/<name>/SKILL.md`) only becomes "live" for an agent when all three layers agree.

| Layer | What it is for skills | Verified by |
|---|---|---|
| 1. Canonical source | The author's edit at `base/skills/<cat>/<name>/SKILL.md` (or `overlays/<name>/skills/<cat>/<name>/SKILL.md`), plus optional `references/` and `scripts/`. | `make check` (frontmatter + size + decay + audit) |
| 2. Materialization | What the installer writes: `~/.claude/skills/<name>/`, `~/.agents/skills/<name>/` (Codex's USER skill root + Cursor canonical), `~/.cursor/skills/<name>` symlink, `~/.codeium/windsurf/skills/<name>/`. Each gets a `.playbook-owned` marker so re-install can tell its own copy from user-authored content. | `make status` |
| 3. Runtime discovery | The agent's skill loader walking the materialization path. Most agents require a NEW chat session before the loader re-scans; the same loader pass is what surfaces the skill to a future invocation. `make doctor-verify` confirms layer 2 + the `.playbook-owned` ownership marker the next install respects; the new-session step is operator workflow, not an offline check. | `make doctor-verify` (marker + path) plus a fresh chat session for true loader discovery; `test_native_skill_install_paths` parametrized across adapters |

### Skill not loading? Three-layer debug checklist

1. **Layer 1**: `cat base/skills/<cat>/<name>/SKILL.md` (or `overlays/<name>/skills/<cat>/<name>/SKILL.md`). Frontmatter present? `make check` clean?
2. **Layer 2a**: `ls ~/.claude/skills/<name>/` (or `~/.agents/skills/<name>/` for Codex, `~/.cursor/skills/<name>` for Cursor, `~/.codeium/windsurf/skills/<name>/` for Windsurf). Does SKILL.md exist with the right body?
3. **Layer 2b**: does the materialized directory have a `.playbook-owned` marker file? If missing, the next `make install` will skip the skill as user-owned. Re-run `make install` or move the dir aside.
4. **Layer 3a**: open a NEW chat session in the target agent. Most skill loaders read the skill index at session start, not on every prompt.
5. **Layer 3b**: try a prompt that should trigger the skill description. If the loader sees the SKILL.md but the description does not match, the agent will not invoke it. Sharpen the `description:` frontmatter.

`make doctor-verify` walks layer 2 in full and the layer-2 half of layer 3 (the `.playbook-owned` marker is the playbook's ownership signal for re-install, not the agent's loader-discovery signal). Layer-3 loader discovery is what happens when a NEW chat session starts and the agent re-walks `~/.agents/skills/` (Codex), `~/.claude/skills/` (Claude), `~/.cursor/skills/` (Cursor), `~/.codeium/windsurf/skills/` (Windsurf). The offline tool cannot prove the agent picked the skill up; opening a fresh session is the proof.

### External skill loaders vs the playbook

A few install surfaces look like the playbook but are not:

- **Cursor marketplace plugins** (`/add-plugin <repo>`) use Cursor's plugin loader and live under `~/.cursor/plugins/<id>/`, not `~/.agents/skills/`. Filesystem-copying a marketplace plugin into `~/.cursor/plugins/local/` is not equivalent to a playbook install; the plugin loader resolves differently. For PR / CI / cross-agent use cases, prefer a playbook skill in `base/skills/<cat>/<name>/` or `overlays/<name>/skills/<cat>/<name>/`. Cursor marketplace plugins are still useful for Cursor-local checks (compiler errors, deslop, thermo-nuclear code quality review).
- **Codex USER skills** (`~/.codex/skills/`) are not scanned by Codex; the USER skill root is `~/.agents/skills/` per OpenAI's 2026 docs. The Codex adapter writes to the correct path.

## Owner And Freshness

Owner: Rehan. Skill owners are responsible for their own `last_reviewed`; this dir-level review covers the schema and category split.
