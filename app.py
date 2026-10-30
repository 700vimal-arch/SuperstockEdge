from __future__ import annotations
import math
import sys, yaml
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.market_data import fetch_ohlcv
from engine.technicals import weekly_ohlcv, analyse_weekly, score_candidate
from engine.fundamentals import quarterly_snapshot
from engine.backtest import run_backtest
from engine.magic_line import build_line
from engine.entry_plan import build_trade_plan

st.set_page_config(page_title="Superstock Edge", page_icon="📈", layout="wide")
with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

st.markdown("""<style>
.block-container{padding-top:1.4rem;padding-bottom:2rem}
[data-testid="stMetric"]{background:rgba(128,128,128,.08);padding:12px;border-radius:10px}
.small-muted{color:#888;font-size:.82rem}
</style>""", unsafe_allow_html=True)
st.title("📈 Superstock Edge")
st.caption("India + US · Swing + Long-term · Free-first research scanner · Version 0.3.1")
st.warning(
    "Research prototype only. Yahoo Finance is best-effort, may be delayed, incomplete or unavailable, "
    "and is not a guaranteed live feed. This app does not provide investment advice or broker execution. "
    "Verify prices, corporate actions and financials with official sources."
)

wl_path = ROOT / "storage" / "watchlist.txt"
wl_path.parent.mkdir(parents=True, exist_ok=True)
if not wl_path.exists():
    wl_path.write_text("\n".join(CFG["markets"]["india"]["symbols"] + CFG["markets"]["us"]["symbols"]), encoding="utf-8")


