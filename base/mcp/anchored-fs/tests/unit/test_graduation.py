import time
from core.graduation import (
    evaluate_edit_anchor,
    evaluate_stale_read_guard,
    GraduationDecision,
)


def test_edit_anchor_stays_auto_rescue_when_sample_too_small():
    records = [
        {"ts": time.time(), "used_upto": False, "old_lines": 30} for _ in range(10)
    ]
    decision = evaluate_edit_anchor(
        records,
        current_mode="auto_rescue",
        threshold_pct=30,
        min_sample=100,
        window_days=28,
        oversize_threshold=25,
    )
    assert decision == GraduationDecision(
        new_mode="auto_rescue", reason="insufficient sample"
    )


def test_edit_anchor_graduates_to_force_reject_when_adoption_low():
    records = [
        {"ts": time.time(), "used_upto": False, "old_lines": 30} for _ in range(150)
    ]
    decision = evaluate_edit_anchor(
        records,
        current_mode="auto_rescue",
        threshold_pct=30,
        min_sample=100,
        window_days=28,
        oversize_threshold=25,
    )
    assert decision.new_mode == "force_reject"


def test_edit_anchor_stays_when_adoption_above_threshold():
    records = [
        {"ts": time.time(), "used_upto": True, "old_lines": 30} for _ in range(80)
    ]
    records += [
        {"ts": time.time(), "used_upto": False, "old_lines": 30} for _ in range(20)
    ]
    decision = evaluate_edit_anchor(
        records,
        current_mode="auto_rescue",
        threshold_pct=30,
        min_sample=100,
        window_days=28,
        oversize_threshold=25,
    )
    assert decision.new_mode == "auto_rescue"


def test_stale_read_graduates_to_block_when_quality_high():
    records = [{"ts": time.time(), "useful": True} for _ in range(48)]
    records += [{"ts": time.time(), "useful": False} for _ in range(2)]
    decision = evaluate_stale_read_guard(
        records, current_mode="warn", threshold_pct=95, min_sample=50, window_days=28
    )
    assert decision.new_mode == "block"


def test_stale_read_stays_warn_when_quality_low():
    records = [{"ts": time.time(), "useful": True} for _ in range(30)]
    records += [{"ts": time.time(), "useful": False} for _ in range(30)]
    decision = evaluate_stale_read_guard(
        records, current_mode="warn", threshold_pct=95, min_sample=50, window_days=28
    )
    assert decision.new_mode == "warn"
