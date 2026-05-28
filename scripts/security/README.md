# scripts/security/

The supply-chain security gate's implementation. Per ADR-0047. Imported skills, MCP bundles, and other third-party content land in the playbook through a block-by-default audit; this module runs the audit and emits the AI Bill of Materials.

## What ships here

| File | Role |
|---|---|
| `__init__.py` | `Finding` and `WrapperResult` NamedTuples shared by every wrapper. |
| `mcp_scan_wrapper.py` | Wrapper around the Snyk skill scanner. Opt-in via `SNYK_AGENT_SCAN_CONFIG` env var (the scanner targets MCP server configs, not skill dirs directly, so the wrapper bridges). |
| `agent_skill_evaluator_wrapper.py` | Wrapper around a third-party agent-skill evaluator. Soft-fail by default; `STRICT_SECURITY=1` escalates to hard-fail. |
| `ddipe_detector.py` | Detects Document-Driven Implicit Payload Execution: the "innocuous markdown contains an executable payload" pattern observed in real compromised skill imports. |
| `ai_bom.py` | Emits the AI Bill of Materials (`docs/security/ai-bom.json`). Idempotent: re-runs on a clean tree produce a bit-identical file. |

## How `make audit` and `make check` consume this

```
  make audit          → scripts/audit_security.py → security/{mcp_scan,evaluator,ddipe,ai_bom}
  make check          → scripts/checks/skill_security.py → security/* (same wrappers, soft-fail context)
```

`make audit` is the block-by-default gate for net-new content (running against newly-imported skills before they land). `make check` runs the same wrappers in soft-fail mode against the in-tree content so an existing repo can iterate without the gate blocking unrelated work.

## Privacy

The BOM emitter (`ai_bom.py`) records public attributes only: source URL, component kind, path inside the repo, `vetted_as_of` date. No user data, no telemetry, no prompt or response bodies, no usage signals.

## Idempotency

`ai_bom.py` preserves `generated_at` when the components list is unchanged. A clean `make check` against an unchanged tree produces a bit-identical `docs/security/ai-bom.json` — no dirty diff, no spurious commit churn. The contract is enforced by `tests/security/test_ai_bom.py::test_bom_is_idempotent_when_components_unchanged`.

## Soft-fail vs strict mode

Default (`STRICT_SECURITY=0` or unset):
- Wrapper failures surface as warnings in the gate output.
- `make check` continues; `make audit` (running against net-new content) blocks.
- Existing repos can iterate on UI / docs without unrelated supply-chain noise.

Strict mode (`STRICT_SECURITY=1`):
- Wrapper failures hard-fail every gate.
- Use when running a final pre-release audit, or in CI for the security-critical branches.

## Opt-in scanner

The Snyk skill scanner is opt-in to avoid forcing every contributor to install Snyk locally:

```bash
export SNYK_AGENT_SCAN_CONFIG=/path/to/snyk/config.toml
make audit
```

Without the env var set, the wrapper is a no-op (logged as "skipped: SNYK_AGENT_SCAN_CONFIG not set"). The gate still runs the DDIPE detector + the agent-skill evaluator + the BOM emitter.

## Related

- [`docs/security/README.md`](../../docs/security/README.md) for the BOM consumer story.
- [`docs/adr/0047-supply-chain-security-gate.md`](../../docs/adr/0047-supply-chain-security-gate.md) for the threat model.
- [`tests/security/`](../../tests/security/) for the test suite.
- `scripts/audit_security.py` for the `make audit` entry point with argparse + `--help`.
