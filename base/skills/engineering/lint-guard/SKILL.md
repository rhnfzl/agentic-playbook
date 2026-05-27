---
name: lint-guard
description: Detect and run the project's linter and formatter after code edits and before commits/pushes. Prevents CI lint failures. Per-file on edits, full-project before commit/push. Supports ruff, eslint, black, prettier, biome via project config.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# Lint Guard

Prevent CI lint failures by running the project's linter locally, after every code edit and before every commit/push.

## Why This Exists

CI lint failures are preventable. They happen because:
1. The linter wasn't run at all before pushing
2. The linter was run on a single file but CI checks the entire project
3. The formatter wasn't run after the linter auto-fixed issues

This skill eliminates all three by enforcing a two-phase check: quick per-file checks after edits, and full-project checks before commits.

## Phase 1: After Editing Code (Quick Check)

After every Edit or Write to a code file, immediately run the linter on **that specific file**.

```bash
# Detect and run, see Detection Table below
<runner> <linter> check <file-path>
<runner> <formatter> --check <file-path>
```

If the linter reports auto-fixable issues, fix them immediately (e.g., `ruff check --fix <file>`), then re-run the formatter. Don't ask, just fix and move on. Only pause to inform the user if there are issues that can't be auto-fixed.

## Phase 2: Before Committing or Pushing (Full Project Check)

Before any `git commit` or `git push`, run the linter and formatter on the **entire project**, this matches what CI does.

```bash
# Always check the full project, not just changed files
<runner> <linter> check .
<runner> <formatter> --check .
```

This is critical: CI runs `ruff check .` (the whole project), not `ruff check src/report/generator.py` (one file). A file you didn't touch can fail if, say, an import you removed was the only consumer of a symbol in another file.

If the full-project check fails:
1. Auto-fix what's fixable (`--fix` flag)
2. Run the formatter to clean up (`ruff format .` or equivalent)
3. Re-run the check to confirm it passes
4. If unfixable issues remain, show them to the user and do NOT proceed with the commit

Never skip linting to "just get the commit done." The whole point is to catch issues before CI does.

## Detection Table

Detect the linter by checking for config files in the project root. Check in this order (first match wins within each language category):

### Python

| Config Signal | Linter | Check Command | Fix Command | Format Command |
|---|---|---|---|---|
| `[tool.ruff]` in `pyproject.toml` or `ruff.toml` exists | ruff | `check .` | `check --fix .` | `format .` |
| `[tool.black]` in `pyproject.toml` | black (formatter only) |, |, | `black --check .` |
| `.flake8` or `[flake8]` in `setup.cfg` | flake8 | `flake8 .` |, |, |
| `[tool.pylint]` in `pyproject.toml` | pylint | `pylint .` |, |, |

### JavaScript / TypeScript

| Config Signal | Linter | Check Command | Fix Command |
|---|---|---|---|
| `eslint.config.*` or `.eslintrc*` | eslint | `eslint .` | `eslint --fix .` |
| `biome.json` or `biome.jsonc` | biome | `biome check .` | `biome check --fix .` |
| `.prettierrc*` or `"prettier"` in `package.json` | prettier | `prettier --check .` | `prettier --write .` |

### Runner Detection

Detect the command runner from lockfiles/config. This determines whether commands are prefixed:

| Signal | Runner Prefix |
|---|---|
| `uv.lock` exists | `uv run` |
| `poetry.lock` exists | `poetry run` |
| `Pipfile.lock` exists | `pipenv run` |
| `package-lock.json` or `node_modules/` | `npx` |
| `pnpm-lock.yaml` | `pnpm exec` |
| `yarn.lock` | `yarn` |
| None of the above | (no prefix, direct command) |

### Combining Runner + Linter

Example for a project with `uv.lock` + `[tool.ruff]` in `pyproject.toml`:
- Quick check: `uv run ruff check <file> && uv run ruff format --check <file>`
- Full check: `uv run ruff check . && uv run ruff format --check .`
- Auto-fix: `uv run ruff check --fix . && uv run ruff format .`

Example for a project with `package-lock.json` + `eslint.config.mjs`:
- Quick check: `npx eslint <file>`
- Full check: `npx eslint .`
- Auto-fix: `npx eslint --fix .`

## Edge Cases

- **Multiple linters**: If both ruff and black are configured, prefer ruff (it subsumes black's formatting). If both eslint and prettier are configured, run both, eslint for lint, prettier for formatting.
- **No linter detected**: Do nothing. Don't warn, not every project uses a linter.
- **Monorepos**: If the project root has no linter config but subdirectories do, check the nearest parent config relative to the edited file.
- **CI config mismatch**: When available, read `.github/workflows/*.yml` to confirm what CI actually runs. Match that command exactly if it differs from the defaults above.
- **Test files**: Lint test files too. CI does. Some projects have per-file-ignores for tests (e.g., ruff's `S101` exemption), and the linter config already handles that.
- **Generated files**: Respect `.gitignore` and linter ignore files. Don't lint files the linter is configured to skip.

## What NOT to Do

- Don't add pre-commit hooks, .pre-commit-config.yaml, or modify the project's tooling unless the user explicitly asks for it. This skill is about Claude's behavior, not the project's infrastructure.
- Don't run `ruff check src/` when CI runs `ruff check .`, always match CI's scope.
- Don't skip the format check. `ruff check` (linting) and `ruff format --check` (formatting) are separate passes, a file can pass lint but fail formatting.
- Don't treat a passing single-file check as proof the project is clean. Always do the full-project check before commits.
