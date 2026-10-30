from __future__ import annotations
import html
import math
import sys, yaml
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.market_data import fetch_ohlcv, prefetch_ohlcv
from data.universe import SOURCES, UNIVERSE_LABELS, load_universe, watchlist_symbols
from engine.technicals import weekly_ohlcv, analyse_weekly, score_candidate
from engine.fundamentals import quarterly_snapshot
from engine.backtest import run_backtest
from engine.entry_plan import build_trade_plan
from ui import theme
from ui.charts import classification_donut, equity_chart, magic_lab_chart, score_leaders, weekly_chart

st.set_page_config(page_title="Superstock Edge", page_icon="📈", layout="wide")
with open(ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)

VERSION = CFG["app"]["version"]
SCAN_CFG = CFG.get("scanner", {})
UNIV_CFG = CFG.get("universe", {})
BATCH_SIZE = int(UNIV_CFG.get("batch_size", 50))
UNIVERSE_TTL = int(UNIV_CFG.get("cache_ttl_days", 7))
FUNDAMENTALS_TOP_N = int(UNIV_CFG.get("fundamentals_top_n", 25))

theme.inject()

wl_path = ROOT / "storage" / "watchlist.txt"
wl_path.parent.mkdir(parents=True, exist_ok=True)
if not wl_path.exists():
    wl_path.write_text("\n".join(CFG["markets"]["india"]["symbols"] + CFG["markets"]["us"]["symbols"]),
                       encoding="utf-8")

WORKSPACES = ["Market overview", "Discovery scanner", "Magic Line lab",
              "Stock analysis", "Backtesting lab", "Watchlist & data"]
UNIVERSE_CHOICES = ["watchlist", *SOURCES.keys()]
LIMIT_CHOICES = ["25", "50", "100", "250", "500", "All"]
INDIA_SUFFIXES = (".NS", ".BO")


