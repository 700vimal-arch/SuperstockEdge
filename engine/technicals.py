from __future__ import annotations
import numpy as np
import pandas as pd

from .magic_line import evaluate_magic_lines


def weekly_ohlcv(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily bars to weeks; exclude an unfinished Mon-Thu week."""
    if daily is None or daily.empty:
        return pd.DataFrame()
    required = ["Open", "High", "Low", "Close", "Volume"]
    if not set(required).issubset(daily.columns):
        return pd.DataFrame()
    weekly = daily.sort_index().resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna(subset=["Open", "High", "Low", "Close"])
    if len(weekly) and pd.Timestamp(daily.index[-1]).weekday() != 4:
        weekly = weekly.iloc[:-1]
    return weekly


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev).abs(),
        (df["Low"] - prev).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _safe_float(value, default=np.nan):
    try:
        out = float(value)
        return out if np.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def analyse_weekly(w: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Analyse only completed weekly bars. Magic Line is configurable, not selected with hindsight."""
    cfg = cfg or {}
    minimum = int(cfg.get("minimum_history_weeks", 40))
    if w is None or w.empty or len(w) < minimum:
        have = 0 if w is None else len(w)
        return {"ready": False, "reason": f"Need at least {minimum} weekly bars; have {have}."}

    x = w.copy().sort_index()
    x["ma10"] = x.Close.rolling(10).mean()
    x["ma10e"] = x.Close.ewm(span=10, adjust=False).mean()
    x["ma20"] = x.Close.rolling(20).mean()
    x["ma30"] = x.Close.rolling(30).mean()
    x["atr14"] = atr(x)
    x["atr_pct"] = x.atr14 / x.Close.replace(0, np.nan) * 100
    x["vol_med10"] = x.Volume.rolling(10).median()

    last, prev = x.iloc[-1], x.iloc[-2]
    close = float(last.Close)
    ma30 = _safe_float(last.ma30)
    ma30_prev4 = _safe_float(x.ma30.iloc[-5]) if len(x) >= 5 else np.nan
    above30 = bool(np.isfinite(ma30) and close > ma30)
    rising30 = bool(np.isfinite(ma30_prev4) and np.isfinite(ma30) and ma30 > ma30_prev4)

    # Evaluate candidate lines with only outcomes observable at the last completed bar.
    lab = evaluate_magic_lines(x, cfg)
    magic_name = lab["selected"]
    selected_metrics = lab.get("selected_metrics") or {}
    magic_value = _safe_float(selected_metrics.get("current_value"))
    magic_extension = (close / magic_value - 1) * 100 if np.isfinite(magic_value) and magic_value > 0 else np.nan
    magic_slope = _safe_float(selected_metrics.get("slope_pct_4w"))

    # Search historical windows ending before the current candle. Prefer the longest
    # window satisfying the configured range ceiling; this gives a variable base length.
    base_min = max(6, int(cfg.get("base_min_weeks", 10)))
    base_max = min(int(cfg.get("base_max_weeks", 26)), len(x) - 2)
    max_range = float(cfg.get("base_max_range_pct", 35))
    base = None
    for n in range(base_max, base_min - 1, -1):
        candidate = x.iloc[-n-1:-1]
        lo, hi = float(candidate.Low.min()), float(candidate.High.max())
        rng = (hi / lo - 1) * 100 if lo > 0 else np.inf
        if np.isfinite(rng) and rng <= max_range:
            base = candidate
            break
    if base is None:
        # Still report a diagnostic window, but it is not a valid base.
        n = min(max(base_min, 1), max(1, len(x)-1))
        base = x.iloc[-n-1:-1]
    base_low = float(base.Low.min()) if len(base) else np.nan
    base_high = float(base.High.max()) if len(base) else np.nan
    base_range = (base_high / base_low - 1) * 100 if base_low > 0 else np.nan
    base_ok = bool(len(base) >= base_min and np.isfinite(base_range) and base_range <= max_range)

    vol_med = _safe_float(last.vol_med10)
    volume_multiple = float(last.Volume / vol_med) if np.isfinite(vol_med) and vol_med > 0 else np.nan
    prior_vol = _safe_float(x.Volume.iloc[-11:-1].median()) if len(x) >= 12 else np.nan
    quiet_vol = float(last.Volume / prior_vol) if np.isfinite(prior_vol) and prior_vol > 0 else np.nan
    prior_atr = _safe_float(x.atr_pct.iloc[-11:-1].median()) if len(x) >= 12 else np.nan
    quiet_atr = float(last.atr_pct / prior_atr) if np.isfinite(prior_atr) and prior_atr > 0 and pd.notna(last.atr_pct) else np.nan

    near_magic_pct = abs(magic_extension) if np.isfinite(magic_extension) else np.nan
    near_magic = bool(np.isfinite(near_magic_pct) and near_magic_pct <= float(cfg.get("quiet_magic_distance_pct", 5)))
    quiet = bool(
        base_ok and near_magic and np.isfinite(quiet_vol) and quiet_vol <= float(cfg.get("quiet_volume_multiple", .75))
        and np.isfinite(quiet_atr) and quiet_atr <= float(cfg.get("quiet_atr_multiple", .85))
        and np.isfinite(magic_value) and close >= magic_value * .98
    )
    breakout = bool(base_ok and close > base_high and np.isfinite(volume_multiple)
                    and volume_multiple >= float(cfg.get("volume_expansion_multiple", 2.0)))

    magic_tests = {}
    if magic_name:
        magic_tests = {magic_name: {
            "tests": selected_metrics.get("tests", 0),
            "successful_tests": selected_metrics.get("successes", 0),
            "failed_tests": selected_metrics.get("failures", 0),
            "open_tests": selected_metrics.get("open_tests", 0),
        }}

    runup_40w = (close / float(x.Close.iloc[-40]) - 1) * 100 if len(x) >= 40 and float(x.Close.iloc[-40]) > 0 else np.nan
    prior_ranges = (x.High - x.Low).iloc[-40:-1]
    biggest_range = bool(len(prior_ranges) and float(last.High-last.Low) > float(prior_ranges.max()))
    parabolic = bool(np.isfinite(runup_40w) and np.isfinite(magic_extension)
                     and runup_40w > float(cfg.get("parabolic_runup_40w_pct", 100))
                     and magic_extension > float(cfg.get("parabolic_extension_pct", 35)))
    below_magic = bool(np.isfinite(magic_value) and close < magic_value * (1 - float(cfg.get("magic_break_buffer_pct", 2))/100))
    exit_score = 0
    if np.isfinite(magic_extension) and magic_extension > float(cfg.get("extended_threshold_pct", 60)):
        exit_score += 20
    if np.isfinite(magic_slope) and magic_slope <= 0:
        exit_score += 15
    if parabolic:
        exit_score += 15
    if biggest_range:
        exit_score += 10
    if below_magic:
        exit_score += 40
    exit_score = min(100, exit_score)

    return {
        "ready": True, "close": close, "weekly_date": str(x.index[-1].date()),
        "base_high": base_high, "base_low": base_low, "base_weeks": len(base),
        "base_range_pct": base_range, "base_ok": base_ok,
        "ma30": ma30 if np.isfinite(ma30) else None, "above30": above30, "rising30": rising30,
        "volume_multiple": volume_multiple, "breakout": breakout,
        "quiet_volume_multiple": quiet_vol, "quiet_atr_multiple": quiet_atr, "quiet": quiet,
        "near_magic": near_magic, "near_magic_pct": near_magic_pct if np.isfinite(near_magic_pct) else None,
        "magic_line_name": magic_name, "magic_line": magic_value if np.isfinite(magic_value) else None,
        "magic_extension_pct": magic_extension if np.isfinite(magic_extension) else None,
        "magic_slope_pct_4w": magic_slope if np.isfinite(magic_slope) else None,
        "magic_tests": magic_tests, "magic_line_lab": lab,
        "magic_breakdown": below_magic, "parabolic_warning": parabolic,
        "largest_weekly_range": biggest_range, "runup_40w_pct": runup_40w if np.isfinite(runup_40w) else None,
        "exit_risk_score": exit_score,
        "atr14": float(last.atr14) if pd.notna(last.atr14) else None,
        "weekly": x,
    }


def score_candidate(tech: dict, fundamentals: dict | None = None, cfg: dict | None = None,
                    plan: dict | None = None) -> dict:
    """Return merit scores separately from data coverage and rule-based classification."""
    cfg = cfg or {}
    fundamentals = fundamentals if isinstance(fundamentals, dict) else {}
    tech = tech if isinstance(tech, dict) else {}
    checks = {}
    if not tech.get("ready"):
        return {
            "fundamental_score": 0, "technical_score": 0, "entry_score": 0,
            "opportunity_score": 0, "data_coverage": "Insufficient price history",
            "fundamental_checks": {}, "classification": "Insufficient Data"
        }

    def number(key):
        return _safe_float(fundamentals.get(key), np.nan)

    eps = number("quarterly_eps_yoy_growth_pct")
    rev = number("quarterly_revenue_yoy_growth_pct")
    op = number("quarterly_operating_income_yoy_growth_pct")
    pe = number("trailing_pe")
    fscore = 0
    checks["Quarterly EPS growth"] = "Missing" if not np.isfinite(eps) else ("Pass" if eps > 0 else "Fail")
    if np.isfinite(eps):
        fscore += 10 if eps >= 50 else 7 if eps > 0 else 0
    checks["Quarterly revenue growth"] = "Missing" if not np.isfinite(rev) else ("Pass" if rev > 0 else "Fail")
    if np.isfinite(rev):
        fscore += 8 if rev >= 15 else 4 if rev > 0 else 0
    checks["Operating income growth"] = "Missing" if not np.isfinite(op) else ("Pass" if op > 0 else "Fail")
    if np.isfinite(op):
        fscore += 7 if op > 0 else 0
    checks["Trailing P/E"] = "Missing" if not np.isfinite(pe) else ("Pass" if 0 < pe <= float(cfg.get("max_trailing_pe", 40)) else "Fail")
    if np.isfinite(pe) and 0 < pe <= float(cfg.get("max_trailing_pe", 40)):
        fscore += 5

    tscore = 0
    tscore += 10 if tech.get("base_ok") else 0
    tscore += 10 if tech.get("above30") and tech.get("rising30") else 5 if tech.get("above30") else 0
    vm = _safe_float(tech.get("volume_multiple"), 0)
    tscore += 5 if vm >= 2 else 3 if vm >= 1.3 else 0
    tests = tech.get("magic_tests", {}).get(tech.get("magic_line_name"), {})
    tscore += min(5, int(tests.get("successful_tests", 0)) * 1)
    tscore += 5 if tech.get("close", 0) > (tech.get("magic_line") or float("inf")) else 0
    tscore += 5 if (tech.get("runup_40w_pct") or 0) > 0 else 0

    escore = 0
    escore += 10 if tech.get("quiet") else 0
    escore += 5 if tech.get("near_magic") else 0
    ext = _safe_float(tech.get("magic_extension_pct"))
    escore += 5 if np.isfinite(ext) and -5 <= ext <= 15 else 0
    escore += 5 if tech.get("base_ok") and not tech.get("breakout") else 0
    rr = _safe_float(plan.get("reward_risk")) if isinstance(plan, dict) else np.nan
    if not np.isfinite(rr):
        close, low, atrv = _safe_float(tech.get("close")), _safe_float(tech.get("base_low")), _safe_float(tech.get("atr14"), 0)
        if np.isfinite(close) and np.isfinite(low):
            stop = min(low, close - 2 * (atrv if np.isfinite(atrv) else 0))
            risk = close - stop
            target = _safe_float(tech.get("base_high"))
            rr = ((target - close) / risk) if np.isfinite(target) and risk > 0 and target > close else None
    escore += 5 if rr is not None and np.isfinite(rr) and rr >= 2 else 0

    total = min(100, fscore + tscore + escore)
    available = sum(v != "Missing" for v in checks.values())
    passed = sum(v == "Pass" for v in checks.values())
    failed = sum(v == "Fail" for v in checks.values())
    missing = sum(v == "Missing" for v in checks.values())

    if tech.get("exit_risk_score", 0) >= 60:
        classification = "Exit Warning"
    elif np.isfinite(ext) and ext > float(cfg.get("extended_threshold_pct", 60)):
        classification = "Extended"
    elif tech.get("quiet"):
        classification = "Ready to Buy"
    elif tech.get("base_ok"):
        classification = "Building Base"
    elif fscore >= 15 and (tech.get("above30") or tech.get("rising30")):
        classification = "Superstock Discovery"
    else:
        classification = "Watchlist / Developing"

    return {
        "fundamental_score": int(fscore), "technical_score": int(tscore),
        "entry_score": int(escore), "opportunity_score": int(total),
        "reward_risk_estimate": rr, "fundamental_checks": checks,
        "fundamental_available": available, "fundamental_passed": passed,
        "fundamental_failed": failed, "fundamental_missing": missing,
        "data_coverage": f"{available}/4 fundamental checks available; {passed} passed, {failed} failed, {missing} missing. Price history: available.",
        "classification": classification,
    }
