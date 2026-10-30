# Superstock Edge 0.4.0

A free-first, research-only stock discovery scanner inspired by the Superstocks methodology. Version 0.4.0 scans real index universes instead of a hand-typed watchlist and rebuilds the interface around that workflow.

- Repository: <https://github.com/700vimal-arch/SuperstockEdge>
- Stack: Python, Streamlit, pandas, Plotly, yfinance
- No API keys, accounts or paid data subscriptions required

> Research prototype only. Yahoo Finance is best-effort and may be delayed, incomplete or unavailable. This app does not provide investment advice or broker execution.

## What it does

- Scans NIFTY 500, S&P 500 and NASDAQ-100 constituents, or your own watchlist, for weekly trend, variable-length bases, relative volume and volatility contraction
- Selects a Magic Line per stock from several candidate weekly averages instead of a hard-coded one
- Produces an entry zone, a structural stop with cited candidates, technical and fundamental targets, and reward/risk bands
- Scores candidates on separate fundamental, technical and entry dimensions
- Backtests one symbol on completed weekly bars

## Requirements

- Python 3.10 or newer (the reference environment uses 3.14)
- Internet access on first run so prices and fundamentals can be downloaded
- macOS, Linux or Windows; no `brew` or `gh` needed

## Quick start

### 1. Get the code

```bash
git clone https://github.com/700vimal-arch/SuperstockEdge.git
cd SuperstockEdge
```

If you already have the working folder, use it instead: `cd ~/Downloads/SuperstockEdge_0_2_0`.

### 2. Create an isolated environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Verify the install

```bash
python -m pytest -q
```

Expected: `39 passed`. If tests are not run, do not treat the environment as verified.

### 5. Run the app

```bash
streamlit run app.py
```

Open <http://localhost:8501>. On macOS you can also use the bundled launcher, which creates the environment, installs requirements and starts the app:

```bash
./launch_mac.command
```

If macOS blocks the script, run `chmod +x launch_mac.command` once, or launch it with right-click → Open.

## Using the app

Pick a universe in the sidebar first. The **Symbols per scan** control caps how many constituents are sampled (evenly across the list) so a 500-name index stays practical; choose **All** to scan everything.

| Workspace | Purpose |
| --- | --- |
| Market overview | Run a scan and see coverage, actionable setup cards, classification mix and score leaders |
| Discovery scanner | Filter the last scan by search, score, classification and actionability, with CSV export |
| Magic Line lab | Candidate comparison, selected line, rationale and historical support tests |
| Stock analysis | Weekly chart, trade plan, fundamentals and raw data for one symbol |
| Backtesting lab | Single-symbol weekly research approximation |
| Watchlist & data | Custom watchlist, constituent snapshots, cache clearing and data notes |

A scan works in two phases: every symbol gets the price-only technical pass, then fundamentals are fetched only for the top 25 by opportunity score. The first run downloads one CSV per symbol and can take a while; later runs read the cache. Tick **Refresh prices from provider** in the sidebar to bypass the cache, press **Refresh constituents** to re-pull the index list, or clear prices from **Watchlist & data**.

## Universes

| Universe | Source | Symbols |
| --- | --- | --- |
| NIFTY 500 | Wikipedia NIFTY 500 constituent table | 500, with the `.NS` suffix |
| S&P 500 | Wikipedia S&P 500 constituent table | ~503, with `.` rewritten to `-` for Yahoo (`BRK.B` → `BRK-B`) |
| NASDAQ-100 | Wikipedia NASDAQ-100 constituent table | ~101 |
| Custom watchlist | `storage/watchlist.txt` | whatever is on the file |

Constituent lists are cached for `universe.cache_ttl_days` (default 7) under `storage/cache/universe/`. If the network fails, the saved snapshot is used and labelled `stale_cache`; if there is no snapshot, the app reports the error instead of guessing. The **Market filter** still narrows a mixed list to Indian or US tickers. Index membership is current, not point-in-time, so historical backtests remain approximate.

## Configuration

All tunables live in `config/settings.yaml`:

