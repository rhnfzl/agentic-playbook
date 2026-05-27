---
name: human-html
description: Use whenever a task produces a human review surface (plan, review, architecture explainer, understanding doc, research synthesis, decision aid, prototype, status review) so the artifact lands as HTML under docs/human-html/ of the active workspace rather than Markdown. Markdown stays for agent scratch, durable references, ticket notes, drafts, and meetings. Provides a script (new / index / check / init) and three hooks (advisory + autoindex + Cursor-flavored advisory wrapper) that wire the contract into Claude Code, Codex, Cursor, Cline, Copilot, and Windsurf.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-25
---

# human-html

## What this is, in plain terms

Picture a tech lead, a product manager, or a teammate opening one of your documents for the first time. They have ten minutes. They want to know what the work is, whether the plan is sound, where the risk sits, and what they need to do next.

If the document is a long Markdown file, they skim. Skim turns into rubber-stamp. They miss the assumption that was buried in paragraph nine. They approve something they didn't really read.

If the document is a single HTML page with a diagram, color-coded risks, a checklist, and the key snippets inline, they read. They ask sharper questions. They catch the thing that was wrong. They redirect work before it lands in the wrong place.

This skill enforces that switch as a workspace contract. When an agent (you, Claude, Codex, or anyone else) produces a *human review surface*, a plan, a code review, an architecture explainer, an understanding doc, a research synthesis, a decision aid, a prototype, or a status report, the artifact lands as HTML under `docs/human-html/` of the active workspace. Not as Markdown. Markdown is still the right format for scratch notes, ticket drafts, durable references, and meeting transcripts; it is the agent's memory layer. HTML is the human's review layer. The split is the point.

Adoption costs ten seconds per workspace. After that, two hooks keep the contract self-enforcing: one nudges an agent that is about to write a human-review Markdown file in the wrong place; the other regenerates the gallery `index.html` automatically whenever an artifact lands.

## What you get

- A `docs/human-html/` artifact lane containing top-level artifacts named `YYYY-MM-DD-kind-slug.html`, optional nested portable collections, plus an auto-generated `index.html` gallery that lists everything in reverse-chronological order.
- Eight named *kinds* that cover the human-review surfaces a software team actually produces: `plan`, `review`, `architecture`, `understanding`, `research`, `decision`, `prototype`, `status`.
- A small Python script that scaffolds new top-level artifacts with the correct filename and metadata, recursively validates artifacts and nested collections, and rebuilds the gallery.
- Two shell hooks that nudge toward the harness when an agent is about to drift, and that keep the gallery current without the agent remembering to refresh it.
- A per-workspace customization knob (`.human-html-allowlist`) for the small set of cases where a workspace has Markdown lanes the baseline does not anticipate.

## When to use it

Use the harness whenever the next artifact will be read by a human to make a decision, redirect work, approve a change, or build understanding of a system. If it would be reasonable to send the artifact to a teammate, the answer is HTML under `docs/human-html/`.

Do not use it for:

- Agent-to-agent handoffs (those parse better as Markdown).
- Source-of-truth specs that get edited weekly in git (HTML diffs are noisy; Markdown wins for git review).
- Short answers under ~20 lines (a chat reply is enough).
- Anything that is not intended for a human reader.

---

## Developer reference

### File contract

```
docs/human-html/
  index.html                       auto-generated gallery
  README.md                        per-workspace contract restatement
  YYYY-MM-DD-kind-slug.html        one artifact per file
  <collection>/
    index.html                     optional portable collection hub
    *.html                         collection pages, validated by metadata
```

Required metadata in every artifact:

```html
<meta name="artifact-kind" content="<one of 8 kinds>">
<meta name="artifact-audience" content="human">
<meta name="artifact-created" content="YYYY-MM-DD">
<meta name="artifact-source" content="<free text>">
<body data-human-html-artifact="true">
```

### Invocation

```bash
# Initialise a workspace (creates docs/human-html/, README, empty index)
python3 ~/.agents/skills/human-html/human_html_artifacts.py init

# Scaffold a new artifact (also refreshes the gallery)
python3 ~/.agents/skills/human-html/human_html_artifacts.py new <kind> "<title>"

# Validate filenames + metadata + local links + no-root-HTML rule
python3 ~/.agents/skills/human-html/human_html_artifacts.py check

# Manually regenerate the gallery (rarely needed; the hook handles it)
python3 ~/.agents/skills/human-html/human_html_artifacts.py index
```

The script resolves the workspace root in this order:

1. `$HUMAN_HTML_ROOT` if set
2. Walk up from current directory; first ancestor containing `docs/human-html/` wins
3. Current directory (used by `init` to seed a new workspace)

This means the script is callable from any subdirectory of any workspace.

### Hooks

