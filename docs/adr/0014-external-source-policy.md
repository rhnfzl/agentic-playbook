# 0014. External-source policy: catalog + audit + status semantics

## Status

Accepted (2026-05-25)

## Context

v0.3 introduces vendored third-party content (mattpocock + frontend pilots) for the first time. Without a policy, external skills can drift into the repo with mismatched licenses, no review trail, and unknown security posture. Security research (Mondoo, Snyk, OWASP, arXiv) catalogs real risks: prompt injection, secret exfiltration, network exfiltration, persistence writes, supply-chain drift.

## Decision

Three artifacts together enforce external-source discipline:

### 1. `docs/research/external-skill-sources.md` (catalog)

Every external source the playbook references, vendors, or has evaluated carries a row with: source URL, pin (commit SHA at vendor time), license, skills (specific approved subset or "all"), status, risk_class, reviewer, last_reviewed, notes.

Status values:

| Status | Meaning |
|---|---|
| `recommended` | Vendored into the playbook, audit clean, ready for teammate use |
| `refer-only` | Catalog reference; do not vendor (legal or strategic reason captured in notes) |
| `audit-needed` | Candidate for vendoring once audit + review complete |
| `rejected` | Evaluated and not adopted, with reason captured |

Risk classes: `docs-only` / `scripts` / `network` / `credentials`. Higher risk requires deeper audit.

### 2. `scripts/audit_external_skill.py` (security audit, block-by-default)

Scans `skills/imported/<source>/<skill>/SKILL.md` plus referenced `scripts/` and `references/` for:

- Hidden Unicode (bidi marks, zero-width chars)
- Secret-file paths (.env / SSH keys / cloud creds / wallets / browser stores / credential env vars)
- Network exfiltration commands (curl / wget piped to shell, python -m http, nc -l)
- Persistence writes (AGENTS.md, CLAUDE.md, MEMORY.md, shell rc files)
- Unpinned package downloads (pip install without version, npm install -g, uv add without --frozen)

Per-skill `<skill-dir>/.audit-allow` accepts category names with a # comment documenting the reviewer signoff. Block-by-default (no allowlist = block).

### 3. Per-skill `PROVENANCE.md` in each vendored bundle

Records upstream URL, license, pin SHA at vendor time, vendored subtrees, and the standard local-modification list. Vendor refresh updates this file and the catalog row.

## Consequences

- Adding a new vendored source = create `skills/imported/<source>/PROVENANCE.md`, add a catalog row, run `make audit`, run `make check`.
- Refer-only sources still appear in the catalog so the reasoning is recoverable (gnurio = all rights reserved, alexgreensh = PolyForm Noncommercial, nickwinder = no LICENSE, etc.).
- Anthropic frontend-design was vendored briefly during v0.3 PR development then downgraded to refer-only after user evaluation (catalog row captures the reasoning).

## Related

- v0.3 plan: scope row 3 + 4
- ADR-0019 (mattpocock + frontend imports + sync mechanism)
- ADR-0020 (refer-only justifications)
