"""Entry, structural stop-loss and target planning.

The planner never issues a trade plan for a failed setup or while a structural
exit warning is active. Entry zones are ranges, stops are chosen from structural
levels that fit a risk budget, and fundamental targets are shown separately from
technical targets.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

SETUP_LABELS = {
    "A": "A. Early accumulation opportunity",
    "B": "B. Post-breakout pullback",
    "C": "C. Magic Line bounce",
    "D": "D. Tight consolidation continuation",
    "E": "E. Failed setup",
}


def _number(value, default=np.nan) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def reward_risk_band(reward_risk: float | None) -> str | None:
    if reward_risk is None or not math.isfinite(reward_risk):
        return None
    if reward_risk < 2:
        return "Below 2R"
    if reward_risk < 3:
        return "2R–3R"
    if reward_risk <= 5:
        return "3R–5R"
    return "Above 5R"


def _target(label: str, source: str, value: float, entry_price: float, risk: float) -> dict:
    upside = (value / entry_price - 1) * 100 if entry_price > 0 else None
    multiple = (value - entry_price) / risk if risk > 0 else None
    return {
        "label": label,
        "source": source,
        "value": float(value),
        "upside_pct": round(upside, 2) if upside is not None else None,
        "r_multiple": round(multiple, 2) if multiple is not None else None,
        "below_entry": bool(value <= entry_price),
    }


def build_trade_plan(tech: dict, fundamentals: dict | None = None, cfg: dict | None = None) -> dict:
    """Return an entry zone, explained stop, targets and reward/risk for a confirmed setup."""
    tech = tech if isinstance(tech, dict) else {}
    fundamentals = fundamentals if isinstance(fundamentals, dict) else {}
    cfg = cfg or {}
    entry_cfg = cfg.get("entry", {}) or {}
    plan = {
        "actionable": False,
        "setup": "E",
        "setup_label": SETUP_LABELS["E"],
        "setup_reason": "",
        "reasons": [],
        "warnings": [],
        "entry_zone_low": None,
        "entry_zone_high": None,
        "entry_reference": None,
        "entry_reference_label": None,
        "distance_from_price_pct": None,
        "stop": None,
        "stop_reason": None,
        "stop_candidates": [],
        "risk_per_share": None,
        "risk_pct": None,
        "annualized_eps": None,
        "annualized_pe": None,
        "technical_targets": [],
        "fundamental_targets": [],
        "targets": [],
        "primary_target": None,
        "primary_target_label": None,
        "primary_target_source": None,
        "reward_risk": None,
        "reward_risk_band": None,
    }

    if not tech.get("ready"):
        plan["reasons"].append("Insufficient confirmed weekly history.")
        return plan
    close = _number(tech.get("close"))
    if not math.isfinite(close) or close <= 0:
        plan["reasons"].append("Current weekly close is unavailable.")
        return plan
    if tech.get("exit_risk_score", 0) >= 60 or tech.get("magic_breakdown"):
        plan["reasons"].append("A structural exit warning is active; no new entry plan is generated.")
        return plan

    width = max(0.0, _number(entry_cfg.get("zone_width_pct"), 2.5)) / 100
    max_distance = max(0.0, _number(entry_cfg.get("max_entry_distance_pct"), 8.0))
    base_ok = bool(tech.get("base_ok"))
    base_high = _number(tech.get("base_high"))
    base_low = _number(tech.get("base_low"))
    magic = _number(tech.get("magic_line"))
    atr_value = max(0.0, _number(tech.get("atr14"), 0.0))
    near_magic = bool(tech.get("near_magic"))
    breakout = bool(tech.get("breakout"))

    volume_ratio = _number(tech.get("quiet_volume_multiple"))
    atr_ratio = _number(tech.get("quiet_atr_multiple"))
    volume_limit = _number(cfg.get("quiet_volume_multiple"), 0.75)
    atr_limit = _number(cfg.get("quiet_atr_multiple"), 0.85)
    contracting = (
        math.isfinite(volume_ratio)
        and math.isfinite(atr_ratio)
        and volume_ratio <= volume_limit
        and atr_ratio <= atr_limit
    )

    setup = "E"
    reference = np.nan
    reference_label = ""
    setup_reason = ""
    if near_magic and contracting and math.isfinite(magic):
        setup, reference, reference_label = "C", magic, "Magic Line support"
        setup_reason = "Volatility and volume are contracting while price tests the Magic Line."
    elif base_ok and contracting and math.isfinite(base_high):
        setup, reference, reference_label = "D", base_high, "Base breakout level"
        setup_reason = "Price is consolidating quietly below the base breakout level."
    elif breakout and math.isfinite(base_high) and close >= base_high:
        setup, reference, reference_label = "B", base_high, "Base breakout retest"
        setup_reason = "The base has broken out; the plan waits for a retest of the base high."
    elif base_ok and not contracting:
        if near_magic and math.isfinite(magic):
            setup, reference, reference_label = "A", magic, "Magic Line support"
            setup_reason = "Early accumulation near Magic Line support before a breakout."
        elif math.isfinite(base_low) and close <= base_low * (1 + max_distance / 100):
            setup, reference, reference_label = "A", base_low, "Base support"
            setup_reason = "Early accumulation near base support before a breakout."

    if setup == "E" or not math.isfinite(reference) or reference <= 0:
        plan["reasons"].append("No confirmed accumulation, pullback or consolidation setup.")
        return plan

    distance_pct = (close / reference - 1) * 100
    plan["distance_from_price_pct"] = round(distance_pct, 2)
    if abs(distance_pct) > max_distance:
        plan["reasons"].append(
            f"Price is {distance_pct:.1f}% from {reference_label.lower()}, outside the "
            f"{max_distance:.1f}% entry-distance limit; avoid chasing."
        )
        return plan

    entry_low = reference * (1 - width)
    entry_high = reference * (1 + width)
    entry_price = entry_high

    swing_lookback = max(2, int(_number(entry_cfg.get("swing_lookback_weeks"), 8)))
    swing_low = np.nan
    weekly = tech.get("weekly")
    if isinstance(weekly, pd.DataFrame) and len(weekly) and "Low" in weekly.columns:
        swing_low = float(weekly.Low.iloc[-min(swing_lookback, len(weekly)):].min())

    atr_multiple = max(0.1, _number(entry_cfg.get("atr_stop_multiple"), 2.0))
    min_stop_atr = max(0.0, _number(entry_cfg.get("min_stop_atr"), 0.75))
    stop_buffer_atr = max(0.0, _number(entry_cfg.get("stop_buffer_atr"), 0.25))
    max_stop_pct = max(0.1, _number(entry_cfg.get("max_stop_pct"), 12.0))
    min_stop_pct = max(0.0, _number(entry_cfg.get("min_stop_pct"), 1.0))
    buffer_value = stop_buffer_atr * atr_value
    minimum_distance = max(entry_price * min_stop_pct / 100, min_stop_atr * atr_value)
    maximum_distance = entry_price * max_stop_pct / 100

    candidates: list[dict] = []

    def add_candidate(label: str, level: float, buffered: bool, kind: str) -> None:
        if not math.isfinite(level) or level <= 0:
            return
        proposed = level - buffer_value if buffered else level
        risk_distance = entry_price - proposed
        valid = (
            proposed < entry_low
            and risk_distance >= minimum_distance
            and risk_distance <= maximum_distance
        )
        candidates.append({
            "label": label,
            "level": round(float(level), 2),
            "stop": round(float(proposed), 2),
            "distance_pct": round(risk_distance / entry_price * 100, 2),
            "distance_atr": round(risk_distance / atr_value, 2) if atr_value > 0 else None,
            "valid": bool(valid),
            "kind": kind,
        })

    add_candidate(f"Recent {swing_lookback}-week swing low", swing_low, True, "structure")
    add_candidate("Base low", base_low, True, "structure")
    add_candidate("Magic Line", magic, True, "structure")
    if atr_value > 0:
        add_candidate("ATR volatility stop", entry_price - atr_multiple * atr_value, False, "volatility")

    valid_candidates = [c for c in candidates if c["valid"]]
    if not valid_candidates:
        plan["stop_candidates"] = candidates
        plan["reasons"].append(
            "No structural stop sits inside the risk budget; the setup is not actionable."
        )
        return plan

    structural = [c for c in valid_candidates if c["kind"] == "structure"]
    chosen = max(structural or valid_candidates, key=lambda c: c["stop"])
    stop = float(chosen["stop"])
    risk_per_share = entry_price - stop
    if chosen["kind"] == "volatility":
        stop_reason = (
            f"No structural level fit the risk budget; using a {atr_multiple:g}×ATR volatility stop "
            f"at {stop:.2f}."
        )
    else:
        stop_reason = (
            f"Stop placed below the {chosen['label'].lower()} at {chosen['level']:.2f}, "
            f"buffered by {stop_buffer_atr:g}×ATR."
        )

    technical_targets: list[dict] = []
    if base_ok and math.isfinite(base_high) and math.isfinite(base_low) and base_high > base_low:
        base_height = base_high - base_low
        technical_targets = [
            _target("Base-height projection", "Technical", base_high + base_height, entry_price, risk_per_share),
            _target("Measured move from entry", "Technical", entry_price + base_height, entry_price, risk_per_share),
            _target("Previous resistance / base high", "Technical", base_high, entry_price, risk_per_share),
        ]
    else:
        plan["warnings"].append("Technical targets unavailable: no valid base high/low.")

    fundamental_targets: list[dict] = []
    eps = _number(fundamentals.get("latest_quarter_eps"))
    scenarios = entry_cfg.get("pe_scenarios", {}) or {}
    pe_set = [
        ("Conservative", _number(scenarios.get("conservative"), 12.0)),
        ("Base", _number(scenarios.get("base"), 20.0)),
        ("Optimistic", _number(scenarios.get("optimistic"), 30.0)),
    ]
    if math.isfinite(eps) and eps > 0:
        annualized_eps = eps * 4
        plan["annualized_eps"] = round(annualized_eps, 4)
        plan["annualized_pe"] = round(close / annualized_eps, 2) if annualized_eps > 0 else None
        for label, pe in pe_set:
            if math.isfinite(pe) and pe > 0:
                fundamental_targets.append(
                    _target(
                        f"Annualized EPS × {pe:g} P/E ({label.lower()})",
                        "Fundamental",
                        annualized_eps * pe,
                        entry_price,
                        risk_per_share,
                    )
                )
        plan["warnings"].append(
            "Fundamental targets annualise the latest quarter's EPS; seasonality or one-off items can distort them."
        )
    else:
        plan["warnings"].append(
            "Fundamental target unavailable: the latest quarterly EPS is missing or non-positive."
        )

    targets = technical_targets + fundamental_targets
    above_entry = [t for t in targets if t["value"] > entry_price]
    qualifying = [
        t for t in above_entry if t["r_multiple"] is not None and t["r_multiple"] >= 1.0
    ]
    pool = qualifying or above_entry
    primary = min(pool, key=lambda t: t["value"]) if pool else None

    plan.update({
        "actionable": primary is not None,
        "setup": setup,
        "setup_label": SETUP_LABELS[setup],
        "setup_reason": setup_reason,
        "entry_zone_low": round(entry_low, 2),
        "entry_zone_high": round(entry_high, 2),
        "entry_reference": round(float(reference), 2),
        "entry_reference_label": reference_label,
        "stop": round(stop, 2),
        "stop_reason": stop_reason,
        "stop_candidates": candidates,
        "risk_per_share": round(risk_per_share, 2),
        "risk_pct": round(risk_per_share / entry_price * 100, 2),
        "technical_targets": technical_targets,
        "fundamental_targets": fundamental_targets,
        "targets": targets,
        "primary_target": primary["value"] if primary else None,
        "primary_target_label": primary["label"] if primary else None,
        "primary_target_source": primary["source"] if primary else None,
    })
    if primary:
        reward_risk = primary["r_multiple"]
        plan["reward_risk"] = reward_risk
        plan["reward_risk_band"] = reward_risk_band(reward_risk)
    if not plan["actionable"]:
        plan["reasons"].append("No target above the entry zone; no reward/risk can be defined.")
    return plan