def load_symbols():
    return [x.strip() for x in wl_path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


with st.sidebar:
    st.header("Scanner controls")
    market = st.selectbox("Market", ["Both markets", "India", "United States"])
    mode = st.radio("Strategy horizon", ["Swing + Long-term", "Swing focus", "Long-term focus"])
    period = st.selectbox("Historical price period", ["2y", "5y", "10y"], index=1)
    refresh = st.checkbox("Refresh downloaded data", value=False)
    st.caption("Symbols are editable in storage/watchlist.txt")
    page = st.radio("Workspace", ["Market overview", "Discovery scanner", "Magic Line lab",
                                   "Stock analysis", "Backtesting lab", "Watchlist & data"])

symbols = load_symbols()
if market == "India":
    symbols = [s for s in symbols if s.endswith((".NS", ".BO"))]
elif market == "United States":
    symbols = [s for s in symbols if not s.endswith((".NS", ".BO"))]


@st.cache_data(ttl=900, show_spinner=False)
def load_symbol(sym, per, force):
    return fetch_ohlcv(sym, period=per, interval="1d", refresh=force)


def fmt_num(value, digits=2):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{number:,.{digits}f}" if math.isfinite(number) else "N/A"


def render_trade_plan(plan):
    st.markdown("#### Entry, stop and target plan")
    if not plan.get("actionable"):
        reasons = plan.get("reasons") or ["No trade plan is available for this setup."]
        st.info(" ".join(reasons))
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Entry zone", f"{fmt_num(plan['entry_zone_low'])}–{fmt_num(plan['entry_zone_high'])}")
    c2.metric("Structural stop", fmt_num(plan["stop"]))
    c3.metric("Primary target", fmt_num(plan["primary_target"]))
    rr = plan.get("reward_risk")
    c4.metric("Reward/risk", f"{rr:.2f}R" if rr is not None else "N/A")
    st.caption(
        f"{plan['setup_label']} — {plan['setup_reason']}  ·  "
        f"Price vs reference {fmt_num(plan.get('distance_from_price_pct'))}%  ·  "
        f"Risk {fmt_num(plan['risk_pct'])}% of entry  ·  "
        f"{plan.get('reward_risk_band') or 'R/R unavailable'}"
    )
    if plan.get("annualized_eps") is not None:
        st.caption(
            f"Indicative annualized EPS {fmt_num(plan['annualized_eps'], 4)} · "
            f"annualized P/E at the current price {fmt_num(plan.get('annualized_pe'))}. "
            "Annualization is unsuitable for seasonal or one-off earnings."
        )
    st.markdown(f"**Stop rationale:** {plan['stop_reason']}")
    stop_rows = [{
        "Candidate": c["label"], "Level": c["level"], "Stop": c["stop"],
        "Risk %": c["distance_pct"], "Risk (ATR)": c["distance_atr"],
        "Selected": c["stop"] == plan["stop"],
    } for c in plan.get("stop_candidates", [])]
    if stop_rows:
        st.dataframe(pd.DataFrame(stop_rows), use_container_width=True, hide_index=True)
    target_rows = [{
        "Target": t["label"], "Source": t["source"], "Price": t["value"],
        "Upside %": t["upside_pct"], "R multiple": t["r_multiple"], "Below entry": t["below_entry"],
    } for t in plan.get("targets", [])]
    if target_rows:
        st.dataframe(pd.DataFrame(target_rows), use_container_width=True, hide_index=True)
    for warning in plan.get("warnings", []):
        st.caption(f"Note: {warning}")


def render_magic_lab(weekly, tech):
    lab = tech.get("magic_line_lab") or {}
    candidates = lab.get("candidates") or []
    st.write(
        f"Evaluated as of the completed week ending **{lab.get('as_of', 'N/A')}**. "
        f"{len(candidates)} candidate averages tested using only outcomes observable at that date."
    )
    if lab.get("selected"):
        current = lab.get("current") or {}
        a, b, c, d = st.columns(4)
        a.metric("Selected line", lab["selected"])
        b.metric("Current line", fmt_num(current.get("value")))
        c.metric("Distance from line", f"{fmt_num(current.get('distance_pct'))}%")
        d.metric("4-week slope", f"{fmt_num(current.get('slope_pct_4w'))}%")
        if lab.get("rationale"):
            st.success(lab["rationale"])
        elif lab.get("message"):
            st.warning(lab["message"])
        if current.get("breakdown"):
            st.error("Price is below the breakdown buffer of the selected line.")
        elif current.get("pending_test"):
            st.info("The latest completed week is an unresolved support test.")
    else:
        st.warning(lab.get("message") or "No reliable Magic Line identified.")

    rows = [{
        "Line": c["name"], "Qualified": c["qualified"], "Score": c["score"],
        "Tests": c["tests"], "Resolved": c["resolved_tests"], "Successes": c["successes"],
        "Failures": c["failures"], "Open": c["open_tests"],
        "Success %": c["success_rate_pct"], "Avg bounce %": c["avg_bounce_pct"],
        "Avg recovery (w)": c["avg_recovery_weeks"],
        "Max close deviation %": c["max_close_deviation_pct"],
        "Breakdowns": c["confirmed_breakdowns"], "Weeks above %": c["trend_consistency_pct"],
        "Current": c["current_value"], "Distance %": c["current_distance_pct"],
        "Slope %": c["slope_pct_4w"], "Note": c["reason"],
    } for c in candidates]
    if rows:
        st.markdown("#### Candidate comparison")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    selected = lab.get("selected_metrics") or {}
    events = selected.get("events") or []
    if events:
        st.markdown("#### Historical support tests for the selected line")
        event_rows = [{
            "Week": e["date"], "Line": e["line"], "Low": e["low"], "Close": e["close"],
            "Outcome": e["status"], "Bounce %": e["bounce_pct"],
            "Recovery weeks": e["recovery_weeks"],
        } for e in events]
        st.dataframe(pd.DataFrame(event_rows), use_container_width=True, hide_index=True)

    if weekly is not None and not weekly.empty and candidates:
        fig = go.Figure(data=[go.Candlestick(
            x=weekly.index, open=weekly.Open, high=weekly.High, low=weekly.Low,
            close=weekly.Close, name="Confirmed weekly"
        )])
        for candidate in candidates:
            is_selected = candidate["name"] == lab.get("selected")
            fig.add_trace(go.Scatter(
                x=weekly.index, y=build_line(weekly.Close, candidate["name"]),
                name=candidate["name"],
                line=dict(width=2.4 if is_selected else 1.1,
                          dash="solid" if is_selected else "dot"),
            ))
        fig.update_layout(height=620, xaxis_rangeslider_visible=False,
                          title="Weekly structure and candidate Magic Lines")
        st.plotly_chart(fig, use_container_width=True)


def scan_one(sym):
    d, meta = load_symbol(sym, period, refresh)
    if not isinstance(meta, dict):
        meta = {"status": "metadata_unavailable", "message": "Price metadata unavailable."}
    if d is None or d.empty:
        return {"symbol": sym, "status": meta.get("status", "no_data"),
                "message": meta.get("message", "No usable price data")}, None, None, meta
    w = weekly_ohlcv(d)
    tech = analyse_weekly(w, CFG["scanner"])
    fund, fmeta = quarterly_snapshot(sym)
    plan = build_trade_plan(tech, fund, CFG["scanner"])
    scores = score_candidate(tech, fund, CFG["scanner"], plan=plan)
    daily_close = float(d.Close.iloc[-1])
    daily_date = str(d.index[-1].date())
    magic = tech.get("magic_line")
    daily_magic_extension = (daily_close / magic - 1) * 100 if magic else None
    row = {
        "symbol": sym, "company": fund.get("company", sym),
        "daily_close_adjusted": daily_close, "daily_date": daily_date,
        "confirmed_weekly_close": tech.get("close"), "confirmed_weekly_date": tech.get("weekly_date"),
        "weekly_bars": len(w), "provider_status": meta.get("status"),
        "market_cap": fund.get("market_cap"), "currency": fund.get("currency"),
        "trailing_pe": fund.get("trailing_pe"), "eps_latest_q": fund.get("latest_quarter_eps"),
        "eps_yoy_growth_pct": fund.get("quarterly_eps_yoy_growth_pct"),
        "revenue_yoy_growth_pct": fund.get("quarterly_revenue_yoy_growth_pct"),
        "operating_income_yoy_growth_pct": fund.get("quarterly_operating_income_yoy_growth_pct"),
        "base_valid": tech.get("base_ok"), "base_weeks": tech.get("base_weeks"),
        "base_range_pct": tech.get("base_range_pct"), "above_30w": tech.get("above30"),
        "rising_30w": tech.get("rising30"), "volume_multiple": tech.get("volume_multiple"),
        "magic_line": magic, "magic_line_name": tech.get("magic_line_name"),
        "weekly_magic_extension_pct": tech.get("magic_extension_pct"),
        "daily_magic_extension_pct": daily_magic_extension,
        "quiet_entry": tech.get("quiet"), "breakout": tech.get("breakout"),
        "setup": plan.get("setup_label") if plan.get("actionable") else None,
        "entry_zone": (f"{plan['entry_zone_low']:,.2f}–{plan['entry_zone_high']:,.2f}"
                       if plan.get("entry_zone_low") is not None else None),
        "stop_loss": plan.get("stop"),
        "primary_target": plan.get("primary_target"),
        "reward_risk": plan.get("reward_risk"),
        "classification": scores.get("classification"),
        "opportunity_score": scores.get("opportunity_score"),
        "fundamental_score": scores.get("fundamental_score"),
        "technical_score": scores.get("technical_score"), "entry_score": scores.get("entry_score"),
        "exit_risk_score": tech.get("exit_risk_score"),
        "fundamental_checks": str(scores.get("fundamental_checks", {})),
        "data_coverage": scores.get("data_coverage"),
        "fundamental_status": fmeta.get("status", "unknown"),
    }
    return row, d, w, {**meta, "fundamentals": fmeta}


def render_scan_table(df, compact=False):
    if df.empty:
        st.info("No rows to display.")
        return
    preferred = [
        "symbol", "company", "classification", "opportunity_score", "exit_risk_score",
        "daily_close_adjusted", "daily_date", "confirmed_weekly_close", "confirmed_weekly_date",
        "base_valid", "base_weeks", "base_range_pct", "above_30w", "rising_30w",
        "magic_line_name", "magic_line", "weekly_magic_extension_pct",
        "quiet_entry", "breakout", "setup", "entry_zone", "stop_loss", "primary_target", "reward_risk",
        "eps_yoy_growth_pct", "revenue_yoy_growth_pct",
        "fundamental_score", "technical_score", "entry_score", "data_coverage", "provider_status"
    ]
    cols = [c for c in preferred if c in df.columns]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)


