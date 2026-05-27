---
name: market-audit-deployed-stack
description: "Use when the user asks to run the periodic market audit, sweep the deployed stack for new releases, check what changed on our stack since last audit, do the homelab follow-up audit, or audit upgrades for AL/Karakeep/FreshRSS/n8n/HACS/HA-core. Tavily-driven, scoped to currently-deployed components, surfaces only meaningful improvements and not generic ecosystem news. Anti-pattern: routine version bumps that Renovate already handles with the 14-day quarantine."
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# Market Audit, Deployed Stack Only

A periodic 2-3 week sweep against the homelab's currently-deployed
components. Scope is narrow on purpose: only changes that could
meaningfully improve what is already running. Generic news, breaking
changes from packages we do not use, and routine version bumps are
out of scope.

## When to invoke

- The user says "run the periodic audit", "homelab market audit",
  "sweep the deployed stack", "what's new on our stack since last
  audit", "run the follow-up audit".
- The user explicitly tags a deployed component ("what's new with
  Karakeep", "any movement on AL v2"): narrow scope to that component.

Do NOT invoke on bare "follow up", "what changed", or "what's new":
those are ambiguous and trigger on unrelated work. Require either an
explicit "audit" word or a tagged-component phrasing.

The cadence record (`reference_audit_watch_list` for the watch list,
`feedback_periodic_market_audit` for the policy) lives in memory and
is consulted on every audit run, but cadence alone does not invoke
this skill: the user has to ask.

## Inputs

- `~/.claude/projects/<homelab-project-slug>/memory/reference_audit_watch_list.md`:
  items the user has flagged "aware of, not yet actionable". Re-scan
  each for "Watch for" criteria.
- `~/.claude/projects/<homelab-project-slug>/memory/feedback_periodic_market_audit.md`:
  the cadence + anti-patterns.
- Repo files for the currently-deployed stack inventory:
  - `AGENTS.md` Services table (canonical deployed list).
  - HA core version: read live via the HA MCP (`ha_get_overview` or
    `ha_get_system_health`). The repo's `configuration.yaml` does not
    pin a core version.
  - HACS-installed integrations list (myVAILLANT, Solcast, AL, Battery
    Notes, PowerCalc, Spook, Whoop, HAGHS, Device Pulse).
  - `docker-compose.yml` files on CT 104 (Karakeep, FreshRSS, RSSHub,
    CouchDB, Forgejo, pgAdmin, n8n).
  - `renovate.json` for the quarantine policy.
- `~/AGENTS.md` Tavily Usage Rules → always advanced/pro mode, never
  basic. Tavily is the research source.

## Loop

1. **Build the in-scope list.** Read the Services table from `AGENTS.md`
   and union with the HACS integrations and the watch-list. This is the
   audit surface. Anything not on this list is out of scope.

2. **2-3 targeted Tavily searches.** For each component cluster, one
   query of the form `<component> 2026 release new feature` in
   advanced/pro mode. Do NOT search for "best X alternatives" or
   "what's new in <ecosystem>", that surfaces generic news.

3. **Re-scan the watch list.** For each entry, check the "Watch for"
   criteria for material movement. If the component is RESOLVED, leave
   the entry as-is. If there is movement, lift it from watch-only to a
   recommendation in this audit's response.

4. **Classify each finding.**

   | Class | Definition | Action |
   |---|---|---|
   | `recommend` | New option / fix replaces a custom workaround | Draft minimal implementation plan, ask before executing |
   | `consider` | Improvement but not strictly better than current | Mention with one-line trade-off |
   | `watch` | Movement but not yet actionable | Add or refresh entry in `reference_audit_watch_list.md` |
   | `skip` | Generic news, version bump, or component not deployed | Drop silently, do not list |

5. **Verify the recommendation cost.** For every `recommend`, confirm:
   - The change is currently released, not a roadmap promise.
   - The version is past the 14-day quarantine (`renovate.json`
     `minimumReleaseAge`).
   - The implementation is a *small* adjustment, not a migration.
     Migrations get framed as separate proposals.

## Output shape

```
RECOMMEND
  <component> <version>
  What changed: ...
  Why it matters here: ...
  Smallest implementation: ...

CONSIDER
  <component> ... (one-line trade-off)

WATCH (added/refreshed in reference_audit_watch_list.md)
  <topic> ... (what to look for next time)

SKIP (debrief only, not surfaced to user unless they ask)
  <items dropped and why>
```

End with: "Last audit: <date from reference_audit_watch_list.md>.
This audit: <today>. Next audit no earlier than <today + 14 days>."

## Anti-patterns (from feedback_periodic_market_audit)

- Recommending a version bump just because it is the latest: Renovate
  handles routine bumps with the 14-day quarantine. The audit's value
  is the "is this WORTH adopting" judgment.
- Suggesting full rewrites or migrations as part of the audit. The
  audit produces a small punch list only. Larger refactors get a
  separate proposal.
- Surfacing breaking changes from packages NOT currently deployed.
- Treating Tavily output as final. Always cross-check the upstream
  changelog or release notes before classifying as `recommend`.
- Basic-mode Tavily. Always advanced/pro mode per memory
  `feedback_tavily_usage`.

## Guardrails

- Do not edit code as part of the audit. The audit produces
  recommendations; the user accepts or skips each before any work begins.
- Do not invoke side-effect scripts as part of the audit (they send
  real Telegram).
- The audit writes NO files until the user has read the output and
  approved the proposed watch-list updates. Present the proposed
  `WATCH` additions/refreshes inline. Only after explicit user
  approval, write to `reference_audit_watch_list.md`. This is the
  only file the audit ever writes to.
