# chat-transcript-debug judge

## Scoring rubric (v0.3 static mode)

Each case is pass/fail. The four cases establish that:

1. **Trigger discipline.** The skill names a when-to-use trigger so it activates from production SSE transcript debugging requests.

2. **Per-event reconstruction.** The skill body talks about events; chat-transcript-debug only works when the SSE stream is reconstructed event-by-event, not aggregated.

3. **Boundary awareness.** The skill references AI Backend or MCP or chat semantics; transcript bugs frequently cross those layer boundaries.

4. **Frontmatter completeness.** Standard required fields populated.

## Future v0.4 dynamic mode

Fixture transcripts to add:
- A capability-claim halucination (assistant says "I sent the message" without an actual send tool call)
- A reasoning event followed by silent abort
- A multi-turn loop that closes on action vs prose-only
- A re-run of the same prompt with diverging outputs
