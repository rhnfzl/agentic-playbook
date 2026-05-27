"""Auto-graduation engine: telemetry-driven mode transitions per validator."""

from __future__ import annotations
import time
from dataclasses import dataclass


@dataclass
class GraduationDecision:
    new_mode: str
    reason: str


def _within_window(records: list[dict], window_days: int) -> list[dict]:
    cutoff = time.time() - window_days * 86400
    return [r for r in records if r.get("ts", 0) >= cutoff]


def evaluate_edit_anchor(
    records: list[dict],
    *,
    current_mode: str,
    threshold_pct: float,
    min_sample: int,
    window_days: int,
    oversize_threshold: int,
) -> GraduationDecision:
    in_window = _within_window(records, window_days)
    qualifying = [r for r in in_window if r.get("old_lines", 0) >= oversize_threshold]
    if len(qualifying) < min_sample:
        return GraduationDecision(new_mode=current_mode, reason="insufficient sample")
    voluntary_count = sum(1 for r in qualifying if r.get("used_upto"))
    voluntary_pct = (voluntary_count / len(qualifying)) * 100
    if current_mode == "auto_rescue" and voluntary_pct < threshold_pct:
        return GraduationDecision(
            new_mode="force_reject",
            reason=f"voluntary adoption {voluntary_pct:.1f}% < {threshold_pct}%",
        )
    return GraduationDecision(
        new_mode=current_mode,
        reason=f"voluntary adoption {voluntary_pct:.1f}% (stable)",
    )


def evaluate_stale_read_guard(
    records: list[dict],
    *,
    current_mode: str,
    threshold_pct: float,
    min_sample: int,
    window_days: int,
) -> GraduationDecision:
    in_window = _within_window(records, window_days)
    if len(in_window) < min_sample:
        return GraduationDecision(new_mode=current_mode, reason="insufficient sample")
    useful_count = sum(1 for r in in_window if r.get("useful"))
    useful_pct = (useful_count / len(in_window)) * 100
    if current_mode == "warn" and useful_pct >= threshold_pct:
        return GraduationDecision(
            new_mode="block",
            reason=f"warn quality {useful_pct:.1f}% >= {threshold_pct}%",
        )
    return GraduationDecision(
        new_mode=current_mode,
        reason=f"warn quality {useful_pct:.1f}% (stable)",
    )