if page == "Market overview":
    st.subheader("Market overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Symbols in current universe", len(symbols))
    c2.metric("Markets", market)
    c3.metric("Mode", mode)
    st.markdown("### What this release evaluates")
    st.write("Variable-length weekly bases, 30-week trend, relative weekly volume, volatility contraction, "
             "an automatically evaluated Magic Line, quiet-entry proximity, an entry/stop/target plan and exit warnings.")
    st.write("Magic Line selection compares 10/20-week SMA/EMA candidates using outcomes observable at the "
             "evaluation date. Fundamental merit is scored separately from data coverage.")
    if st.button("Run scan", type="primary"):
        rows, progress, status = [], st.progress(0), st.empty()
        for i, sym in enumerate(symbols):
            status.write(f"Scanning {sym}…")
            row, _, _, _ = scan_one(sym)
            rows.append(row)
            progress.progress((i + 1) / max(1, len(symbols)))
        st.session_state["scan_results"] = pd.DataFrame(rows)
        status.success("Scan completed. Inspect provider status and data coverage for each symbol.")
    if "scan_results" in st.session_state:
        df = st.session_state["scan_results"]
        if "opportunity_score" in df:
            df = df.sort_values("opportunity_score", ascending=False, na_position="last")
        render_scan_table(df)


