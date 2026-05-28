# Prompt: Onboard a New Teammate

Paste the prompt below into your coding agent **inside the new teammate's machine** (or have the teammate paste it themselves). The agent walks them through a one-session onboarding so they leave with the playbook installed, their preferred coding agent detected and configured, and at least one skill, one rule, and one hook firing correctly against a test workflow.

Different from `bootstrap-your-playbook.md` (which scaffolds a new playbook for a team that doesn't have one) and from `global-audit.md` (which audits an established setup). This prompt is for "new joiner, has the playbook already, needs to be ready in one session."

---

## The prompt

```
I just joined the team and I'm new to agentic-playbook. Walk me through a single-session
onboarding where I end up with:

  1. The playbook installed for whichever coding agents I have on this machine.
  2. At least one skill firing correctly when I trigger its description phrase.
  3. At least one rule loaded and active in my next chat session.
  4. At least one hook firing on a real tool call.
  5. A bookmark of where the playbook lives so I can find it again.

Constraints:

  - Stop after each step and let me confirm before moving on. Do not chain steps.
  - If I get stuck, explain WHY a step matters before retrying.
  - Surface every command you run before running it.

Walk in this order:

  Step 1 -- Detect what I have.
    Run `which claude codex cursor windsurf cline aider gemini pi 2>/dev/null` and
    summarize which coding agents are installed on my machine. Tell me which one I'm
    most likely to use day-to-day and why (based on what's in my PATH, what's pinned
    in my .zshrc / .bashrc, etc.).

  Step 2 -- Locate the playbook checkout.
    Find where agentic-playbook is cloned. Likely paths:
      ~/agentic-playbook, ~/code/agentic-playbook, ~/dev/agentic-playbook,
      ~/projects/agentic-playbook, ~/workspace/agentic-playbook, $PLAYBOOK_HOME.
    If you can't find it, ask me where it lives. If it's not cloned anywhere, walk
    me through `git clone https://github.com/rhnfzl/agentic-playbook.git ~/agentic-playbook`.

  Step 3 -- Pick a profile.
    Ask me what role I play on the team (tech-lead / backend-developer /
    frontend-developer / qa / research / product-manager / devops). Show me the
    skills, rules, hooks, and MCPs that profile includes (read profiles/<role>.toml).
    Confirm before installing.

  Step 4 -- Install.
    Run `make install PROFILE=<role>` from the playbook checkout. Surface the install
    summary (which agents were detected, how many skills / rules / hooks materialized
    per adapter). Stop and let me read it.

  Step 5 -- Verify one skill fires.
    Pick a skill from the installed set that's easy to trigger (e.g. `grill-me`,
    `handoff`, `human-html`). Tell me the description phrase that triggers it.
    Ask me to start a fresh chat session in my coding agent of choice and paste a
    message that should fire the skill. Tell me what I should see when it fires
    correctly. If it doesn't fire, walk me through the three-layer debug checklist
    from base/skills/README.md.

  Step 6 -- Verify one rule loads.
    Identify a rule I should now have at the user level (e.g. `no-em-dashes`,
    `never-push-to-develop`). In a fresh chat session, ask me to paste a sentence
    that violates the rule and confirm the agent rejects or rewrites it.

  Step 7 -- Verify one hook fires (NEVER against a real remote).
    Identify a hook that's installed (e.g. `lint-guard.sh`, `never-push-to-develop.sh`).
    Trigger the hook against a throwaway local remote, never against a real shared
    upstream. Recipe for `never-push-to-develop.sh`:
      1. Create a scratch dir + bare local remote:
           tmp=$(mktemp -d); git init --bare "$tmp/remote.git"; cd "$tmp"
           git clone "$tmp/remote.git" sandbox; cd sandbox
           git checkout -b develop && git commit --allow-empty -m "init" && git push -u origin develop
      2. Edit a file in the sandbox, stage it, attempt the push:
           echo x > a && git add a && git commit -m t
           git push origin develop
      3. Confirm the hook blocked (non-zero exit + the never-push message on stderr).
    For `lint-guard.sh`: edit a Python file under the sandbox and save; the hook
    runs the project's linter against the file (read-only).
    If neither fires, walk me through the three-layer debug checklist from
    base/hooks/README.md. Do NOT attempt this verification against a real
    origin/develop branch; that defeats the purpose of the hook by either
    pushing or assuming the hook works without proof.

  Step 8 -- Bookmark the playbook.
    Show me the locations I should remember:
      - The playbook checkout (so I can run `make update` later).
      - The user-level installs in ~/.claude/, ~/.codex/, ~/.cursor/, etc.
      - The CONTRIBUTING.md so I know how to add my own skill or rule.
      - The /playbook-retrospective command for capturing patterns at session-end.
      - The /playbook-promote command for graduating a draft into the playbook.

  Step 9 -- Recap.
    One paragraph: what I just installed, what's loaded, what to do next week.

After step 9, stop. Don't propose anything else; let me settle in for a few days
before adding more content.
```

---

## What this prompt produces

A guided session of ~15-25 minutes during which the new joiner:

- Installs the playbook for whichever Tier 1 / 2 / 3 agents they have.
- Sees a skill, a rule, and a hook fire end-to-end.
- Bookmarks the locations they need for ongoing use.
- Leaves with a concrete "what to do next week" prompt.

## When to use it

- A new teammate joins and you want a self-serve onboarding that doesn't require pairing.
- A teammate is upgrading from a different agent (e.g. moving from Cursor to Claude Code) and needs the playbook to follow.
- A teammate has the playbook cloned but never ran `make install` and wants a guided walkthrough.

## When NOT to use it

- The teammate is the maintainer; they don't need an onboarding.
- The team doesn't have a playbook yet; use `bootstrap-your-playbook.md` first to scaffold one.
- The teammate has an established setup; use `global-audit.md` to integrate rather than blindly install.

## Iteration

This prompt is intentionally narrow (just enough to leave the user productive). The follow-up moves are:

1. After a week, run `global-audit.md` to identify Phase 2 / 3 content worth adopting.
2. After a month, capture any patterns the user invented via `/playbook-retrospective` and graduate them with `/playbook-promote`.
