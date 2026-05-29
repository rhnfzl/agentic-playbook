# Scripts

Owner: Rehan
last_reviewed: 2026-05-29 (marketplace emitter package added; ADR-0043)

## Purpose

Python scripts that power the installer, linters, checks, and lifecycle commands. These are the engine of the playbook; ADR-0003 records the choice to own the installer rather than depend on Ruler/skills.sh.

## What Lives Here

- `install.py` and `adapters/` for materializing playbook content per agent.
- `install_verify.py` for `--verify` (ADR-0036 layer-3 verification); `hook_native_config.py` is the adapter shape registry it consumes.
- `frontmatter_lint.py`, `check_agents_md.py`, `audit_external_skill.py`, `size_check.py`, `decay_check.py`, `check_em_dashes.py` for `make check`.
- `bulk_import.py`, `new_skill.py`, `promote_skill.py`, `retrospective.py`, `new_trajectory.py` for authoring lifecycle.
- Trajectory work (ADR-0044, ADR-0045, ADR-0046):
  - `trajectory_matcher.py` evaluates the DSL primitives against a `TraceRecord`.
  - `trajectory_judge.py` defines the `JudgeClient` Protocol and `evaluate_judge` for the LLM-judge half of the hybrid contract.
  - `trajectory_harness.py` runs the matrix; `_evaluate_cell` is the per-cell decision tree that honors cost ceilings, retries, and the hybrid contract.
  - `trajectory_verify.py` is the single-trajectory inner-loop tool.
  - `trajectory_calibrate.py` reports rubric score range across N runs; isolates judge infra errors from the noise metric.
  - `trajectory_coverage.py` emits the ADR-0044 reject-if coverage ratio.
  - `trajectory_record.py` spawns a live Claude Code session and drafts a `<scenario>.yaml.draft` (or `.draft.2`, `.draft.3` ...) plus the JSONL fixture for the author to edit.
  - `adapters/trace_record.py` defines the normalized cross-adapter trace shape (NamedTuples + `KNOWN_TRACE_ADAPTERS`).
  - `adapters/claude_code_trace.py` is the canonical OTel parser used by BOTH the fixture replay (`parse_otel_jsonl`) and the live provider; exports `spans_from_text` + `events_from_text`.
  - `adapters/claude_code_provider.py` is the Phase 2B live provider; spawns `claude -p` under a default tool allowlist (`PHASE2_LIVE_DANGEROUS=1` opts into `--dangerously-skip-permissions` with a stderr warning per spawn).
  - `adapters/anthropic_judge_client.py` calls the Anthropic Messages API via stdlib `urllib` to score rubrics; surfaces transport failures via `JudgeResult(is_infra_error=True)`.
- `test_adapters.py` smoke tests.
- `playbook_init.py`, `playbook_update.py` for per-project init.
- `sync_distribution.py` for distributing `base/` to an external destination per ADR-0042. Scheduled via the wrapper in `templates/distribution-cron.example.sh`; runbook at `docs/runbooks/distribution-sync-cron.md`. Calls `marketplace_config.run_marketplace_emit()` after content sync when `[marketplace]` is configured in the operator manifest.
- `marketplace/` package for emitting per-agent marketplace catalogs + per-profile plugin manifests at the destination per ADR-0043. Public surface lives in `marketplace/__init__.py` (`emit`, `main`, `TOOL_VERSION`, `EmitterConfig`, the `Profile` union, the `EmitError` hierarchy). Idempotent: re-emit on unchanged content writes zero files. Materializes (does NOT symlink) plugin content into the destination so cross-OS portability is preserved. Exits with code 5 on reserved-name collision, slug-validation failure, path-safety violation, or materialize failure.
- `marketplace_emitter.py` for the back-compat CLI shim that re-exports the public surface from the `marketplace/` package and forwards to `main()`. Direct `python3 scripts/marketplace_emitter.py --help` continues to work for ad-hoc invocations.
- `marketplace_config.py` for the typed facade `sync_distribution.py` calls. Constructs `EmitterConfig` from a manifest-like Protocol-typed input and invokes `emit()`; keeps `sync_distribution.py` decoupled from the package's internal layout.
- Supply-chain security (ADR-0047):
  - `audit_security.py` is the standalone CLI; wraps three sources (Snyk `snyk-agent-scan`, `agent-skill-evaluator`, in-house DDIPE detector) plus emits the AI-BOM. Soft-by-default; `STRICT_SECURITY=1` escalates skipped wrappers to errors.
  - `security/mcp_scan_wrapper.py`, `security/agent_skill_evaluator_wrapper.py`, `security/ddipe_detector.py`, `security/ai_bom.py` are the wrappers and BOM emitter.
