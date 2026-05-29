"""Contract tests for scripts/skill_identity.py.

skill_identity.py is the canonical join key for "which skill is this?":
the answer must be the same across decay, atlas, telemetry, and any
future cross-subsystem aggregate. The tests pin every branch of the
parser, the convenience field accessor, and the identity resolver so
behavior cannot drift silently.

Suite layout:

    TestParseFrontmatter     happy-path frontmatter, missing markers,
                             unterminated block, empty values, quoted
                             values, comment + blank-line tolerance.
    TestFrontmatterField     present field, missing field, empty
                             field returns None.
    TestSkillIdentity        frontmatter wins, directory fallback,
                             empty frontmatter falls back, unreadable
                             file falls back gracefully.
"""

from __future__ import annotations

from pathlib import Path

from skill_identity import frontmatter_field, parse_frontmatter, skill_identity


class TestParseFrontmatter:
    def test_no_frontmatter_returns_empty_dict_and_full_content(self):
        fm, body = parse_frontmatter("body only")
        assert fm == {}
        assert body == "body only"

    def test_unterminated_frontmatter_returns_empty(self):
        fm, body = parse_frontmatter("---\nname: x\nno closing")
        assert fm == {}
        assert body == "---\nname: x\nno closing"

    def test_simple_field_parsed(self):
        fm, body = parse_frontmatter("---\nname: foo\n---\nbody\n")
        assert fm["name"] == "foo"
        assert body == "body\n"

    def test_quoted_value_stripped(self):
        fm, _ = parse_frontmatter('---\nname: "foo bar"\n---\nbody\n')
        assert fm["name"] == "foo bar"

    def test_single_quoted_value_stripped(self):
        fm, _ = parse_frontmatter("---\nname: 'foo bar'\n---\nbody\n")
        assert fm["name"] == "foo bar"

    def test_empty_value_returns_empty_string(self):
        fm, _ = parse_frontmatter("---\nname:\n---\nbody\n")
        assert fm["name"] == ""

    def test_whitespace_trimmed(self):
        fm, _ = parse_frontmatter("---\nname:   foo   \n---\nbody\n")
        assert fm["name"] == "foo"

    def test_multiple_fields_all_parsed(self):
        fm, _ = parse_frontmatter(
            "---\nname: foo\ndescription: short\nowner: rehan\n---\nbody\n"
        )
        assert fm["name"] == "foo"
        assert fm["description"] == "short"
        assert fm["owner"] == "rehan"

    def test_comment_lines_skipped(self):
        fm, _ = parse_frontmatter("---\n# this is a comment\nname: foo\n---\nbody\n")
        assert fm == {"name": "foo"}

    def test_blank_lines_skipped(self):
        fm, _ = parse_frontmatter("---\n\nname: foo\n\n---\nbody\n")
        assert fm == {"name": "foo"}


class TestFrontmatterField:
    def test_missing_field_returns_none(self):
        assert frontmatter_field("---\nname: foo\n---\nbody", "missing") is None

    def test_empty_field_returns_none(self):
        assert frontmatter_field("---\nname:\n---\nbody", "name") is None

    def test_present_field_returned(self):
        assert frontmatter_field("---\nname: foo\n---\nbody", "name") == "foo"

    def test_no_frontmatter_returns_none(self):
        assert frontmatter_field("body only", "name") is None


class TestSkillIdentity:
    def test_frontmatter_name_wins(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "directory-name"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: frontmatter-name\n---\nbody", encoding="utf-8")
        assert skill_identity(skill_md) == "frontmatter-name"

    def test_directory_fallback_when_no_frontmatter(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "dir-name"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("body only", encoding="utf-8")
        assert skill_identity(skill_md) == "dir-name"

    def test_directory_fallback_when_frontmatter_name_empty(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "dir-name"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname:\n---\nbody", encoding="utf-8")
        assert skill_identity(skill_md) == "dir-name"

    def test_directory_fallback_when_frontmatter_lacks_name(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "dir-name"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\ndescription: x\n---\nbody", encoding="utf-8")
        assert skill_identity(skill_md) == "dir-name"

    def test_unreadable_file_falls_back_to_directory(self, tmp_path: Path):
        skill_dir = tmp_path / "skills" / "dir-name"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        # Do not create the file. skill_identity should fall back gracefully.
        assert skill_identity(skill_md) == "dir-name"
