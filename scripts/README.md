# Scripts

This directory holds the installer, lint scripts, decay checks, and content-management tooling for the playbook. Everything here is Python 3.11+ stdlib only (no external deps); `make` is the user-facing entry point.

## What ships in this directory

### Install + lifecycle

| Script | Purpose | `make` target |
|---|---|---|
| [install.py](install.py) | Argparse + dispatcher. Detects coding agents, prompts for target project, dispatches to per-agent adapters, manages the install lockfile + concurrency lock. | `make install`, `make list`, `make status`, `make update`, `make remove` |
| [install_lockfile.py](install_lockfile.py) | Lockfile data model (`generate_lockfile`, `load_lockfile`, `hash_file`, `hash_dir`, `entry_for`, `entry_*` classifiers). Per ADR-0024 (split out during the C1 install.py decomposition). | (used by `install.py`) |
| [install_bundles.py](install_bundles.py) | Bundle lifecycle: `run_bundle_bootstraps()` invokes each bundle's `bootstrap.sh`; `bundle_health_scripts()` + `run_bundle_health()` aggregate `health.sh` exit codes for `make doctor`. Per ADR-0026. | (used by `install.py --diagnose`) |
| [install_orphans.py](install_orphans.py) | Per-adapter orphan cleanup with ADR-0023 ownership + edit guard, ADR-0034 symlink-through guard, ADR-0036 copied_dir drift detection. | (used by `install.py`) |
| [install_verify.py](install_verify.py) | `--verify` command: walks the lockfile, parses each native config, confirms managed hooks + MCP entries match. Per ADR-0036. | `make doctor-verify` |
| [hook_native_config.py](hook_native_config.py) | Adapter shape registry (Claude / Codex / Cursor / Windsurf / Cline / Copilot native hook config schemas). Single source of truth shared by install_verify + lifecycle tests. | (library) |
| [hook_registration.py](hook_registration.py) | Hook header parsers + per-adapter shape emitters (Claude-shaped, Codex auto-promote, Cursor camelCase, Windsurf Cascade). Per ADR-0027 + ADR-0034. | (library) |
| [mcp_runtime_probe.py](mcp_runtime_probe.py) | JSON-RPC `initialize` handshake against each registered MCP server. Per ADR-0036. Honors `command`/`args`/`env`/`cwd` + 10s timeout; stdio transports only (HTTP/SSE entries skipped cleanly). | (used by `make doctor-verify`) |
| [target_materializer.py](target_materializer.py) | Writes the per-project `.agents/` tree + per-tool projections + per-target `AGENTS.md` managed block. Per ADR-0028. | (used by `playbook_init.py` + `playbook_update.py`) |
| [target_registry.py](target_registry.py) | Machine-wide registry at `~/.coding-agents-playbook-targets.json`. Per ADR-0038. | `make targets-list`, `make targets-doctor` |
| [playbook_init.py](playbook_init.py) | Per-project init: scaffolds `AGENTS.md` + `.playbook-config.yaml` in a target, registers the target. | `make init TARGET=...` |
| [playbook_update.py](playbook_update.py) | Re-applies playbook content into a previously-initialized target. Refreshes pointer header + last_reviewed; re-runs materialization per `install_mode`. | `make update` (per-project variants in roadmap) |
| [playbook_profile.py](playbook_profile.py) | `--profile <role>` filter: reads `profiles/<role>.toml`, narrows `PlaybookContent` to listed slugs, surfaces dangling-entry drift. Per ADR-0025. | (used by `install.py`) |
| [agents_md.py](agents_md.py) | The `AgentsMd` parsed type (frontmatter, pointer, sections, managed blocks). Single round-trip-able document model used by every consumer. Per ADR-0027. | (library) |

### Quality gates

`make check` runs `scripts/check.py`, which iterates the `scripts/checks/` package. 17 gates today (see `scripts/checks/__init__.py:CHECKS` for the source of truth):

