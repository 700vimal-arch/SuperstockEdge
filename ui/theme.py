"""Presentational helpers: design tokens, global CSS and HTML components."""
from __future__ import annotations

import html

import streamlit as st

PALETTE = {
    "mint": "#2EE6A8",
    "violet": "#8B7CFF",
    "sky": "#5FD4FF",
    "amber": "#FFC857",
    "rose": "#FF6B9A",
    "text": "#E8EEF9",
    "muted": "#93A4BF",
}

TONES = {
    "Ready to Buy": "mint",
    "Building Base": "sky",
    "Superstock Discovery": "violet",
    "Extended": "amber",
    "Exit Warning": "rose",
    "Watchlist / Developing": "neutral",
    "Insufficient Data": "neutral",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

:root{
  --sse-bg:#070B14; --sse-panel:rgba(17,26,43,.78); --sse-line:rgba(148,163,184,.14);
  --sse-text:#E8EEF9; --sse-muted:#93A4BF; --sse-mint:#2EE6A8; --sse-violet:#8B7CFF;
  --sse-sky:#5FD4FF; --sse-amber:#FFC857; --sse-rose:#FF6B9A;
}
html, body, [class*="css"], [data-testid="stAppViewContainer"]{
  font-family:'Space Grotesk',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  color:var(--sse-text);
}
.stApp{
  background:
    radial-gradient(1100px 620px at 10% -10%, rgba(46,230,168,.16), transparent 60%),
    radial-gradient(950px 520px at 95% -5%, rgba(139,124,255,.18), transparent 58%),
    radial-gradient(700px 420px at 60% 110%, rgba(95,212,255,.08), transparent 60%),
    linear-gradient(180deg,#070B14 0%,#05070D 55%,#070B14 100%);
}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}
[data-testid="stMainBlockContainer"]{padding-top:1.1rem;max-width:1560px;}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,rgba(12,18,32,.97),rgba(7,11,20,.99));
  border-right:1px solid var(--sse-line);
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:var(--sse-muted);}
[data-testid="stSidebar"] hr{border-color:var(--sse-line);}
[data-testid="stSidebar"] [role="radiogroup"] label{
  background:rgba(148,163,184,.05);border:1px solid transparent;border-radius:12px;
  padding:7px 11px;margin-bottom:5px;transition:background .15s ease,border-color .15s ease;
  width:100%;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{background:rgba(46,230,168,.08);}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
  background:linear-gradient(120deg,rgba(46,230,168,.16),rgba(139,124,255,.16));
  border-color:rgba(46,230,168,.35);
}

