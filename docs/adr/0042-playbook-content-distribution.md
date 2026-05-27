# 0042. Playbook content distribution via manifest-driven sync

## Status

Proposed (2026-05-27); landing in v0.13.

## Context

ADR-0040 split the playbook into `base/` (generic, portable) and `overlays/<name>/` (workspace-specific). The split makes `base/` a clean candidate for external distribution: a downstream destination repo can receive the portable subtree without the team-specific layer.

Three reasons a maintainer might want to publish `base/` to an external destination:

- **Open-source release:** the playbook's portable patterns (skills, rules, hooks, agents, MCPs, commands, prompts) are valuable to anyone running coding agents, not just the team that authored them.
- **Per-team distribution:** another team inside the same org or a partner team can install only `base/` and add their own overlay alongside.
- **Backup or mirror:** an off-site mirror at a different VCS provider acts as durable archive in case the primary repo loses availability.

The mechanism must satisfy four constraints:

### Constraint 1: scrub layer, not raw copy

Even after the base + overlay split, `base/` still has peripheral references that are appropriate inside the playbook's home repo but inappropriate at the destination. Examples include ticket-tracker IDs in example URL forms, internal hostnames in example configurations, and team-specific examples used to illustrate generic rules. A raw copy ships these references through. A scrub layer of regex substitutions cleans the periphery uniformly without per-file edits.

### Constraint 2: destination-only content must survive

The destination repo has its own additions that do not exist in this repo: license file, destination-specific README, optional `overlays/<other>/` content, CI configuration matching the destination's host. The sync must not delete those on each run.

### Constraint 3: audit trail

Re-running sync three months later, a reviewer needs to know which source commit produced the destination's current state, and which scrub-rules version applied. Without a recorded audit trail, divergence is invisible until something breaks.

### Constraint 4: scheduled execution

The sync runs on a schedule (cron / launchd), unattended. Failure must surface (notification, log file) rather than fail silently. Overlap must abort cleanly when two scheduled runs collide. The script must be idempotent so a re-run on the same source commit is a no-op.

## Decision

### Script: `scripts/sync_distribution.py`

A standalone Python script (stdlib + `tomllib` only) that reads a manifest, computes the destination delta, applies scrub rules, and writes the result. The script never auto-commits and never auto-pushes; the destination's working tree is updated, the user reviews via `git diff`, then commits and pushes manually.

### Manifest schema

```toml
[destination]
path = "/absolute/path/to/destination/repo"
require_clean_git = true

[sources]
allowlist = [
  "base/",
  "scripts/sync_distribution.py",
  "scripts/install.py",
  "scripts/install_lifecycle.py",
  "scripts/install_lockfile.py",
  "scripts/install_bundles.py",
  "scripts/install_orphans.py",
  "scripts/checks/",
  "scripts/hook_registration/",
  "scripts/playbook_init.py",
  "scripts/playbook_update.py",
  "scripts/playbook_profile.py",
  "scripts/scope_resolution.py",
  "scripts/target_materializer.py",
  "scripts/target_registry.py",
  "scripts/agents_md.py",
  "scripts/install_lockfile.py",
  "scripts/adapters/",
  "scripts/sync_curated_skills.py",
  "scripts/sync_mattpocock.sh",
  "scripts/new_skill.py",
  "scripts/promote_skill.py",
  "scripts/check_em_dashes.py",
  "scripts/check_agents_md.py",
  "scripts/size_check.py",
  "scripts/decay_check.py",
  "scripts/frontmatter_lint.py",
  "scripts/audit_external_skill.py",
  "scripts/check_skill_description.py",
  "scripts/hook_source_unification.py",
  "scripts/hook_metadata.py",
  "scripts/eval_runner.py",
  "scripts/bulk_import.py",
  "scripts/templates/",
  "scripts/__init__.py",
  "tests/",
  "docs/adr/",
  "Makefile",
  "VERSION",
  ".gitattributes",
  "CONTEXT.md",
  "CHANGELOG.md",
  "TOOLS.md",
  "AGENTS.md",
]
denylist = [
  # specific files in allowlisted dirs that should not flow
]

[scrubs]
patterns = [
  # ticket-tracker IDs
  { match = '\\b(R8|MATCH)-\\d+\\b', replace = "[ticket]" },
  # team identifiers (case-sensitive whole-word)
  { match = '\\bteam\\b', replace = "the team", case_insensitive = false },
  { match = '\\binternal-host\\b', replace = "internal-host", case_insensitive = false },
  # VCS / CI / observability vendor mentions
  { match = "VCS", replace = "VCS" },
  { match = "CI", replace = "CI" },
  { match = "code-quality", replace = "code-quality" },
  { match = "error-tracking", replace = "error-tracking" },
  # internal hostnames + customer-specific example domains
  # (extended per-workspace; defaults shown here are starting point)
]
```

