# 0016. Installer lifecycle: list / status / update / remove / drift + lockfile

## Status

Accepted (2026-05-25)

## Context

v0.2.1 installer supported `make install` (interactive detection + materialization) and `make doctor` (detection report). Users had no answers to:

- "What playbook content is installed?"
- "Did the installer write what the playbook currently says, or have I drifted?"
- "Can I roll back a specific install cleanly?"

Mature neighboring tools (Microsoft APM, skills.sh, gh skill) all expose list / status / update / remove plus lockfiles with content hashes.

## Decision

`scripts/install.py` (kept as a single dispatcher under the 700-line threshold) gains five flags:

| Flag | Function |
|---|---|
| `--list` | Walk per-adapter destination dirs and print installed playbook content |
| `--status` | Read `.playbook-lock.json`, diff against current state, report ADDED / REMOVED / CHANGED per adapter |
| `--update` | Re-materialize selected adapters; refresh lockfile |
| `--remove` | Walk `.playbook-lock.json` and unlink every recorded file |
| `--drift` | Alias of `--status` |

`ADAPTER_DEST_PATHS` table (in install.py) publishes the (dest_dir, glob_pattern) tuples per adapter. Adding a new adapter destination = adding one row.

## Lockfile

`.playbook-lock.json` generated on every successful install/update. Shape:

```json
{
  "version": "0.3.0",
  "generated_at": "2026-05-25T14:30:00+00:00",
  "target": "/path/to/project | null for global install",
  "adapters": {
    "claude-code": { ".claude/skills/<name>/SKILL.md": "<sha256>", ... },
    "codex": { ".agents/skills/<name>/SKILL.md": "<sha256>", ... }
  }
}
```

Sha256 of every materialized file enables drift detection (content change OR removal).

## Rejected alternatives

- Splitting `install.py` into `install_cmds/<name>.py` per subcommand: deferred; install.py stays a flat dispatcher until it crosses 700 lines.
- Adopting Microsoft APM's manifest schema for lockfile interop: deferred to optional v0.x (per v0.3 plan; Phase 5 only after internal governance stabilizes).
- Per-adapter lockfiles (one per adapter): rejected; a single global lockfile is simpler to diff and rollback.

## Consequences

- Teammates can answer "what is installed where" in one command (`make list`).
- Drift between playbook source and adapter dest is visible (`make status`).
- Clean uninstall is possible (`make remove`), preserving the user's other content.
- `make update` becomes the normal sync motion; `make install` is the first-time setup.

## Related

- v0.3 plan: scope row 5
- Microsoft APM: https://github.com/microsoft/apm (concepts borrowed, schema not adopted)
- ADR-0003 (custom installer over Ruler)
