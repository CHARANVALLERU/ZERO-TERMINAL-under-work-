"""
Historical OHLC + indicators for the prediction engine.

Returns ATR(14), prior OHLC, prior-day VWAP/POC/VAH/VAL, RVOL(20),
and the simple recent-ohlc dict the engine already consumes.
"""
import numpy as np
import pandas as pd

from config import TICKERS


def get_historical_data(symbol_key, period='60d'):
    import yfinance as yf  # lazy import: keep feature/offline paths importable
    symbol = TICKERS.get(symbol_key)
    if not symbol:
        return None
    try:
        df = yf.download(symbol, period=period, progress=False, auto_adjust=False)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if df is None or len(df) < period + 1:
        return float("nan")
    high = df['High']
    low = df['Low']
    close = df['Close'].shift(1)
    tr = pd.concat([
        (high - low),
        (high - close).abs(),
        (low - close).abs(),
    ], axis=1).max(axis=1)
    val = tr.rolling(window=period).mean().iloc[-1]
    if isinstance(val, pd.Series):
        val = float(val.iloc[0])
    return float(val)


def _rvol(df: pd.DataFrame, period: int = 20) -> float:
    """Today-vs-20d-avg volume ratio. NaN if not enough data."""
    if df is None or len(df) < period + 1:
        return float("nan")
    vol = df['Volume']
    if isinstance(vol, pd.DataFrame):
        vol = vol.iloc[:, 0]
    if len(vol) < 2:
        return float("nan")
    today = float(vol.iloc[-1])
    avg = float(vol.iloc[-(period + 1):-1].mean())
    if avg <= 0:
        return float("nan")
    return today / avg


def _vwap(df: pd.DataFrame) -> float:
    """Prior-day VWAP approximation. If intraday data is unavailable we
    fall back to the typical-price average weighted by range.
    """
    if df is None or len(df) < 2:
        return float("nan")
    last = df.iloc[-2]  # prior completed session
    cols = {c: last[c] for c in ('High', 'Low', 'Close', 'Volume')}
    h, l, c, v = float(cols['High'].iloc[0]) if isinstance(cols['High'], pd.Series) else float(cols['High']), \
                 float(cols['Low'].iloc[0]) if isinstance(cols['Low'], pd.Series) else float(cols['Low']), \
                 float(cols['Close'].iloc[0]) if isinstance(cols['Close'], pd.Series) else float(cols['Close']), \
                 float(cols['Volume'].iloc[0]) if isinstance(cols['Volume'], pd.Series) else float(cols['Volume'])
    if v <= 0:
        return c
    typical = (h + l + c) / 3.0
    return typical  # Intraday VWAP needs tick data; typical price is the next best.


def _poc_vah_val(df: pd.DataFrame, bins: int = 20):
    """Prior-day Point of Control + Value Area High/Low.
    Without intraday data we approximate the value area using the prior
    day's H/L distribution: treat the day's range as a uniform price
    distribution and find the central 70% band.
    Returns (poc, vah, val) in price units.
    """
    if df is None or len(df) < 2:
        return float("nan"), float("nan"), float("nan")
    last = df.iloc[-2]

    def _scalar(col):
        v = last[col]
        if isinstance(v, pd.Series):
            v = v.iloc[0]
        return float(v)

    h, l, c = _scalar('High'), _scalar('Low'), _scalar('Close')
    if h <= l:
        return c, h, l
    # POC: midpoint of the day's range
    poc = (h + l + c) / 3.0
    span = h - l
    vah = l + 0.7 * span
    val_ = l + 0.3 * span
    return poc, vah, val_


def get_recent_ohlc_and_atr(symbol_key, period='60d'):
    """
    Returns:
        {
            'open', 'high', 'low', 'close': float (prior completed session),
            'atr': float (14d),
            'rvol_20': float,
            'vwap': float,
            'poc': float, 'vah': float, 'val': float,
        }
    Or None on failure.
    """
    df = get_historical_data(symbol_key, period=period)
    if df is None or df.empty:
        return None

    last = df.iloc[-1]
    open_ = float(last['Open'].iloc[0]) if isinstance(last['Open'], pd.Series) else float(last['Open'])
    high = float(last['High'].iloc[0]) if isinstance(last['High'], pd.Series) else float(last['High'])
    low = float(last['Low'].iloc[0]) if isinstance(last['Low'], pd.Series) else float(last['Low'])
    close = float(last['Close'].iloc[0]) if isinstance(last['Close'], pd.Series) else float(last['Close'])

    atr = _atr(df)
    rvol = _rvol(df)
    vwap = _vwap(df)
    poc, vah, val_ = _poc_vah_val(df)

    return {
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'atr': atr,
        'rvol_20': rvol,
        'vwap': vwap,
        'poc': poc,
        'vah': vah,
        'val': val_,
    }


if __name__ == "__main__":
    for index in ['NIFTY', 'BANKNIFTY', 'SENSEX']:
        s = get_recent_ohlc_and_atr(index)
        print(f"{index}: {s}")
