from __future__ import annotations
import pandas as pd


def quarterly_snapshot(symbol: str) -> tuple[dict, dict]:
    """Return provider fundamentals and retrieval metadata as separate dictionaries."""
    from data.market_data import fetch_fundamentals
    try:
        data, meta = fetch_fundamentals(symbol)
    except Exception as exc:
        return {}, {"source": "Yahoo Finance", "status": "error", "message": str(exc)}
    if not isinstance(data, dict):
        data = {}
    if not isinstance(meta, dict):
        meta = {"source": "Yahoo Finance", "status": "invalid_metadata"}
    return data, meta


def earnings_acceleration_from_statement(statement: pd.DataFrame) -> dict:
    """Compare the latest quarterly EPS YoY growth with the previous quarter's YoY growth."""
    if statement is None or statement.empty:
        return {"available": False, "reason": "Quarterly statement unavailable."}
    rows = [r for r in ("Diluted EPS", "Basic EPS") if r in statement.index]
    if not rows:
        return {"available": False, "reason": "No comparable quarterly EPS row."}
    s = pd.to_numeric(statement.loc[rows[0]], errors="coerce").dropna()
    try:
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
    except Exception:
        return {"available": False, "reason": "Quarterly statement dates could not be parsed."}
    if len(s) < 6:
        return {"available": False, "reason": "Fewer than six quarterly EPS observations."}
    latest, prior_yoy = float(s.iloc[-1]), float(s.iloc[-5])
    prior_q, prior_q_yoy = float(s.iloc[-2]), float(s.iloc[-6])
    if prior_yoy <= 0 or prior_q_yoy <= 0:
        return {"available": False, "reason": "Percentage growth is not meaningful with non-positive comparison EPS."}
    latest_growth = (latest / prior_yoy - 1) * 100
    previous_growth = (prior_q / prior_q_yoy - 1) * 100
    return {
        "available": True, "latest_yoy_growth_pct": latest_growth,
        "previous_yoy_growth_pct": previous_growth,
        "accelerating": latest_growth > previous_growth,
    }
