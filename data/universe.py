"""Index constituent loaders with an on-disk snapshot cache.

Constituents come from public Wikipedia tables and are best-effort snapshots,
not a licensed index feed. Without network access the last snapshot is reused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import json
import re

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "storage" / "cache" / "universe"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    url: str
    table_index: int
    column: str
    market: str
    suffix: str = ""
    replace: tuple[tuple[str, str], ...] = ()
    header_row: bool = False
    pattern: str = r"^[A-Z0-9&.\-]{1,20}$"


SOURCES: dict[str, Source] = {
    "nifty500": Source(
        key="nifty500",
        label="NIFTY 500 · India",
        url="https://en.wikipedia.org/wiki/NIFTY_500",
        table_index=3,
        column="Symbol",
        market="india",
        suffix=".NS",
        header_row=True,
        pattern=r"^[A-Z0-9&\-]{1,20}$",
    ),
    "sp500": Source(
        key="sp500",
        label="S&P 500 · US",
        url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        table_index=0,
        column="Symbol",
        market="us",
        replace=((".", "-"),),
    ),
    "nasdaq100": Source(
        key="nasdaq100",
        label="Nasdaq-100 · US",
        url="https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
        table_index=0,
        column="Ticker",
        market="us",
    ),
}

UNIVERSE_LABELS = {key: spec.label for key, spec in SOURCES.items()}


def normalize_symbols(values, spec: Source) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if raw is None or (not isinstance(raw, str) and pd.isna(raw)):
            continue
        symbol = str(raw).strip().upper()
        for old, new in spec.replace:
            symbol = symbol.replace(old, new)
        if not symbol or symbol in {"SYMBOL", "TICKER"} or not re.match(spec.pattern, symbol):
            continue
        symbol = f"{symbol}{spec.suffix}"
        if symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def fetch_constituents(key: str, timeout: int = 30) -> list[str]:
    spec = SOURCES[key]
    html = requests.get(spec.url, headers=HEADERS, timeout=timeout).text
    tables = pd.read_html(StringIO(html))
    frame = tables[spec.table_index]
    if spec.header_row:
        frame = frame.rename(columns=frame.iloc[0]).iloc[1:]
    if spec.column not in frame.columns:
        raise ValueError(f"{key}: column {spec.column!r} not found in source table")
    symbols = normalize_symbols(frame[spec.column].tolist(), spec)
    if not symbols:
        raise ValueError(f"{key}: source table produced no usable symbols")
    return symbols


def _cache_path(key: str, cache_dir: Path) -> Path:
    return Path(cache_dir) / f"{key}.json"


def _read_cache(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not payload.get("symbols"):
        return None
    return payload


def load_universe(
    key: str,
    *,
    refresh: bool = False,
    ttl_days: int = 7,
    fetcher=fetch_constituents,
    cache_dir: Path | None = None,
    now: datetime | None = None,
) -> tuple[list[str], dict]:
    """Return (symbols, metadata). Falls back to a stale snapshot when offline."""
    spec = SOURCES[key]
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    path = _cache_path(key, cache_dir)
    cached = _read_cache(path)
    now = now or datetime.now(timezone.utc)

    if cached and not refresh:
        try:
            as_of = datetime.fromisoformat(cached["as_of"])
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)
            fresh = now - as_of <= timedelta(days=ttl_days)
        except (KeyError, ValueError):
            fresh = False
        if fresh:
            return list(cached["symbols"]), {
                "key": key,
                "label": spec.label,
                "status": "cache",
                "as_of": cached.get("as_of"),
                "count": len(cached["symbols"]),
                "source": spec.url,
            }

    try:
        symbols = fetcher(key)
        if not symbols:
            raise ValueError("empty constituent list")
        payload = {"as_of": now.isoformat(timespec="seconds"), "symbols": symbols}
        cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return symbols, {
            "key": key,
            "label": spec.label,
            "status": "network",
            "as_of": payload["as_of"],
            "count": len(symbols),
            "source": spec.url,
        }
    except Exception as exc:
        if cached:
            return list(cached["symbols"]), {
                "key": key,
                "label": spec.label,
                "status": "stale_cache",
                "as_of": cached.get("as_of"),
                "count": len(cached["symbols"]),
                "source": spec.url,
                "warning": f"Using the last saved snapshot: {exc}",
            }
        return [], {
            "key": key,
            "label": spec.label,
            "status": "error",
            "as_of": None,
            "count": 0,
            "source": spec.url,
            "warning": str(exc),
        }


def watchlist_symbols(path: Path) -> list[str]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
