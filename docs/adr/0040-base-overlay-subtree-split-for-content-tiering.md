# 0040. Base + overlay subtree split for content tiering

## Status

Accepted (2026-05-26); landing in v0.11.

## Context

The playbook serves team internal use. All content (skills, rules, hooks, MCP configs, ADRs, READMEs) lives at the repo root with company-specific references interleaved throughout: R8/MATCH Jira IDs, VCS-only commands, CI and code-quality specifics, internal hostnames (internal-host), error-tracking deployment hosts, and LLM-router vendor references.

The playbook's intellectual content separates naturally into two layers. Roughly 90% is generic infrastructure: the AGENTS.md curator, the codex-review pattern, the writing-style rule, the hook reconciliation machinery, the adapter dispatch logic, the profile loader. The remaining 10% is genuinely team-shaped: skills tied to internal services (error-tracking triage, CI debug, internal Kubernetes verification), rules that name team's VCS or ticket projects (R8/MATCH/code-quality), and references to team's internal hosts and vendor stack.

The split is not visible in the directory structure today.

### Gap 1: no scope boundary in the tree

Files like `skills/devops/error-tracking-issue-triage/SKILL.md` and `skills/devops/CI-pipeline-debug/SKILL.md` sit alongside generic content (`skills/meta/agents-md-curator/SKILL.md`, `rules/writing-style.md`). A contributor cannot tell from a file path which files are team-shaped. A code reviewer cannot enforce "do not leak team specifics into generic infrastructure" without reading every file's content.

### Gap 2: profile scope ambiguity

The `devops` profile bundles team-specific skills (error-tracking, CI, internal Kubernetes verification). The current single-tree structure has no machinery to express that this profile is scope-gated. The profile loads on any clone without a scope check; an installer who picks `devops` outside the team environment gets skills that reference internals they cannot use.

### Gap 3: PlaybookContent.load() is the real integration point, not just install.py

The first draft of this ADR called for `scripts/install.py` to gain a `--scope` flag and merge base + overlay. Review surfaced that install.py is a thin caller; the actual content resolution happens in `scripts/adapters/_protocol.py` (the `PlaybookContent` type) and `scripts/adapters/_reader.py` (which currently hardcodes flat `skills/`, `rules/`, etc.). Both must change for the overlay model to take effect; install.py changes are downstream of that. Every other content-touching script (target_materializer, playbook_init, playbook_update, eval_runner, new_skill, all `scripts/checks/*.py`) reads through the same seam.

### Gap 4: maintainability under growth

As the playbook grows (7+ adapters, 100+ skills, 50+ rules, multiple hook surfaces), the boundary between "infrastructure that any team would benefit from" and "infrastructure shaped by team's specific stack" becomes load-bearing. Mixing the two surfaces makes future refactors harder (each refactor has to handle both layers blindly) and makes code review burden invisible (reviewers cannot easily check "is this layer-appropriate?"). The same problem motivated the per-adapter shape package split in v0.9; this ADR extends the principle from "code that depends on adapter shape" to "content that depends on vendor scope."

### Gap 5: PLAYBOOK_VERSION drift hidden

The constant `PLAYBOOK_VERSION` in `scripts/install.py:46` has been stale at `"0.4.0"` since at least v0.5 despite v0.10 having shipped. A `VERSION` file also exists at root with a separate value (`"0.3.0"`). Neither is enforced against the other or against ADR headers. v0.11 is the right moment to fix the drift, but the fix needs a robust rule rather than ad-hoc parsing.

## Decision

### Adopt a base + overlay subtree split

Top-level structure becomes:

```
base/                       # generic, vendor-neutral playbook infrastructure
overlays/<name>/            # team-specific additions (skills, rules, references)
scripts/                    # install + utility scripts (stay at root)
tests/                      # tests (cover both base and overlay)
docs/                       # ADRs + human-html (stay at root)
profiles/                   # profile definitions (stay at root; declare overlay needs)
evals/                      # eval suites (stay at root; cases declare required scope)
```

### Classification policy (three buckets)

The split rule is grep-driven as a starting point, not a verdict. Each grep match needs a 5-second classification review against this policy:

1. **STRICT team** (file IS an team-only artifact, tied to internal services/tooling):
   - `skills/devops/error-tracking-issue-triage/`, `skills/devops/CI-pipeline-debug/`, `skills/devops/aws-secrets-configmap-apply/`, `skills/devops/k8s-dashboard-verify/`
   - `skills/engineering/code-review/` (uses VCS REST API)
   - `rules/label-policy.md` (team label scheme), any rule that prescribes team-internal procedure
   - Resolution: move to `overlays/<name>/`.

