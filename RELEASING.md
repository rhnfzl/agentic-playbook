# Releasing the Coding Agents Playbook

Owner: Rehan
last_reviewed: 2026-05-25

How to cut a new release of the playbook. Steipete-style discipline (per ADR-0020).

## Pre-release checklist

Before tagging:

1. **make check** must pass on a clean clone (no manual fixups).
2. **make test** must pass (adapter smoke tests).
3. **make audit** must pass (no findings outside `.audit-allow` files).
4. **python3 scripts/eval_runner.py** must pass (all eval suites green).
5. **VERSION** file updated to the new release.
6. **CHANGELOG.md** updated with the new section at the top.
7. ADRs for any architectural decisions added under `docs/adr/`.
8. README counts (skills total, AGENTS.md coverage, lifecycle commands) updated.

## Release commits

Use the `feat(vX.Y.Z):` prefix for the release-bump commit. Body lists the major work-streams. Tag commit message is the version (e.g. `v0.3.0`).

```bash
git checkout -b release/vX.Y.Z
# ... ensure VERSION + CHANGELOG.md + README are updated ...
git add VERSION CHANGELOG.md README.md
git commit -m "feat(vX.Y.Z): bump VERSION + CHANGELOG + README"
git push -u origin release/vX.Y.Z
# Open PR; merge after Codex review
```

After merge:

```bash
git checkout develop
git pull --ff-only
git tag vX.Y.Z
git push origin vX.Y.Z
```

## Codex review before push

Per `feedback_codex_review_not_human` memory, run `/codex:adversarial-review` (or equivalent Codex agent) on the release branch BEFORE opening the PR. Codex provides the independent second-eye that catches policy drift the author missed.

## Lockfile considerations

Releases that change adapter destination paths or MCP bundles must regenerate `.playbook-lock.json`. Teammates with existing installs should `make update` to refresh.

## Announce

Slack channel: `#coding-agents-playbook` (or relevant). One-liner pointing to CHANGELOG.md + the PR URL. Per `rules/writing-style.md`, lead with what the release does for the user, then the technical detail.

## Hotfix path

For urgent fixes during production incidents:

```bash
git checkout -b hotfix/short-slug develop
# fix
git push -u origin hotfix/short-slug
# PR + emergency-review + merge
# Tag a patch release (e.g. v0.3.1)
```

Direct push to develop is forbidden (per `rules/never-push-to-develop.md`). Hotfixes still go through PR; the only acceptable exception is documented in the rule itself.

## Yanking a release

If a release ships broken: revert the merge commit on develop, tag a new patch with the revert, update CHANGELOG.md noting the yank reason. Do NOT delete the broken tag (preserve the audit trail).
