import json
import pytest
from core.manifest import load_template, validate, render


def test_template_loads_and_validates():
    template = load_template()
    assert template["schema_version"] == 1
    assert "hooks" in template
    assert "mcp_servers" in template
    validate(template)


def test_render_substitutes_anchored_fs_root():
    template = load_template()
    rendered = render(
        template,
        anchored_fs_root="/Users/test/.config/agent-shared/mcp_servers/anchored-fs",
    )
    pretool_cmd = rendered["hooks"]["claude_code_pre_tool_use"]["command"]
    assert pretool_cmd.startswith(
        "python3 /Users/test/.config/agent-shared/mcp_servers/anchored-fs/"
    )
    assert "{anchored_fs_root}" not in json.dumps(rendered)


def test_validate_rejects_missing_schema_version():
    with pytest.raises(ValueError, match="schema_version"):
        validate({"hooks": {}, "mcp_servers": {}})
