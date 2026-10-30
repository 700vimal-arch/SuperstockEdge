from __future__ import annotations
import pandas as pd
from .technicals import analyse_weekly


def run_backtest(weekly: pd.DataFrame, initial_capital=100000, commission_bps=10,
                 slippage_bps=10, risk_pct=.005, config: dict | None = None):
    """Single-symbol long-only weekly research test; signals at close, fills next open."""
    if weekly is None or weekly.empty or len(weekly) < 45:
        return {"trades": pd.DataFrame(), "equity": pd.Series(dtype=float),
                "metrics": {"error": "At least 45 weekly bars required."}}
    cfg = config or {}
    cash = float(initial_capital)
    qty = 0
    entry = stop = 0.0
    entry_date = None
    trades, curve = [], []
    friction = (float(commission_bps) + float(slippage_bps)) / 10000
    for i in range(40, len(weekly)-1):
        hist = weekly.iloc[:i+1]
        row, nextrow = weekly.iloc[i], weekly.iloc[i+1]
        a = analyse_weekly(hist, cfg)
        if qty > 0 and float(row.Low) <= stop:
            raw_fill = min(float(row.Open), stop)
            fill = raw_fill * (1-friction)
            proceeds = qty * fill
            pnl = proceeds - qty * entry
            cash += proceeds
            trades.append({"entry_date": entry_date, "exit_date": weekly.index[i],
                           "entry": entry, "exit": fill, "shares": qty, "pnl": pnl,
                           "return_pct": (fill/entry-1)*100, "reason": "Structural stop"})
            qty, entry, stop, entry_date = 0, 0.0, 0.0, None
        elif qty > 0 and (a.get("magic_breakdown") or a.get("exit_risk_score", 0) >= 60):
            fill = float(nextrow.Open) * (1-friction)
            proceeds = qty * fill
            pnl = proceeds - qty * entry
            cash += proceeds
            trades.append({"entry_date": entry_date, "exit_date": weekly.index[i+1],
                           "entry": entry, "exit": fill, "shares": qty, "pnl": pnl,
                           "return_pct": (fill/entry-1)*100, "reason": "Magic Line / exit risk"})
            qty, entry, stop, entry_date = 0, 0.0, 0.0, None

        if qty == 0 and a.get("ready") and a.get("quiet") and a.get("above30") and a.get("rising30"):
            fill = float(nextrow.Open) * (1+friction)
            atrv = float(a.get("atr14") or 0)
            proposed_stop = min(float(a.get("base_low", fill)), fill-2*atrv)
            risk_per_share = fill-proposed_stop
            if risk_per_share > 0:
                risk_cash = cash * float(risk_pct)
                shares = int(min(risk_cash/risk_per_share, (cash*.10)/fill))
                total_cost = shares * fill
                if shares > 0 and total_cost <= cash:
                    qty, entry, stop, entry_date = shares, fill, proposed_stop, weekly.index[i+1]
                    cash -= total_cost

        # Check the stop against the next week's low after a next-open entry/fill.
        # This is conservative at weekly resolution; the exact intrabar path is unknown.
        if qty > 0 and float(nextrow.Low) <= stop:
            raw_fill = min(float(nextrow.Open), stop)
            fill = raw_fill * (1-friction)
            proceeds = qty * fill
            pnl = proceeds - qty * entry
            cash += proceeds
            trades.append({"entry_date": entry_date, "exit_date": weekly.index[i+1],
                           "entry": entry, "exit": fill, "shares": qty, "pnl": pnl,
                           "return_pct": (fill/entry-1)*100, "reason": "Structural stop (next-week low)"})
            qty, entry, stop, entry_date = 0, 0.0, 0.0, None

        # Mark to the next week's close, because any next-open transaction has occurred.
        mark_price = float(nextrow.Close) if qty else 0.0
        curve.append((weekly.index[i+1], cash + qty*mark_price))

    if qty > 0:
        last = weekly.iloc[-1]
        fill = float(last.Close) * (1-friction)
        proceeds = qty*fill
        pnl = proceeds-qty*entry
        cash += proceeds
        trades.append({"entry_date": entry_date, "exit_date": weekly.index[-1],
                       "entry": entry, "exit": fill, "shares": qty, "pnl": pnl,
                       "return_pct": (fill/entry-1)*100, "reason": "End of test"})
    t = pd.DataFrame(trades)
    eq = pd.Series({d: v for d, v in curve}, dtype=float)
    if len(eq):
        eq.loc[weekly.index[-1]] = cash
        maxdd = float((eq/eq.cummax()-1).min()*100)
    else:
        maxdd = 0.0
    wins = t[t.pnl > 0] if len(t) else pd.DataFrame()
    losses = t[t.pnl <= 0] if len(t) else pd.DataFrame()
    gross_win = float(wins.pnl.sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses.pnl.sum())) if len(losses) else 0.0
    metrics = {
        "initial_capital": float(initial_capital), "final_equity": float(cash),
        "total_return_pct": (cash/float(initial_capital)-1)*100,
        "trades": len(t), "win_rate_pct": len(wins)/len(t)*100 if len(t) else 0.0,
        "profit_factor": gross_win/gross_loss if gross_loss else (float("inf") if gross_win else 0.0),
        "max_drawdown_pct": maxdd,
        "average_trade_pct": float(t.return_pct.mean()) if len(t) else 0.0,
        "note": "Single-symbol weekly approximation. Signals use completed bars and next-week open fills. "
                "Stops use weekly OHLC with conservative gap handling; intrabar order is unknown. "
                "Yahoo adjusted data and current-universe symbols are not survivorship-free. "
                "Historical fundamentals are not point-in-time and are not used in entries."
    }
    return {"trades": t, "equity": eq, "metrics": metrics}