2. **GENERIC with team examples** (universal rule, mentions team as concrete illustration):
   - `rules/no-em-dashes.md` (universal style rule)
   - `rules/no-ticket-ids-in-code.md` (universal; uses R8 as example)
   - `rules/never-push-to-develop.md` (universal; mentions team repos as the example trigger)
   - `rules/writing-style.md` (universal; uses team project examples)
   - Resolution: STAYS in `base/`. Examples are illustrative; their presence does not bind the rule to team.

3. **HYBRID** (mostly generic with a clear team-only section):
   - `skills/meta/agents-md-curator/` (one team bullet in an otherwise generic skill)
   - Resolution: if practical, split the file (extract the team section into `overlays/<name>/`). If not (single short paragraph), classify by PRIMARY AUDIENCE.
   - Decision rule: "if a base-only user gets value from this file, base; if value is only realized with team context, overlay."

The `scope_boundary.py` check (see ADR-0041) enforces bucket 1: `base/` may not contain team markers except for files explicitly allowlisted with a rationale comment (bucket 2).

### PlaybookContent.load() walks ordered roots with overlay-wins merge

`scripts/adapters/_protocol.py` and `scripts/adapters/_reader.py` are the integration seam. Both change to accept multiple ordered content roots:

```python
@dataclass
class ContentPaths:
    """Resolved content roots in load order. Later entries override earlier."""
    roots: list[Path]  # e.g. [REPO/base, REPO/overlays/<name>]

def resolve_content_paths(scope: list[str], repo_root: Path) -> ContentPaths:
    """Resolves scope name list to ordered ContentPaths. base/ is always first."""
    ...
```

`PlaybookContent.load(repo_root, scope=None)` calls `resolve_content_paths`, walks each root in order, and merges with overlay-wins semantics. An overlay file at `overlays/<name>/skills/foo/SKILL.md` overrides a same-name file in `base/skills/foo/SKILL.md`.

All content-touching scripts (install.py, install_lifecycle.py, target_materializer.py, playbook_init.py, playbook_update.py, eval_runner.py, new_skill.py, install_bundles.py, install_orphans.py, sync_curated_skills.py, sync_mattpocock.sh, and every `scripts/checks/*.py`) call through this seam. None hardcode `repo_root / "skills"` (or equivalent) post-v0.11. Path-scanning checks (em-dash lint, frontmatter lint, decay check, size check, audit external skill, skill description check, hook source unification) use the resolved roots.

### Profile scope gating via `requires_overlays`

Profile TOML schema gains an optional field:

```toml
# profiles/devops.toml
name = "devops"
description = "DevOps profile for team Kubernetes + error-tracking + CI stack"
requires_overlays = ["team"]

[skills]
include = ["devops/error-tracking-issue-triage", ...]
```

Install behavior: when loading a profile with `requires_overlays = ["X"]`, the installer asserts `"X"` is in the active scope set. If not, install fails with:

```
Profile 'devops' requires overlay 'team' but it is not in the active scope.
Resolution: pass --scope team, or pick a profile that does not require overlays.
Active scope: <list>
```

Profiles without `requires_overlays` work in base-only context.

**Concrete v0.11 profile-to-overlay mapping** (derived from existing skill/rule/MCP references in each profile):

| Profile | `requires_overlays` |
|---|---|
| `devops` | `["team"]` (error-tracking, CI, internal Kubernetes skills + MCP) |
| `backend-developer` | `["team"]` (VCS PR review, code-quality PR gate, MATCH ticket grounding) |
| `tech-lead` | `["team"]` (same engineering surface as backend) |
| `frontend-developer` | `["team"]` (VCS PR review, VCS MCP) |
| `qa` | `["team"]` (error-tracking triage, code-quality MCP) |
| `research` | (omitted; base-compatible) |
| `product-manager` | (omitted; base-compatible) |

A profile not listed has no overlay requirements and installs in any scope. The v0.11 implementation step is: edit each `profiles/<name>.toml` from the table above and add the `requires_overlays = ["team"]` line.

