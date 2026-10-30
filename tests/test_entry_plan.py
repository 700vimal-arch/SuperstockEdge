import numpy as np
import pandas as pd
from engine.entry_plan import build_trade_plan, reward_risk_band

CONFIG = {
    "quiet_volume_multiple": 0.75,
    "quiet_atr_multiple": 0.85,
    "entry": {
        "zone_width_pct": 2.5,
        "max_entry_distance_pct": 8.0,
        "swing_lookback_weeks": 8,
        "atr_stop_multiple": 2.0,
        "min_stop_atr": 0.75,
        "stop_buffer_atr": 0.25,
        "min_stop_pct": 1.0,
        "max_stop_pct": 12.0,
        "pe_scenarios": {"conservative": 12, "base": 20, "optimistic": 30},
    },
}


def weekly_fixture(lows=None):
    values = lows or [101, 99, 100, 99.5, 100.5, 99.2, 100.8, 100.1]
    index = pd.date_range("2023-01-06", periods=len(values), freq="W-FRI")
    return pd.DataFrame({
        "Open": values, "High": [v + 1 for v in values],
        "Low": values, "Close": [v + 0.4 for v in values],
        "Volume": np.full(len(values), 100_000),
    }, index=index)


def tech_fixture(**overrides):
    tech = {
        "ready": True,
        "close": 104.0,
        "base_ok": True,
        "base_high": 108.0,
        "base_low": 90.0,
        "magic_line": 103.0,
        "near_magic": True,
        "quiet_volume_multiple": 0.6,
        "quiet_atr_multiple": 0.7,
        "atr14": 3.0,
        "breakout": False,
        "exit_risk_score": 10,
        "magic_breakdown": False,
        "weekly": weekly_fixture(),
    }
    tech.update(overrides)
    return tech


def test_confirmed_quiet_setup_produces_entry_stop_and_targets():
    plan = build_trade_plan(tech_fixture(), {"latest_quarter_eps": 2.0}, CONFIG)
    assert plan["actionable"] is True
    assert plan["setup"] == "C"
    assert plan["entry_zone_low"] < plan["entry_zone_high"]
    assert plan["stop"] < plan["entry_zone_low"]
    assert plan["risk_per_share"] > 0
    assert plan["technical_targets"] and plan["fundamental_targets"]
    assert all(t["source"] == "Technical" for t in plan["technical_targets"])
    assert all(t["source"] == "Fundamental" for t in plan["fundamental_targets"])
    assert plan["primary_target"] is not None
    assert plan["reward_risk"] is not None and plan["reward_risk"] >= 1
    assert plan["reward_risk_band"] is not None
    assert plan["annualized_eps"] == 8.0
    assert plan["annualized_pe"] == round(104 / 8, 2)


def test_stop_prefers_a_structural_level_over_a_tighter_atr_stop():
    plan = build_trade_plan(tech_fixture(), {"latest_quarter_eps": 2.0}, CONFIG)
    assert plan["stop_reason"].startswith("Stop placed below the")
    expected = round(99.0 - 0.25 * 3.0, 2)
    assert abs(plan["stop"] - expected) < 0.01


def test_non_positive_eps_skips_fundamental_targets():
    plan = build_trade_plan(tech_fixture(), {"latest_quarter_eps": -1.5}, CONFIG)
    assert plan["actionable"] is True
    assert plan["fundamental_targets"] == []
    assert plan["annualized_eps"] is None
    assert any("non-positive" in warning for warning in plan["warnings"])


def test_elevated_exit_risk_blocks_new_entry_plan():
    plan = build_trade_plan(tech_fixture(exit_risk_score=70), {"latest_quarter_eps": 2.0}, CONFIG)
    assert plan["actionable"] is False
    assert plan["setup"] == "E"
    assert any("exit warning" in reason.lower() for reason in plan["reasons"])


def test_price_far_from_reference_is_rejected():
    tech = tech_fixture(close=130.0, base_ok=False, near_magic=False,
                        quiet_volume_multiple=1.2, quiet_atr_multiple=1.1,
                        magic_line=100.0)
    plan = build_trade_plan(tech, {"latest_quarter_eps": 2.0}, CONFIG)
    assert plan["actionable"] is False
    assert plan["setup"] == "E"


def test_post_breakout_setup_uses_base_high_retest_zone():
    tech = tech_fixture(close=110.0, breakout=True, near_magic=False,
                        quiet_volume_multiple=1.3, quiet_atr_multiple=1.2,
                        magic_line=98.0)
    plan = build_trade_plan(tech, {"latest_quarter_eps": 2.0}, CONFIG)
    assert plan["actionable"] is True
    assert plan["setup"] == "B"
    assert plan["entry_reference"] == 108.0
    assert plan["entry_zone_low"] < plan["entry_zone_high"]


def test_reward_risk_bands_match_spec_boundaries():
    assert reward_risk_band(None) is None
    assert reward_risk_band(1.99) == "Below 2R"
    assert reward_risk_band(2.0) == "2R–3R"
    assert reward_risk_band(2.99) == "2R–3R"
    assert reward_risk_band(3.0) == "3R–5R"
    assert reward_risk_band(5.0) == "3R–5R"
    assert reward_risk_band(5.01) == "Above 5R"


def test_unready_technical_data_yields_no_plan():
    plan = build_trade_plan({"ready": False}, {}, CONFIG)
    assert plan["actionable"] is False
    assert plan["setup"] == "E"
    assert plan["reasons"]


