"""Tests for the skill_telemetry_report CLI.

Two contracts:
  1. The CLI respects the TELEMETRY=off env var (no-op exit 0).
  2. With a seeded JSONL, the CLI prints per-skill rows.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import skill_telemetry_report  # noqa: E402


def _seed_jsonl(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "skill": "to-prd",
                    "adapter": "claude-code",
                    "model": "claude-opus-4-7",
                    "fired_at": "2026-05-28T12:00:00+00:00",
                    "latency_ms": 1200.0,
                    "input_tokens": 100,
                    "output_tokens": 200,
                }
            )
            + "\n"
        )
    return path


def test_disabled_skips_with_message(monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY", "off")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = skill_telemetry_report.main(["--days", "30"])
    assert rc == 0
    assert "telemetry disabled" in buf.getvalue()


def test_empty_storage_prints_no_events_notice(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = skill_telemetry_report.main(
            [
                "--days",
                "30",
                "--input",
                str(tmp_path / "missing.jsonl"),
            ]
        )
    assert rc == 0
    assert "no skill events" in buf.getvalue()


def test_reports_table_with_seeded_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    seeded = _seed_jsonl(tmp_path / "skills.jsonl")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = skill_telemetry_report.main(
            [
                "--days",
                "0",  # all-time
                "--input",
                str(seeded),
            ]
        )
    assert rc == 0
    out = buf.getvalue()
    assert "to-prd" in out
    assert "TRIGGERS" in out


def test_json_mode_emits_machine_readable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    seeded = _seed_jsonl(tmp_path / "skills.jsonl")
    buf = io.StringIO()
    with redirect_stdout(buf):
        skill_telemetry_report.main(
            [
                "--days",
                "0",
                "--input",
                str(seeded),
                "--json",
            ]
        )
    payload = json.loads(buf.getvalue())
    assert payload[0]["skill"] == "to-prd"
    assert payload[0]["trigger_count"] == 1
