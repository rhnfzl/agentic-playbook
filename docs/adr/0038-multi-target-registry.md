---
status: accepted
date: 2026-05-25
amends: ["0022", "0025"]
related: ["0028", "0036"]
---

# ADR-0038: Multi-target registry at ~/.coding-agents-playbook-targets.json

## Status

Accepted. Implemented in v0.8.

## Context

Through v0.7 the playbook had a clean answer for one-project installs
(`.playbook-config.yaml` lives in the target; `make doctor-verify
--target=<path>` covers it) and a clean answer for global installs
(home-level adapters). It had no answer for the very common case of
"one Mac, three projects, each on a different profile."

The architecture review (May 2026) flagged this as the clearest
remaining product gap. The cross-check pass from a separate Codex
session called out the same item: "the repo still has per-target
lockfiles, but no global registry like
`~/.coding-agents-playbook-targets.json`."

Adding a machine-wide registry unblocks:

- `make targets-list`: tell me which projects have the playbook.
- `make targets-doctor`: prune missing project dirs; surface registry
  drift.
- A future `make targets-update`: iterate every recorded target and
  re-run update with the project's recorded profile, with no manual
  bookkeeping.

## Decision

A machine-wide JSON file at `~/.coding-agents-playbook-targets.json`
records every target the playbook has been bound to.

Schema (versioned for future widen):

```json
{
  "version": 1,
  "targets": {
    "<absolute target path>": {
      "profile": "<role-slug>",
      "install_mode": "pointer|symlink|copy",
      "registered_at": "ISO8601 UTC",
      "last_updated_at": "ISO8601 UTC"
    }
  }
}
```

Path keys are absolute and resolved. `registered_at` is set on the first
write and never changes; `last_updated_at` is refreshed every time
`playbook_init.py` or `playbook_update.py` writes a successful run.

The registry is best-effort: a load failure returns an empty registry,
a write failure logs a warning and does not block init/update. This
keeps existing single-target workflows zero-cost and zero-risk.

Locking is intentionally not implemented for v0.8. Concurrent installs
against different targets on the same machine are rare; if they
become load-bearing, file locking via the existing `fcntl`/`msvcrt`
scaffolding in `install.py` is the natural follow-up.

New Make targets:

- `make targets-list` prints the registry as a table.
- `make targets-doctor` prunes missing directories, then prints the
  registry with a "MISSING" / "ok" marker and the presence of
  `.playbook-config.yaml` per target.

A future `make targets-update` (deferred; not in v0.8) would iterate
the registry and run `playbook_update.py --target=<each>` so a single
command refreshes every bound project.

## Consequences

Positive:

- One-line answer to "where is the playbook installed on this Mac?"
- `make targets-doctor` surfaces deleted projects so the registry does
  not silently grow stale.
- Future cross-target automations (bulk updates, profile audits, time-
  since-last-update warnings) have a stable data source.

Negative:

- A new file in `$HOME` the user has to know about. The registry is
  documented in the README and `make help` lists the new targets, so
  the file is discoverable.
- Path-keyed storage means a `git mv` of the project root produces a
  stale entry. `prune_missing_targets()` catches the obvious case (the
  old dir is gone); a smarter rename detection (inode + content-hash
  matching) is not in v0.8.

Risk:

- The registry sits at `$HOME` and is **not** synced via dotfiles by
  default. Users who clone their dotfiles across machines should add
  this file to their sync list or expect a per-machine registry. The
  README documents this trade-off.

## Implementation

- `scripts/target_registry.py`: registry I/O (`load_registry`,
  `save_registry`, `record_target`, `forget_target`, `list_targets`,
  `prune_missing_targets`) + the two `cmd_targets_*` entry points.
- `scripts/playbook_init.py`: calls `record_target` on success.
- `scripts/playbook_update.py`: refreshes via `record_target` on every
  successful update.
- `Makefile`: `targets-list` + `targets-doctor` targets.
- 5 regression tests in `tests/lifecycle/test_lifecycle.py` covering
  record/list/prune/dedup-by-path/atomic-write paths against a
  tmpdir-redirected registry.

## Related

- ADR-0022 (per-project init customization): the registry is the
  machine-wide counterpart; each entry references a project that
  produced one `.playbook-config.yaml`.
- ADR-0025 (Profile end-to-end): the registry stores the per-target
  profile so a `make targets-update` can re-apply the right profile
  without rediscovery.
- ADR-0028 (target materializer): unchanged; the registry sits above
  the materializer, not inside it.
- ADR-0036 (three-layer content contract): future `make targets-doctor`
  variants can fan layer-3 verification across every registered target.
