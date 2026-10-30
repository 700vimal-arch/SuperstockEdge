import numpy as np
import pandas as pd
from engine.magic_line import evaluate_magic_lines

DEFAULT_NAMES = {"10W SMA", "10W EMA", "20W SMA", "20W EMA"}


def cyclic_weekly(n=180, start=20.0, slope=0.18, amplitude=0.045, period=14):
    i = np.arange(n)
    index = pd.date_range("2019-01-04", periods=n, freq="W-FRI")
    trend = start + slope * i
    close = trend * (1 + amplitude * np.sin(2 * np.pi * i / period))
    return pd.DataFrame({
        "Open": close * 0.998,
        "High": close * 1.015,
        "Low": close * 0.988,
        "Close": close,
        "Volume": np.full(n, 100_000),
    }, index=index)


def flat_weekly(n=120, price=100.0):
    index = pd.date_range("2019-01-04", periods=n, freq="W-FRI")
    return pd.DataFrame({
        "Open": price, "High": price * 1.005, "Low": price * 0.995,
        "Close": price, "Volume": np.full(n, 100_000),
    }, index=index)


def test_candidates_are_evaluated_and_one_is_selected():
    lab = evaluate_magic_lines(cyclic_weekly(), {})
    assert {c["name"] for c in lab["candidates"]} == DEFAULT_NAMES
    assert lab["selected"] in DEFAULT_NAMES
    selected = lab["selected_metrics"]
    assert selected["qualified"] is True
    assert selected["tests"] >= 3
    assert selected["resolved_tests"] >= 2
    assert selected["successes"] >= 1
    assert 0 <= selected["score"] <= 100
    assert selected["avg_bounce_pct"] is not None
    assert lab["rationale"].startswith(selected["name"])


def test_selection_is_deterministic():
    x = cyclic_weekly()
    first = evaluate_magic_lines(x, {})
    second = evaluate_magic_lines(x.copy(), {})
    assert first["selected"] == second["selected"]
    assert first["candidates"] == second["candidates"]


def test_historical_outcomes_only_use_bars_available_at_evaluation_date():
    full = cyclic_weekly(180)
    cutoff = 140
    truncated = full.iloc[:cutoff]
    full_lab = evaluate_magic_lines(full, {"magic_line": {"forced_method": "10W SMA"}})
    truncated_lab = evaluate_magic_lines(truncated, {"magic_line": {"forced_method": "10W SMA"}})

    resolved_truncated = {
        e["date"]: e for e in truncated_lab["selected_metrics"]["events"] if e["status"] != "open"
    }
    resolved_full = {
        e["date"]: e for e in full_lab["selected_metrics"]["events"] if e["status"] != "open"
    }
    assert resolved_truncated
    for date, event in resolved_truncated.items():
        assert resolved_full[date] == event


def test_no_reliable_line_when_candidates_never_bounce():
    lab = evaluate_magic_lines(flat_weekly(), {})
    assert lab["selected"] is None
    assert "No reliable Magic Line identified" in lab["message"]
    assert all(c["successes"] == 0 for c in lab["candidates"])


def test_forced_method_overrides_selection():
    lab = evaluate_magic_lines(flat_weekly(), {"magic_line_method": "10W EMA"})
    assert lab["forced"] is True
    assert lab["selected"] == "10W EMA"
    assert "insufficient evidence" in lab["message"].lower()


def test_disabling_auto_select_uses_first_candidate():
    cfg = {"magic_line": {"auto_select": False, "candidates": ["10W SMA", "20W SMA"]}}
    lab = evaluate_magic_lines(cyclic_weekly(), cfg)
    assert [c["name"] for c in lab["candidates"]] == ["10W SMA"]
    assert lab["selected"] == "10W SMA"


def test_insufficient_history_reports_no_line():
    lab = evaluate_magic_lines(cyclic_weekly(20), {})
    assert lab["selected"] is None
    assert "No reliable Magic Line identified" in lab["message"]
