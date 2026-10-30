import pandas as pd
import pytest

import data.market_data as market_data


def make_raw(tickers, periods=60):
    dates = pd.date_range("2024-01-01", periods=periods, freq="D")
    frames = {}
    for ticker in tickers:
        close = pd.Series(range(100, 100 + periods), index=dates, dtype=float)
        frames[ticker] = pd.DataFrame({
            "Open": close, "High": close + 1, "Low": close - 1,
            "Close": close, "Volume": 1000,
        })
    return pd.concat(frames, axis=1)


def test_prefetch_writes_cache_and_second_run_skips_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(market_data, "CACHE", tmp_path)
    calls = []

    def fake_download(tickers, **kwargs):
        calls.append(list(tickers))
        return make_raw(list(tickers))

    monkeypatch.setattr(market_data.yf, "download", fake_download)

    first = market_data.prefetch_ohlcv(["AAA", "BBB"], period="1y")
    second = market_data.prefetch_ohlcv(["AAA", "BBB"], period="1y")

    assert sorted(first["downloaded"]) == ["AAA", "BBB"]
    assert first["failed"] == []
    assert second["downloaded"] == []
    assert second["cached"] == 2
    assert len(calls) == 1
    assert (tmp_path / "AAA_1y_1d.csv").exists()
    frame, meta = market_data.fetch_ohlcv("AAA", period="1y")
    assert meta["status"] == "cached"
    assert len(frame) == 60


def test_prefetch_isolates_a_failing_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(market_data, "CACHE", tmp_path)

    def fake_download(tickers, **kwargs):
        raw = make_raw([t for t in tickers if t != "BAD"])
        return raw

    monkeypatch.setattr(market_data.yf, "download", fake_download)
    monkeypatch.setattr(market_data, "fetch_ohlcv", lambda *a, **k: (pd.DataFrame(), {"status": "error"}))

    result = market_data.prefetch_ohlcv(["GOOD", "BAD"], period="1y")

    assert result["downloaded"] == ["GOOD"]
    assert result["failed"] == ["BAD"]


def test_prefetch_reports_progress(monkeypatch, tmp_path):
    monkeypatch.setattr(market_data, "CACHE", tmp_path)
    monkeypatch.setattr(market_data.yf, "download", lambda tickers, **kw: make_raw(list(tickers)))
    events = []

    market_data.prefetch_ohlcv(["AAA"], period="1y", progress=lambda done, total, label: events.append((done, total, label)))

    assert events and events[-1][0] == 1
