import numpy as np
import pandas as pd
from engine.technicals import weekly_ohlcv, analyse_weekly, atr, score_candidate


def sample_daily(n=600):
    idx = pd.bdate_range("2020-01-01", periods=n)
    close = 20 + np.linspace(0, 15, n) + np.sin(np.arange(n)/12)
    return pd.DataFrame({"Open": close*.995, "High": close*1.01, "Low": close*.99,
                         "Close": close, "Volume": np.full(n, 100000)}, index=idx)


def test_weekly_aggregation_has_ohlcv():
    w = weekly_ohlcv(sample_daily())
    assert {"Open", "High", "Low", "Close", "Volume"}.issubset(w.columns)
    assert len(w) > 40


def test_atr_positive():
    assert atr(sample_daily()).dropna().gt(0).all()


def test_analysis_returns_insufficient_for_short_history():
    assert analyse_weekly(sample_daily(80).iloc[:30])["ready"] is False


def test_analysis_has_expected_fields():
    result = analyse_weekly(weekly_ohlcv(sample_daily()))
    assert result["ready"] is True
    assert result["magic_line_name"] == "10W EMA"
    assert 0 <= result["exit_risk_score"] <= 100
    assert "base_ok" in result


def test_score_candidate_does_not_invent_missing_fundamentals():
    tech = analyse_weekly(weekly_ohlcv(sample_daily()))
    result = score_candidate(tech, {})
    assert result["fundamental_score"] == 0
    assert "0/4" in result["data_coverage"]
    assert 0 <= result["opportunity_score"] <= 100


def test_quiet_entry_requires_valid_base_and_magic_proximity():
    w = weekly_ohlcv(sample_daily())
    cfg = {"minimum_history_weeks": 40, "base_min_weeks": 10, "base_max_weeks": 26,
           "base_max_range_pct": 0.01, "quiet_magic_distance_pct": 0.01}
    result = analyse_weekly(w, cfg)
    assert result["quiet"] is False


def test_magic_line_method_is_configurable():
    w = weekly_ohlcv(sample_daily())
    result = analyse_weekly(w, {"magic_line_method": "20W SMA"})
    assert result["magic_line_name"] == "20W SMA"