with st.sidebar:
    st.markdown(
        f"""
        <div style="display:flex;gap:10px;align-items:center;margin:2px 0 16px">
          <div class="sse-mark" style="width:38px;height:38px;border-radius:12px">{theme.MARK}</div>
          <div>
            <div style="font-weight:700;letter-spacing:-.02em;font-size:1.05rem">Superstock Edge</div>
            <div style="font:600 .66rem/1 'JetBrains Mono',monospace;letter-spacing:.16em;color:#2EE6A8">
              VERSION {VERSION}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("UNIVERSE")
    universe_choice = st.selectbox(
        "Universe", UNIVERSE_CHOICES,
        format_func=lambda key: "Custom watchlist" if key == "watchlist" else UNIVERSE_LABELS[key],
        label_visibility="collapsed",
    )
    market = st.selectbox("Market filter", ["Both markets", "India", "United States"])
    period = st.selectbox("History", ["2y", "5y", "10y"], index=1)
    limit_choice = st.selectbox("Symbols per scan", LIMIT_CHOICES, index=2)
    refresh = st.checkbox("Refresh prices from provider", value=False)
    refresh_universe = st.button("Refresh constituents", width="stretch")
    st.divider()
    page = st.radio("Workspace", WORKSPACES)
    st.divider()
    st.caption("Prices: Yahoo Finance, best effort. Research only, no broker execution.")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_universe(key: str, ttl: int):
    return load_universe(key, ttl_days=ttl)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def load_symbol(sym, per, force):
    return fetch_ohlcv(sym, period=per, interval="1d", refresh=force)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fundamentals_cached(sym):
    return quarterly_snapshot(sym)


def resolve_universe():
    if universe_choice == "watchlist":
        symbols = watchlist_symbols(wl_path)
        meta = {"label": "Custom watchlist", "status": "local", "count": len(symbols),
                "as_of": None, "source": str(wl_path)}
    elif refresh_universe:
        symbols, meta = load_universe(universe_choice, ttl_days=UNIVERSE_TTL, refresh=True)
        st.session_state["universe_override"] = {"key": universe_choice, "symbols": symbols, "meta": meta}
    else:
        override = st.session_state.get("universe_override")
        if override and override["key"] == universe_choice:
            symbols, meta = override["symbols"], override["meta"]
        else:
            symbols, meta = cached_universe(universe_choice, UNIVERSE_TTL)
    if market == "India":
        symbols = [s for s in symbols if s.endswith(INDIA_SUFFIXES)]
    elif market == "United States":
        symbols = [s for s in symbols if not s.endswith(INDIA_SUFFIXES)]
    return symbols, meta


def sample_evenly(symbols, choice):
    if choice == "All" or len(symbols) <= int(choice):
        return list(symbols)
    limit = max(1, int(choice))
    if limit == 1:
        return symbols[:1]
    picks = [round(i * (len(symbols) - 1) / (limit - 1)) for i in range(limit)]
    return [symbols[i] for i in dict.fromkeys(picks)]


def fmt_num(value, digits=2):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "N/A"
    return f"{number:,.{digits}f}" if math.isfinite(number) else "N/A"


def fmt_pct(value, digits=1):
    text = fmt_num(value, digits)
    return "N/A" if text == "N/A" else f"{text}%"


def fmt_cell(value, digits=2, suffix=""):
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:,.{digits}f}{suffix}" if math.isfinite(number) else ""


def build_row(sym, daily, weekly, tech, plan, scores, meta, fund=None, fmeta=None):
    fund = fund or {}
    fmeta = fmeta or {}
    magic = tech.get("magic_line")
    daily_close = float(daily.Close.iloc[-1])
    daily_extension = (daily_close / magic - 1) * 100 if magic else None
    return {
        "symbol": sym, "company": fund.get("company", sym),
        "daily_close_adjusted": daily_close, "daily_date": str(daily.index[-1].date()),
        "confirmed_weekly_close": tech.get("close"), "confirmed_weekly_date": tech.get("weekly_date"),
        "weekly_bars": len(weekly), "provider_status": meta.get("status"),
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
        "daily_magic_extension_pct": daily_extension,
        "quiet_entry": tech.get("quiet"), "breakout": tech.get("breakout"),
        "setup": plan.get("setup_label") if plan.get("actionable") else None,
        "entry_zone": (f"{plan['entry_zone_low']:,.2f}–{plan['entry_zone_high']:,.2f}"
                       if plan.get("entry_zone_low") is not None else None),
        "stop_loss": plan.get("stop"), "primary_target": plan.get("primary_target"),
        "reward_risk": plan.get("reward_risk"),
        "classification": scores.get("classification"),
        "opportunity_score": scores.get("opportunity_score"),
        "fundamental_score": scores.get("fundamental_score"),
        "technical_score": scores.get("technical_score"), "entry_score": scores.get("entry_score"),
        "exit_risk_score": tech.get("exit_risk_score"),
        "fundamental_checks": str(scores.get("fundamental_checks", {})),
        "data_coverage": scores.get("data_coverage"),
        "fundamental_status": fmeta.get("status", "not fetched"),
    }


def scan_universe(symbols, period, refresh):
    status = st.status(f"Scanning {len(symbols)} symbols · {UNIVERSE_LABELS.get(universe_choice, 'watchlist')}",
                       expanded=True)
    bar = st.progress(0.0)
    caption = st.empty()

    def price_progress(done, total, label):
        bar.progress(min(1.0, done / max(1, total)))
        caption.caption(f"Prices · {done}/{total} · {label}")

    fetch_summary = prefetch_ohlcv(
        symbols, period=period, interval="1d", refresh=refresh,
        chunk_size=BATCH_SIZE, progress=price_progress,
    )
    caption.caption("Analysing weekly structure and building plans…")

    rows, analysed, failures = [], {}, []
    for index, sym in enumerate(symbols):
        daily, meta = load_symbol(sym, period, False)
        if daily is None or daily.empty:
            failures.append({"symbol": sym, "reason": meta.get("message") or meta.get("status")})
            bar.progress((index + 1) / max(1, len(symbols)))
            continue
        weekly = weekly_ohlcv(daily)
        tech = analyse_weekly(weekly, SCAN_CFG)
        plan = build_trade_plan(tech, {}, SCAN_CFG)
        scores = score_candidate(tech, {}, SCAN_CFG, plan=plan)
        analysed[sym] = {"daily": daily, "weekly": weekly, "tech": tech}
        rows.append(build_row(sym, daily, weekly, tech, plan, scores, meta))
        bar.progress((index + 1) / max(1, len(symbols)))

    df = pd.DataFrame(rows)
    caption.caption("Fetching fundamentals for the strongest candidates…")
    if not df.empty and "opportunity_score" in df:
        top = df.sort_values("opportunity_score", ascending=False, na_position="last")["symbol"].head(FUNDAMENTALS_TOP_N)
        fund_bar = st.progress(0.0)
        for done, sym in enumerate(top, start=1):
            fund, fmeta = fundamentals_cached(sym)
            cached = analysed.get(sym)
            if cached is None:
                continue
            weekly, tech = cached["weekly"], cached["tech"]
            plan = build_trade_plan(tech, fund, SCAN_CFG)
            scores = score_candidate(tech, fund, SCAN_CFG, plan=plan)
            row = build_row(sym, cached["daily"], weekly, tech, plan, scores,
                            {"status": "cached"}, fund, fmeta)
            df.loc[df["symbol"] == sym, list(row.keys())] = list(row.values())
            fund_bar.progress(done / max(1, len(top)))

    st.session_state["scan_results"] = df
    st.session_state["scan_meta"] = {
        "requested": len(symbols),
        "analysed": len(df),
        "failures": failures,
        "downloads": len(fetch_summary["downloaded"]),
        "universe": UNIVERSE_LABELS.get(universe_choice, "Custom watchlist"),
        "period": period,
    }
    st.session_state["scan_universe"] = list(analysed.keys())
    status.update(label=f"Scan complete · {len(df)} symbols analysed · {len(fetch_summary['downloaded'])} downloaded",
                  state="complete", expanded=False)
    bar.empty()
    caption.empty()
    return df


def render_scan_table(df, height=460):
    if df is None or df.empty:
        theme.flag("No rows yet. Run a scan to populate results.", "amber")
        return
    preferred = [
        "symbol", "company", "classification", "opportunity_score", "exit_risk_score",
        "setup", "entry_zone", "stop_loss", "primary_target", "reward_risk",
        "daily_close_adjusted", "daily_date", "confirmed_weekly_close", "weekly_bars",
        "base_valid", "base_weeks", "base_range_pct", "magic_line_name", "magic_line",
        "weekly_magic_extension_pct", "quiet_entry", "breakout",
        "eps_yoy_growth_pct", "revenue_yoy_growth_pct",
        "fundamental_score", "technical_score", "entry_score", "provider_status",
    ]
    cols = [c for c in preferred if c in df.columns]
    view = df[cols].copy()
    text_columns = {
        "symbol", "company", "classification", "setup", "entry_zone", "magic_line_name",
        "provider_status", "daily_date", "confirmed_weekly_date", "fundamental_status",
        "fundamental_checks",
    }
    for column in view.columns.intersection(text_columns):
        view[column] = view[column].map(lambda value: "" if pd.isna(value) else value)
    for column, digits, suffix in [
        ("stop_loss", 2, ""), ("primary_target", 2, ""), ("reward_risk", 2, "×"),
        ("magic_line", 2, ""), ("weekly_magic_extension_pct", 1, "%"),
        ("base_range_pct", 1, "%"), ("eps_yoy_growth_pct", 1, "%"),
        ("revenue_yoy_growth_pct", 1, "%"), ("base_weeks", 0, ""),
        ("daily_close_adjusted", 2, ""), ("confirmed_weekly_close", 2, ""),
        ("weekly_bars", 0, ""), ("fundamental_score", 0, ""),
        ("technical_score", 0, ""), ("entry_score", 0, ""),
    ]:
        if column in view:
            view[column] = view[column].map(
                lambda value, d=digits, s=suffix: fmt_cell(value, d, s) if pd.notna(value) else "")
    for column in view.columns.intersection({"base_valid", "quiet_entry", "breakout"}):
        view[column] = view[column].astype("boolean")
    for column in view.columns.intersection({"opportunity_score", "exit_risk_score"}):
        view[column] = pd.to_numeric(view[column], errors="coerce")
    config = {
        "symbol": st.column_config.TextColumn("Symbol"),
        "company": st.column_config.TextColumn("Company", width="medium"),
        "classification": st.column_config.TextColumn("Classification"),
        "opportunity_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d"),
        "exit_risk_score": st.column_config.NumberColumn("Exit risk", format="%d"),
        "setup": st.column_config.TextColumn("Setup"),
        "entry_zone": st.column_config.TextColumn("Entry zone", width="medium"),
        "stop_loss": st.column_config.TextColumn("Stop", width="medium"),
        "primary_target": st.column_config.TextColumn("Target", width="medium"),
        "reward_risk": st.column_config.TextColumn("R/R"),
        "daily_close_adjusted": st.column_config.TextColumn("Last"),
        "daily_date": st.column_config.TextColumn("Daily date"),
        "confirmed_weekly_close": st.column_config.TextColumn("Weekly close"),
        "weekly_bars": st.column_config.TextColumn("Bars"),
        "base_weeks": st.column_config.TextColumn("Base weeks"),
        "base_range_pct": st.column_config.TextColumn("Base range"),
        "magic_line_name": st.column_config.TextColumn("Magic line"),
        "magic_line": st.column_config.TextColumn("Line value"),
        "weekly_magic_extension_pct": st.column_config.TextColumn("vs Magic"),
        "eps_yoy_growth_pct": st.column_config.TextColumn("EPS YoY"),
        "revenue_yoy_growth_pct": st.column_config.TextColumn("Revenue YoY"),
        "fundamental_score": st.column_config.TextColumn("Fund score"),
        "technical_score": st.column_config.TextColumn("Tech score"),
        "entry_score": st.column_config.TextColumn("Entry score"),
        "base_valid": st.column_config.CheckboxColumn("Base"),
        "quiet_entry": st.column_config.CheckboxColumn("Quiet"),
        "breakout": st.column_config.CheckboxColumn("Breakout"),
        "provider_status": st.column_config.TextColumn("Provider"),
    }
    st.dataframe(view, hide_index=True, width="stretch", height=height,
                 column_config={k: v for k, v in config.items() if k in view.columns})


def render_setup_cards(df, limit=3):
    if df is None or df.empty:
        return
    actionable = df[df["setup"].notna()] if "setup" in df else pd.DataFrame()
    if actionable.empty:
        theme.flag("No actionable setup in this scan. That is a valid outcome, not a failure: "
                   "the planner needs a confirmed structure, a defined stop and a target above entry.", "amber")
        return
    sort_keys = [key for key in ("reward_risk", "opportunity_score") if key in actionable]
    picks = actionable.sort_values(sort_keys, ascending=False).head(limit)
    columns = st.columns(len(picks))
    for column, (_, row) in zip(columns, picks.iterrows()):
        reward = fmt_num(row.get("reward_risk"))
        with column:
            st.markdown(
                f"""
                <div class="sse-card">
                  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
                    <span style="font-weight:700;font-size:1.08rem;letter-spacing:-.01em">{html.escape(str(row['symbol']))}</span>
                    {theme.badge(row.get('classification', 'Watchlist / Developing'))}
                  </div>
                  <div style="color:var(--sse-muted);font-size:.8rem;margin:6px 0 16px">
                    {html.escape(str(row.get('setup', 'Setup')))} · score {fmt_num(row.get('opportunity_score'), 0)}
                  </div>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
                    <div><div class="k-label" style="font:600 .62rem/1 'JetBrains Mono',monospace;color:#93A4BF;letter-spacing:.14em">ENTRY ZONE</div>
                      <div style="font-weight:600;margin-top:6px">{html.escape(str(row.get('entry_zone') or 'N/A'))}</div></div>
                    <div><div style="font:600 .62rem/1 'JetBrains Mono',monospace;color:#93A4BF;letter-spacing:.14em">STOP</div>
                      <div style="font-weight:600;margin-top:6px;color:#FFB3C7">{fmt_num(row.get('stop_loss'))}</div></div>
                    <div><div style="font:600 .62rem/1 'JetBrains Mono',monospace;color:#93A4BF;letter-spacing:.14em">TARGET</div>
                      <div style="font-weight:600;margin-top:6px;color:#B7E9FF">{fmt_num(row.get('primary_target'))}</div></div>
                    <div><div style="font:600 .62rem/1 'JetBrains Mono',monospace;color:#93A4BF;letter-spacing:.14em">REWARD/RISK</div>
                      <div style="font-weight:600;margin-top:6px;color:#8FF3CF">{reward}×</div></div>
                  </div>
                  {theme.meter(float(row.get('opportunity_score') or 0))}
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_trade_plan(plan):
    theme.section("Entry, stop and target", eyebrow="Trade plan",
                  note="Structural reference first, then a stop with cited candidates and conservative targets.")
    if not plan.get("actionable"):
        reasons = plan.get("reasons") or ["No trade plan is available for this setup."]
        theme.flag(" ".join(html.escape(str(r)) for r in reasons), "amber")
        return
    theme.kpi_row([
        {"label": "Entry zone", "value": f"{fmt_num(plan['entry_zone_low'])}–{fmt_num(plan['entry_zone_high'])}",
         "hint": plan.get("setup_label", ""), "accent": "mint"},
        {"label": "Structural stop", "value": fmt_num(plan["stop"]),
         "hint": f"Risk {fmt_pct(plan.get('risk_pct'))} of entry", "accent": "rose"},
        {"label": "Primary target", "value": fmt_num(plan.get("primary_target")),
         "hint": plan.get("reward_risk_band") or "R/R unavailable", "accent": "violet"},
        {"label": "Reward / risk", "value": f"{fmt_num(plan.get('reward_risk'))}×",
         "hint": f"Price vs reference {fmt_pct(plan.get('distance_from_price_pct'))}", "accent": "amber"},
    ])
    theme.flag(html.escape(str(plan.get("setup_reason", ""))), "mint")
    stop_rows = [{
        "Candidate": c["label"], "Level": c["level"], "Stop": c["stop"],
        "Risk %": c["distance_pct"], "Risk (ATR)": c["distance_atr"],
        "Selected": "●" if c["stop"] == plan["stop"] else "",
    } for c in plan.get("stop_candidates", [])]
    target_rows = [{
        "Target": t["label"], "Source": t["source"], "Price": t["value"],
        "Upside %": t["upside_pct"], "R multiple": t["r_multiple"], "Below entry": t["below_entry"],
    } for t in plan.get("targets", [])]
    left, right = st.columns(2)
    with left:
        st.markdown("**Stop candidates**")
        if stop_rows:
            st.dataframe(pd.DataFrame(stop_rows), hide_index=True, width="stretch")
    with right:
        st.markdown("**Targets**")
        if target_rows:
            st.dataframe(pd.DataFrame(target_rows), hide_index=True, width="stretch")
    if plan.get("annualized_eps") is not None:
        st.caption(
            f"Indicative annualized EPS {fmt_num(plan['annualized_eps'], 4)} · "
            f"annualized P/E at the current price {fmt_num(plan.get('annualized_pe'))}. "
            "Annualization is unsuitable for seasonal or one-off earnings."
        )
    for warning in plan.get("warnings", []):
        st.caption(f"Note · {warning}")


def render_magic_lab(weekly, tech):
    lab = tech.get("magic_line_lab") or {}
    candidates = lab.get("candidates") or []
    theme.section("Magic Line laboratory", eyebrow="Evidence, not a fixed average",
                  note=(f"Evaluated as of the completed week ending {lab.get('as_of', 'N/A')}. "
                        f"{len(candidates)} candidate averages tested using outcomes observable at that date."))
    if not lab.get("selected"):
        theme.flag(html.escape(str(lab.get("message") or "No reliable Magic Line identified.")), "amber")
        return
    current = lab.get("current") or {}
    theme.kpi_row([
        {"label": "Selected line", "value": lab["selected"],
         "hint": "Highest evidence score", "accent": "violet"},
        {"label": "Current line", "value": fmt_num(current.get("value")),
         "hint": f"4-week slope {fmt_pct(current.get('slope_pct_4w'))}", "accent": "mint"},
        {"label": "Distance from line", "value": fmt_pct(current.get("distance_pct")),
         "hint": "Weekly close vs line", "accent": "amber"},
        {"label": "Confirmed breakdowns",
         "value": str((lab.get("selected_metrics") or {}).get("confirmed_breakdowns", "N/A")),
         "hint": "Weekly closes below buffer", "accent": "rose"},
    ])
    if lab.get("rationale"):
        theme.flag(html.escape(lab["rationale"]), "mint")
    elif lab.get("message"):
        theme.flag(html.escape(lab["message"]), "amber")
    if current.get("breakdown"):
        theme.flag("Price is below the breakdown buffer of the selected line.", "rose")
    elif current.get("pending_test"):
        theme.flag("The latest completed week is an unresolved support test.", "amber")

    st.plotly_chart(magic_lab_chart(weekly, candidates, lab.get("selected")), width="stretch")

    rows = [{
        "Line": c["name"], "Qualified": "●" if c["qualified"] else "○", "Score": c["score"],
        "Tests": c["tests"], "Resolved": c["resolved_tests"], "Successes": c["successes"],
        "Failures": c["failures"], "Open": c["open_tests"], "Success %": fmt_cell(c["success_rate_pct"], 1, "%"),
        "Avg bounce %": fmt_cell(c["avg_bounce_pct"], 1, "%"), "Avg recovery (w)": fmt_cell(c["avg_recovery_weeks"], 1),
        "Max dev %": fmt_cell(c["max_close_deviation_pct"], 1, "%"), "Breakdowns": c["confirmed_breakdowns"],
        "Weeks above %": fmt_cell(c["trend_consistency_pct"], 0, "%"), "Current": fmt_cell(c["current_value"]),
    } for c in candidates]
    if rows:
        theme.section("Candidate comparison", eyebrow="All tested averages")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=210)

    events = (lab.get("selected_metrics") or {}).get("events") or []
    if events:
        with st.expander(f"Historical support tests · {len(events)} events", expanded=False):
            event_rows = [{
                "Week": e["date"], "Line": e["line"], "Low": e["low"], "Close": e["close"],
                "Outcome": e["status"], "Bounce %": fmt_cell(e["bounce_pct"], 1, "%"),
                "Recovery weeks": fmt_cell(e["recovery_weeks"], 1),
            } for e in events]
            st.dataframe(pd.DataFrame(event_rows), hide_index=True, width="stretch")


