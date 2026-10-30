# Superstock Edge 0.3.1

A free-first, research-only stock discovery scanner inspired by the Superstocks methodology. Version 0.3.1 adds an automatic Magic Line laboratory and an entry/stop/target planning engine.

## Included
- India and US watchlist scanning
- Weekly trend, variable-length base, relative volume and volatility contraction
- **Magic Line laboratory** comparing 10-week SMA/EMA and 20-week SMA/EMA (configurable)
- **Entry, structural stop and target planning** with reward/risk bands
- Separate fundamental, technical and entry scores
- Fundamental data coverage distinguishes passed, failed and missing checks
- Stock analysis, watchlist, CSV export and single-symbol weekly backtesting

## Magic Line laboratory

The scanner no longer uses a single hard-coded moving average. For each stock it evaluates candidate weekly averages and selects the one with the strongest evidence of historical support:

- Meaningful pullback tests where price touched the line while still closing near it
- Resolved tests that recovered versus tests that failed
- Average bounce magnitude and average recovery time
- Maximum weekly closing deviation below the line
- Confirmed weekly closing breakdown episodes
- Percentage of weeks closing above the line

The evaluation runs as of the last completed weekly bar. A test only receives an outcome when the outcome window is already inside the supplied history, so the current week's test stays `open` and never contributes to the success rate. This makes the selection reproducible without future information.

A candidate must have a minimum number of tests, resolved outcomes and successful bounces before it can be selected. If none qualifies, the app reports **"No reliable Magic Line identified"** rather than inventing one. The comparison table, rationale and historical test list are on the **Magic Line lab** workspace.

The selected line can change over time as new completed weeks arrive. That is intentional: the selection uses the information available at each evaluation date.

## Entry, stop and target plan

The planner only produces a plan for a confirmed setup:

- **A. Early accumulation** near base or Magic Line support
- **B. Post-breakout pullback** at a base-high retest
- **C. Magic Line bounce** during volume and volatility contraction
- **D. Tight consolidation continuation** below a base breakout level
- **E. Failed setup** — no plan

It does not issue a plan while a structural exit warning is active, when price is too far from the planned reference (avoiding chasing), or when no stop fits the risk budget.

- **Entry zone:** a range around the structural reference, not a false-precision price.
- **Stop:** selected from the recent swing low, base low or Magic Line, buffered by ATR. Structural candidates are preferred over a tighter ATR volatility stop. Every candidate and the chosen rationale are displayed.
- **Technical targets:** base-height projection, measured move and previous resistance.
- **Fundamental targets:** annualized latest-quarter EPS × conservative/base/optimistic P/E scenarios. They are hidden when EPS is missing or non-positive.
- **Reward/risk:** potential reward divided by defined risk, flagged as Below 2R, 2R–3R, 3R–5R or Above 5R.

Fundamental and technical targets are shown separately. The primary target is the most conservative target above entry that provides at least 1R.

## Important limitations
- Yahoo Finance is best-effort and not a guaranteed live feed.
- OHLCV is requested with `auto_adjust=True`; the displayed price is an adjusted historical close, not an executable quote.
- Current company fundamentals are not point-in-time.
- Fundamental targets annualize one quarter and may be distorted by seasonality or one-off items. They are not forecasts.
- Magic Line selection is evidence-based but not predictive; a line that supported price historically can fail in the future.
- Entry planning does not yet use earnings announcement timing, gap support or reversal-candle confirmation.
- The backtest is a single-symbol weekly approximation, not a survivorship-free portfolio simulation.
- No insider-buying signal, broker execution, paper-trading portfolio, alert engine or guaranteed profitability is provided.
- Microcap liquidity, spreads, corporate actions, delistings and survivorship bias require further treatment before live use.

## Mac setup
```bash
cd ~/Downloads/SuperstockEdge_0_2_0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
streamlit run app.py
```

## Configuration
Edit `config/settings.yaml` to change:

- minimum history
- base minimum/maximum length and maximum range
- quiet volume / ATR thresholds
- Magic Line candidates, qualification thresholds, test tolerance, recovery window and breakdown buffer
- entry-zone width, maximum entry distance, swing lookback, stop buffer and P/E scenarios
- extension / parabolic warning thresholds

Magic Line settings:

```yaml
magic_line:
  auto_select: true
  forced_method: null          # e.g. "10W EMA" to override automatic selection
  candidates: ["10W SMA", "10W EMA", "20W SMA", "20W EMA"]
  min_tests: 3
  min_resolved_tests: 2
  min_successes: 1
  min_defined_bars: 30
  test_tolerance_pct: 2.5
  test_close_tolerance_pct: 1.5
  min_separation_weeks: 4
  recovery_window_weeks: 4
  recovery_threshold_pct: 3.0
  breakdown_buffer_pct: 2.0
```

Entry-plan settings:

```yaml
entry:
  zone_width_pct: 2.5
  max_entry_distance_pct: 8.0
  swing_lookback_weeks: 8
  atr_stop_multiple: 2.0
  min_stop_atr: 0.75
  stop_buffer_atr: 0.25
  min_stop_pct: 1.0
  max_stop_pct: 12.0
  pe_scenarios:
    conservative: 12
    base: 20
    optimistic: 30
```

Symbols are edited in `storage/watchlist.txt`.

## Classification
- **Exit Warning:** elevated technical exit-risk score
- **Extended:** price exceeds the configured extension threshold
- **Ready to Buy:** quiet-entry criteria are all satisfied
- **Building Base:** a valid base is detected
- **Superstock Discovery:** fundamental merit and trend criteria are present
- **Watchlist / Developing:** does not currently meet the above states

A classification is a rules-based research label, not a buy/sell recommendation.

## Project structure
- `data/market_data.py`: price and fundamentals adapters
- `engine/technicals.py`: weekly bars, base/MA/volume/quiet-entry/exit analysis
- `engine/magic_line.py`: candidate evaluation, support-test scoring and selection
- `engine/entry_plan.py`: setup classification, entry zone, stop candidates, targets and reward/risk
- `engine/backtest.py`: weekly single-symbol test harness
- `engine/fundamentals.py`: quarterly statement helper
- `app.py`: Streamlit interface
- `config/settings.yaml`: scanner, Magic Line, entry-plan and risk settings
- `tests/`: automated tests

## Next production milestones
1. Earnings-date-aware quiet-entry timing and gap-support confirmation.
2. Official exchange and SEC filing ingestion with source-level audit trails.
3. Point-in-time quarterly fundamentals and historical earnings release timestamps.
4. Complete Form 4 and Indian insider disclosure classification.
5. Historical constituent and delisted-stock universe.
6. Portfolio-level event-driven backtesting with market-specific transaction costs and liquidity constraints.
7. Robust corporate-action and symbol-history handling.
8. Independent validation of strategy parameters and walk-forward results.