.sse-hero{
  position:relative;overflow:hidden;border-radius:26px;padding:34px 38px 30px;
  margin:0 0 22px;border:1px solid rgba(148,163,184,.16);
  background:linear-gradient(135deg,rgba(17,26,43,.94),rgba(9,14,25,.82));
  box-shadow:0 30px 90px -50px rgba(0,0,0,.95), inset 0 1px 0 rgba(255,255,255,.05);
}
.sse-hero::before{
  content:"";position:absolute;inset:-55% -10% auto;height:320px;
  background:radial-gradient(closest-side,rgba(46,230,168,.30),transparent);
  filter:blur(12px);animation:sse-drift 16s ease-in-out infinite alternate;pointer-events:none;
}
.sse-hero::after{
  content:"";position:absolute;right:-6%;bottom:-70%;width:420px;height:420px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(139,124,255,.22),transparent);pointer-events:none;
}
@keyframes sse-drift{from{transform:translate3d(-4%,0,0)}to{transform:translate3d(6%,10%,0)}}
.sse-hero-row{display:flex;gap:16px;align-items:center;position:relative;z-index:1;}
.sse-mark{
  width:54px;height:54px;border-radius:16px;flex:0 0 auto;
  background:linear-gradient(140deg,#2EE6A8,#5FD4FF 55%,#8B7CFF);
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 18px 40px -18px rgba(46,230,168,.75);
}
.sse-eyebrow{
  font:600 .7rem/1.1 'JetBrains Mono',monospace;letter-spacing:.26em;text-transform:uppercase;
  color:var(--sse-mint);margin-bottom:8px;
}
.sse-title{
  font-weight:700;font-size:clamp(2rem,3.4vw,3.1rem);letter-spacing:-.035em;line-height:1.02;
  background:linear-gradient(100deg,#FFFFFF 4%,#B9F5DF 32%,#A79BFF 68%,#FFFFFF 98%);
  -webkit-background-clip:text;background-clip:text;color:transparent;margin:0;
}
.sse-sub{color:var(--sse-muted);max-width:78ch;margin-top:10px;font-size:1.02rem;line-height:1.55;position:relative;z-index:1;}
.sse-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:20px;position:relative;z-index:1;}
.sse-chip{
  font:500 .76rem/1 'JetBrains Mono',monospace;letter-spacing:.02em;color:#CFE0F5;
  border:1px solid rgba(148,163,184,.22);border-radius:999px;padding:8px 12px;
  background:rgba(148,163,184,.06);display:inline-flex;gap:7px;align-items:center;
}
.sse-chip b{color:var(--sse-mint);font-weight:600;}
.sse-chip[data-tone="violet"] b{color:var(--sse-violet);}
.sse-chip[data-tone="amber"] b{color:var(--sse-amber);}
.sse-chip[data-tone="rose"] b{color:var(--sse-rose);}

.sse-kpi{
  position:relative;overflow:hidden;min-height:116px;padding:18px 20px;border-radius:18px;
  border:1px solid var(--sse-line);
  background:linear-gradient(160deg,rgba(22,32,52,.86),rgba(10,16,28,.82));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04);transition:transform .18s ease,border-color .18s ease;
}
.sse-kpi:hover{transform:translateY(-2px);border-color:rgba(46,230,168,.28);}
.sse-kpi::before{
  content:"";position:absolute;left:0;top:0;height:3px;width:100%;
  background:linear-gradient(90deg,var(--sse-mint),transparent 70%);
}
.sse-kpi[data-accent="violet"]::before{background:linear-gradient(90deg,var(--sse-violet),transparent 70%);}
.sse-kpi[data-accent="amber"]::before{background:linear-gradient(90deg,var(--sse-amber),transparent 70%);}
.sse-kpi[data-accent="rose"]::before{background:linear-gradient(90deg,var(--sse-rose),transparent 70%);}
.sse-kpi .k-label{
  font:600 .68rem/1 'JetBrains Mono',monospace;letter-spacing:.16em;text-transform:uppercase;
  color:var(--sse-muted);margin-bottom:12px;
}
.sse-kpi .k-value{font-size:1.85rem;font-weight:650;letter-spacing:-.03em;line-height:1.1;}
.sse-kpi .k-hint{margin-top:10px;font-size:.8rem;color:var(--sse-muted);}
.sse-kpi[data-accent="rose"] .k-value{color:#FFB3C7;}
.sse-kpi[data-accent="amber"] .k-value{color:#FFE0A3;}

.sse-section{margin:30px 0 14px;}
.sse-section .s-eyebrow{
  font:600 .68rem/1 'JetBrains Mono',monospace;letter-spacing:.22em;text-transform:uppercase;
  color:var(--sse-mint);
}
.sse-section h2{margin:7px 0 0;font-size:1.55rem;letter-spacing:-.02em;font-weight:650;}
.sse-section p{margin:6px 0 0;color:var(--sse-muted);font-size:.92rem;max-width:90ch;}

.sse-badge{
  display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:4px 11px;
  font:600 .72rem/1 'JetBrains Mono',monospace;letter-spacing:.03em;white-space:nowrap;
  border:1px solid rgba(148,163,184,.25);color:#CFE0F5;background:rgba(148,163,184,.08);
}
.sse-badge[data-tone="mint"]{color:#8FF3CF;background:rgba(46,230,168,.12);border-color:rgba(46,230,168,.38);}
.sse-badge[data-tone="sky"]{color:#B7E9FF;background:rgba(95,212,255,.10);border-color:rgba(95,212,255,.34);}
.sse-badge[data-tone="violet"]{color:#CFC5FF;background:rgba(139,124,255,.14);border-color:rgba(139,124,255,.38);}
.sse-badge[data-tone="amber"]{color:#FFE0A3;background:rgba(255,200,87,.12);border-color:rgba(255,200,87,.36);}
.sse-badge[data-tone="rose"]{color:#FFB3C7;background:rgba(255,107,154,.12);border-color:rgba(255,107,154,.38);}

.sse-meter{height:8px;border-radius:99px;background:rgba(148,163,184,.14);overflow:hidden;margin-top:8px;}
.sse-meter i{display:block;height:100%;border-radius:99px;background:linear-gradient(90deg,#2EE6A8,#8B7CFF);}

.sse-card{
  border:1px solid var(--sse-line);border-radius:18px;padding:20px 22px;
  background:linear-gradient(165deg,rgba(20,30,49,.8),rgba(9,14,25,.86));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.04);height:100%;
}
.sse-card h4{margin:0 0 8px;font-size:1rem;letter-spacing:-.01em;}
.sse-card p{margin:0;color:var(--sse-muted);font-size:.86rem;line-height:1.5;}
.sse-card .sse-card-index{
  font:600 .68rem/1 'JetBrains Mono',monospace;color:var(--sse-mint);letter-spacing:.18em;
  margin-bottom:10px;display:block;
}
.sse-flag{
  border-radius:14px;padding:13px 16px;border:1px solid var(--sse-line);
  background:rgba(148,163,184,.05);font-size:.88rem;line-height:1.5;color:#CFE0F5;margin:12px 0;
}
.sse-flag[data-tone="mint"]{border-color:rgba(46,230,168,.32);background:rgba(46,230,168,.07);}
.sse-flag[data-tone="amber"]{border-color:rgba(255,200,87,.32);background:rgba(255,200,87,.07);}
.sse-flag[data-tone="rose"]{border-color:rgba(255,107,154,.34);background:rgba(255,107,154,.08);}
.sse-grid{display:grid;gap:14px;}
.sse-grid.three{grid-template-columns:repeat(auto-fit,minmax(240px,1fr));}

.stButton>button, .stDownloadButton>button{
  border-radius:12px!important;border:1px solid rgba(46,230,168,.35)!important;
  background:linear-gradient(120deg,rgba(46,230,168,.16),rgba(139,124,255,.16))!important;
  color:#EAF6F1!important;font-weight:600!important;transition:transform .15s ease,box-shadow .15s ease!important;
}
.stButton>button:hover, .stDownloadButton>button:hover{
  transform:translateY(-1px);box-shadow:0 14px 34px -20px rgba(46,230,168,.9);
  border-color:rgba(46,230,168,.6)!important;
}
.stButton>button[kind="primary"]{
  background:linear-gradient(120deg,#2EE6A8,#5FD4FF)!important;color:#04120E!important;border:none!important;
}
.stTabs [data-baseweb="tab-list"]{
  gap:6px;background:rgba(148,163,184,.06);padding:6px;border-radius:14px;border:1px solid var(--sse-line);
}
.stTabs [data-baseweb="tab"]{border-radius:10px;padding:8px 16px;color:var(--sse-muted);}
.stTabs [aria-selected="true"]{
  background:linear-gradient(120deg,rgba(46,230,168,.20),rgba(139,124,255,.20));color:#fff!important;
}
[data-testid="stDataFrame"]{border:1px solid var(--sse-line);border-radius:16px;overflow:hidden;}
[data-baseweb="select"]>div,[data-baseweb="input"],.stTextInput input,.stTextArea textarea,.stNumberInput input{
  background-color:rgba(13,20,34,.88)!important;border-color:rgba(148,163,184,.2)!important;border-radius:12px!important;
}
[data-testid="stExpander"] details{
  border:1px solid var(--sse-line);border-radius:14px;background:rgba(13,20,34,.6);
}
[data-testid="stAlert"]{border-radius:14px;border:1px solid var(--sse-line);}
[data-testid="stAppDeployButton"],#MainMenu{display:none!important;}
header[data-testid="stHeader"]{background:transparent;}
[data-testid="stMetric"]{background:rgba(148,163,184,.05);border:1px solid var(--sse-line);border-radius:16px;padding:12px;}
div[data-testid="stStatusWidget"]{background:transparent;}
.sse-footer{
  margin-top:44px;padding-top:18px;border-top:1px solid var(--sse-line);
  color:var(--sse-muted);font-size:.78rem;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;
}
.sse-footer code{background:rgba(148,163,184,.1);border-radius:6px;padding:2px 6px;color:#CFE0F5;}
::-webkit-scrollbar{width:10px;height:10px;}
::-webkit-scrollbar-thumb{background:rgba(148,163,184,.22);border-radius:99px;}
@media (prefers-reduced-motion: reduce){*{animation:none!important;transition:none!important;}}
</style>
"""

MARK = (
    '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
    '<path d="M3 17.5 9 11l4 3.5L21 6" stroke="#04120E" stroke-width="2.4" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="9" cy="11" r="1.6" fill="#04120E"/></svg>'
)


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, chips: list[tuple[str, str, str]] | None = None) -> None:
    chip_html = "".join(
        f'<span class="sse-chip" data-tone="{tone}">{html.escape(label)} <b>{html.escape(value)}</b></span>'
        for label, value, tone in (chips or [])
    )
    st.markdown(
        f"""
        <section class="sse-hero">
          <div class="sse-hero-row">
            <div class="sse-mark">{MARK}</div>
            <div>
              <div class="sse-eyebrow">Weekly structure intelligence</div>
              <h1 class="sse-title">{html.escape(title)}</h1>
            </div>
          </div>
          <p class="sse-sub">{subtitle}</p>
          <div class="sse-chips">{chip_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def kpi(label: str, value: str, hint: str = "", accent: str = "mint") -> str:
    return (
        f'<div class="sse-kpi" data-accent="{accent}">'
        f'<div class="k-label">{html.escape(label)}</div>'
        f'<div class="k-value">{html.escape(value)}</div>'
        f'<div class="k-hint">{html.escape(hint)}</div>'
        "</div>"
    )


def kpi_row(items: list[dict]) -> None:
    columns = st.columns(len(items))
    for column, item in zip(columns, items):
        with column:
            st.markdown(
                kpi(item["label"], item["value"], item.get("hint", ""), item.get("accent", "mint")),
                unsafe_allow_html=True,
            )


def section(title: str, eyebrow: str = "", note: str = "") -> None:
    note_html = f"<p>{note}</p>" if note else ""
    st.markdown(
        f'<div class="sse-section"><div class="s-eyebrow">{html.escape(eyebrow)}</div>'
        f"<h2>{html.escape(title)}</h2>{note_html}</div>",
        unsafe_allow_html=True,
    )


def badge(text: str) -> str:
    tone = TONES.get(str(text), "neutral")
    return f'<span class="sse-badge" data-tone="{tone}">{html.escape(str(text))}</span>'


def meter(value: float, ceiling: float = 100.0) -> str:
    pct = 0.0 if ceiling <= 0 else max(0.0, min(100.0, float(value) / ceiling * 100))
    return f'<div class="sse-meter"><i style="width:{pct:.0f}%"></i></div>'


def flag(text: str, tone: str = "neutral") -> None:
    st.markdown(f'<div class="sse-flag" data-tone="{tone}">{text}</div>', unsafe_allow_html=True)


def feature_cards(cards: list[tuple[str, str, str]]) -> None:
    body = "".join(
        f'<div class="sse-card"><span class="sse-card-index">{html.escape(index)}</span>'
        f"<h4>{html.escape(title)}</h4><p>{html.escape(body_text)}</p></div>"
        for index, title, body_text in cards
    )
    st.markdown(f'<div class="sse-grid three">{body}</div>', unsafe_allow_html=True)


def footer(version: str) -> None:
    st.markdown(
        '<div class="sse-footer">'
        f"<span>Superstock Edge <code>{html.escape(version)}</code> · research prototype · no broker execution</span>"
        "<span>Prices via Yahoo Finance · best effort · verify against official filings</span>"
        "</div>",
        unsafe_allow_html=True,
    )
