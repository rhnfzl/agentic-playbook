# Scripts

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Python scripts that power the installer, linters, checks, and lifecycle commands. These are the engine of the playbook; ADR-0003 records the choice to own the installer rather than depend on Ruler/skills.sh.

## What Lives Here

- `install.py` and `adapters/` for materializing playbook content per agent.
- `install_verify.py` for `--verify` (ADR-0036 layer-3 verification); `hook_native_config.py` is the adapter shape registry it consumes.
- `frontmatter_lint.py`, `check_agents_md.py`, `audit_external_skill.py`, `size_check.py`, `decay_check.py`, `check_em_dashes.py` for `make check`.
- `bulk_import.py`, `new_skill.py`, `promote_skill.py`, `retrospective.py` for authoring lifecycle.
- `test_adapters.py` smoke tests.
- `playbook_init.py`, `playbook_update.py` for per-project init.
- `templates/` Python script scaffolds.

## Local Commands

- Each script supports `--help`. Long-running scripts also support `--dry-run` where applicable.
- `make check` invokes the lint/check pipeline.
- `make test` runs `test_adapters.py`.
- `make doctor` invokes `python3 scripts/install.py --diagnose` for the detection map.
- `make doctor-verify` invokes `python3 scripts/install.py --verify` for the ADR-0036 layer-3 audit (lockfile vs native config vs on-disk).

## Edit Rules

- One concern per script. install.py is now orchestration-only (argparse + lifecycle commands + lock); shape contracts live in `hook_native_config.py`, verification in `install_verify.py`. New install-time concerns belong in their own module rather than further inline growth of install.py.
- No PyYAML dependency for core scripts (parse YAML naively); the playbook targets dependency-light.
- Exit codes: 0 pass, 1 fail. Warnings print but exit 0.
- Output goes to stdout for normal flow, stderr for warnings/errors.
- READMEs and AGENTS.md files must not name a playbook version. `check_no_versions_in_readmes.py` enforces this. Release-flavoured content belongs in `CHANGELOG.md`, `RELEASING.md`, or `docs/adr/`.

## Required Checks

- `ruff check scripts/` clean (no rule violations).
- `ruff format scripts/` clean.
- `make check` includes the `pyright-zero` gate: pyright must report 0 errors AND 0 warnings across `scripts/`, `tests/`, and `mcp/anchored-fs/`. Every `# pyright: ignore[...]` must be paired with a `# justification: <one sentence on why this is safe>` comment on the same line. The justification keeps suppressions visible during review.

## Required Skills

- `/playbook-doctor` for diagnosing install issues.

## Do Not

- Add external dependencies casually. Each new dep is a new install burden.
- Modify files outside the playbook repo from scripts run in the repo.
- Skip `--help` when adding a new entry point.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a script or changing the CLI surface.
