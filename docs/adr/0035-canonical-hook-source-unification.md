# ADR-0035: Canonical hook source unification (skill-owned vs root)

## Status

Accepted (2026-05-25); landed in v0.6.

## Context

The `human-html-advisory.sh` hook was authored alongside the human-html skill (`skills/meta/human-html/`) but the playbook installer scanned `hooks/` for hooks to install. Until v0.6, the canonical source lived at the user level (`~/.agents/skills/human-html/hooks/`) and the playbook's vendored copy at `hooks/human-html-advisory.sh` drifted behind. The 2026-05-25 gap analysis (F7, F23) showed that:

- Vendored `hooks/human-html-advisory.sh` was missing `CURSOR_PROJECT_DIR`, `tool_input.path` (for Cursor's `StrReplace` tool), and `.cursor/` workspace allowlist entries.
- The canonical version had a sibling Cursor wrapper (`human-html-advisory-cursor.sh`) that the playbook never shipped.
- Authors had to update both copies on every hook change. The skill owner shipped fixes upstream; the playbook never caught up.

v0.6 unifies the source so each hook has ONE canonical home and an author updates one file.

## Decision

Hooks with a skill owner live in `skills/<category>/<skill>/hooks/`. Root `hooks/<name>.sh` becomes a symlink to the skill-owned canonical. Orphan hooks (no skill owner) keep their canonical home at the root `hooks/`.

Current allocation:

```
skills/meta/human-html/hooks/
  human-html-advisory.sh          (canonical, with Cursor-aware fields)
  human-html-advisory-cursor.sh   (canonical, PLAYBOOK-HOOK-CURSOR-ONLY)
  human-html-autoindex.sh         (canonical, probes 4 skill install paths)

hooks/
  human-html-advisory.sh          -> ../skills/meta/human-html/hooks/human-html-advisory.sh
  human-html-autoindex.sh         -> ../skills/meta/human-html/hooks/human-html-autoindex.sh
  human-html-advisory-cursor.sh   -> ../skills/meta/human-html/hooks/human-html-advisory-cursor.sh
  lint-guard.sh                   (canonical; no skill owner)
  never-push-to-develop.sh        (canonical; no skill owner)
  code-review-graph-update.sh     (canonical; no skill owner)
  memory-curator-postwrite.sh     (canonical; no skill owner)
  agent-memory-session-brief.sh   (canonical; no skill owner)
  sonar-advisory.sh               (canonical; no skill owner)
  _cascade-translate.sh           (Windsurf translator helper; loader skips underscore-prefixed files)
```

Reader semantics (`scripts/adapters/_reader.py::load_hooks`):

- Reads `hooks/*.sh`, following symlinks transparently (`Path.read_text()` follows symlinks by default).
- Skips underscore-prefixed files (e.g. `_cascade-translate.sh`). Those are adapter-internal helpers, not registered hooks.
- Adapter copy operations use `shutil.copy2` which dereferences symlinks at install time, so the installed file at `~/.claude/hooks/<name>.sh` is a real file with the canonical content (not a dangling symlink).

## Consequences

### Good

- One file edit propagates to every installer-vendored copy. The human-html skill ships a Cursor wrapper; the playbook installer picks it up automatically because the symlink resolves to the canonical.
- Skill self-containment: a skill plus its hooks can be moved or copied as one unit. Future agents that consume skills (Codex USER skill root, Cursor `~/.cursor/skills/`) get hooks alongside the SKILL.md without a separate sync step.
- Authors who don't write a skill (lint-guard, never-push-to-develop, etc.) keep their canonical at the root; no forced skill creation.

### Risks / open threads

- A contributor who edits a root `hooks/*.sh` may not realize they are editing the skill-owned canonical (the symlink target). Mitigation: `git status` shows the symlink path and the modified file path is the skill-owned canonical, surfacing the indirection in the diff. Recommendation: add a `check_hook_source_unification.py` in v0.7 that fails CI if a root hook is a real file when its skill-owner counterpart exists.
- Symlinks on Windows require dev-mode enabled or admin privileges. v0.7 amends this: `scripts/adapters/_writer.py::safe_symlink_or_copy` catches the Windows `ERROR_PRIVILEGE_NOT_HELD` (1314) and falls back to a content copy (with the relative target resolved against `link_path.parent`). Windows is now best-effort rather than a non-target; Developer Mode is still recommended so layer-1 source-of-truth via symlink stays intact.
- The `_cascade-translate.sh` helper sits at the root but is NOT a hook. Future "helper" files should follow the underscore-prefix convention so the loader skips them.

## Implementation

- File moves: `hooks/human-html-advisory.sh` and `hooks/human-html-autoindex.sh` deleted; canonical bodies recreated under `skills/meta/human-html/hooks/`; root paths replaced with symlinks. New `skills/meta/human-html/hooks/human-html-advisory-cursor.sh` created with the Cursor wrapper logic.
- `scripts/adapters/_reader.py::load_hooks`: filters out underscore-prefixed files; otherwise unchanged (symlink reads work transparently).
- `scripts/hook_registration.py`: adds `is_cursor_only` and `resolve_cursor_wrapper` to honor the new PLAYBOOK-HOOK-CURSOR-ONLY / PLAYBOOK-HOOK-CURSOR-WRAPPER headers.
- Cursor adapter: copies both core + wrapper to `~/.cursor/hooks/`, registers only the wrapper (the core is invoked as a sibling by the wrapper script via `$(dirname "$0")`).
- Other adapters: skip cursor-only hooks for both copy and registration.

## Related

- ADR-0027 (PLAYBOOK-HOOK-EVENT header): predecessor convention.
- ADR-0033 (AgentsMd canonical write API): analogous pattern (one canonical author surface per domain object).
- ADR-0034 (cross-agent hook contract): v0.6 companion; defines the per-adapter shape functions that consume the canonical hook source.
- `docs/human-html/2026-05-25-research-cursor-adapter-deployment-gap-analysis.html`: F7 + F23 documented the drift this ADR resolves.
