import json
from pathlib import Path
from core.adoption_tracker import log_edit, AdoptionRecord


def test_log_edit_writes_jsonl(tmp_path: Path):
    log_path = tmp_path / "adoption.jsonl"
    log_edit(
        log_path,
        AdoptionRecord(
            agent="claude_code",
            session="abc",
            used_upto=True,
            old_lines=42,
            rescued=False,
            file_extension=".py",
        ),
    )
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["used_upto"] is True
    assert record["old_lines"] == 42


def test_log_edit_appends(tmp_path: Path):
    log_path = tmp_path / "a.jsonl"
    log_edit(
        log_path,
        AdoptionRecord(
            agent="codex",
            session="s1",
            used_upto=False,
            old_lines=10,
            rescued=False,
            file_extension=".md",
        ),
    )
    log_edit(
        log_path,
        AdoptionRecord(
            agent="codex",
            session="s1",
            used_upto=True,
            old_lines=30,
            rescued=False,
            file_extension=".md",
        ),
    )
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 2