symbols_all, universe_meta = resolve_universe()
scan_symbols = sample_evenly(symbols_all, limit_choice)
universe_label = UNIVERSE_LABELS.get(universe_choice, "Custom watchlist")
scan_df = st.session_state.get("scan_results")
scan_meta = st.session_state.get("scan_meta") or {}
scan_pool = st.session_state.get("scan_universe") or scan_symbols

HERO_COPY = {
    "Market overview": (
        "Weekly structure, one screen",
        "Scan a real index universe, rank confirmed weekly setups and see the trade plan before you look at a single candle.",
    ),
    "Discovery scanner": (
        "Find the setup, not the story",
        "Filter the last scan by score, classification and actionability, then open the chart behind any name.",
    ),
    "Magic Line lab": (
        "Which average actually held?",
        "Every candidate line is tested only on outcomes observable at each point in time. The winner is evidence, not a fixed rule.",
    ),
    "Stock analysis": (
        "One name, full context",
        "Weekly structure, the selected Magic Line, a structural stop and a conservative target, with the fundamentals that support or contradict it.",
    ),
    "Backtesting lab": (
        "Pressure-test the rules",
        "Long-only weekly approximation with commission and slippage. It is a research sanity check, not proof of edge.",
    ),
    "Watchlist & data": (
        "Control the inputs",
        "Edit the custom watchlist, refresh index constituents and clear the local price cache.",
    ),
}
hero_title, hero_subtitle = HERO_COPY[page]
theme.hero(hero_title, hero_subtitle, [
    ("Universe", universe_label, "mint"),
    ("Scan window", f"{len(scan_symbols)} symbols", "violet"),
    ("History", period, "amber"),
    ("Version", VERSION, "rose"),
])


