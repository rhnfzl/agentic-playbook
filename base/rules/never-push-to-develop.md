# Never Push To Develop

Always create a feature branch first. Never push directly to `develop` (or any default integration branch) without an explicit code review.

## The rule

- Default branches in team repos: `develop` (team-ai-backend, team_mcp), `main` (some smaller repos).
- ALL changes go through a PR. ALL PRs need at least one review.
- The PR is the audit trail. Direct pushes bypass that audit trail.

## What this looks like

```bash
git checkout -b feat/my-feature   # create feature branch
# ... make changes ...
git push -u origin feat/my-feature
# Open PR in VCS
```

NOT:

```bash
git checkout develop
git pull
# ... make changes directly on develop ...
git push  # ABSOLUTELY NOT
```

## Exception

The only acceptable direct-push case is an emergency hotfix during a production incident, and even then it should be cherry-picked back to develop via PR within 24 hours so the audit trail catches up.

## Hook enforcement

The `never-push-to-develop.sh` hook (in this playbook's `hooks/` directory) blocks direct pushes to develop at the git-hook level. Install it via `make install` for any team repo you actively work in.