elif page == "Discovery scanner":
    st.subheader("Superstock discovery scanner")
    st.caption("Watchlist-sized research scan; not a complete exchange-wide feed.")
    if st.button("Scan universe", type="primary"):
        rows, bar, msg = [], st.progress(0), st.empty()
        for i, sym in enumerate(symbols):
            msg.write(f"Downloading and analysing {sym}")
            row, _, _, _ = scan_one(sym)
            rows.append(row)
            bar.progress((i + 1) / max(1, len(symbols)))
        st.session_state["scan_results"] = pd.DataFrame(rows)
        msg.success("Scan finished.")
    if "scan_results" in st.session_state:
        df = st.session_state["scan_results"].copy()
        minscore = st.slider("Minimum opportunity score", 0, 100, 0)
        if "opportunity_score" in df:
            df = df[pd.to_numeric(df.opportunity_score, errors="coerce").fillna(-1) >= minscore]
        classes = ["All"] + sorted(df.classification.dropna().unique().tolist()) if "classification" in df else ["All"]
        chosen = st.selectbox("Classification", classes)
        if chosen != "All":
            df = df[df.classification == chosen]
        render_scan_table(df)
        st.download_button("Download scan CSV", df.to_csv(index=False), "superstock_scan.csv", "text/csv")


elif page == "Magic Line lab":
    st.subheader("Magic Line laboratory")
    st.caption("Candidate weekly averages are compared with historical outcomes known at the evaluation date.")
    if not symbols:
        st.info("No symbols in the selected market. Edit the watchlist.")
    else:
        symbol = st.selectbox("Select symbol", symbols, key="magic_lab_symbol")
        with st.spinner(f"Loading {symbol}…"):
            daily, meta = load_symbol(symbol, period, refresh)
        if daily is None or daily.empty:
            st.error(f"No usable OHLCV data: {meta.get('message', 'Unknown provider error')}")
        else:
            weekly = weekly_ohlcv(daily)
            tech = analyse_weekly(weekly, CFG["scanner"])
            if tech.get("ready"):
                st.caption(f"Price source: {meta.get('source')} · Status: {meta.get('status')} · "
                           f"Weekly candle: {tech.get('weekly_date')}")
                render_magic_lab(weekly, tech)
            else:
                st.warning(tech.get("reason", "Insufficient confirmed weekly history."))


