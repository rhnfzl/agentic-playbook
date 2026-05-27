from core.envelope import build_envelope


def test_build_envelope_required_fields():
    env = build_envelope(
        validator="edit_anchor",
        kind="anchor_not_unique",
        message="3 matches",
        candidates=[{"location": "X.py:12", "snippet": "..."}],
        hint="Use longer prefix",
        context={"file": "X.py"},
    )
    assert env["ok"] is False
    assert env["validator"] == "edit_anchor"
    assert env["candidates"] == [{"location": "X.py:12", "snippet": "..."}]


def test_build_envelope_defaults_empty_candidates():
    env = build_envelope(
        validator="stale_read_guard", kind="stale_read", message="x", hint="re-read"
    )
    assert env["candidates"] == [] and env["context"] == {}
