"""Tests for the usage-based decay path in decay_check.

The check should:
  * silently skip when TELEMETRY=off
  * silently skip when no JSONL exists
  * flag skills as "no usage signal" when JSONL exists but the
    skill has no events
  * flag skills as "usage-decay band" when last fired > 60d ago
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import decay_check  # noqa: E402


def _seed_skill(repo: Path, skill_name: str) -> Path:
    skill_dir = repo / "base" / "skills" / "engineering" / skill_name
    skill_dir.mkdir(parents=True)
    md = skill_dir / "SKILL.md"
    md.write_text(
        f"---\nname: {skill_name}\ndescription: t\nversion: 0.1.0\n"
        f"owner: t\nlast_reviewed: 2026-05-28\n---\n\n# {skill_name}\n",
        encoding="utf-8",
    )
    return md


def _seed_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def test_silent_skip_when_telemetry_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY", "off")
    skill_md = _seed_skill(tmp_path, "demo")
    out = decay_check._usage_decay_findings(
        [skill_md],
        tmp_path,
        today=date(2026, 5, 28),
    )
    assert out == []


def test_silent_skip_when_no_jsonl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    monkeypatch.setenv("TELEMETRY_DIR", str(tmp_path / "no-such-dir"))
    skill_md = _seed_skill(tmp_path, "demo")
    out = decay_check._usage_decay_findings(
        [skill_md],
        tmp_path,
        today=date(2026, 5, 28),
    )
    assert out == []


def test_flags_skill_with_no_telemetry_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    monkeypatch.setenv("TELEMETRY_DIR", str(tmp_path / "tele"))
    _seed_jsonl(
        tmp_path / "tele" / "skills.jsonl",
        [
            {
                "skill": "other-skill",
                "adapter": "claude-code",
                "model": "m",
                "fired_at": "2026-05-27T12:00:00+00:00",
                "latency_ms": 100,
                "input_tokens": 1,
                "output_tokens": 1,
            }
        ],
    )
    skill_md = _seed_skill(tmp_path, "demo")
    out = decay_check._usage_decay_findings(
        [skill_md],
        tmp_path,
        today=date(2026, 5, 28),
    )
    assert any("no telemetry events" in line for line in out)


def test_flags_skill_with_stale_usage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    monkeypatch.setenv("TELEMETRY_DIR", str(tmp_path / "tele"))
    stale_iso = (date(2026, 5, 28) - timedelta(days=65)).isoformat() + "T00:00:00+00:00"
    _seed_jsonl(
        tmp_path / "tele" / "skills.jsonl",
        [
            {
                "skill": "demo",
                "adapter": "claude-code",
                "model": "m",
                "fired_at": stale_iso,
                "latency_ms": 100,
                "input_tokens": 1,
                "output_tokens": 1,
            }
        ],
    )
    skill_md = _seed_skill(tmp_path, "demo")
    out = decay_check._usage_decay_findings(
        [skill_md],
        tmp_path,
        today=date(2026, 5, 28),
    )
    assert any("usage-decay band" in line for line in out)


def test_does_not_flag_skill_with_recent_usage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY", raising=False)
    monkeypatch.delenv("TELEMETRY_ENABLED", raising=False)
    monkeypatch.delenv("PLAYBOOK_TELEMETRY", raising=False)
    monkeypatch.setenv("TELEMETRY_DIR", str(tmp_path / "tele"))
    fresh_iso = (date(2026, 5, 28) - timedelta(days=5)).isoformat() + "T00:00:00+00:00"
    _seed_jsonl(
        tmp_path / "tele" / "skills.jsonl",
        [
            {
                "skill": "demo",
                "adapter": "claude-code",
                "model": "m",
                "fired_at": fresh_iso,
                "latency_ms": 100,
                "input_tokens": 1,
                "output_tokens": 1,
            }
        ],
    )
    skill_md = _seed_skill(tmp_path, "demo")
    out = decay_check._usage_decay_findings(
        [skill_md],
        tmp_path,
        today=date(2026, 5, 28),
    )
    assert out == []