- Skill telemetry (ADR-0048):
  - `skill_telemetry_report.py` is the per-skill CLI (30d trigger count, p50/p95 latency, last fired, total tokens).
  - `telemetry/pyotel_collector.py` is the stdlib OTLP/HTTP receiver; `telemetry/ingest.py` is the JSONL aggregator. `telemetry/__init__.py` exposes `is_enabled()` so every consumer respects `TELEMETRY=off`.
  - `telemetry/otel_collector/` ships the docker-compose recipe + `otelcol-contrib` config for users who prefer the industry-standard container path.
  - `decay_check.py` adds a usage-based decay layer that is silent when telemetry is off.
- `skill_identity.py` is the canonical join key for "which skill is this?". Any new code that aggregates per-skill data across consumers (decay, audit, telemetry, atlas) should call `skill_identity(skill_md)` instead of inventing its own answer from `parent.name` or frontmatter `name`. The parser semantics match `adapters._reader._parse_frontmatter` so existing callers can migrate without behavioral surprises.
- Why Atlas (ADR-0049):
  - `build_atlas.py` walks ADRs + skills + trajectories and renders `docs/atlas/`. Reads AI-BOM + telemetry aggregates at render time; missing signals degrade silently.
  - `atlas/graph_builder.py` produces the JSON adjacency; `atlas/template_engine.py` is the f-string + html.escape helper (no Jinja, no PyYAML).
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
- Exit codes: 0 pass, 1 fail. Warnings print but exit 0. **Carve-out for `sync_distribution.py`**: also uses 2 (lock held by another sync), 3 (IO error during copy), 4 (reverse direction not implemented), 5 (marketplace emit safety failure per ADR-0043: reserved catalog name, slug-validation, path-safety, materialize failure) so the cron wrapper can distinguish operational from logical failures. The `marketplace/` package and its shim use the same set (0/1/5); the EmitError subclasses in `marketplace/errors.py` carry the exit code as a class attribute. Document any other carve-outs in the script's module docstring.
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
- Modify files outside the playbook repo from scripts run in the repo. **Carve-outs**:
  - **Distribution sync**: `sync_distribution.py` and the `marketplace/` package write to an operator-configured external destination by design (ADR-0042, ADR-0043). Their boundary is the manifest's `[destination].path` and the path-traversal safety check in `_resolve_sources` (sync) plus `_within(target, base)` in `marketplace/content_ops.py` (emitter materialization).
  - **Telemetry (ADR-0048)**: `telemetry/pyotel_collector.py`, the docker collector in `telemetry/otel_collector/`, and the `telemetry/ingest.py` consumer all read or write under `~/.coding-agents-playbook/telemetry/` (or `$TELEMETRY_DIR` when set). The destination is operator-controlled, the JSONL contract is privacy-bounded (banned-prefix list at `telemetry/_otlp_record.py`), and the entire layer is off unless the user explicitly opts in. The boundary is `telemetry.storage_path()`.
  Nothing else in `scripts/` should reach outside `$PLAYBOOK_HOME`.
- Skip `--help` when adding a new entry point.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a script or changing the CLI surface.