**Validation shape (split parse and validation):** Parsing `requires_overlays` from the TOML lives in `scripts/playbook_profile.py:load_profile` (raw field read into the `Profile` dataclass). Validation against the active scope lives in a separate `validate_profile_scope(profile: Profile, active_scope: list[str]) -> None` function called by the install dispatch AFTER `load_profile` (and after `load_profiles`, the v0.10 multi-profile union helper). This separation lets `load_profile` stay pure (no implicit scope dependency) and lets `load_profiles` merge the `requires_overlays` sets from each profile before validation.

Lockfile schema change: each lockfile entry records the content_scope set used at install time (see lockfile section below).

### Lockfile content_scope persistence

Lockfile gains a top-level `content_scope` field, list[str], matching the `profile` field shape from v0.10. The name `content_scope` (rather than just `scope`) avoids collision with `ManagedMcpEntry.scope` which already means "global" | "project" (adapter config location) elsewhere in the lockfile schema. Same word, different meaning; the rename keeps reading the lockfile unambiguous.

```json
{
  "version": "0.11.0",
  "profile": ["backend-developer"],
  "content_scope": ["team"],
  ...
}
```

`make update` reads `content_scope` from the lockfile; no re-detection. Migration: lockfiles without `content_scope` (pre-v0.11) default to auto-detect on first update, with a warning advising the user to re-run install with explicit `--scope`.

`scripts/playbook_init.py` also writes the resolved content_scope to `.playbook-config.yaml` (so init/update parity exists for projects that never ran global install). `playbook_update.py` reads from lockfile first, falls back to `.playbook-config.yaml`, then to auto-detect.

### Scope resolution rules (auto-detect matrix)

When `--scope` is not passed, install resolves scope by inspecting the **target project's** git remote (the project where `make install` runs, not the playbook checkout). For most cases this matters only when the user has both repos cloned separately. The target-project remote is the authoritative signal because that is the surface being installed into.

| Scenario | Resolved scope |
|---|---|
| Explicit `--scope <name>` | `[<name>]` |
| Explicit `--scope none` or `--scope base` | `[]` (base only) |
| Target project remote matches `<vcs-host>:<team>/*` | `["team"]` |
| Other recognized remote (future cases) | base only with warning + advisory to set `--scope` |
| No git remote on target project | base only |
| `PLAYBOOK_HOME` env var set, no git remote | base only, advisory to set `--scope` explicitly |
| Multiple remotes, primary unclear | base only with warning |

The warning paths exist so silent auto-detect does not surprise users. Explicit `--scope` always wins over auto-detect.

Implementation note (v0.11): when `--scope` is omitted AND auto-detect returns `[]` (no recognized remote / no remote at all / unknown remote), install.py prints `Content scope: base only (no recognized remote detected). Pass --scope <overlay> explicitly if a profile needs an overlay.` This surfaces the silent fallback before `validate_profile_scope` rejects a profile that needed an overlay. Tested via worktree fixture in `test_scope_resolution.py`.

### PLAYBOOK_VERSION single source of truth

Drop the brittle "parse latest ADR's `landing in vX.Y` line" approach. The `VERSION` file at repo root is the single source of truth:

```
VERSION         # e.g. "0.11.0\n"
```

`scripts/install.py` reads `PLAYBOOK_VERSION` from `VERSION` at import time (not as a Python constant). `scripts/checks/playbook_version.py` asserts:

- `VERSION` file content is a well-formed semver string (e.g. matches `^\d+\.\d+\.\d+$`)
- No drift between Python code and `VERSION` (no `PLAYBOOK_VERSION` constant should exist post-v0.11; all reads happen from the `VERSION` file at runtime)

A root `pyproject.toml` does not currently exist (only `mcp/anchored-fs/pyproject.toml` does); cross-checking against it would require introducing one as new scope. Out of scope for v0.11. The lockfile records `playbook_version` at install time, which serves as the audit trail for what shipped.

This sidesteps the duplicate-ADR-number issue (ADR parsing breaks when two ADRs share a number; the historical 0032 collision demonstrated the failure mode).

### Per-type AGENTS.md files move into `base/<type>/AGENTS.md`

`skills/AGENTS.md`, `rules/AGENTS.md`, `hooks/AGENTS.md`, `mcp/AGENTS.md`, `agents/AGENTS.md` are governance documents about authoring. They move with their content type into `base/<type>/AGENTS.md`. The content describes generic authoring guidance and applies to BOTH base and overlay content of that type. If overlay-specific authoring rules emerge later (rare), add `overlays/<name>/<type>/AGENTS.md` separately.

