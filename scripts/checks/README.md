# scripts/checks/

The 13 pluggable quality-gate modules that `make check` runs against the playbook. Each module exports a `run(ctx) -> CheckResult` function; `scripts/check.py` iterates the registry in `scripts/checks/__init__.py:CHECKS` and aggregates exit status.

Module shape is split between:

- **Self-contained checks** that implement their logic directly inside `scripts/checks/<name>.py` (the three at the bottom of the table).
- **Delegating checks** that call `run_legacy_main()` into a legacy `scripts/<name>.py` so the standalone CLI (e.g. `make audit` invoking `scripts/audit_external_skill.py` directly) and the gate share one implementation.

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

## How to add a new gate

1. Create `scripts/checks/<name>.py`. Implement `def run(ctx: CheckContext) -> CheckResult`.
2. Choose: self-contained (implement logic inline) or delegating (call `run_legacy_main("scripts/<name>.py")`).
3. Register in `scripts/checks/__init__.py:CHECKS`. Order matters when one gate's output is consumed by a later gate.
4. Add a row to the table above so reviewers know what the new gate covers.
5. Run `make check` against a clean tree + a tree with a known violation; confirm pass and fail.

## CheckResult shape

```python
@dataclass
class CheckResult:
    name: str            # gate slug, e.g. "frontmatter"
    passed: bool
    errors: list[str]    # one entry per violation; rendered with the file path + line
    warnings: list[str]
    notices: list[str]   # informational, surfaced but never blocking
```

Errors fail the gate (`make check` exits non-zero). Warnings surface in the report but don't fail. Notices surface only when verbose.

## CheckContext shape

```python
@dataclass
class CheckContext:
    repo_root: Path
    scope: Literal["base", "overlay", "all"]
    verbose: bool
    fast: bool           # skip expensive sub-checks (pyright, BOM regen)
```

`scope` lets a gate filter to base content or overlay content. `fast` mode skips multi-second checks for faster iteration.

## Related

- [`scripts/README.md`](../README.md) for the full installer + lint pipeline.
- ADR-0013 (AGENTS.md governance), ADR-0014 (external-source policy), ADR-0015 (skill size policy), ADR-0035 (canonical hook source), ADR-0047 (supply-chain gate) for the gates' underlying design.
- `make check` is the user-facing entry point; `make check FAST=1` enables fast mode.
