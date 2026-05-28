# Scripts

Owner: Rehan
last_reviewed: 2026-05-28

## Purpose

Python scripts that power the installer, linters, checks, and lifecycle commands. These are the engine of the playbook; ADR-0003 records the choice to own the installer rather than depend on Ruler/skills.sh.

## What Lives Here

- `install.py` and `adapters/` for materializing playbook content per agent.
- `install_verify.py` for `--verify` (ADR-0036 layer-3 verification); `hook_native_config.py` is the adapter shape registry it consumes.
- `frontmatter_lint.py`, `check_agents_md.py`, `audit_external_skill.py`, `size_check.py`, `decay_check.py`, `check_em_dashes.py` for `make check`.
- `bulk_import.py`, `new_skill.py`, `promote_skill.py`, `retrospective.py`, `new_trajectory.py` for authoring lifecycle.
- `trajectory_matcher.py` (DSL evaluator), `trajectory_harness.py` (matrix runner; pluggable trace_provider seam for Phase 2 live spawn), `trajectory_verify.py` (single-trajectory inner-loop tool) for ADR-0044 trajectory work. `adapters/trace_record.py` is the normalized cross-adapter trace shape; `adapters/claude_code_trace.py` is the Phase 1 OTel JSONL shim.
- `test_adapters.py` smoke tests.
- `playbook_init.py`, `playbook_update.py` for per-project init.
- `sync_distribution.py` for distributing `base/` to an external destination per ADR-0042. Scheduled via the wrapper in `templates/distribution-cron.example.sh`; runbook at `docs/runbooks/distribution-sync-cron.md`. Calls `marketplace_emitter.emit()` after content sync when `[marketplace]` is configured in the manifest.
- `marketplace_emitter.py` for emitting per-agent marketplace catalogs + per-profile plugin manifests at the destination per ADR-0043. Idempotent. Symlinks plugin content back into `base/` (never copies). Exits with code 5 on reserved-name collision or symlink escape.
- `templates/` Python script scaffolds + the distribution wrapper / manifest example.

## Local Commands

- Each script supports `--help`. Long-running scripts also support `--dry-run` where applicable.
- `make check` invokes the lint/check pipeline.
- `make test` runs `test_adapters.py`.
- `make doctor` invokes `python3 scripts/install.py --diagnose` for the detection map.
- `make doctor-verify` invokes `python3 scripts/install.py --verify` for the ADR-0036 layer-3 audit (lockfile vs native config vs on-disk).

## Edit Rules

- One concern per script. install.py is now orchestration-only (argparse + lifecycle commands + lock); shape contracts live in `hook_native_config.py`, verification in `install_verify.py`. New install-time concerns belong in their own module rather than further inline growth of install.py.
- No PyYAML dependency for core scripts (parse YAML naively); the playbook targets dependency-light.
- Exit codes: 0 pass, 1 fail. Warnings print but exit 0. **Carve-out for `sync_distribution.py`**: also uses 2 (lock held by another sync), 3 (IO error during copy), 4 (reverse direction not implemented), 5 (marketplace emit safety failure: reserved name or symlink escape per ADR-0043) so the cron wrapper can distinguish operational from logical failures. `marketplace_emitter.py` uses the same set (0/1/5). Document any other carve-outs in the script's module docstring.
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
- Modify files outside the playbook repo from scripts run in the repo. **Carve-out for distribution sync**: `sync_distribution.py` and `marketplace_emitter.py` write to an operator-configured external destination by design (ADR-0042, ADR-0043). Their boundary is the manifest's `[destination].path` and the path-traversal safety check in `_resolve_sources` (sync) plus `_within(target, base_dir) and _within(base_dir, destination)` (emitter symlinks); nothing else in `scripts/` should reach outside `$PLAYBOOK_HOME`.
- Skip `--help` when adding a new entry point.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a script or changing the CLI surface.