`profiles/AGENTS.md` is the exception: profiles do not move (they stay at root). `profiles/AGENTS.md` stays alongside `profiles/*.toml`.

`evals/AGENTS.md` similarly stays alongside `evals/`.

Content updates during the v0.11 sweep:

- `base/skills/AGENTS.md`: add section "Choosing base vs overlays/<name>" referencing the three-bucket classification.
- `base/rules/AGENTS.md`: remove the current "no team-internal context, generic phrasing only" sentence (which contradicts reality post-refactor); replace with the overlay model.
- `profiles/AGENTS.md`: remove the "no team-internal grouping" sentence; document `requires_overlays`.
- `base/hooks/AGENTS.md`, `base/mcp/AGENTS.md`, `base/agents/AGENTS.md`: same treatment as needed.
- `evals/AGENTS.md`: update to reflect the actual eval format (`cases.yaml` + `judge.md`), which was already drifted pre-v0.11.

### evals/ handling

`evals/` stays at root. The current format is `evals/<suite>/cases.yaml` (each suite has a YAML file with a `cases:` list, plus `judge.md`). Eval cases gain an optional `required_scope` field as a per-case YAML key:

```yaml
# evals/code-review/cases.yaml
cases:
  - name: code-review-happy-path
    required_scope: ["team"]
    skill: overlays/<name>/skills/engineering/code-review  # post-refactor path
    ...
```

`scripts/eval_runner.py` filters cases by the active install scope. Cases without `required_scope` run in any scope. Skill paths in cases need updating after the content move (or resolved via `PlaybookContent.load`).

### mcp/anchored-fs/ handling

Classification: `base/mcp/anchored-fs/` (generic MCP bundle). The ~5k vendored files (`node_modules`) are a separate review-noise concern not addressed by this ADR; consider `.gitattributes` `linguist-vendored` for diff suppression in a follow-up.

### Restructure as a single mass git-mv PR

The directory restructure is one atomic PR with one commit per content-type batch (skills, rules, hooks, mcp, agents, commands, prompts). Profiles and evals do NOT move (they stay at root). Splitting moves across multiple PRs would force every other PR in flight to rebase through a shifting filesystem.

## Consequences

### Good

- Contributors see which files are team-shaped (`overlays/<name>/`) vs generic (`base/`) by directory alone. No frontmatter read required.
- Profile definitions are explicit about overlay needs (`requires_overlays`); install-time validation prevents stranded overlay-only skills.
- Lockfile records scope; `make update` is deterministic, no re-detect surprise.
- Code review gets a heuristic: "does this PR add to `base/`? Is the content actually generic?" The directory boundary doubles as a checklist item, complemented by `scope_boundary.py` (ADR-0041).
- `PLAYBOOK_VERSION` single source of truth: drift caught in CI.
- `PlaybookContent.load()` named as primary seam: every content-touching script flows through it post-v0.11. No silent path-hardcoding.

### Bad

- Every existing path reference changes. Wide sweep: `scripts/adapters/_reader.py`, `scripts/install.py`, `scripts/install_lifecycle.py`, `scripts/target_materializer.py`, `scripts/playbook_init.py`, `scripts/playbook_update.py`, `scripts/eval_runner.py`, `scripts/new_skill.py`, `scripts/install_bundles.py`, `scripts/install_orphans.py`, `scripts/sync_curated_skills.py`, `scripts/sync_mattpocock.sh`, every `scripts/checks/*.py`, `scripts/check_em_dashes.py`, `Makefile`, `README.md`, `CONTRIBUTING.md`, hook scripts, `profiles/*.toml`, per-type `AGENTS.md` files, ADR cross-references, test fixtures.
- The v0.11 PR is large (~80% of content files moved). Reviewers cannot easily see "what changed" because the change is "where everything lives." Per-content-type commit batches help but do not eliminate visual noise.
- Newcomers must learn the overlay concept before contributing. Documentation cost: a new section in `CONTRIBUTING.md` titled "Choosing base vs overlays/<name>" referencing this ADR.

### Trade-offs considered and rejected

