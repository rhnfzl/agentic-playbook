# 0028. TargetMaterializer + unified target layout

## Status

Accepted (2026-05-25); landing in v0.5.

## Context

Through v0.4, the playbook had two ways to "install" its content into a user's environment:

1. **Home install** via `scripts/install.py --profile X`: runs the Adapter Protocol against `$HOME`, writing into `~/.claude/`, `~/.codex/`, `~/.cursor/`, etc. per-tool.
2. **Per-project init** via `scripts/playbook_init.py --target P --install-mode {pointer,symlink,copy}`: writes `target/AGENTS.md` (a steipete-style pointer) plus `target/.playbook-config.yaml` recording the chosen install_mode.

The per-project install_mode field is materially broken. Only `install_mode: pointer` is fully wired (AGENTS.md pointer refresh via `scripts/playbook_update.py`). `install_mode: symlink` and `install_mode: copy` are written to the config but no code reads them; the developer who sets one of those modes gets the same behavior as `pointer`. The v0.4 file docstring acknowledges this:

> "NOT YET DONE (queued follow-up): materializing the profile's skill set into the target per install_mode (symlink/copy). [...] For now, per-project content installation goes through `scripts/install.py --profile <name>` which writes to the user's home-dir adapters."

This is a silent gap: the config knob exists, the documentation says it works, and no one notices it doesn't until an adopter inspects `target/.agents/` and finds nothing there.

The grilling for v0.5 also surfaced three sub-decisions inside this single architectural choice (layering, storage layout, and lockfile semantics) that depend on each other.

## Decision

### Layering: augment, not replace

Per-project install **augments** the home install rather than replacing it. Both layers run; tools read both natively via parent-directory walks (Claude Code, Codex) or tool-specific lookups (Cursor, Copilot, etc.). Project-local wins for same-named content; home provides defaults.

Rationale: tools already implement this layering at the read side (parent-dir walks for AGENTS.md, `~/.claude/skills/` plus `target/.claude/skills/`, etc.). Building "replace" semantics into the playbook would fight the tool conventions. The unix dotfile pattern (`~/.X` defaults, project `.X` overrides) is the natural fit.

### Storage layout: unified `target/.agents/` canonical + per-tool projections

The target materializer writes content once into `target/.agents/{skills,rules,hooks,mcp,agents,commands,prompts}/` and then projects per-tool views from it:

```
target/
  .agents/                           canonical content (single source of truth)
    skills/<name>/                   symlink to playbook (symlink mode) or copy
    rules/<name>.md
    hooks/<name>.sh
    mcp/<name>.json
    agents/<name>.md
    commands/<name>.md
    prompts/<name>.md
  .claude/skills/    -> ../.agents/skills/        (symlink projection)
  .claude/commands/  -> ../.agents/commands/      (symlink projection)
  .claude/agents/    -> ../.agents/agents/        (symlink projection)
  .claude/hooks/     -> ../.agents/hooks/         (symlink projection)
  .claude/settings.json                            (generated; merges hooks + MCP)
  .codex/skills/     -> ../.agents/skills/        (symlink projection)
  .codex/prompts/    -> ../.agents/prompts/       (symlink projection)
  .codex/config.toml                               (generated; merges MCP)
  .cursor/rules/<name>.mdc                         (generated from .agents/rules/)
  .github/copilot-instructions.md                  (generated managed block)
  AGENTS.md                                        (managed block from .agents/rules/)
  .playbook-state.json                             (lockfile)
```

`install_mode` controls how the canonical store is populated:

- `pointer`: canonical store is empty; `target/AGENTS.md` points at the playbook (current v0.4 behavior).
- `symlink`: `.agents/skills/<name>` is a symlink to the playbook's `skills/<category>/<name>/`. Updates to the playbook propagate immediately. No deep copy.
- `copy`: `.agents/skills/<name>` is a deep copy of the playbook skill. Independent of the playbook from then on; explicit re-materialize to pick up upstream changes.

