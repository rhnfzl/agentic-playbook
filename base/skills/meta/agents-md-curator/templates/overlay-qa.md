## Role overlay: QA

### Malformed inputs get equal weight

A test suite that only exercises the happy path is incomplete. For each feature, enumerate:

- Happy path: normal valid input.
- Edge cases: empty, very large, very small, near-boundary, off-by-one.
- Malformed: invalid types, missing fields, extra fields, wrong encoding.
- Adversarial: inputs designed to break invariants (path traversal in filenames, special characters in identifiers, etc.).

Write the tests in this order. Happy-path-first is fine; happy-path-only is not.

### Establish baselines BEFORE changing anything

When investigating a regression or comparing behavior across branches: capture the baseline state on the known-good revision FIRST, then change. Without the pre-state, "this looks broken now" is unfalsifiable.

For probes that may be flaky, run them 30 times and report the pass rate. Single-run results are noise, not signal.

### Tests create their own data

A test that depends on production data, an external API, or a fixture file maintained outside the test is a flake waiting to happen. Tests construct their own input data inline so the failure mode is contained.

### Distinguish flake from regression

When a test fails intermittently:

1. Re-run it 30 times.
2. If the failure rate is below 5 percent on a known-good revision: probably flake; document and isolate the non-determinism.
3. If the failure rate is meaningfully higher than baseline: regression; bisect.

Do not conclude "flake" without the data. The premature "flake" tag hides real regressions.

### Reproduce before diagnosing

For any reported bug, recreate the failure end-to-end on your machine before proposing a fix. If you cannot reproduce, surface that. "Cannot reproduce" is a useful diagnostic finding; speculative fixes are worse than no fix.

### Capture surface first, diagnose second

When stuck on an opaque failure, build the capture surface (stack trace, logs, container teardown output) FIRST. Do not hypothesize about root cause until you can see what the system actually did.