| Gate | Module | Implementation |
|---|---|---|
| frontmatter | `checks/frontmatter.py` -> `frontmatter_lint.py` | Validates SKILL.md required fields. |
| agents-md | `checks/agents_md.py` -> `check_agents_md.py` | AGENTS.md governance per ADR-0013. |
| external-skill-audit | `checks/external_skill_audit.py` -> `audit_external_skill.py` | Block-by-default security audit for imported skills. |
| size | `checks/size.py` -> `size_check.py` | Skill body size budget (warns >=500, blocks >1000) per ADR-0015. |
| decay | `checks/decay.py` -> `decay_check.py` | Skill freshness bands: 60-day notice (informational), 90-day warn (`make check` flags), 180-day block (`make check` fails). Trajectory freshness uses the same bands per ADR-0044. |
| em-dashes | `checks/em_dashes.py` -> `check_em_dashes.py` | Enforces `rules/no-em-dashes.md` against authored prose. |
| no-versions-in-readmes | `checks/no_versions.py` -> `check_no_versions_in_readmes.py` | Keeps playbook version markers out of README.md / AGENTS.md. |
| skill-description-length | `checks/skill_description.py` -> `check_skill_description.py` | <=1024-char SKILL.md description (Codex schema limit). |
| hook-metadata | `checks/hook_metadata.py` -> `check_hook_metadata.py` | Every hook ships PLAYBOOK-HOOK-EVENT + PLAYBOOK-HOOK-MATCHER. |
| hook-source-unification | `checks/hook_source_unification.py` (self-contained) | Skill-owned hooks live under `skills/<cat>/<name>/hooks/`; root symlinks back. Per ADR-0035. |
| pyright-zero | `checks/pyright_zero.py` (self-contained) | Pyright errors + warnings must be zero; `# pyright: ignore` lines must carry a `# justification:` note. |
| human-html-allowlist | `checks/human_html_allowlist.py` (self-contained) | `.human-html-allowlist` patterns must not contain `$(`, backticks, `||`, `&&`, `; ` (shell-substitution risk). |

Architecture: self-contained checks (the three at the bottom) implement their logic directly. The other nine delegate via `checks.run_legacy_main()` to the legacy `scripts/<name>.py` so the legacy scripts stay shellable (e.g., `make audit` invokes `scripts/audit_external_skill.py` directly) while the wrappers in `checks/` are one delegation line each.

### Content + meta tooling

| Script | Purpose | `make` target |
|---|---|---|
| [test_adapters.py](test_adapters.py) | Smoke tests for adapter idempotency, target safety, content preservation, agent TOML conversion. Runs in tmpdirs with HOME redirected. 202 checks today. | `make test` |
| [bulk_import.py](bulk_import.py) | Imports skills + subagents from `~/.agents/skills/`, `~/.claude/agents/`, `~/.codex/agents/` into the playbook. Dry-run by default; `--apply` to commit. | (no make target; direct invocation) |
| [new_skill.py](new_skill.py) | Scaffolds `skills/<category>/<name>/SKILL.md` with frontmatter pre-filled. | `make new SKILL=<name>` |
| [promote_skill.py](promote_skill.py) | Backend for `/playbook-promote`: graduates a draft from `~/.playbook-proposals/` into the appropriate playbook artifact. | (invoked by skill) |
| [retrospective.py](retrospective.py) | Backend for `/playbook-retrospective`: walks session transcripts across Claude Code + Codex storage layouts. | (invoked by skill) |
| [eval_runner.py](eval_runner.py) | LLM-judge-driven evals for skills. Slow; intentionally split out of `make check` into its own `make eval` target. | `make eval` |
| [sync_mattpocock.sh](sync_mattpocock.sh) | Pulls `mattpocock/skills` upstream updates into `skills/imported/mattpocock/`. | `make sync-mattpocock` |
| [adapters/](adapters/) | Per-agent adapter modules. See [adapters/AGENTS.md](adapters/AGENTS.md) for the protocol contract. | (invoked by `install.py`) |
| [checks/](checks/) | Pluggable quality-gate modules (see table above). | (invoked by `check.py`) |
| [templates/](templates/) | Python + shell scaffolds the user customizes locally (workspace-status dashboard, upstream-drift report, launchd installer). Not installed by `make install`. | (manual copy) |

## Adapter module structure (`scripts/adapters/`)

Each adapter implements the `Adapter` Protocol from `scripts/adapters/_protocol.py`:

```python
class Adapter(Protocol):
    name: str
    tier: int
    def detect(self) -> bool: ...
    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]: ...
```

Tier 1 (full surface, hook-capable): `claude_code.py`, `codex.py`, `cursor.py`, `windsurf.py`, `cline.py`, `copilot.py`.
Tier 2 (rules-only): `aider.py`, `gemini_cli.py`, `pi.py`.
Tier 3 (AGENTS.md-only, declarative): 16 entries in `tier3.toml` produce `TierThreeAdapter` instances via `tier3.py`. Per ADR-0030.

Shared helpers live in:
- `adapters/_reader.py`: `load_skills`, `load_rules`, `load_hooks`, `load_mcp_configs`, `load_agents`, `load_commands`, `load_prompts`.
- `adapters/_writer.py`: `copy_skill_payload`, `materialize_mcp_sources`, `merge_managed_mcp_into_json`, `upsert_managed_block`, `agent_to_toml`, `safe_symlink_or_copy` (Windows fallback), `expand_agent_shared_placeholder`.
- `adapters/_detect.py`: `which`, `vscode_extension_present`, `resolve_target`.
- `adapters/_protocol.py`: typed contracts (`Skill`, `Rule`, `Hook`, `McpConfig`, `Agent`, `Command`, `Prompt`, `InstalledPath`, `PlaybookContent`) + the `Adapter` Protocol itself + `reconcile_managed_json_mcp` / `reconcile_managed_hook_commands`.
- `adapters/_loader.py`: re-export shim that preserves the pre-decomposition import surface.

