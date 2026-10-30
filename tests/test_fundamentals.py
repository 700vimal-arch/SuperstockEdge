import sys
from types import ModuleType
import pandas as pd
from engine import fundamentals as fundamentals_module
from engine.fundamentals import earnings_acceleration_from_statement
from engine.technicals import score_candidate


def install_fake_market_data(monkeypatch, payload):
    module = ModuleType("data.market_data")
    module.fetch_fundamentals = lambda symbol: payload
    monkeypatch.setitem(sys.modules, "data.market_data", module)


def test_quarterly_snapshot_returns_two_dicts(monkeypatch):
    install_fake_market_data(monkeypatch, ({"company": "RELIANCE.NS"}, {"status": "best_effort"}))
    data, meta = fundamentals_module.quarterly_snapshot("RELIANCE.NS")
    assert isinstance(data, dict) and isinstance(meta, dict)
    assert data["company"] == "RELIANCE.NS"


def test_quarterly_snapshot_normalizes_bad_provider_payload(monkeypatch):
    install_fake_market_data(monkeypatch, ("provider error", "metadata"))
    data, meta = fundamentals_module.quarterly_snapshot("RELIANCE.NS")
    assert data == {} and isinstance(meta, dict)


def test_score_candidate_accepts_malformed_fundamentals():
    result = score_candidate({"ready": False}, "provider error")
    assert result["fundamental_score"] == 0
    assert result["opportunity_score"] == 0


def test_earnings_acceleration_requires_six_quarters():
    idx = pd.date_range("2024-01-01", periods=6, freq="QS")
    statement = pd.DataFrame([ [1, 1.1, 1.2, 1.4, 1.7, 2.0] ], index=["Diluted EPS"], columns=idx)
    result = earnings_acceleration_from_statement(statement)
    assert result["available"] is True
    assert result["accelerating"] is True
