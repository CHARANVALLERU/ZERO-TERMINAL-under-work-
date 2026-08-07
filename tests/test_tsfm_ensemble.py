"""TSFM ensemble coverage across all ZERO index tabs."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.prediction_matrix import INDEX_HIST_KEYS
from engine.tsfm_predictor import TSFMForecaster, get_forecaster
from config import TICKERS


INDEX_KEYS = ("NIFTY", "BANKNIFTY", "SENSEX")
DISPLAY_NAMES = ("NIFTY 50", "BANKNIFTY", "SENSEX")


def _synth_ohlc(n: int = 40, seed: int = 7, start: float = 24000.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Regular business days — Chronos can infer OR accept freq=B.
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    close = start + np.cumsum(rng.normal(0, 40, size=n))
    high = close + rng.uniform(20, 80, size=n)
    low = close - rng.uniform(20, 80, size=n)
    open_ = close + rng.normal(0, 15, size=n)
    vol = rng.integers(1000, 5000, size=n)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def _gappy_indian_like(n: int = 40, seed: int = 3, start: float = 24000.0) -> pd.DataFrame:
    """Yahoo-like calendar with holiday gaps (freq inference fails without freq=B)."""
    rng = np.random.default_rng(seed)
    # Start from calendar days then drop weekends + a few mid-week holidays.
    cal = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n + 8)
    # Drop a few mid-week dates to simulate Diwali / Republic Day gaps.
    drop = {cal[5], cal[12], cal[20]}
    idx = cal.delete([cal.get_loc(d) for d in drop if d in cal])[:n]
    close = start + np.cumsum(rng.normal(0, 50, size=len(idx)))
    high = close + rng.uniform(30, 90, size=len(idx))
    low = close - rng.uniform(30, 90, size=len(idx))
    open_ = close + rng.normal(0, 20, size=len(idx))
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 0},
        index=idx,
    )


def test_index_hist_keys_cover_all_tabs():
    for name in DISPLAY_NAMES:
        assert name in INDEX_HIST_KEYS
        key = INDEX_HIST_KEYS[name]
        assert key in TICKERS
        assert TICKERS[key]  # ^NSEI / ^NSEBANK / ^BSESN


def test_normalize_accepts_yfinance_multiindex():
    raw = _synth_ohlc()
    # Simulate yfinance MultiIndex columns: (field, ticker)
    mi = pd.MultiIndex.from_product(
        [["Adj Close", "Close", "High", "Low", "Open", "Volume"], ["^NSEBANK"]]
    )
    wide = pd.DataFrame(
        {
            mi[0]: raw["Close"],
            mi[1]: raw["Close"],
            mi[2]: raw["High"],
            mi[3]: raw["Low"],
            mi[4]: raw["Open"],
            mi[5]: raw["Volume"],
        },
        index=raw.index,
    )
    norm = TSFMForecaster._normalize_hist(wide)
    assert norm is not None
    assert set(["open", "high", "low", "close"]).issubset(norm.columns)
    assert len(norm) == len(raw)


def test_gappy_calendar_chronos_freq_or_fallback(monkeypatch):
    """Holiday-gapped series must not hard-fail every index in auto mode."""
    fc = TSFMForecaster(backend="auto")
    # Prefer a cheap path: if chronos/kronos unavailable, still assert no-raise + structured result.
    df = _gappy_indian_like()
    out = fc.forecast_ohlc(df, horizon=1, covariates={"vix": 14.0})
    assert isinstance(out, dict)
    assert out.get("status") in ("forecasted", "unavailable", "error")
    if out.get("status") == "forecasted":
        assert out["close"]["p50"] is not None
        assert out.get("backend") in ("chronos2", "kronos", "timesfm")


@pytest.mark.parametrize("start,seed", [(24500.0, 1), (57000.0, 2), (78000.0, 3)])
def test_forecast_levels_near_index_scale(start, seed):
    """Each index price scale should produce a forecast near its own level."""
    fc = TSFMForecaster(backend="auto")
    df = _synth_ohlc(n=48, seed=seed, start=start)
    out = fc.forecast_ohlc(df, horizon=1)
    if out.get("status") != "forecasted":
        pytest.skip(f"no TSFM backend online: {out.get('error') or out.get('status')}")
    p50 = float(out["close"]["p50"])
    # Within 15% of last close — guards against wrong-symbol / zeroed output.
    last = float(df["Close"].iloc[-1])
    assert abs(p50 - last) / last < 0.15


def test_get_forecaster_singleton():
    a = get_forecaster()
    b = get_forecaster()
    assert a is b
