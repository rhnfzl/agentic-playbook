# scripts/checks/

The 17 pluggable quality-gate modules that `make check` runs against the playbook. Each module exports a `run(ctx) -> CheckResult` function; `scripts/check.py` iterates the registry in `scripts/checks/__init__.py:CHECKS` and aggregates exit status.

Module shape is split between:

- **Self-contained checks** that implement their logic directly inside `scripts/checks/<name>.py` (the three at the bottom of the table).
- **Delegating checks** that call `capture_legacy_main()` (from `scripts/checks/_legacy.py`) into a legacy `scripts/<name>.py` so the standalone CLI (e.g. `make audit` invoking `scripts/audit_external_skill.py` directly) and the gate share one implementation.

## Gates today

| Gate | Module | Implementation |
|---|---|---|
| frontmatter | `frontmatter.py` | -> `frontmatter_lint.py`. Validates SKILL.md / agents / commands / prompts required fields. |
| agents-md | `agents_md.py` | -> `check_agents_md.py`. AGENTS.md governance per ADR-0013. |
| external-skill-audit | `external_skill_audit.py` | -> `audit_external_skill.py`. Block-by-default security audit for imported skills (per ADR-0014). |
| size | `size.py` | -> `size_check.py`. Skill body size budget (warns >=500 lines, blocks >1000 per ADR-0015). |
| decay | `decay.py` | -> `decay_check.py`. Skill freshness: 60-day notice, 90-day warn, 180-day block. Trajectory freshness uses the same bands. |
| em-dashes | `em_dashes.py` | -> `check_em_dashes.py`. Enforces `base/rules/no-em-dashes.md` against authored prose. |
| no-versions-in-readmes | `no_versions.py` | -> `check_no_versions_in_readmes.py`. Keeps playbook version markers out of README.md / AGENTS.md. |
| skill-description-length | `skill_description.py` | -> `check_skill_description.py`. <=1024-char SKILL.md description (Codex schema limit). |
| hook-metadata | `hook_metadata.py` | -> `check_hook_metadata.py`. Every hook ships PLAYBOOK-HOOK-EVENT + PLAYBOOK-HOOK-MATCHER. |
| hook-source-unification | `hook_source_unification.py` | Self-contained. Skill-owned hooks live under `base/skills/<cat>/<name>/hooks/`; root symlinks back. Per ADR-0035. |
| pyright-zero | `pyright_zero.py` | Self-contained. Pyright errors + warnings must be zero; every `# pyright: ignore` line must carry a `# justification:` note. |
| human-html-allowlist | `human_html_allowlist.py` | Self-contained. `.human-html-allowlist` patterns must not contain shell-substitution risk characters. |
| skill-security | `skill_security.py` | Self-contained. Walks `scripts/security/` wrappers (Snyk, agent-skill-evaluator, DDIPE) and aggregates findings into the BOM. Per ADR-0047. |
| adr-number-unique | `adr_number_unique.py` | Self-contained. Walks `docs/adr/NNNN-*.md` and refuses duplicate ADR numbers. |
| ignored-containment | `ignored_containment.py` | Self-contained. Refuses any content under gitignored paths that would surface in tracked artifacts (e.g. docs/human-html ↔ docs/atlas links). |
| playbook-version | `playbook_version.py` | Self-contained. Validates the single source-of-truth `VERSION` file shape. |
| trajectory | `trajectory.py` | Self-contained. Lints `base/trajectories/<skill>/<scenario>.yaml` files for required fields per ADR-0044. |

## How to add a new gate

1. Create `scripts/checks/<name>.py`. Implement `def run(ctx: CheckContext) -> CheckResult`.
2. Choose: self-contained (implement logic inline) or delegating (call `capture_legacy_main("<legacy-module-name>", summary="...")` from `_legacy.py`).
3. Register in `scripts/checks/__init__.py:CHECKS`. Order matters when one gate's output is consumed by a later gate.
4. Add a row to the table above so reviewers know what the new gate covers.
5. Run `make check` against a clean tree + a tree with a known violation; confirm pass and fail.

## CheckResult shape

```python
@dataclass(frozen=True)
class CheckResult:
    status: Literal["ok", "warn", "fail"]
    summary: str         # one-line headline rendered with the gate name
    details: list[str]   # zero or more lines surfaced under the headline
```

`status="fail"` fails the gate (`make check` exits non-zero). `status="warn"` surfaces in the report but does not fail. `status="ok"` passes silently unless verbose output is requested.

## CheckContext shape

```python
@dataclass(frozen=True)
class CheckContext:
    repo_root: Path
    content: object      # PlaybookContent (per ADR-0024); typed as object to avoid import cycle
```

`content` is the pre-loaded inventory of the eight content types (skills, rules, hooks, mcp, agents, commands, prompts, trajectories), so gates that walk the content types do not re-load them.

## Related

- [`scripts/README.md`](../README.md) for the full installer + lint pipeline.
- ADR-0013 (AGENTS.md governance), ADR-0014 (external-source policy), ADR-0015 (skill size policy), ADR-0035 (canonical hook source), ADR-0047 (supply-chain gate) for the gates' underlying design.
- `make check` is the user-facing entry point; `make check FAST=1` enables fast mode.
