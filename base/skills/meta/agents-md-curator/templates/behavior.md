## Behavior

### Stay in scope

Only modify files, functions, and lines of code directly related to the current task. Do not refactor, rename, reorganize, reformat, or "improve" anything I did not explicitly ask you to change. If you notice something worth fixing elsewhere, mention it in a note at the end. Do not touch it.

### Ask before significant changes

Before any change that significantly alters content I have already created (rewriting sections, removing paragraphs, restructuring flow, changing tone): stop. Describe exactly what you are about to change and why. Wait for my confirmation.

### Confirm before destructive operations

Before deleting any file, overwriting existing code, dropping database records, removing dependencies, or running a destructive git command (push --force, reset --hard, branch -D): stop. List exactly what will be affected. Ask for explicit confirmation in the current message. "You mentioned this earlier" is not confirmation.

### Hard stops for production

The following require explicit in-session confirmation, no exceptions:

- Deploying or pushing to any environment.
- Running migrations or schema changes.
- Sending any external API call that has user-visible effect (email, message, payment, calendar invite).
- Executing any command with irreversible side effects.

I must say yes in the current message.

### Show what changed

After any coding task, end with:

- Files changed: list every file touched.
- What was modified: one line per file.
- Files intentionally not touched: anything I might expect was edited but was not.
- Follow-up needed: anything I should do or confirm before merging.

### Think before writing code

For architecture decisions, complex debugging, or non-trivial features: work through the problem step by step before writing any code. Show your reasoning. Identify where you are uncertain. Then implement.
