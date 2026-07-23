"""
Global / US-market feeds with caching and India VIX as a first-class signal.
"""
import pytz

from config import TICKERS
from data.cache import get_or_fetch
from data.last_good import save as lg_save, load as lg_load


CACHE_KEY = "us_market_summary"
CACHE_TTL = 600
SOURCE_NAME = "us_market_summary"


def get_market_data(ticker_key, period='5d'):
    import yfinance as yf  # lazy: offline callers fall back to last-good cache
    ticker_symbol = TICKERS.get(ticker_key)
    if not ticker_symbol:
        return None
    try:
        df = yf.Ticker(ticker_symbol).history(period=period)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def _live_us():
    summary = {}
    for key in ['SP500', 'NASDAQ', 'VIX', 'DXY', 'BRENT', 'USDINR', 'INDIAVIX']:
        if key not in TICKERS:
            continue
        df = get_market_data(key)
        if df is None or len(df) < 2:
            continue
        last = float(df['Close'].iloc[-1])
        prev = float(df['Close'].iloc[-2])
        chg = ((last - prev) / prev) * 100 if prev else 0
        summary[key] = {
            'price': round(last, 4),
            'change_pct': round(chg, 4),
            'status': 'Bullish' if chg > 0 else 'Bearish',
        }
    return summary


def get_us_market_summary():
    """Returns dict of US/global signals, or {} on failure."""
    value, stale = get_or_fetch(CACHE_KEY, CACHE_TTL, _live_us)
    if value and not stale:
        lg_save(SOURCE_NAME, value)
    if value is None:
        last, age = lg_load(SOURCE_NAME)
        if last is not None:
            return last
        return {}
    return value


def get_commodity_summary():
    """Legacy interface preserved for any callers."""
    us = get_us_market_summary()
    return {k: v for k, v in us.items() if k in ('DXY', 'BRENT', 'USDINR')}


if __name__ == "__main__":
    print("US Market Summary:")
    s = get_us_market_summary()
    for k, v in s.items():
        print(f"  {k}: {v}")
