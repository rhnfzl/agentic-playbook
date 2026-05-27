---
name: anchored-edit
description: Use anchored edits when an MCP edit_file call would require copying a large unchanged block as old_text. Route ALL [upto] usage to MCP tools (mcp__filesystem__edit_file or mcp__anchored_fs__edit_file), native Claude Code Edit does not support [upto] due to a Claude Code limitation (issue #15897 + pre-hook validation).
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# Anchored Edit

Replace `old_text` of the form `prefix[upto]suffix` to anchor a span without restating the middle. The shared `anchored-fs` filesystem MCP resolves the span server-side before applying the edit.

## Why not native Edit?

Claude Code's native `Edit` tool validates `old_string` against file content BEFORE PreToolUse hooks fire. An `old_string` containing literal `[upto]` (which is not in the file) is rejected at validation, the hook never gets a chance to transform it. Additionally, Claude Code bug [#15897](https://github.com/anthropics/claude-code/issues/15897) causes `updatedInput` to be silently dropped by the hook-result aggregation logic in `cli.js` when multiple PreToolUse hooks are registered for the same tool (this workspace has 3+). Both issues are stacked, making the PreToolUse rewrite path unreachable.

**Consequence: `[upto]` resolution works ONLY through the MCP tools.**

The PreToolUse hook for Edit (`pretool_edit.py`) is now scoped to advisory validators only: stale-read-guard and adoption telemetry.

## When to use

- Replacing or deleting a contiguous block longer than ~25 lines.
- Replacing a generated section, a fixture, a verbose docstring, or a whole function body.
- Any time you would otherwise paste a long identical middle in `old_text`.

Use ordinary editing for small local changes (under ~25 lines).

## How to write the pattern

`prefix` and `suffix` are literal text. The resolver finds the FIRST unique location of `prefix`, then the NEXT occurrence of `suffix` after it, then replaces the whole span from prefix start through suffix end.

Make both anchors non-empty, exact, and long enough that the resolved span is unique.

## Which MCP tool to call

Use `mcp__filesystem__edit_file` if that is the only filesystem MCP registered in your session. Use `mcp__anchored_fs__edit_file` if the anchored-fs wrapper is registered (it adds preview, path-resolver, and stale-read on top). Both accept the same `old_text` / `new_text` / `path` parameters and both resolve `[upto]` server-side.

## Example 1: replace a function body

```
mcp__filesystem__edit_file(
  path="/abs/path/to/file.py",
  old_text="def compute_score(items):[upto]    return total",
  new_text="def compute_score(items):\n    return sum(item.weight for item in items)"
)
```

## Example 2: delete a deprecated block, preserve a following header

```
mcp__filesystem__edit_file(
  path="/abs/path/to/file.py",
  old_text="def obsolete_worker(...[upto]\n\nclass ActiveWorker:",
  new_text="class ActiveWorker:"
)
```

The `\n\n` between `obsolete_worker` and `class ActiveWorker:` is inside the matched span, so put `class ActiveWorker:` in `new_text` to preserve it.

## Example 3: rewrite a multi-paragraph doc section

```
mcp__filesystem__edit_file(
  path="/abs/path/to/doc.md",
  old_text="## Old section heading[upto]## Next section heading",
  new_text="## New section heading\n\nNew body text that replaces everything between the headings.\n\n## Next section heading"
)
```

## Escape: literal `[upto]` in the prefix

If your prefix needs to contain the literal text `[upto]` (rare), escape with `\[upto\]`:

```
mcp__filesystem__edit_file(
  path="/abs/path/to/file.py",
  old_text='msg = "\[upto\] is a marker"[upto]return 1',
  new_text='msg = "[upto] is a marker"\nreturn 1'
)
```

## Decision rule

- Below ~25 lines: ordinary `Edit` or `mcp__filesystem__edit_file` (verbatim).
- 25 lines or more, exact replacement: anchored edit via MCP.
- If preview returns multiple matches or no match: lengthen the anchors, do not weaken them.

## Failure handling

When the resolver returns a failure envelope, it includes candidate locations with line numbers. Read those candidates, pick the right one, and retry with a more specific prefix or suffix. Never paste-and-pray on ambiguous anchors.
