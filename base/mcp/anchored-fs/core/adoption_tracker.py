"""Per-Edit telemetry: voluntary [upto] vs auto-rescued vs full-old-block."""

from __future__ import annotations
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class AdoptionRecord:
    agent: str
    session: str
    used_upto: bool
    old_lines: int
    rescued: bool
    file_extension: str


def log_edit(log_path: Path, record: AdoptionRecord) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": time.time(), **asdict(record)}) + "\n"
    with open(log_path, "a") as fh:
        fh.write(line)