- **Manifest-tagged single tree**: each file gets a `scope: generic|team` frontmatter field. No file moves. Rejected because the boundary is soft (you have to read frontmatter to know what's what), harder to enforce in review, and per-file labor still adds up to ~150 files needing a one-time tag sweep.
- **Root-as-base + small `overlays/<name>/` subdir**: keep most files at root, move only the team-specific minority. Less churn. Rejected because the boundary line drifts: where do you draw the line when a file is mostly-generic-with-a-few-team-mentions? The directory-as-boundary rule needs full coverage.
- **ADR-parsing for version drift**: rejected because ADR format is mixed ("landing in" / "landed in") and duplicate ADR numbers (the 0032 collision found during this design pass) break the parse. VERSION file as single source of truth is more robust.
- **Hard-fail profiles missing `requires_overlays`**: rejected. Profiles without the field default to base-compatible. This avoids forcing every existing profile to be re-saved before v0.11 install works.

## Implementation note

### Integration seam (primary)

- `scripts/adapters/_protocol.py`: `PlaybookContent`, `ContentPaths`, `resolve_content_paths(scope, repo_root)`.
- `scripts/adapters/_reader.py`: walks ordered roots with overlay-wins merge. No more `repo_root / "skills"` hardcoding.

### Content-touching scripts (all flow through PlaybookContent.load)

- `scripts/install.py`, `scripts/install_lifecycle.py`, `scripts/install_lockfile.py`
- `scripts/install_bundles.py`, `scripts/install_orphans.py`
- `scripts/target_materializer.py`
- `scripts/playbook_init.py` (accepts `--scope`; writes to `.playbook-config.yaml`)
- `scripts/playbook_update.py` (reads scope from lockfile)
- `scripts/playbook_profile.py` (validates `requires_overlays`)
- `scripts/new_skill.py` (accepts `--scope`; writes to `base/skills/` or `overlays/<name>/skills/`)
- `scripts/eval_runner.py` (filters cases by scope)
- `scripts/sync_curated_skills.py`, `scripts/sync_mattpocock.sh`

### Path-scanning checks (use resolved roots, not hardcoded patterns)

- `scripts/check_em_dashes.py` (legacy root script): read roots from PlaybookContent, scan `*.md`, `*.py`, etc. within them.
- `scripts/checks/frontmatter.py`
- `scripts/checks/decay.py`
- `scripts/checks/size.py`
- `scripts/checks/external_skill_audit.py`
- `scripts/checks/skill_description.py`
- `scripts/checks/hook_source_unification.py`

Without this conversion, post-refactor those checks silently scan nothing.

### Top-level documents

- `README.md`: path references swept.
- `CONTRIBUTING.md`: new section "Choosing base vs overlays/<name>" with the three-bucket policy.
- `profiles/AGENTS.md` (stays at root): rewritten to reflect overlay model.
- `evals/AGENTS.md` (stays at root): updated to reflect `cases.yaml` + `judge.md` reality.
- `base/skills/AGENTS.md`, `base/rules/AGENTS.md`, `base/hooks/AGENTS.md`, `base/mcp/AGENTS.md`, `base/agents/AGENTS.md` (moved with their content type): rewritten for overlay model.
- `Makefile`: install, update, status, check, `make new` all scope-aware.

### Test fixtures

- base-only install (no overlay)
- base + team install
- Profile with `requires_overlays = ["team"]` in base-only context (must FAIL with clear message)
- Profile without `requires_overlays` in base + team context (must succeed)
- Lockfile round-trip preserves `scope` field
- Pre-v0.11 lockfile (no `scope` field) triggers auto-detect + warning on `make update`

### Companion: ADR-0041 guardrails

Three new checks land alongside this refactor to enforce what prose cannot:

- `scripts/checks/adr_number_unique.py`: prevents duplicate ADR numbers (the 0032 collision found during this design pass).
- `scripts/checks/scope_boundary.py`: fails if `base/` contains team markers without an allowlist entry.
- `scripts/checks/ignored_containment.py`: scans the whole working tree (including gitignored files) for term patterns supplied via external configuration; catches the class of leak that a stale row in gitignored `docs/human-html/index.html` exhibited.

See ADR-0041 for details.

## References

- ADR-0024 (adapter protocol and install manifest): the overlay logic plugs into the existing adapter dispatch via `resolve_content_paths`.
- ADR-0025 (profile end-to-end): profiles gain `requires_overlays`; install-time validation closes the previously-open scope-gating question.
- ADR-0029 (hook reconciliation): the same code-review-by-directory principle that motivated v0.5 hook headers also motivates this ADR. This extends the principle from "code that depends on adapter shape" to "content that depends on vendor scope."
- ADR-0041 (content tiering guardrails): the three checks that enforce what this ADR specifies.
