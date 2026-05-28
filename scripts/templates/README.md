# scripts/templates/

Workspace-IP scaffolds that ship in the repo but are NOT installed by `make install`. These are starting points the maintainer (or a fork) customizes locally and runs out of band.

## What ships here

See [`CUSTOMIZE.md`](CUSTOMIZE.md) (when present) for the full list and per-template customization steps.

Typical contents:

- **Workspace dashboard scaffolds** (Python + shell): a one-stop status page that shows installed skills, recent activity, decay warnings, and pending proposals. Depends on workspace-specific paths.
- **Upstream-drift report scaffolds**: compares this repo's `.sync-manifest.json` against the upstream's tagged releases. Useful for the maintainer when planning a sync; not useful for downstream consumers.
- **Cron / launchd installer scaffolds**: idempotent installers for the periodic sync (`scripts/sync_distribution.py`), the decay sweep, and the telemetry rotation. Per-OS variants (launchd for macOS, systemd for Linux).
- **New-skill / new-command scaffolds**: scaffolds used by `make new SKILL=<name>` and `make new COMMAND=<name>`. These are read by `scripts/new_skill.py` and `scripts/new_command.py`.

## Why these aren't installed

The installer's contract (per ADR-0024) is: `make install` materializes the playbook's CONTENT into agent surfaces. Operational tooling (dashboards, cron jobs, sync scripts) is the maintainer's responsibility and doesn't belong on every contributor's machine.

If a template gets useful enough to ship by default, it migrates out of `templates/` into the top-level `scripts/` directory and the installer wires it in. Until then, it lives here.

## How to use a template

1. Read [`CUSTOMIZE.md`](CUSTOMIZE.md) for the template you want.
2. Copy the file to your local override location (the customization steps name where).
3. Replace the `{{SENTINEL}}` placeholders with your workspace-specific values.
4. Run it manually or wire it into your shell config / cron.

## Related

- [`scripts/README.md`](../README.md) for the installer + lint pipeline that lives one level up.
- `scripts/sync_distribution.py` (the canonical sync) and `scripts/new_skill.py` (the canonical scaffolder) for the implementations these templates customize.
- ADR-0042 (playbook content distribution) for the sync design.
