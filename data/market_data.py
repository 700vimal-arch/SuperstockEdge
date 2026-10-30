"""Free-first market data adapter. Yahoo Finance access is best-effort, not guaranteed/live."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "storage" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)


def _clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns={c: str(c).title() for c in df.columns})
    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(c in df.columns for c in required):
        return pd.DataFrame()
    df = df[required].copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    df = df[(df.High >= df[["Open", "Close", "Low"]].max(axis=1)) &
            (df.Low <= df[["Open", "Close", "High"]].min(axis=1))]
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_ohlcv(symbol: str, period: str = "5y", interval: str = "1d", refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    path = cache_path(symbol, period, interval)
    if path.exists() and not refresh:
        try:
            df = _clean_ohlcv(pd.read_csv(path, index_col=0, parse_dates=True))
            if not df.empty:
                return df, {"source": "Yahoo Finance cache", "status": "cached",
                            "retrieved_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                            "adjustment": "auto_adjust=True"}
        except Exception:
            pass
    try:
        raw = yf.download(symbol, period=period, interval=interval, auto_adjust=True,
                          progress=False, threads=False)
        df = _clean_ohlcv(raw)
        if df.empty:
            return pd.DataFrame(), {"source": "Yahoo Finance", "status": "no_data",
                                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                                    "message": "Provider returned no usable OHLCV rows."}
        df.to_csv(path)
        return df, {"source": "Yahoo Finance", "status": "downloaded",
                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "rows": len(df), "adjustment": "auto_adjust=True"}
    except Exception as exc:
        return pd.DataFrame(), {"source": "Yahoo Finance", "status": "error",
                                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                                "message": str(exc)}


def cache_path(symbol: str, period: str = "5y", interval: str = "1d") -> Path:
    safe = symbol.replace("/", "_").replace("^", "IDX_")
    return CACHE / f"{safe}_{period}_{interval}.csv"


def prefetch_ohlcv(
    symbols: list[str],
    period: str = "5y",
    interval: str = "1d",
    refresh: bool = False,
    chunk_size: int = 50,
    progress=None,
) -> dict:
    """Warm the CSV cache for many symbols using batched provider requests.

    Cached symbols are skipped. A failing batch is retried one symbol at a time so
    a single bad ticker does not discard the rest of the chunk.
    """
    symbols = list(dict.fromkeys(symbols))
    todo = symbols if refresh else [s for s in symbols if not cache_path(s, period, interval).exists()]
    downloaded: list[str] = []
    failed: list[str] = []
    total = max(1, len(todo))
    done = 0

    def report(label: str) -> None:
        if progress:
            progress(done, len(todo), label)

    report("Starting download")
    for start in range(0, len(todo), max(1, chunk_size)):
        chunk = todo[start:start + max(1, chunk_size)]
        try:
            raw = yf.download(chunk, period=period, interval=interval, auto_adjust=True,
                              progress=False, threads=True, group_by="ticker")
        except Exception:
            raw = None
        for symbol in chunk:
            frame = None
            if raw is not None and not raw.empty:
                try:
                    frame = raw[symbol] if symbol in getattr(raw.columns, "levels", [[]])[0] else raw
                except (KeyError, IndexError):
                    frame = None
            clean = _clean_ohlcv(frame)
            if clean.empty:
                failed.append(symbol)
            else:
                clean.to_csv(cache_path(symbol, period, interval))
                downloaded.append(symbol)
            done += 1
            report(symbol)

    for symbol in list(failed):
        frame, meta = fetch_ohlcv(symbol, period, interval, refresh=True)
        if not frame.empty:
            failed.remove(symbol)
            downloaded.append(symbol)
            report(f"{symbol} retried")

    return {
        "requested": len(symbols),
        "cached": len(symbols) - len(todo),
        "downloaded": downloaded,
        "failed": failed,
    }


def fetch_fundamentals(symbol: str) -> tuple[dict, dict]:
    """Best-effort snapshot; fields are not point-in-time and may be absent."""
    try:
        t = yf.Ticker(symbol)
        info = t.get_info() or {}
        q = t.quarterly_income_stmt

        def row_series(candidates):
            if q is None or q.empty:
                return None
            for name in candidates:
                if name in q.index:
                    s = pd.to_numeric(q.loc[name], errors="coerce").dropna()
                    if len(s):
                        try:
                            s.index = pd.to_datetime(s.index)
                            return s.sort_index()
                        except Exception:
                            return s
            return None

        def latest(candidates):
            s = row_series(candidates)
            return float(s.iloc[-1]) if s is not None and len(s) else None

        def yoy(candidates):
            s = row_series(candidates)
            if s is None or len(s) < 5:
                return None
            current, prior = float(s.iloc[-1]), float(s.iloc[-5])
            if prior <= 0:
                return None
            return (current / prior - 1) * 100

        out = {
            "company": info.get("longName") or info.get("shortName") or symbol,
            "sector": info.get("sector"), "industry": info.get("industry"),
            "market_cap": info.get("marketCap"), "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "trailing_pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"),
            "currency": info.get("currency"),
            "latest_quarter_eps": latest(["Diluted EPS", "Basic EPS"]),
            "latest_quarter_revenue": latest(["Total Revenue", "Operating Revenue"]),
            "latest_quarter_operating_income": latest(["Operating Income"]),
            "quarterly_eps_yoy_growth_pct": yoy(["Diluted EPS", "Basic EPS"]),
            "quarterly_revenue_yoy_growth_pct": yoy(["Total Revenue", "Operating Revenue"]),
            "quarterly_operating_income_yoy_growth_pct": yoy(["Operating Income"]),
            "website": info.get("website"),
        }
        return out, {"source": "Yahoo Finance company snapshot", "status": "best_effort",
                     "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                     "warning": "Not point-in-time data; fields may be missing or stale. Verify against official filings."}
    except Exception as exc:
        return {}, {"source": "Yahoo Finance", "status": "error",
                    "message": str(exc), "retrieved_utc": datetime.now(timezone.utc).isoformat()}
