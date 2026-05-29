"""HttpAnthropicJudgeClient: real client using stdlib urllib (Phase 2A Task 3).

Tests mock urllib.request.urlopen so no live HTTP calls are made.
The repo has a no-deps policy so the Anthropic SDK is not used; the
client speaks the Anthropic Messages REST API directly.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
# unittest.mock not needed; monkeypatch covers the cases here.

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


def _mock_urlopen_response(payload: dict, status: int = 200):
    """Build a context-manager-compatible mock for urllib.request.urlopen.

    The Anthropic Messages API returns JSON like:
      {"content": [{"type": "text", "text": "..."}], "model": "...", ...}
    """

    class _Resp:
        def __init__(self, body: bytes, status: int):
            self.fp = io.BytesIO(body)
            self.status = status

        def read(self) -> bytes:
            return self.fp.read()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(json.dumps(payload).encode("utf-8"), status)


def test_client_posts_to_anthropic_messages_endpoint(monkeypatch) -> None:
    from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

    captured: dict = {}

    def fake_urlopen(request, *args, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _mock_urlopen_response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": '{"score": 0.9, "reasoning": "good"}',
                    }
                ],
                "model": "claude-sonnet-4-6",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = HttpAnthropicJudgeClient(api_key="sk-ant-test")
    result = client.score_trajectory(
        rubric="x",
        trace_summary="y",
        model="claude-sonnet-4-6",
    )

    assert "api.anthropic.com" in captured["url"]
    assert captured["method"] == "POST"
    # Headers are stored title-cased by urllib; check case-insensitively.
    header_keys_lower = {k.lower() for k in captured["headers"]}
    assert "x-api-key" in header_keys_lower
    assert "anthropic-version" in header_keys_lower
    assert "content-type" in header_keys_lower
    assert captured["body"]["model"] == "claude-sonnet-4-6"
    assert captured["body"]["messages"][0]["role"] == "user"
    assert "x" in captured["body"]["messages"][0]["content"]
    assert captured["body"]["temperature"] == 0.0
    assert result.score == 0.9
    assert result.reasoning == "good"


def test_client_raises_on_missing_api_key() -> None:
    """Cheaper than letting urlopen fail with an opaque 401: refuse to
    even attempt a call without credentials."""
    from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

    import pytest as _pytest

    with _pytest.raises(ValueError, match="api_key"):
        HttpAnthropicJudgeClient(api_key="")


def test_client_returns_zero_score_on_http_error(monkeypatch) -> None:
    """Network or rate-limit errors must not crash the harness; they
    surface as score=0 with the error in reasoning."""
    import urllib.error as _urlerror

    from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

    def boom(*args, **kwargs):
        raise _urlerror.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=429,
            msg="rate limited",
            hdrs=None,
            fp=None,  # type: ignore[arg-type]
        )

    monkeypatch.setattr("urllib.request.urlopen", boom)

    client = HttpAnthropicJudgeClient(api_key="sk-ant-test")
    result = client.score_trajectory(
        rubric="x",
        trace_summary="y",
        model="claude-sonnet-4-6",
    )
    assert result.score == 0.0
    assert "429" in result.reasoning or "rate" in result.reasoning.lower()


def test_client_picks_up_api_key_from_env(monkeypatch) -> None:
    """Default credential source: ANTHROPIC_API_KEY env var. Explicit
    api_key= overrides; both must work."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    from adapters.anthropic_judge_client import HttpAnthropicJudgeClient

    client = HttpAnthropicJudgeClient()
    assert client._api_key == "sk-ant-from-env"  # noqa: SLF001
