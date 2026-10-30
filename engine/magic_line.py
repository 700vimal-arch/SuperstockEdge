"""Magic Line laboratory.

Evaluates candidate weekly moving averages using only bars that were known at the
evaluation date. A support test at week *i* may only be scored with outcomes that
occurred in weeks *i+1 .. i+window* that are already inside the supplied history.
Tests near the evaluation date therefore remain ``open`` and do not contribute to
success rates.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

DEFAULT_CANDIDATES = ["10W SMA", "10W EMA", "20W SMA", "20W EMA"]
_LINE_SPEC = re.compile(r"^\s*(\d{1,3})\s*W\s+(SMA|EMA)\s*$", re.IGNORECASE)


def parse_line_spec(name: str) -> tuple[int, str] | None:
    match = _LINE_SPEC.match(str(name or ""))
    if not match:
        return None
    period = int(match.group(1))
    kind = match.group(2).upper()
    if period < 2 or period > 200:
        return None
    return period, kind


def build_line(close: pd.Series, name: str) -> pd.Series:
    spec = parse_line_spec(name)
    if spec is None or close is None or len(close) == 0:
        return pd.Series(dtype=float)
    period, kind = spec
    values = pd.to_numeric(close, errors="coerce")
    if kind == "SMA":
        return values.rolling(period, min_periods=period).mean()
    return values.ewm(span=period, adjust=False, min_periods=period).mean()


def _number(value, default):
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def _params(cfg: dict) -> dict:
    ml = cfg.get("magic_line", {}) or {}
    return {
        "min_tests": int(_number(ml.get("min_tests"), 3)),
        "min_resolved_tests": int(_number(ml.get("min_resolved_tests"), 2)),
        "min_successes": int(_number(ml.get("min_successes"), 1)),
        "min_defined_bars": int(_number(ml.get("min_defined_bars"), 30)),
        "test_tolerance_pct": _number(ml.get("test_tolerance_pct"), 2.5),
        "test_close_tolerance_pct": _number(ml.get("test_close_tolerance_pct"), 1.5),
        "min_separation_weeks": int(_number(ml.get("min_separation_weeks"), 4)),
        "recovery_window_weeks": int(_number(ml.get("recovery_window_weeks"), 4)),
        "recovery_threshold_pct": _number(ml.get("recovery_threshold_pct"), 3.0),
        "breakdown_buffer_pct": _number(
            ml.get("breakdown_buffer_pct"), _number(cfg.get("magic_break_buffer_pct"), 2.0)
        ),
        "proximity_pct": _number(cfg.get("quiet_magic_distance_pct"), 5.0),
    }


def _candidate_names(cfg: dict) -> list[str]:
    ml = cfg.get("magic_line", {}) or {}
    forced = ml.get("forced_method") or cfg.get("magic_line_method")
    if forced:
        return [str(forced)]
    configured = ml.get("candidates") or DEFAULT_CANDIDATES
    if ml.get("auto_select", True) is False:
        configured = list(configured)[:1]
    names: list[str] = []
    for name in configured:
        text = str(name)
        if text not in names and parse_line_spec(text):
            names.append(text)
    return names or list(DEFAULT_CANDIDATES)


def _test_outcome(x: pd.DataFrame, i: int, line_value: float, close: float, p: dict) -> dict:
    window = p["recovery_window_weeks"]
    recovery_pct = p["recovery_threshold_pct"] / 100.0
    breakdown_pct = p["breakdown_buffer_pct"] / 100.0
    end = min(i + window, len(x) - 1)
    status = "open"
    recovery_weeks = None
    max_close = close
    for j in range(i + 1, end + 1):
        future_close = float(x.Close.iloc[j])
        max_close = max(max_close, future_close)
        if status != "open":
            continue
        if future_close >= line_value * (1 + recovery_pct):
            status = "success"
            recovery_weeks = j - i
        elif future_close <= line_value * (1 - breakdown_pct):
            status = "failed"
    if status == "open" and end - i >= window:
        status = "failed"
    bounce_pct = (max_close / close - 1) * 100 if close > 0 else np.nan
    return {
        "date": str(x.index[i].date()),
        "line": float(line_value),
        "low": float(x.Low.iloc[i]),
        "close": float(close),
        "status": status,
        "bounce_pct": float(bounce_pct) if np.isfinite(bounce_pct) else None,
        "recovery_weeks": recovery_weeks,
    }


def _find_tests(x: pd.DataFrame, line: pd.Series, p: dict) -> list[dict]:
    tolerance = p["test_tolerance_pct"] / 100.0
    close_tolerance = p["test_close_tolerance_pct"] / 100.0
    separation = max(1, p["min_separation_weeks"])
    events: list[dict] = []
    last_index = -10**9
    for i in range(1, len(x)):
        line_value = line.iloc[i]
        previous_line = line.iloc[i - 1]
        if pd.isna(line_value) or pd.isna(previous_line) or line_value <= 0:
            continue
        previous_close = float(x.Close.iloc[i - 1])
        if previous_close < float(previous_line):
            continue
        low = float(x.Low.iloc[i])
        close = float(x.Close.iloc[i])
        if low > line_value * (1 + tolerance):
            continue
        if close < line_value * (1 - close_tolerance):
            continue
        if i - last_index < separation:
            continue
        last_index = i
        events.append(_test_outcome(x, i, float(line_value), close, p))
    return events


def _confirmed_breakdowns(x: pd.DataFrame, line: pd.Series, buffer_pct: float) -> int:
    buffer = buffer_pct / 100.0
    episodes = 0
    in_episode = False
    ever_above = False
    for i in range(len(x)):
        line_value = line.iloc[i]
        if pd.isna(line_value) or line_value <= 0:
            continue
        close = float(x.Close.iloc[i])
        if close >= float(line_value):
            ever_above = True
        below = close < float(line_value) * (1 - buffer)
        if below and not in_episode and ever_above:
            episodes += 1
            in_episode = True
        elif close > float(line_value):
            in_episode = False
    return episodes


def _score(metrics: dict) -> float:
    success_rate = metrics["success_rate_pct"] or 0.0
    bounce = min(100.0, max(0.0, metrics["avg_bounce_pct"] or 0.0) / 10.0 * 100.0)
    consistency = metrics["trend_consistency_pct"] or 0.0
    deviation = max(0.0, 100.0 - (metrics["max_close_deviation_pct"] or 0.0) * 10.0)
    penalty = min(30.0, metrics["confirmed_breakdowns"] * 10.0)
    raw = 0.45 * success_rate + 0.20 * bounce + 0.20 * consistency + 0.15 * deviation - penalty
    return round(max(0.0, min(100.0, raw)), 2)


def _evaluate_candidate(x: pd.DataFrame, name: str, p: dict) -> dict:
    spec = parse_line_spec(name)
    line = build_line(x.Close, name)
    defined = line.notna() & (line > 0)
    defined_count = int(defined.sum())
    required_bars = max(p["min_defined_bars"], (spec[0] * 2) if spec else 0)
    result = {
        "name": name,
        "period_weeks": spec[0] if spec else None,
        "kind": spec[1] if spec else None,
        "qualified": False,
        "reason": "",
        "score": 0.0,
        "tests": 0,
        "resolved_tests": 0,
        "successes": 0,
        "failures": 0,
        "open_tests": 0,
        "success_rate_pct": None,
        "avg_bounce_pct": None,
        "avg_recovery_weeks": None,
        "max_close_deviation_pct": None,
        "confirmed_breakdowns": None,
        "trend_consistency_pct": None,
        "current_value": None,
        "current_distance_pct": None,
        "slope_pct_4w": None,
        "breakdown": False,
        "near": False,
        "events": [],
    }
    if spec is None:
        result["reason"] = "Unrecognised moving-average specification."
        return result
    if defined_count < required_bars:
        result["reason"] = f"Only {defined_count} weekly bars with a defined line; {required_bars} required."
        return result

    events = _find_tests(x, line, p)
    successes = [e for e in events if e["status"] == "success"]
    failures = [e for e in events if e["status"] == "failed"]
    open_tests = [e for e in events if e["status"] == "open"]
    resolved = len(successes) + len(failures)

    deviation_series = (x.Close[defined] / line[defined] - 1) * 100
    max_deviation = max(0.0, -float(deviation_series.min())) if len(deviation_series) else None
    current_value = float(line.iloc[-1])
    current_close = float(x.Close.iloc[-1])
    distance_pct = (current_close / current_value - 1) * 100 if current_value > 0 else None
    slope_pct = None
    if len(line) >= 5 and pd.notna(line.iloc[-5]) and float(line.iloc[-5]) > 0:
        slope_pct = (current_value / float(line.iloc[-5]) - 1) * 100

    result.update({
        "tests": len(events),
        "resolved_tests": resolved,
        "successes": len(successes),
        "failures": len(failures),
        "open_tests": len(open_tests),
        "success_rate_pct": round(len(successes) / resolved * 100, 1) if resolved else None,
        "avg_bounce_pct": round(float(np.mean([e["bounce_pct"] for e in successes])), 2) if successes else None,
        "avg_recovery_weeks": round(float(np.mean([e["recovery_weeks"] for e in successes])), 1) if successes else None,
        "max_close_deviation_pct": round(max_deviation, 2) if max_deviation is not None else None,
        "confirmed_breakdowns": _confirmed_breakdowns(x, line, p["breakdown_buffer_pct"]),
        "trend_consistency_pct": round(float((x.Close[defined] > line[defined]).mean() * 100), 1),
        "current_value": current_value,
        "current_distance_pct": round(distance_pct, 2) if distance_pct is not None else None,
        "slope_pct_4w": round(slope_pct, 2) if slope_pct is not None else None,
        "breakdown": bool(current_value > 0 and current_close < current_value * (1 - p["breakdown_buffer_pct"] / 100)),
        "near": bool(distance_pct is not None and abs(distance_pct) <= p["proximity_pct"]),
        "events": events,
    })
    result["score"] = _score(result)
    result["qualified"] = (
        len(events) >= p["min_tests"]
        and resolved >= p["min_resolved_tests"]
        and len(successes) >= p["min_successes"]
    )
    if result["qualified"]:
        result["reason"] = (
            f"{len(successes)} of {resolved} resolved tests recovered; "
            f"{result['confirmed_breakdowns']} confirmed breakdown(s)."
        )
    else:
        result["reason"] = (
            f"Needs at least {p['min_tests']} tests, {p['min_resolved_tests']} resolved outcomes "
            f"and {p['min_successes']} successful bounce; found {len(events)} tests, "
            f"{resolved} resolved and {len(successes)} successful."
        )
    return result


def _rationale(metrics: dict) -> str:
    success_rate = metrics.get("success_rate_pct")
    bounce = metrics.get("avg_bounce_pct")
    consistency = metrics.get("trend_consistency_pct")
    deviation = metrics.get("max_close_deviation_pct")
    parts = [
        f"{metrics['successes']}/{metrics['resolved_tests']} resolved tests recovered"
        + (f" ({success_rate:.0f}%)" if success_rate is not None else ""),
    ]
    if bounce is not None:
        parts.append(f"average bounce {bounce:.1f}%")
    if consistency is not None:
        parts.append(f"{consistency:.0f}% of weeks closed above the line")
    if deviation is not None:
        parts.append(f"maximum close deviation {deviation:.1f}%")
    parts.append(f"{metrics['confirmed_breakdowns']} confirmed breakdown(s)")
    return f"{metrics['name']} selected: " + "; ".join(parts) + "."


def evaluate_magic_lines(x: pd.DataFrame, cfg: dict | None = None) -> dict:
    """Compare candidate moving averages as of the last completed weekly bar."""
    cfg = cfg or {}
    empty = {
        "as_of": None,
        "candidates": [],
        "selected": None,
        "selected_metrics": None,
        "message": "No reliable Magic Line identified: no weekly history is available.",
        "rationale": None,
        "forced": False,
        "current": {
            "value": None,
            "distance_pct": None,
            "slope_pct_4w": None,
            "breakdown": False,
            "near": False,
            "approaching": False,
            "pending_test": False,
        },
    }
    if x is None or x.empty or not {"Close", "Low"}.issubset(x.columns):
        return empty

    params = _params(cfg)
    names = _candidate_names(cfg)
    forced = bool((cfg.get("magic_line", {}) or {}).get("forced_method") or cfg.get("magic_line_method"))
    candidates = [_evaluate_candidate(x, name, params) for name in names]
    qualified = [c for c in candidates if c["qualified"]]

    if forced:
        selected = candidates[0]
        if selected["qualified"]:
            message = f"Forced Magic Line {selected['name']} is qualified."
        else:
            message = (
                f"Forced Magic Line {selected['name']} has insufficient evidence: {selected['reason']}"
            )
    elif qualified:
        selected = max(
            qualified,
            key=lambda c: (c["score"], c["successes"], c["tests"], c["period_weeks"] or 0),
        )
        message = _rationale(selected)
    else:
        selected = None
        message = (
            "No reliable Magic Line identified. "
            f"No candidate produced at least {params['min_tests']} tests with "
            f"{params['min_resolved_tests']} resolved outcomes."
        )

    current = dict(empty["current"])
    if selected:
        distance = selected["current_distance_pct"]
        current = {
            "value": selected["current_value"],
            "distance_pct": distance,
            "slope_pct_4w": selected["slope_pct_4w"],
            "breakdown": selected["breakdown"],
            "near": selected["near"],
            "approaching": bool(
                distance is not None and 0 < distance <= params["proximity_pct"]
            ),
            "pending_test": bool(
                selected["events"]
                and selected["events"][-1]["date"] == str(x.index[-1].date())
                and selected["events"][-1]["status"] == "open"
            ),
        }

    return {
        "as_of": str(x.index[-1].date()),
        "candidates": candidates,
        "selected": selected["name"] if selected else None,
        "selected_metrics": selected,
        "message": message,
        "rationale": _rationale(selected) if selected and selected["qualified"] else None,
        "forced": forced,
        "current": current,
    }