elif page == "Stock analysis":
    st.subheader("Stock analysis")
    if not symbols:
        st.info("No symbols in the selected market. Edit the watchlist.")
    else:
        symbol = st.selectbox("Select symbol", symbols)
        with st.spinner(f"Loading {symbol}…"):
            daily, meta = load_symbol(symbol, period, refresh)
            fundamentals, fmeta = quarterly_snapshot(symbol)
        if daily is None or daily.empty:
            st.error(f"No usable OHLCV data: {meta.get('message', 'Unknown provider error')}")
        else:
            weekly = weekly_ohlcv(daily)
            tech = analyse_weekly(weekly, CFG["scanner"])
            plan = build_trade_plan(tech, fundamentals, CFG["scanner"])
            scores = score_candidate(tech, fundamentals, CFG["scanner"], plan=plan)
            a, b, c, d = st.columns(4)
            a.metric("Latest daily adjusted close", f"{daily.Close.iloc[-1]:,.2f}")
            b.metric("Opportunity score", scores.get("opportunity_score", 0))
            c.metric("Exit risk", tech.get("exit_risk_score", 0))
            d.metric("Confirmed weekly bars", len(weekly))
            st.caption(f"Price source: {meta.get('source')} · Status: {meta.get('status')} · "
                       f"Daily candle: {daily.index[-1].date()} · Weekly candle: {tech.get('weekly_date', 'not available')} · "
                       "OHLCV requested with auto_adjust=True.")
            if tech.get("ready"):
                st.write(f"**Classification:** {scores.get('classification')}  ·  "
                         f"**Base:** {'Valid' if tech.get('base_ok') else 'Not valid'} "
                         f"({tech.get('base_weeks')} weeks, {fmt_num(tech.get('base_range_pct'), 1)}% range)")
                st.write(f"**Magic Line:** {tech.get('magic_line_name') or 'No reliable Magic Line identified'} "
                         f"at {fmt_num(tech.get('magic_line'))} · "
                         f"weekly extension {fmt_num(tech.get('magic_extension_pct'))}%")
                fig = go.Figure(data=[go.Candlestick(
                    x=weekly.index, open=weekly.Open, high=weekly.High, low=weekly.Low,
                    close=weekly.Close, name="Confirmed weekly"
                )])
                x = tech["weekly"]
                for col, name, dash in [("ma30", "30-week SMA", "solid"), ("ma10", "10-week SMA", "dot"),
                                        ("ma10e", "10-week EMA", "dash")]:
                    fig.add_trace(go.Scatter(x=x.index, y=x[col], name=name, line=dict(width=1.3, dash=dash)))
                if tech.get("magic_line") is not None:
                    fig.add_hline(y=tech["magic_line"], line_dash="dash",
                                  annotation_text=f"Magic Line: {tech['magic_line_name']}")
                fig.add_hline(y=tech["base_high"], line_dash="dot", annotation_text="Base high")
                fig.update_layout(height=620, xaxis_rangeslider_visible=False, title=f"{symbol} — weekly chart")
                st.plotly_chart(fig, use_container_width=True)
                render_trade_plan(plan)
                left, right = st.columns(2)
                with left:
                    st.markdown("#### Technical structure")
                    st.json({k: v for k, v in tech.items() if k not in ("weekly", "magic_line_lab")})
                with right:
                    st.markdown("#### Fundamental snapshot")
                    st.json(fundamentals)
                    st.caption(f"Fundamental source: {fmeta.get('status')} — "
                               f"{fmeta.get('warning', 'Verify against official filings.')}")
                    st.json(scores.get("fundamental_checks", {}))
            else:
                st.warning(tech.get("reason", "Insufficient confirmed weekly history."))
            st.markdown("#### Daily adjusted OHLCV")
            st.dataframe(daily.tail(30).sort_index(ascending=False), use_container_width=True)