- universe caching, scan cap and download batching
- watchlist defaults per market
- minimum history, base length and base range
- quiet-entry volume / ATR thresholds
- Magic Line candidates, qualification thresholds, tolerances and breakdown buffer
- entry-zone width, maximum entry distance, swing lookback, stop buffer and P/E scenarios
- extension and parabolic warning thresholds
- risk and backtest defaults

The live symbol list is `storage/watchlist.txt` (created from the config defaults on first run). One symbol per line; `#` starts a comment. Indian symbols need the `.NS` or `.BO` suffix, US symbols use the plain ticker.

Universe settings:

```yaml
universe:
  cache_ttl_days: 7       # constituent snapshot lifetime
  max_scan_symbols: 500   # intended ceiling for a scan
  batch_size: 50          # symbols per batched price download
  fundamentals_top_n: 25  # fundamentals are fetched only for this many leaders
```

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

## Magic Line laboratory

The scanner no longer uses a single hard-coded moving average. For each stock it evaluates candidate weekly averages and selects the one with the strongest evidence of historical support:

- meaningful pullback tests where price touched the line while still closing near it
- resolved tests that recovered versus tests that failed
- average bounce magnitude and average recovery time
- maximum weekly closing deviation below the line
- confirmed weekly closing breakdown episodes
- percentage of weeks closing above the line

The evaluation runs as of the last completed weekly bar. A test only receives an outcome when the outcome window is already inside the supplied history, so the current week's test stays `open` and never contributes to the success rate. This keeps selection reproducible without future information.

A candidate must clear minimum tests, resolved outcomes and successful bounces before it can be selected. If none qualifies, the app reports **"No reliable Magic Line identified"** rather than inventing one. The comparison table, rationale and historical test list are in the **Magic Line lab** workspace.

The selected line can change as new completed weeks arrive. That is intentional: the selection uses only the information available at each evaluation date.

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
- **Fundamental targets:** annualized latest-quarter EPS × conservative/base/optimistic P/E scenarios. Hidden when EPS is missing or non-positive.
- **Reward/risk:** potential reward divided by defined risk, flagged as Below 2R, 2R–3R, 3R–5R or Above 5R.

Fundamental and technical targets are shown separately. The primary target is the most conservative target above entry that provides at least 1R.

## Data and caching

- Prices come from Yahoo Finance with `auto_adjust=True`; the displayed price is an adjusted historical close, not an executable quote.
- Symbols without a cache are downloaded in batches (`batch_size`) with `yf.download`, then retried one by one if the batch misses them.
- Each download is cached as CSV in `storage/cache/`, keyed by symbol, period and interval.
- Index constituents are snapshotted as JSON in `storage/cache/universe/` and fall back to the last snapshot when the source is unreachable.
- Streamlit caches loaded frames for a few hours in-process.
- The cache is disposable: delete the folder, use **Watchlist & data**, or tick **Refresh prices from provider**.
- Fundamentals are a best-effort snapshot and are not point-in-time.

## Troubleshooting

**`streamlit: command not found` or `ModuleNotFoundError`**
The virtual environment is not active. Re-run `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\Activate.ps1` (Windows) from the project root.

**A symbol returns no data**
Check the ticker and suffix: `RELIANCE.NS` for India, `AAPL` for the US. Delisted, renamed or thinly traded symbols may be missing. Try a shorter period (`2y`) or a different symbol.

**Yahoo Finance errors, timeouts or empty scans**
Free endpoints rate-limit and occasionally fail. Wait a few minutes, retry with fewer symbols, and avoid ticking **Refresh prices from provider** repeatedly. Cached symbols keep working while the provider is unavailable.

**Universe is empty or says `error`**
The constituent list is pulled from a public index page. Check the internet connection, press **Refresh constituents**, and confirm the table layout on the source page has not changed. A previously saved snapshot keeps working offline; clear `storage/cache/universe/` only if you want to force a fresh pull.

**A large scan is slow**
The first pass downloads history for every uncached symbol. Reduce **Symbols per scan**, reuse the cache, or keep `batch_size` at 50 unless the provider is stable.