if page == "Market overview":
    actionable_count = 0 if scan_df is None or scan_df.empty else int(scan_df["setup"].notna().sum())
    theme.kpi_row([
        {"label": "Universe members", "value": f"{len(symbols_all):,}",
         "hint": f"{universe_label} · {universe_meta.get('status', 'local')}", "accent": "mint"},
        {"label": "Scan window", "value": f"{len(scan_symbols):,}",
         "hint": f"Evenly sampled · {period} history", "accent": "violet"},
        {"label": "Analysed", "value": f"{scan_meta.get('analysed', 0):,}",
         "hint": f"{scan_meta.get('downloads', 0)} freshly downloaded" if scan_meta else "Run a scan to populate",
         "accent": "sky"},
        {"label": "Actionable plans", "value": str(actionable_count),
         "hint": "Confirmed structure with stop and target", "accent": "amber"},
    ])

    if not scan_symbols:
        hint = "No symbols match this universe and market filter. Switch the market filter or pick another universe."
        if universe_meta.get("status") == "error":
            hint = f"The constituent list could not be loaded: {universe_meta.get('warning', 'unknown error')}"
        theme.flag(hint, "amber")
    elif scan_df is None or scan_df.empty:
        theme.feature_cards([
            ("01", "Pick a real universe", "NIFTY 500, S&P 500 and NASDAQ-100 constituent lists are pulled and cached, so a scan covers hundreds of names instead of a hand-typed watchlist."),
            ("02", "Rank confirmed structure", "Every symbol is compressed to completed weekly bars, scored on base quality, trend, Magic Line extension and entry timing."),
            ("03", "Get a plan, not a prompt", "Actionable rows carry an entry zone, a structural stop with cited candidates, a conservative target and a reward/risk ratio."),
        ])
        theme.section("Ready when you are", eyebrow="Scan",
                      note="Prices are prefetched in batches; the first run downloads history, later runs read the local cache.")
        run = st.button("Run scan", type="primary", width="stretch")
        st.caption(f"Universe source: {universe_meta.get('source', 'local file')} · asked for {len(symbols_all)} symbols after the {market.lower()} filter.")
        if run:
            scan_universe(scan_symbols, period, refresh)
            st.rerun()
    else:
        theme.section("Today's board", eyebrow="Actionable setups",
                      note=f"Top reward/risk from {scan_meta.get('analysed', len(scan_df))} analysed symbols · {scan_meta.get('universe', universe_label)}.")
        render_setup_cards(scan_df, limit=3)
        left, right = st.columns([1, 1.6])
        with left:
            st.plotly_chart(classification_donut(scan_df), width="stretch")
        with right:
            st.plotly_chart(score_leaders(scan_df), width="stretch")
        theme.section("Full scan", eyebrow="Every analysed symbol")
        render_scan_table(scan_df)
        failures = scan_meta.get("failures") or []
        if failures:
            with st.expander(f"Symbols without usable data · {len(failures)}", expanded=False):
                st.dataframe(pd.DataFrame(failures), hide_index=True, width="stretch")
        st.download_button("Download scan CSV", scan_df.to_csv(index=False),
                           f"superstock_scan_{VERSION}.csv", "text/csv")
        if st.button("Re-run scan", width="content"):
            scan_universe(scan_symbols, period, refresh)
            st.rerun()


