"""Plotly figures styled for the dark glass interface."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from engine.magic_line import build_line

MINT = "#2EE6A8"
ROSE = "#FF6B9A"
VIOLET = "#8B7CFF"
SKY = "#5FD4FF"
AMBER = "#FFC857"
MUTED = "#93A4BF"
GRID = "rgba(148,163,184,.12)"
FONT = "Space Grotesk, -apple-system, sans-serif"

TONE_COLORS = {
    "Ready to Buy": MINT,
    "Building Base": SKY,
    "Superstock Discovery": VIOLET,
    "Extended": AMBER,
    "Exit Warning": ROSE,
    "Watchlist / Developing": MUTED,
    "Insufficient Data": MUTED,
}


def _style(fig, height=560, title=None):
    fig.update_layout(
        template=None,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color="#CFE0F5", size=12),
        margin=dict(l=8, r=96, t=56 if title else 24, b=8),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(9,14,25,.95)", font=dict(family=FONT, color="#E8EEF9")),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, bgcolor="rgba(0,0,0,0)"),
        showlegend=True,
    )
    if title:
        fig.update_layout(title=dict(text=title, x=0.008, xanchor="left",
                                     font=dict(size=16, color="#E8EEF9")))
    fig.update_xaxes(showgrid=False, zeroline=False, color=MUTED, rangeslider_visible=False)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, color=MUTED)
    return fig


def weekly_chart(weekly, *, plan=None, magic_line=None, magic_name=None, base_high=None,
                 height=560, show_volume=True):
    if weekly is None or weekly.empty:
        return go.Figure()
    rows = 2 if show_volume else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.78, 0.22] if show_volume else [1.0])
    fig.add_trace(go.Candlestick(
        x=weekly.index, open=weekly.Open, high=weekly.High, low=weekly.Low, close=weekly.Close,
        name="Weekly",
        increasing=dict(line=dict(color=MINT, width=1), fillcolor="rgba(46,230,168,.55)"),
        decreasing=dict(line=dict(color=ROSE, width=1), fillcolor="rgba(255,107,154,.5)"),
        showlegend=False,
    ), row=1, col=1)

    for column, name, color, dash in [
        ("ma30", "30W SMA", "#7EA6FF", "solid"),
        ("ma10", "10W SMA", "#C7B8FF", "dot"),
        ("ma10e", "10W EMA", AMBER, "dash"),
    ]:
        if column in weekly.columns:
            fig.add_trace(go.Scatter(
                x=weekly.index, y=weekly[column], name=name, mode="lines",
                line=dict(color=color, width=1.3, dash=dash),
                hovertemplate="%{y:.2f}<extra>" + name + "</extra>",
            ), row=1, col=1)

    if magic_line is not None and pd.notna(magic_line):
        fig.add_hline(
            y=float(magic_line), row=1, col=1,
            line=dict(color=VIOLET, width=1.4, dash="dash"),
            annotation_text="Magic line",
            annotation_position="right", annotation_font=dict(color="#CFC5FF", size=11),
        )
    if base_high is not None and pd.notna(base_high):
        fig.add_hline(y=float(base_high), row=1, col=1,
                      line=dict(color="rgba(148,163,184,.55)", width=1, dash="dot"),
                      annotation_text="Base high", annotation_position="right",
                      annotation_font=dict(color=MUTED, size=10))

    if plan and plan.get("actionable"):
        low, high = plan.get("entry_zone_low"), plan.get("entry_zone_high")
        if low is not None and high is not None:
            fig.add_vrect(x0=weekly.index[0], x1=weekly.index[-1], row=1, col=1,
                          fillcolor="rgba(46,230,168,.08)", line_width=0)
            fig.add_hline(y=float(low), row=1, col=1, line=dict(color=MINT, width=1, dash="dot"))
            fig.add_hline(y=float(high), row=1, col=1, line=dict(color=MINT, width=1, dash="dot"),
                          annotation_text="Entry zone", annotation_position="left",
                          annotation_font=dict(color=MINT, size=10))
        if plan.get("stop") is not None:
            fig.add_hline(y=float(plan["stop"]), row=1, col=1,
                          line=dict(color=ROSE, width=1.2, dash="dash"),
                          annotation_text=f"Stop {plan['stop']:,.2f}", annotation_position="left",
                          annotation_font=dict(color=ROSE, size=10))
        if plan.get("primary_target") is not None:
            fig.add_hline(y=float(plan["primary_target"]), row=1, col=1,
                          line=dict(color=SKY, width=1.2, dash="dash"),
                          annotation_text=f"Target {plan['primary_target']:,.2f}", annotation_position="right",
                          annotation_font=dict(color=SKY, size=10))

    if show_volume and "Volume" in weekly.columns:
        colors = [MINT if c >= o else ROSE for o, c in zip(weekly.Open, weekly.Close)]
        fig.add_trace(go.Bar(x=weekly.index, y=weekly.Volume, marker_color=colors,
                             marker_line_width=0, opacity=0.55, name="Volume",
                             showlegend=False, hovertemplate="%{y:,.0f}<extra>Volume</extra>"),
                      row=2, col=1)
        fig.update_yaxes(title_text="", row=2, col=1)

    return _style(fig, height=height)


def magic_lab_chart(weekly, candidates, selected, height=560):
    if weekly is None or weekly.empty:
        return go.Figure()
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=weekly.index, open=weekly.Open, high=weekly.High, low=weekly.Low, close=weekly.Close,
        name="Weekly",
        increasing=dict(line=dict(color=MINT, width=1), fillcolor="rgba(46,230,168,.5)"),
        decreasing=dict(line=dict(color=ROSE, width=1), fillcolor="rgba(255,107,154,.45)"),
        showlegend=False,
    ))
    palette = [SKY, AMBER, ROSE, VIOLET, "#7EA6FF"]
    for index, candidate in enumerate(candidates or []):
        name = candidate["name"]
        is_selected = name == selected
        fig.add_trace(go.Scatter(
            x=weekly.index, y=build_line(weekly.Close, name), name=name, mode="lines",
            line=dict(width=2.6 if is_selected else 1.1,
                      color=VIOLET if is_selected else palette[index % len(palette)],
                      dash="solid" if is_selected else "dot"),
            hovertemplate="%{y:.2f}<extra>" + name + "</extra>",
        ))
    if selected:
        metric = next((c for c in candidates if c["name"] == selected), None)
        if metric and metric.get("current_value"):
            fig.add_hline(y=float(metric["current_value"]), line=dict(color=VIOLET, width=1, dash="dash"),
                          annotation_text=f"{selected}", annotation_position="right",
                          annotation_font=dict(color="#CFC5FF", size=11))
    return _style(fig, height=height)


def equity_chart(equity: pd.Series, height=320):
    if equity is None or equity.empty:
        return go.Figure()
    fig = go.Figure(go.Scatter(
        x=equity.index, y=equity.values, mode="lines", name="Equity",
        line=dict(color=MINT, width=2.2),
        fill="tozeroy", fillcolor="rgba(46,230,168,.10)",
        hovertemplate="%{y:,.0f}<extra>Equity</extra>",
    ))
    return _style(fig, height=height)


def classification_donut(df: pd.DataFrame, height=300):
    fig = go.Figure()
    if df is None or df.empty or "classification" not in df:
        return _style(fig, height=height)
    counts = df["classification"].fillna("Insufficient Data").value_counts()
    fig.add_trace(go.Pie(
        labels=counts.index, values=counts.values, hole=0.62,
        marker=dict(colors=[TONE_COLORS.get(str(label), MUTED) for label in counts.index],
                    line=dict(color="rgba(7,11,20,.9)", width=2)),
        textinfo="label+percent", textfont=dict(family=FONT, size=11),
        hovertemplate="%{label}: %{value}<extra></extra>", sort=False,
    ))
    fig.add_annotation(text=f"<b>{len(df)}</b><br><span style='font-size:10px'>scanned</span>",
                       showarrow=False, font=dict(family=FONT, size=18, color="#E8EEF9"))
    return _style(fig, height=height).update_layout(showlegend=False)


def score_leaders(df: pd.DataFrame, limit=10, height=340):
    fig = go.Figure()
    if df is None or df.empty or "opportunity_score" not in df:
        return _style(fig, height=height)
    frame = df.dropna(subset=["opportunity_score"]).sort_values("opportunity_score", ascending=True).tail(limit)
    colors = [TONE_COLORS.get(str(c), MUTED) for c in frame.get("classification", pd.Series([None] * len(frame)))]
    fig.add_trace(go.Bar(
        x=frame["opportunity_score"], y=frame["symbol"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:.0f}" for v in frame["opportunity_score"]],
        textposition="outside", textfont=dict(family=FONT, color="#CFE0F5", size=11),
        hovertemplate="%{y}: %{x:.0f}<extra></extra>", showlegend=False,
    ))
    fig.update_xaxes(range=[0, 105], showgrid=False)
    fig.update_yaxes(showgrid=False)
    return _style(fig, height=height).update_layout(margin=dict(l=8, r=30, t=20, b=8))