**SSL certificate errors on macOS**
Install the Python certificate bundle, then retry:

```bash
/Applications/Python\ 3.*/Install\ Certificates.command
python -m pip install --upgrade certifi
```

**Port 8501 already in use**

```bash
streamlit run app.py --server.port 8502
```

**"No reliable Magic Line identified"**
This is an evidence gate, not a crash: the candidate averages did not have enough resolved, successful support tests. Lower `min_tests` / `min_resolved_tests` only if you accept weaker evidence.

**Fundamental fields are blank**
Yahoo does not publish every field for every listing, especially smaller Indian companies. Missing values are reported as missing rather than assumed.

**Browser page is blank after an update**
Stop the app, clear the cache from **Watchlist & data**, and restart Streamlit.

## Tests

```bash
python -m pytest -q          # full suite
./run_tests.sh               # activates .venv and runs the suite
```

The suite covers weekly aggregation, structural analysis, Magic Line selection and as-of behaviour, entry-plan construction, scoring, the backtest harness, universe loading and the batched price cache.

## Project structure

- `data/universe.py` — index constituent loaders, symbol normalisation and snapshot caching
- `data/market_data.py` — price and fundamentals adapters with CSV caching and batched downloads
- `engine/technicals.py` — weekly bars, base/MA/volume/quiet-entry/exit analysis
- `engine/magic_line.py` — candidate evaluation, support-test scoring and selection
- `engine/entry_plan.py` — setup classification, entry zone, stop candidates, targets and reward/risk
- `engine/backtest.py` — weekly single-symbol test harness
- `engine/fundamentals.py` — quarterly statement helper
- `ui/theme.py` — design tokens, global CSS and HTML building blocks
- `ui/charts.py` — Plotly weekly, Magic Line, equity and distribution charts
- `app.py` — Streamlit interface
- `config/settings.yaml` — universe, scanner, Magic Line, entry-plan, risk and backtest settings
- `storage/` — watchlist and downloaded price/constituent cache (not tracked)
- `tests/` — automated tests

## Limitations

- Yahoo Finance is best-effort and not a guaranteed live feed.
- Index membership is current, not point-in-time; the S&P 500 and NASDAQ-100 lists are US-only and the NIFTY 500 list depends on a public wiki table. Constituent pages can change format, and a scan samples the list rather than covering it exhaustively unless **All** is selected.
- OHLCV is requested with `auto_adjust=True`; the displayed price is an adjusted historical close, not an executable quote.
- Current company fundamentals are not point-in-time.
- Fundamental targets annualize one quarter and may be distorted by seasonality or one-off items. They are not forecasts.
- Magic Line selection is evidence-based but not predictive; a line that supported price historically can fail in the future.
- Entry planning does not yet use earnings announcement timing, gap support or reversal-candle confirmation.
- The backtest is a single-symbol weekly approximation, not a survivorship-free portfolio simulation.
- No insider-buying signal, broker execution, paper-trading portfolio, alert engine or guaranteed profitability is provided.
- Microcap liquidity, spreads, corporate actions, delistings and survivorship bias require further treatment before live use.

## Next milestones

1. Earnings-date-aware quiet-entry timing and gap-support confirmation.
2. Official exchange and SEC filing ingestion with source-level audit trails.
3. Point-in-time quarterly fundamentals and historical earnings release timestamps.
4. Complete Form 4 and Indian insider disclosure classification.
5. Historical constituent and delisted-stock universe.
6. Portfolio-level event-driven backtesting with market-specific transaction costs and liquidity constraints.
7. Robust corporate-action and symbol-history handling.
8. Independent validation of strategy parameters and walk-forward results.

## Classification reference

- **Exit Warning:** elevated technical exit-risk score
- **Extended:** price exceeds the configured extension threshold
- **Ready to Buy:** quiet-entry criteria are all satisfied
- **Building Base:** a valid base is detected
- **Superstock Discovery:** fundamental merit and trend criteria are present
- **Watchlist / Developing:** does not currently meet the above states

A classification is a rules-based research label, not a buy/sell recommendation.
