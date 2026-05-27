from core.upto_resolver import resolve, ResolvedSpan, ResolveFailure


def test_resolve_unique_anchor():
    content = "line 1\ndef foo():\n    x = 1\n    return x\n\nline 6\n"
    result = resolve(content, "def foo():[upto]    return x")
    assert isinstance(result, ResolvedSpan)
    assert result.text == "def foo():\n    x = 1\n    return x"
    assert result.start_line == 2
    assert result.end_line == 4


def test_resolve_no_upto_marker_returns_failure():
    result = resolve("anything", "no marker here")
    assert isinstance(result, ResolveFailure) and result.kind == "no_upto_marker"


def test_resolve_prefix_not_found():
    result = resolve("line a\nline b\n", "def missing():[upto]    return x")
    assert isinstance(result, ResolveFailure) and result.kind == "prefix_not_found"


def test_resolve_prefix_ambiguous():
    content = "def foo():\n    x = 1\ndef foo():\n    x = 2\n"
    result = resolve(content, "def foo():[upto]    x = 1")
    assert isinstance(result, ResolveFailure)
    assert result.kind == "prefix_not_unique"
    assert len(result.candidates) == 2


def test_resolve_suffix_not_found_after_prefix():
    result = resolve("def foo():\n    x = 1\n", "def foo():[upto]    return missing")
    assert isinstance(result, ResolveFailure) and result.kind == "suffix_not_found"


def test_resolve_escape_literal_upto():
    content = 'msg = "[upto] is a marker"\nreturn 1\n'
    result = resolve(content, 'msg = "\\[upto\\] is a marker"[upto]return 1')
    assert isinstance(result, ResolvedSpan)
    assert result.text == 'msg = "[upto] is a marker"\nreturn 1'
