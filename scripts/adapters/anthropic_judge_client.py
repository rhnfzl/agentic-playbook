"""Anthropic Messages API client for the trajectory judge (Phase 2A Task 3).

Anthropic Messages API version header is pinned to `2023-06-01`. If
Anthropic deprecates that header value, the client surfaces an HTTP
error via `JudgeResult.is_infra_error=True` (HTTP 4xx pathway below)
rather than crashing the harness. To bump the pinned version, edit
`_ANTHROPIC_VERSION` and re-run the test suite (the test fixture
mocks urlopen so live API behavior is not exercised in CI).



Implements the JudgeClient protocol from `scripts/trajectory_judge.py`.
Uses stdlib `urllib.request` to stay within the repo's no-deps policy
(the Anthropic SDK is not a dependency; the Messages API is HTTP).

The client is a thin wrapper:

  1. Build a JSON request body (model, messages, system, temperature).
  2. POST to https://api.anthropic.com/v1/messages.
  3. Parse the first `content` block of the response.
  4. Hand the raw text to `parse_judge_response` from trajectory_judge.

HTTP errors do NOT crash the harness; they surface as score=0 with the
error class in reasoning, mirroring the parse-failure pathway.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from trajectory_judge import (
    JudgeResult,
    build_judge_messages,
    parse_judge_response,
)


_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 512  # judges produce short JSON; 512 is generous.


_SYSTEM_PROMPT = (
    "You are a strict trajectory judge. You receive a rubric and a "
    "summary of an AI agent's tool-call trace. Score how well the "
    "trace satisfies the rubric on a 0.0-1.0 scale. Return ONLY a JSON "
    'object with two keys: {"score": <float>, "reasoning": "<one '
    'sentence>"}. Do not include explanation outside the JSON.'
)


class HttpAnthropicJudgeClient:
    """Anthropic Messages API client implementing JudgeClient.

    Construction options:
      api_key=...   explicit credential (preferred for tests; do not
                    commit real keys).
      (default)     reads ANTHROPIC_API_KEY from the environment.

    Missing credentials raise ValueError at construction so the harness
    fails fast rather than burning a network round-trip.
    """

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError(
                "HttpAnthropicJudgeClient requires an api_key (or the "
                "ANTHROPIC_API_KEY env var); refuse to fire a request "
                "without credentials."
            )
        self._api_key = api_key
        self._timeout = timeout

    def score_trajectory(
        self,
        rubric: str,
        trace_summary: str,
        model: str,
        temperature: float = 0.0,
    ) -> JudgeResult:
        messages = build_judge_messages(rubric, trace_summary)
        body = json.dumps(
            {
                "model": model,
                "max_tokens": _DEFAULT_MAX_TOKENS,
                "system": _SYSTEM_PROMPT,
                "messages": messages,
                "temperature": temperature,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            _ANTHROPIC_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return JudgeResult(
                score=0.0,
                reasoning=f"HTTP {exc.code} from Anthropic: {exc.reason}",
                raw_response="",
                model=model,
                is_infra_error=True,
            )
        except urllib.error.URLError as exc:
            return JudgeResult(
                score=0.0,
                reasoning=f"URLError from Anthropic: {exc.reason}",
                raw_response="",
                model=model,
                is_infra_error=True,
            )
        except (TimeoutError, OSError) as exc:
            return JudgeResult(
                score=0.0,
                reasoning=f"network error from Anthropic: {exc}",
                raw_response="",
                model=model,
                is_infra_error=True,
            )

        text = _extract_text(payload)
        return parse_judge_response(text, model=payload.get("model", model))


def _extract_text(payload: dict) -> str:
    """Pull the first text block out of an Anthropic Messages response.

    Response shape (https://docs.anthropic.com/en/api/messages):
      {"content": [{"type": "text", "text": "..."}, ...], ...}
    """
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            return block["text"]
    return ""
