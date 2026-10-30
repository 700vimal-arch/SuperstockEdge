from datetime import datetime, timedelta, timezone

from data.universe import SOURCES, load_universe, normalize_symbols, watchlist_symbols


def test_sp500_symbols_become_yahoo_safe():
    symbols = normalize_symbols(["MMM", "BRK.B", "BF.B", " brk.b "], SOURCES["sp500"])
    assert symbols == ["MMM", "BRK-B", "BF-B"]


def test_nifty_symbols_get_the_ns_suffix():
    symbols = normalize_symbols(["RELIANCE", "M&M", "360ONE", "BAJAJ-AUTO"], SOURCES["nifty500"])
    assert symbols == ["RELIANCE.NS", "M&M.NS", "360ONE.NS", "BAJAJ-AUTO.NS"]


def test_normalize_drops_headers_and_duplicates():
    symbols = normalize_symbols(["Symbol", "AAPL", "AAPL", "", "??", None], SOURCES["sp500"])
    assert symbols == ["AAPL"]


def test_cache_round_trip_calls_the_fetcher_once(tmp_path):
    calls = []

    def fetcher(key):
        calls.append(key)
        return ["AAA", "BBB"]

    first, meta_first = load_universe("sp500", fetcher=fetcher, cache_dir=tmp_path)
    second, meta_second = load_universe("sp500", fetcher=fetcher, cache_dir=tmp_path)

    assert first == second == ["AAA", "BBB"]
    assert calls == ["sp500"]
    assert meta_first["status"] == "network"
    assert meta_second["status"] == "cache"


def test_stale_snapshot_is_used_when_refresh_fails(tmp_path):
    def good(key):
        return ["AAA"]

    def broken(key):
        raise RuntimeError("offline")

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    load_universe("sp500", fetcher=good, cache_dir=tmp_path, now=start)
    symbols, meta = load_universe(
        "sp500", fetcher=broken, cache_dir=tmp_path,
        now=start + timedelta(days=30), refresh=True,
    )

    assert symbols == ["AAA"]
    assert meta["status"] == "stale_cache"
    assert "offline" in meta["warning"]


def test_expired_cache_triggers_a_refresh(tmp_path):
    calls = []

    def fetcher(key):
        calls.append(len(calls))
        return [f"S{len(calls)}"]

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    load_universe("sp500", fetcher=fetcher, cache_dir=tmp_path, now=start)
    symbols, meta = load_universe(
        "sp500", fetcher=fetcher, cache_dir=tmp_path,
        now=start + timedelta(days=8), ttl_days=7,
    )

    assert symbols == ["S2"]
    assert meta["status"] == "network"
    assert len(calls) == 2


def test_missing_cache_and_failing_source_reports_error(tmp_path):
    def broken(key):
        raise RuntimeError("no network")

    symbols, meta = load_universe("nasdaq100", fetcher=broken, cache_dir=tmp_path)
    assert symbols == []
    assert meta["status"] == "error"
    assert "no network" in meta["warning"]


def test_watchlist_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "watchlist.txt"
    path.write_text("# comment\nAAPL\n\nRELIANCE.NS\n", encoding="utf-8")
    assert watchlist_symbols(path) == ["AAPL", "RELIANCE.NS"]
