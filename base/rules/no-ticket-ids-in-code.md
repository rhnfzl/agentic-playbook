# No Ticket IDs In Code

Never put Jira ticket numbers (R8-*, MATCH-*) in code comments, docstrings, test names, JSON descriptions, or env example files. Ticket IDs belong in commits, PRs, Jira itself, and workspace notes.

## Why

Ticket IDs in code rot. A reference to [ticket] in a comment is meaningful today but meaningless to anyone reading the code in six months. The PR description and commit message are the right place for ticket context because they are linked to the code change at commit time.

## What to do instead

- Commit message: `fix(chat): resolve city-level geocoder regression ([ticket])`
- PR description: include the ticket link prominently
- Code comment: describe WHY the code does what it does, without ticket reference

## Specific anti-patterns

Avoid:

```python
# Fix for [ticket]
def normalize_city(...):
    ...
```

```python
# Per [ticket] we now use the geocoder
```

Prefer:

```python
# City-level normalization to handle ambiguous user input ("amsterdam" vs "Amsterdam, NL").
def normalize_city(...):
    ...
```