Both hooks live at the playbook root `hooks/` directory (per ADR-0027). The playbook installer copies them to `~/.claude/hooks/` and registers them in `~/.claude/settings.json` automatically. Each hook script carries an explicit `# PLAYBOOK-HOOK-EVENT:` header line so the installer knows which event to register it for. They resolve workspace root via `$CLAUDE_PROJECT_DIR` -> `$CODEX_WORKSPACE` -> `pwd` fallback. They are advisory only; neither blocks any tool call.

**Advisory hook** (`hooks/human-html-advisory.sh`, PreToolUse). Fires on `Edit | Write | MultiEdit | NotebookEdit`. When the target is `.md`, the slug matches an HIL pattern (`plan | review | audit | architecture | understanding | research | decision | prototype | status | report | incident | postmortem`), AND the path is outside the Markdown-OK allowlist, the hook prints a suggestion to stderr pointing at this script. Exits 0 regardless.

**Autoindex hook** (`hooks/human-html-autoindex.sh`, PostToolUse). Fires on `Edit | Write | MultiEdit` to any file under `<workspace>/docs/human-html/` with an `.html` extension, except the root gallery `index.html` itself. Also handles Codex `apply_patch` events by conservatively regenerating the gallery whenever `docs/human-html/` exists, because Codex patch events do not always expose a single target path. Shell-tool events are indexed only when the command references `human_html_artifacts.py` or `docs/human-html`. Runs the script's `index` subcommand to keep the gallery current. Exits 0 regardless.

### Wiring

Claude Code: add to `<workspace>/.claude/settings.json` `hooks` section:

```json
{
  "PreToolUse": [{
    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
    "hooks": [{"type": "command", "command": "/Users/<you>/.claude/hooks/human-html-advisory.sh", "timeout": 5}]
  }],
  "PostToolUse": [{
    "matcher": "Edit|Write|MultiEdit|Bash",
    "hooks": [{"type": "command", "command": "/Users/<you>/.claude/hooks/human-html-autoindex.sh", "timeout": 10}]
  }]
}
```

Codex: enable hooks in `<workspace>/.codex/config.toml`, then wire the commands in `<workspace>/.codex/hooks.json` or the equivalent Codex hook config. The PreToolUse advisory matcher should include `Edit|Write|MultiEdit|NotebookEdit`; the PostToolUse autoindex matcher should include `Edit|Write|MultiEdit|apply_patch|Bash|exec_command|functions\.exec_command` when the hook system exposes shell events. The hook scripts are agent-neutral; they read JSON from stdin in the same shape that both Claude Code and Codex emit.

### Workspace customization

Each workspace MAY ship a `.human-html-allowlist` file at the workspace root with one path pattern per line. The advisory hook reads it and appends entries to its baseline allowlist, so a workspace with custom Markdown lanes (e.g. `myproject/notes/`) can carve them out without editing the global hook.

Example `.human-html-allowlist`:

```
# Workspace-specific Markdown lanes that should NEVER trigger the HTML advisory.
# One glob-style pattern per line (matched against path relative to workspace root).
# Lines starting with # are comments. Blank lines ignored.
myproject/notes/*
internal/runbooks/*
```

Built-in baseline allowlist (applies to every workspace, no customization needed):

- Protocol files at any depth: `AGENTS.md`, `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `DOCS_CONVENTIONS.md`, `DOCS_INDEX.md`, `MEMORY.md`
- Workspace-root Markdown lanes: `docs/superpowers/`, `docs/drafts/`, `docs/tickets/`, `docs/references/`, `docs/contracts/`, `docs/architecture/`, `docs/adr/`, `docs/agents/`, `docs/reports/`, `docs/presentations/`, `meetings/`, `archive/`, `platform/`, `external/`, `graphify-out/`
- Hidden/build/agent dirs at any depth: `.git/`, `.venv/`, `.pytest_cache/`, `.agent-harness/`, `.clawpatch/`, `.codex/`, `.claude/`, `.worktrees/`, `reviews/`, `tests/results/`, `node_modules/`

### Per-workspace adoption

To opt a new workspace into the harness:

```bash
cd <workspace>
python3 ~/.agents/skills/human-html/human_html_artifacts.py init
# wire the two hooks into .claude/settings.json and .codex/hooks.json
# optionally seed .human-html-allowlist with workspace-specific MD lanes
```

After init: every `new <kind> "<title>"` writes a scaffold and refreshes `index.html`; the autoindex hook catches later direct artifact edits, and the advisory hook nudges if an HIL-shaped MD slips through.

### Rollback

A workspace that does not benefit from HTML artifacts can simply omit `docs/human-html/`. The autoindex hook is silent when no artifact write occurs; the advisory hook nudges only on HIL-shaped MD writes; neither hook fails if the script is missing. There is no global state to undo.

### Source

Pattern from Thariq Shihipar, "The Unreasonable Effectiveness of HTML" (2026-05-08), `https://thariqs.github.io/html-effectiveness/`. Industry layer-split framing (HTML for human review, Markdown for agent memory) converged across Simon Willison, Beam.ai, AI Architects, and Anthropic engineering blog by mid-May 2026.