elif page == "Discovery scanner":
    if scan_df is None or scan_df.empty:
        theme.flag("No scan in memory yet. Run one from Market overview, then come back to filter it.", "amber")
        if st.button("Run scan now", type="primary"):
            scan_universe(scan_symbols, period, refresh)
            st.rerun()
    else:
        theme.section("Filters", eyebrow="Narrow the board",
                      note="Search matches symbol and company name. Score is the blended technical + fundamental opportunity score.")
        f1, f2, f3 = st.columns([1.2, 1, 1])
        with f1:
            query = st.text_input("Search symbol or company", "")
        with f2:
            min_score = st.slider("Minimum score", 0, 100, 40, step=5)
        with f3:
            actionable_only = st.checkbox("Actionable plans only", value=False)
        classifications = sorted(scan_df["classification"].dropna().unique()) if "classification" in scan_df else []
        chosen = st.multiselect("Classification", classifications, default=classifications)

        view = scan_df.copy()
        if query:
            needle = query.strip().lower()
            mask = view["symbol"].str.lower().str.contains(needle, na=False)
            if "company" in view:
                mask = mask | view["company"].str.lower().str.contains(needle, na=False)
            view = view[mask]
        if "opportunity_score" in view:
            view = view[view["opportunity_score"].fillna(0) >= min_score]
        if chosen and "classification" in view:
            view = view[view["classification"].isin(chosen)]
        if actionable_only and "setup" in view:
            view = view[view["setup"].notna()]

        theme.kpi_row([
            {"label": "Matches", "value": f"{len(view):,}", "hint": f"of {len(scan_df):,} analysed", "accent": "mint"},
            {"label": "Actionable", "value": str(int(view["setup"].notna().sum()) if "setup" in view else 0),
             "hint": "Entry, stop and target defined", "accent": "violet"},
            {"label": "Above 30-week", "value": str(int(view["above_30w"].fillna(False).sum()) if "above_30w" in view else 0),
             "hint": "Trend filter passed", "accent": "sky"},
            {"label": "Median score", "value": fmt_num(view["opportunity_score"].median() if "opportunity_score" in view and not view.empty else None, 0),
             "hint": "Current filtered set", "accent": "amber"},
        ])
        render_setup_cards(view, limit=3)
        theme.section("Results", eyebrow="Filtered scan")
        render_scan_table(view, height=520)
        st.download_button("Download filtered CSV", view.to_csv(index=False),
                           f"superstock_filtered_{VERSION}.csv", "text/csv")


