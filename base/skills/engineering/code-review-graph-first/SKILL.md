---
name: code-review-graph-first
description: Use when exploring or reviewing a codebase that has the code-review-graph MCP server registered, instead of starting with Grep / Glob / Read.
version: 1.0.0
owner: rehan
last_reviewed: 2026-05-25
tags: [code-review, mcp, exploration, performance]
scope: [engineering]
---

# Code-review-graph first

When the codebase has a `code-review-graph` MCP server registered, the graph index returns structural answers (callers, dependents, test coverage, impact radius) that raw text search cannot. It is also faster and uses fewer tokens than reading source files end-to-end. This skill is the standing decision tree for "graph tool vs grep" so you do not waste turns scanning files when the graph would answer in one call.

## When to use

- The agent is about to Grep, Glob, or Read source to answer "where is X defined", "what calls Y", "what does Z depend on", or "what tests cover W".
- The agent is reviewing a code change and needs a risk-scored summary or the source snippets that matter.
- The user asks "what is the blast radius of changing this function" or "which flows hit this module".
- The agent needs architecture-level context (clusters, modules, the high-level shape of a service).

## When NOT to use

- The repo has no `code-review-graph` MCP server registered. The graph tools will fail; just use Grep / Glob / Read directly.
- The question is genuinely about non-indexed content: raw markdown docs, image alt-text, generated build artifacts, JSON config values.
- The user explicitly asks you to grep or read directly to compare results against the graph's view.

## Workflow

1. **Confirm the graph is live.** If you are unsure, run `query_graph` with a trivial probe (e.g. search for a known function name). If it fails, fall back to Grep / Glob / Read for this session.
2. **Pick the right graph tool by intent.** Use the table below.
3. **If the graph result is empty or shallow,** then fall back to Grep / Glob / Read on the relevant files.
4. **Refresh on demand.** The graph auto-updates on file changes via the `code-review-graph-update.sh` hook (see `hooks/` in the playbook), so a recent edit by you should be reflected. If you suspect staleness, run `code-review-graph status` from a shell.

## Worked example

User: "I'm about to refactor `normalize_city` in `geocoder.py`. What calls it and which tests cover it?"

Without this skill: Grep for `normalize_city` across the repo, Read several call sites, Grep test files, Read each test.

With this skill:
- `query_graph` with `pattern="callers_of"`, `target="geocoder.py:normalize_city"` returns the call sites with line numbers.
- `query_graph` with `pattern="tests_for"`, `target="geocoder.py:normalize_city"` returns the test references.
- `get_impact_radius` for the same target returns a risk score plus the modules likely affected.

Three calls, structured results, no file reading. Fall back to Read only on the specific lines the graph flagged.

## Tool selection table

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes; produces risk-scored analysis. |
| `get_review_context` | Need source snippets for review; token-efficient. |
| `get_impact_radius` | Understanding the blast radius of a change. |
| `get_affected_flows` | Finding which execution paths are impacted. |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies. |
| `semantic_search_nodes` | Finding functions or classes by name or keyword. |
| `get_architecture_overview` | Understanding high-level codebase structure. |
| `refactor_tool` | Planning renames; finding dead code. |

## Output

You should produce the answer to the user's question using the graph result as primary evidence, plus a sentence naming which graph tool you used (so the user can replay the query). If you fell back to Grep / Read, say so explicitly.

## Provenance

Promoted from `rules/code-review-graph-first.md` per Cursor R2 audit: the content is a conditional workflow (only applies when the graph is registered) with workflow steps, not an always/never directive. Skills are the right home for conditional procedures; rules are for unconditional constraints.
