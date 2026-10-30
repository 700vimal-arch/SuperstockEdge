# Superstock Edge 0.2.0

A free-first, research-only stock discovery scanner inspired by the Superstocks methodology.

## Included
- India and US watchlist scanning
- Weekly trend, variable-length base, relative volume and volatility contraction
- Configurable Magic Line (10-week EMA by default; 10-week SMA or 20-week SMA selectable in YAML)
- Quiet-entry qualification requires a valid base, proximity to Magic Line, low relative volume and volatility contraction
- Separate fundamental, technical and entry scores
- Fundamental data coverage distinguishes passed, failed and missing checks
- Stock analysis, watchlist, CSV export and single-symbol weekly backtesting

## Important limitations
- Yahoo Finance is best-effort and not a guaranteed live feed.
- OHLCV is requested with `auto_adjust=True`; the displayed price is an adjusted historical close, not an executable quote.
- Current company fundamentals are not point-in-time. They must not be used to claim historical information availability.
- The backtest is a single-symbol weekly approximation, not a survivorship-free portfolio simulation.
- No insider-buying signal, broker execution, or guaranteed profitability is provided.
- Microcap liquidity, spreads, corporate actions, delistings and survivorship bias require further treatment before live use.

## Mac setup
```bash
cd ~/Downloads
unzip SuperstockEdge_0.2.0.zip
cd SuperstockEdge_0_2_0
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
- Magic Line method
- quiet volume / ATR thresholds
- Magic Line proximity and breakdown buffer
- extension / parabolic warning thresholds

Symbols are edited in `storage/watchlist.txt`.

## Classification
- **Exit Warning:** elevated technical exit-risk score
- **Extended:** price exceeds the configured extension threshold
- **Ready to Buy:** quiet-entry criteria are all satisfied
- **Building Base:** a valid base is detected
- **Superstock Discovery:** fundamental merit and trend criteria are present
- **Watchlist / Developing:** does not currently meet the above states

A classification is a rules-based research label, not a buy/sell recommendation.