elif page == "Backtesting lab":
    st.subheader("Backtesting lab")
    st.info("Single-symbol weekly research approximation. It does not use historical point-in-time fundamentals or a survivorship-free universe.")
    if not symbols:
        st.info("No symbols in the selected market.")
    else:
        symbol = st.selectbox("Symbol to test", symbols)
        cap = st.number_input("Initial capital (symbol currency)", min_value=1000.0, value=100000.0, step=10000.0)
        commission = st.number_input("Commission (basis points per side)", min_value=0.0, value=10.0)
        slippage = st.number_input("Slippage (basis points per side)", min_value=0.0, value=10.0)
        risk = st.number_input("Risk per trade (%)", min_value=.1, max_value=2.0, value=.5, step=.1) / 100
        if st.button("Run historical test", type="primary"):
            d, meta = load_symbol(symbol, period, refresh)
            if d.empty:
                st.error(meta.get("message", "No data"))
            else:
                result = run_backtest(weekly_ohlcv(d), cap, commission, slippage, risk, CFG["scanner"])
                st.session_state["bt_result"], st.session_state["bt_symbol"] = result, symbol
        if "bt_result" in st.session_state:
            res, m = st.session_state["bt_result"], st.session_state["bt_result"]["metrics"]
            if "error" in m:
                st.error(m["error"])
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Total return", f"{m['total_return_pct']:.2f}%")
                c2.metric("Max drawdown", f"{m['max_drawdown_pct']:.2f}%")
                c3.metric("Trades", m["trades"])
                c4.metric("Win rate", f"{m['win_rate_pct']:.1f}%")
                st.json(m)
                if not res["equity"].empty:
                    st.line_chart(res["equity"].rename("Equity"))
                st.dataframe(res["trades"], use_container_width=True, hide_index=True)
                st.download_button("Download trades CSV", res["trades"].to_csv(index=False),
                                   f"{st.session_state['bt_symbol']}_trades.csv", "text/csv")


elif page == "Watchlist & data":
    st.subheader("Watchlist and data configuration")
    st.write("One ticker per line. Examples: RELIANCE.NS, TCS.NS, AAPL, NVDA. Provider suffixes may change.")
    current = wl_path.read_text(encoding="utf-8")
    edited = st.text_area("Editable symbols", current, height=240)
    if st.button("Save watchlist", type="primary"):
        cleaned = [x.strip().upper() for x in edited.splitlines() if x.strip()]
        wl_path.write_text("\n".join(dict.fromkeys(cleaned)), encoding="utf-8")
        st.success(f"Saved {len(set(cleaned))} symbols. Reload the app to refresh the sidebar universe.")
    st.markdown("#### Data provider notes")
    st.markdown("- **Prices:** Yahoo Finance via yfinance; adjusted OHLCV, best-effort, not a guaranteed live feed.\n"
                "- **Fundamentals:** company snapshot and quarterly statements vary by ticker/provider.\n"
                "- **Insider data:** not integrated into scoring; verify SEC filings or Indian exchange disclosures.\n"
                "- **Point-in-time data:** not supplied. Historical fundamental backtests are not validated.")
    st.markdown("#### Local cache")
    cache = ROOT / "storage" / "cache"
    cached = list(cache.glob("*.csv")) if cache.exists() else []
    st.write(f"Cached price files: {len(cached)}")
    if st.button("Clear downloaded price cache"):
        for f in cached:
            f.unlink(missing_ok=True)
        st.cache_data.clear()
        st.success("Cache cleared.")

st.divider()
st.caption("Superstock Edge 0.3.1 · Paper/research only · No broker execution · Verify all prices, filings and corporate actions.")