elif page == "Magic Line lab":
    if not scan_pool:
        theme.flag("No symbols available in the current universe.", "amber")
    else:
        pick = st.selectbox("Symbol", scan_pool, index=0)
        daily, meta = load_symbol(pick, period, refresh)
        if daily is None or daily.empty:
            theme.flag(f"No usable OHLCV for {pick}. {meta.get('message', '')}", "rose")
        else:
            weekly = weekly_ohlcv(daily)
            tech = analyse_weekly(weekly, SCAN_CFG)
            if not tech.get("ready"):
                theme.flag(tech.get("reason", "Insufficient confirmed weekly history."), "amber")
            else:
                st.caption(f"{pick} · {meta.get('source')} · daily candle {daily.index[-1].date()} · {len(weekly)} confirmed weekly bars")
                render_magic_lab(weekly, tech)


elif page == "Stock analysis":
    if not scan_pool:
        theme.flag("No symbols available in the current universe.", "amber")
    else:
        pick = st.selectbox("Symbol", scan_pool, index=0)
        daily, meta = load_symbol(pick, period, refresh)
        if daily is None or daily.empty:
            theme.flag(f"No usable OHLCV for {pick}. {meta.get('message', '')}", "rose")
        else:
            fundamentals, fmeta = fundamentals_cached(pick)
            weekly = weekly_ohlcv(daily)
            tech = analyse_weekly(weekly, SCAN_CFG)
            plan = build_trade_plan(tech, fundamentals, SCAN_CFG)
            scores = score_candidate(tech, fundamentals, SCAN_CFG, plan=plan)
            if not tech.get("ready"):
                theme.flag(tech.get("reason", "Insufficient confirmed weekly history."), "amber")
            else:
                theme.kpi_row([
                    {"label": "Last close", "value": fmt_num(daily.Close.iloc[-1]),
                     "hint": f"{daily.index[-1].date()} · adjusted", "accent": "mint"},
                    {"label": "Opportunity score", "value": fmt_num(scores.get("opportunity_score"), 0),
                     "hint": str(scores.get("classification", "")), "accent": "violet"},
                    {"label": "Exit risk", "value": fmt_num(tech.get("exit_risk_score"), 0),
                     "hint": "Higher means more structural damage", "accent": "rose"},
                    {"label": "Weekly bars", "value": str(len(weekly)),
                     "hint": f"Magic line: {tech.get('magic_line_name') or 'none'}", "accent": "amber"},
                ])
                badges = " ".join([
                    theme.badge(scores.get("classification", "Watchlist / Developing")),
                    theme.badge("Base valid" if tech.get("base_ok") else "Base invalid"),
                    theme.badge(f"{tech.get('base_weeks')}w base"),
                ])
                if plan.get("actionable"):
                    badges += " " + theme.badge(plan.get("setup_label", "Setup"))
                st.markdown(f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px">{badges}</div>',
                            unsafe_allow_html=True)
                st.caption(f"{pick} · {meta.get('source')} · daily candle {daily.index[-1].date()} · "
                           f"weekly candle {tech.get('weekly_date', 'n/a')} · auto_adjust=True")

                chart_tab, plan_tab, fund_tab, raw_tab = st.tabs(
                    ["Chart", "Trade plan", "Fundamentals", "Raw data"])
                with chart_tab:
                    st.plotly_chart(
                        weekly_chart(weekly, plan=plan, magic_line=tech.get("magic_line"),
                                     magic_name=tech.get("magic_line_name"),
                                     base_high=tech.get("base_high")),
                        width="stretch",
                    )
                with plan_tab:
                    render_trade_plan(plan)
                with fund_tab:
                    theme.section("Fundamental snapshot", eyebrow="Reported data",
                                  note=f"Source status: {fmeta.get('status', 'unknown')} · {fmeta.get('warning', 'Verify against official filings.')}")
                    st.json(fundamentals)
                    st.json(scores.get("fundamental_checks", {}))
                with raw_tab:
                    st.dataframe(daily.tail(60).sort_index(ascending=False), width="stretch", height=420)


