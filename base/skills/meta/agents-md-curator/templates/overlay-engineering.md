## Role overlay: Engineering

### Simplest solution first

Implement the simplest thing that could work. Do not add abstractions, configuration knobs, or flexibility that I did not explicitly request. Three similar lines beat a premature abstraction.

If a future need would justify an abstraction, mention it as a note at the end, do not introduce it.

### Tests for new behavior

New behavior ships with a test. If you cannot write a test for something, surface why before writing the code. Common reasons: the surface is integration-only, the input is hard to construct, the failure mode is non-deterministic. Each is a useful signal about design.

Never lower an assertion to make a test pass. If the assertion was wrong, fix the test and explain why; do not silently weaken the bar.

### Functions and types over inline cleverness

When in doubt, extract a function or a type. Names communicate intent; clever one-liners do not. The cost of one extra type definition is much smaller than the cost of a future reader bouncing between five lines trying to reconstruct meaning.

### Comments explain WHY, not WHAT

Default to no comments. Only add one when WHY is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behavior that would surprise a reader. Do not narrate WHAT the code does; identifiers already say that.

Do not put ticket numbers in code comments. Ticket context belongs in the commit message and the PR.

### Boundary validation only

Trust internal code. Validate at system boundaries: user input, external API responses, file parsing, network frames. Do not validate inside the codebase against scenarios that internal callers cannot produce.

### Error handling and fallbacks

Do not add fallback paths for scenarios that cannot happen. Do not catch exceptions you have not thought about. A bare `except` that swallows errors is worse than an unhandled crash, because the silent failure mode is harder to debug than a stack trace.