Keys are TOML strings; values are documented inline. The manifest lives OUTSIDE the playbook repo (in the operator's own workspace) so each downstream maintains their own destination + scrub set. The playbook ships an example manifest in `docs/templates/distribution-manifest.example.toml` for reference.

### Idempotent three-phase execution

1. **Validate:** destination is a clean git working tree (override via `--allow-dirty`), source is on an expected branch, manifest parses, lock file is not already held.
2. **Copy with scrub:** each source file is read, run through every applicable scrub pattern in order, written to destination at the same relative path. Files in destination not in source allowlist are preserved (this is how destination-only content survives).
3. **Audit:** write `.sync-manifest.json` to destination with source commit SHA, sync timestamp, scrub-rules content hash, allowlist content hash. Subsequent syncs compare hashes to flag manifest drift.

### Audit file schema

```json
{
  "source_repo": "git@<vcs-host>:<org>/<repo>.git",
  "source_commit": "abc123...",
  "source_branch": "develop",
  "synced_at": "2026-05-27T09:00:00Z",
  "scrub_rules_hash": "sha256:...",
  "allowlist_hash": "sha256:...",
  "tool_version": "sync_distribution.py v1.0"
}
```

### Lock file + overlap prevention

The script writes `/tmp/playbook-distribution-sync.lock` on start, removes on exit. A second invocation while the first is running aborts cleanly with exit code 2 and a clear message. Stale locks (older than 1 hour) auto-clear so a crash does not leave the system in a permanent locked state.

### Failure surface

On non-zero exit (validation failure, scrub error, write error), the script writes the full traceback to `~/Library/Logs/playbook-distribution-sync.log` (creates the parent dir if absent) and calls `osascript -e 'display notification ...'` to surface a native macOS notification. The cron / launchd wrapper script captures the script's exit code and propagates.

### Memory transfer sub-command

`python3 scripts/sync_distribution.py memory --manifest <path>` reads a separate `[memory]` table in the manifest:

```toml
[memory]
source_dir = "/Users/.../memory/"
destination_dir = "/Users/.../memory/"
allowlist = [
  # entry slugs to port; everything else stays put
  "feedback_writing_style",
  "feedback_no_em_dashes",
  # ...
]
denylist = [
  # entry slugs to explicitly exclude even if allowlist would include
]
```

The same scrub engine applies to memory entries. The destination's `MEMORY.md` index is regenerated from the ported entries.

### Cron / launchd installation

The playbook ships `scripts/templates/distribution-cron.example.sh` as a wrapper that:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$PLAYBOOK_HOME"
python3 scripts/sync_distribution.py --manifest "$DISTRIBUTION_MANIFEST" || {
  /usr/bin/osascript -e "display notification \"Sync failed; see ~/Library/Logs/playbook-distribution-sync.log\" with title \"Playbook distribution\""
  exit 1
}
```

The user installs this via `crontab -e` (or a `launchd` plist for wake-from-sleep catch-up behavior). Documented in `docs/runbooks/distribution-sync-cron.md`.

### Direction-flip preserved via flag stub

The script accepts `--direction reverse` that initially exits with "not implemented." The argument parser, the help text, and a `[reverse_direction]` placeholder in the manifest all exist from day one. When a downstream becomes canonical, the implementation fills in; no re-architecture, no manifest schema break.

## Consequences

### Good

- Auditable: manifest is explicit, destination's `.sync-manifest.json` records source SHA + scrub-rules hash + sync timestamp.
- Idempotent: re-running on the same source commit with the same manifest is a no-op (assuming no destination drift).
- Destination-only content survives: only allowlisted paths are written; everything else is left alone.
- Scrub layer handles peripheral references uniformly, without per-file edits, and the regex list is centralized in one manifest file.
- Direction-flip future state is preserved cheaply.
- Stdlib-only: installs unchanged across both the source playbook and any destination.
- Scheduled-friendly: lock file, exit codes, notifications, log file all in place from the start.

### Bad

- Operator must run sync explicitly via cron / manual invocation. A pre-push prompt in the source repo is out of scope; manual discipline carries.
- Scrub rules need ongoing maintenance. New peripheral references emerging in future content require manifest updates. Stale scrub rules leak.
- Destination path is hardcoded in the manifest; moving the destination on disk requires editing the manifest.
- Memory port is a sub-command, not bundled. Operator runs `sync_distribution.py` then `sync_distribution.py memory` separately.
- macOS notification is platform-specific; on Linux the wrapper would call `notify-send` instead. The script logs identically on both; the wrapper script handles the platform branch.

### Trade-offs considered and rejected

- **`git subtree push`:** cleaner history but no content filter. The destination would receive source-specific paths. Also conflates "history sync" with "content selection" which are different operations.
- **CI cron in the source repo:** more automatic but couples source CI to destination VCS credentials, adds operational complexity, and obscures the audit trail. Reverses the "deliberate operation" framing.
- **No automation; hand-curated copies:** lowest tooling cost, highest discipline cost. Recipe for drift within weeks.
- **Auto-commit + auto-push from the script:** removes the human review checkpoint. A scrub-rule gap then ships to the destination immediately. The cost of a manual `git commit && git push` per sync is small; the cost of an accidental leak to a public destination is large.

### Risks

- **Conservative scrubs miss patterns.** First-day scrub list is best-effort; new patterns surface on the first sync's diff review. The script's idempotency makes iteration cheap (run, review, edit manifest, re-run).
- **Manifest is operator-owned and lives outside the repo.** If the operator loses their manifest, the audit trail in the destination's `.sync-manifest.json` carries the rule hashes but not the rules themselves. Backup discipline is the operator's responsibility.
- **Cron skip on laptop sleep.** macOS cron does not catch up on missed runs. The operator can switch to `launchd` `StartCalendarInterval` with `RunAtLoad` if catch-up matters.

## References

- ADR-0040 (base + overlay subtree split): this ADR depends on the `base/` subtree existing as a clean portable boundary.
- ADR-0014 (external source policy): the inverse direction (pulling vendored content INTO the playbook). The same discipline (pinned source, explicit transformation, audit trail) applies in reverse here.
- ADR-0019 (mattpocock frontend imports and sync): the `SOURCES.toml` + pinned-SHA + PROVENANCE pattern from skill imports has the same shape as the manifest here.
- ADR-0041 (content tiering guardrails): the `scope_boundary` and `ignored_containment` checks reduce the surface area the scrub layer must clean (cleaner `base/` means fewer scrub patterns needed).