Per-tool projections (the `.claude/`, `.codex/`, `.cursor/`, `.github/`, `AGENTS.md` outputs) are always symlinks or generated derivatives, regardless of install_mode. They are owned by the playbook and regenerated on every update from the canonical store; hand-edits to projections do not survive.

Rationale: unifying on `.agents/` matches Codex's convention and keeps the canonical write/read path short. Per-tool projections handle the tools that need their own native paths (Cursor's `.mdc`, Copilot's single file, AGENTS.md managed block). The deletion test of the unification: if we delete the unified store, every per-tool projection has to maintain its own copy and consistency between them becomes the user's problem.

### Code path: separate TargetMaterializer module

The home Adapter Protocol stays focused on per-tool, home-dir installs. A new `scripts/target_materializer.py` owns the unified canonical write + projection generation. Adapters are NOT extended with target semantics.

Rationale: the deletion test. If we delete the TargetMaterializer module, the unification logic has to live inside every adapter as `if target_is_project: write_unified` branches across 10 files. Locality collapses. The seam is real.

The TargetMaterializer reuses helpers from `adapters/_writer.py` (compose_agents_md, copy_skill_payload) and `agents_md.py` (AgentsMd document type), and consumes `PlaybookContent` the same way home adapters do.

### Lockfile: track canonical + projections

`target/.playbook-state.json` is the per-target lockfile. It records both the canonical entries (`.agents/<type>/<name>`) and every projection (per-tool symlink, generated `.mdc` file, copilot file, AGENTS.md managed block).

Rationale: tracking everything makes cleanup precise. On profile narrow (e.g. dropping a skill), the materializer can walk the lockfile and remove exactly the prior entries plus their projections, instead of trying to re-derive what was there. Canonical-only tracking would leave stale projections behind on narrow operations.

## Consequences

### Good

- The previously-broken `install_mode: symlink|copy` becomes functional end to end.
- A team can choose copy-mode for a project to lock its playbook content version and check it into git; symlink-mode for personal projects that should follow the playbook live.
- Per-tool projections are derived, not authored, so adding a new tool (e.g. a future Aider that reads `target/.agents/`) does not require a new adapter; just point at the canonical.
- The canonical `.agents/` tree is grep-able: a developer can ls one directory and see the entire playbook content scoped to that project.

### Bad

- New module surface (`scripts/target_materializer.py`) that overlaps in concept with the home Adapter Protocol. Without ADR-0028 + the grilling rationale, a future reader could reasonably ask "why not extend the Adapter Protocol?" We answer in the Context section, but the mental cost is real.
- Per-tool projection paths (`.cursor/rules/X.mdc`, `.github/copilot-instructions.md`, etc.) are owned by the playbook. Hand-edits to these do not survive a re-materialize. Documented in the projection files themselves via header text.
- Lockfile carries more entries (projection rows) than strictly necessary if the recipe were "regenerate projections from canonical every time." Tradeoff for precise cleanup; revisitable later.

### Followups not addressed in v0.5

- Multi-target awareness: each target has its own lockfile. No global registry maps "which targets has this user materialized into?" If we want that, add `~/.coding-agents-playbook-targets.json` later.
- Symlink mode on Windows without dev-mode enabled: install warns, no automatic fallback to copy. Revisit if a Windows user reports friction.
- Concurrent install safety: two parallel `playbook_update.py --target X` runs. Not addressed; file locking would be a separate ADR.

## Implementation note

Lives at `scripts/target_materializer.py`, called from `scripts/playbook_update.py`. Composes content via `PlaybookContent.load(playbook_root)`, filters by the target's profile (`.playbook-config.yaml`), and writes per the install_mode value in that same config. Lockfile reads/writes go through a small helper in `target_materializer.py` rather than reusing the home `scripts/install.py` lockfile code, because the schemas differ (target lockfile carries projection entries).