elif page == "Backtesting lab":
    theme.flag("Single-symbol weekly research approximation. It does not use point-in-time fundamentals or a survivorship-free universe.", "amber")
    if not scan_pool:
        theme.flag("No symbols available in the current universe.", "amber")
    else:
        symbol = st.selectbox("Symbol to test", scan_pool)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            capital = st.number_input("Initial capital", min_value=1000.0, value=100000.0, step=10000.0)
        with c2:
            commission = st.number_input("Commission (bps per side)", min_value=0.0, value=10.0)
        with c3:
            slippage = st.number_input("Slippage (bps per side)", min_value=0.0, value=10.0)
        with c4:
            risk = st.number_input("Risk per trade (%)", min_value=0.1, max_value=2.0, value=0.5, step=0.1) / 100
        if st.button("Run historical test", type="primary"):
            data, meta = load_symbol(symbol, period, refresh)
            if data is None or data.empty:
                theme.flag(meta.get("message", "No data"), "rose")
            else:
                st.session_state["bt_result"] = run_backtest(
                    weekly_ohlcv(data), capital, commission, slippage, risk, SCAN_CFG)
                st.session_state["bt_symbol"] = symbol
        result = st.session_state.get("bt_result")
        if result:
            metrics = result["metrics"]
            if "error" in metrics:
                theme.flag(metrics["error"], "rose")
            else:
                theme.section(f"{st.session_state.get('bt_symbol', symbol)} · equity curve", eyebrow="Backtest")
                theme.kpi_row([
                    {"label": "Total return", "value": f"{metrics['total_return_pct']:.2f}%",
                     "hint": "After commission and slippage", "accent": "mint"},
                    {"label": "Max drawdown", "value": f"{metrics['max_drawdown_pct']:.2f}%",
                     "hint": "Peak to trough", "accent": "rose"},
                    {"label": "Trades", "value": str(metrics["trades"]),
                     "hint": "Long-only weekly", "accent": "violet"},
                    {"label": "Win rate", "value": f"{metrics['win_rate_pct']:.1f}%",
                     "hint": "Closed trades", "accent": "amber"},
                ])
                if not result["equity"].empty:
                    st.plotly_chart(equity_chart(result["equity"]), width="stretch")
                st.dataframe(result["trades"], width="stretch", hide_index=True, height=320)
                st.download_button("Download trades CSV", result["trades"].to_csv(index=False),
                                   f"{st.session_state.get('bt_symbol', symbol)}_trades.csv", "text/csv")


