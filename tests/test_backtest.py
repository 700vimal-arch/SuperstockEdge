import numpy as np
import pandas as pd
from engine.backtest import run_backtest


def test_backtest_handles_insufficient_history():
    idx = pd.date_range("2022-01-07", periods=20, freq="W-FRI")
    df = pd.DataFrame({"Open": 10, "High": 11, "Low": 9, "Close": 10, "Volume": 1000}, index=idx)
    assert "error" in run_backtest(df)["metrics"]


def test_backtest_result_schema():
    idx = pd.date_range("2018-01-05", periods=100, freq="W-FRI")
    close = np.linspace(10, 30, 100)
    df = pd.DataFrame({"Open": close*.99, "High": close*1.02, "Low": close*.98,
                       "Close": close, "Volume": 10000}, index=idx)
    result = run_backtest(df)
    assert "total_return_pct" in result["metrics"]
    assert isinstance(result["trades"], pd.DataFrame)
    assert "note" in result["metrics"]
