# Tests

`tests/` holds the lifecycle, atlas, security, and telemetry test suites for the playbook's Python tooling. Different from `evals/` (which checks per-skill behavior) and from `make check` (which lints artifact shape). The tests here catch installer regressions before they reach users.

## How to run

```bash
make test                       # adapter + lifecycle smoke tests (fast; ~2 minutes)
pytest tests/                   # run every suite
pytest tests/lifecycle/         # just the lifecycle suite
pytest tests/security/          # just the supply-chain gate suite
pytest tests/atlas/             # just the atlas knowledge-graph suite
pytest tests/telemetry/         # just the telemetry suite
pytest -k "<keyword>"           # filter by test name
pytest --lf                     # rerun only last-failed
```

## What lives here

| Subdirectory | What it covers | Backing module |
|---|---|---|
| `lifecycle/` | Installer behavior end-to-end: detection, materialization, lockfile, idempotency, drift, multi-target registry, scope resolution. | `scripts/install.py` + every `scripts/adapters/<tool>.py` |
| `atlas/` | Knowledge-graph builder: node enumeration via `git ls-files`, edge derivation, per-skill page rendering, telemetry opt-in. | `scripts/atlas/`, `scripts/build_atlas.py` |
| `security/` | Supply-chain gate: AI BOM emitter, DDIPE detector, wrapper soft-fail, idempotency. | `scripts/security/`, `scripts/audit_security.py` |
| `telemetry/` | OTel collector: OTLP parser, ingest, JSONL aggregation, banned-prefix privacy contract, decay integration. | `scripts/telemetry/`, `scripts/skill_telemetry_report.py` |

Plus `conftest.py` for shared pytest fixtures (HOME redirect, tmp-target setup, frozen time).

## Test count

480+ tests across the four suites. `make test` runs the fast lifecycle subset (adapter smoke + installer regressions); the slower `pytest tests/` includes the security, atlas, and telemetry suites which take longer (each ~30 seconds).

## How to add a new test

1. Decide which suite fits: lifecycle (installer behavior), atlas (graph rendering), security (BOM / DDIPE), telemetry (OTLP / ingest).
2. Create `tests/<suite>/test_<name>.py` following the existing file's structure. Use `tmp_path` + the shared `conftest.py` fixtures rather than touching real `$HOME`.
3. Name tests descriptively: `test_lockfile_idempotent_under_rerun`, not `test_install_works`.
4. Include the reason in a one-line docstring when the test guards against a regression that's been caught in PR review or fix-fold.
5. Run `pytest tests/<suite>/test_<name>.py -v` to confirm.
6. Open a PR per `CONTRIBUTING.md`.

## What `make check` covers vs what `pytest` covers

| Concern | Where |
|---|---|
| Frontmatter, AGENTS.md governance, em-dashes, content tiering, decay, size, hook metadata, pyright | `make check` (calls `scripts/check.py`) |
| Adapter materialization, lockfile reconciliation, installer drift, MCP probe, multi-target registry | `make test` / `pytest tests/lifecycle/` |
| Per-skill behavior (does the skill body still encode the discipline) | `make eval` |
| Cross-adapter behavior (does the same prompt produce the same tool-call sequence in Claude Code vs Codex vs Cursor vs Windsurf) | `make trajectory-check` |
| Knowledge-graph build correctness | `pytest tests/atlas/` |
| Supply-chain gate (BOM idempotency, DDIPE detection) | `pytest tests/security/` |
| Telemetry privacy contract | `pytest tests/telemetry/` |

## Privacy in test fixtures

Test fixtures NEVER include real user data. The shared `conftest.py` redirects `$HOME` to a `tmp_path` for every test. The telemetry suite tests use synthetic OTel spans; no real OpenTelemetry collector or remote endpoint is contacted.

## CI

CI runs `make check && make test` on every PR. `make eval` and `make trajectory-check` are slower and run on a separate cadence (manual trigger today; future ADR may add a nightly CI workflow).

## Related

- [`scripts/README.md`](../scripts/README.md) for the modules under test.
- [`evals/README.md`](../evals/README.md) for per-skill behavior tests (different layer).
- `base/trajectories/README.md` for cross-adapter behavior tests (different layer).
- `tests/AGENTS.md` for the in-flight authoring rules the contributor follows when adding a test.