elif page == "Watchlist & data":
    theme.section("Custom watchlist", eyebrow="Input",
                  note="One ticker per line. Examples: RELIANCE.NS, TCS.NS, AAPL, NVDA. Provider suffixes may change.")
    current = wl_path.read_text(encoding="utf-8")
    edited = st.text_area("Editable symbols", current, height=220)
    if st.button("Save watchlist", type="primary"):
        cleaned = [line.strip().upper() for line in edited.splitlines() if line.strip()]
        wl_path.write_text("\n".join(dict.fromkeys(cleaned)), encoding="utf-8")
        st.success(f"Saved {len(set(cleaned))} symbols. The sidebar universe refreshes on the next rerun.")
    st.caption(f"Watchlist file: {wl_path}")

    theme.section("Index universes", eyebrow="Constituents", note="Lists are pulled from public index pages and cached for a week; a saved snapshot is used if the network fails.")
    uni_rows = []
    for key, spec in SOURCES.items():
        symbols, meta = cached_universe(key, UNIVERSE_TTL)
        uni_rows.append({
            "Universe": spec.label, "Symbols": meta.get("count", len(symbols)),
            "Status": meta.get("status"), "As of": meta.get("as_of") or "—", "Source": spec.url,
        })
    st.dataframe(pd.DataFrame(uni_rows), hide_index=True, width="stretch")

    theme.section("Local cache", eyebrow="Storage")
    cache = ROOT / "storage" / "cache"
    cached_prices = sorted(cache.glob("*.csv")) if cache.exists() else []
    cached_lists = sorted((cache / "universe").glob("*.json")) if (cache / "universe").exists() else []
    theme.kpi_row([
        {"label": "Price files", "value": str(len(cached_prices)), "hint": "Daily OHLCV CSVs", "accent": "mint"},
        {"label": "Constituent snapshots", "value": str(len(cached_lists)), "hint": "Index lists", "accent": "violet"},
    ])
    if st.button("Clear downloaded price cache"):
        for file in cached_prices:
            file.unlink(missing_ok=True)
        st.cache_data.clear()
        st.success("Price cache cleared. Constituent snapshots were kept.")


theme.footer(VERSION)