## Common workflows

### First-time install on a fresh machine

```bash
git clone https://github.com/rhnfzl/agentic-playbook.git
cd agentic-playbook
make install                                        # detects + prompts
# or
make install AGENTS=auto TARGET=<path-to-project>   # non-interactive
```

### Per-project init

```bash
make init TARGET=/path/to/project
# Scaffolds AGENTS.md + .playbook-config.yaml in the target.
# Registers the target in ~/.coding-agents-playbook-targets.json.
```

### Bulk-import existing skills + subagents

```bash
python3 scripts/bulk_import.py             # dry-run
python3 scripts/bulk_import.py --apply     # commit
```

### Diagnose installer detection on this machine

```bash
make doctor          # which agents detected + bundle health
make doctor-verify   # lockfile vs native config vs on-disk + MCP runtime probe
make targets-list    # every target the playbook is bound to
make targets-doctor  # registry state + missing-dir pruning
```

## Templates (workspace-IP scaffolds)

`scripts/templates/` ships Python and shell scaffolds that depend on workspace-specific values and are NOT installed by `make install`. See [`scripts/templates/CUSTOMIZE.md`](templates/CUSTOMIZE.md) for the full list.

## Why Python 3.11+ stdlib only

The installer runs on a new teammate's machine before they have installed anything else. Requiring `pip install <package>` before running `make install` would defeat the "60 seconds to first usable install" claim. Stdlib-only also means the script works equally well on macOS, Linux, WSL2, and bare Windows once Python is present.

Python 3.11 is required for `tomllib` (used by `bulk_import.py` for TOML subagent conversion, `test_adapters.py` for round-trip parsing, `tier3.py` for the declarative registry, `mcp_runtime_probe.py` for codex TOML config parsing).

## How to add a new script

1. Create `scripts/<name>.py` with a Python 3.11+ stdlib-only implementation.
2. Add a docstring describing what it does, when to run it, and what flags it accepts.
3. Wire it into `Makefile` if it should be a make target. Otherwise document the invocation in this README.
4. Run `make check` (covers `scripts/*.py` for em-dash drift + pyright-zero).
5. PR per `CONTRIBUTING.md`.

## How to add a new check gate

1. Create `scripts/checks/<name>.py` returning a `CheckResult` from `run(ctx)`.
2. Either implement directly (self-contained) or delegate via `run_legacy_main()` to a legacy `scripts/<name>.py`.
3. Register in `scripts/checks/__init__.py:CHECKS`.
4. Add a row to the gates table above.

## Quality bar

- Stdlib only. No `pip install` should be required to run any script here (pyright is the one exception; it runs via `npx` in CI and is optional locally).
- Dry-run by default for any script that mutates user files. The user opts in to writes with `--apply` or similar.
- Idempotent. Re-running any script should not produce duplicates, corrupt user content, or change unrelated state.
- Verbose enough to debug. Print what the script is about to do; print what it did. Silent successes are hard to trust.

## References

- [`Makefile`](../Makefile) for the canonical entry points.
- ADR-0001 (skill format), ADR-0009 (agents directory), ADR-0010 (commands + prompts) for the formats these scripts validate.
- ADR-0024 (Adapter Protocol), ADR-0025 (Profile), ADR-0026 (MCP bundle lifecycle), ADR-0027 (AgentsMd type + hook metadata), ADR-0029 (hook reconciliation + matcher), ADR-0030 (Tier-3 TOML), ADR-0031 (loader split), ADR-0034 (cross-agent hook contract), ADR-0035 (canonical hook source), ADR-0036 (three-layer content contract), ADR-0037 (generalized hook adapter scoping), ADR-0038 (multi-target registry), ADR-0039 (per-config managed_keys hard cut + lockfile_version 3 + HTTP MCP probe) for the architectural decisions these modules implement.

### Exit codes

`scripts/install.py` returns:

- `0` -- success.
- `1` -- generic failure (one or more adapters failed, detection
  issues, missing profile, etc.).
- `3` -- incompatible lockfile detected (older lockfile present;
  upgrade in progress; per ADR-0039). The dispatcher prints the
  cleanup workflow before exiting; distinct from `1` so Make targets
  and CI scripts can distinguish "needs cleanup" from a runtime fail.
