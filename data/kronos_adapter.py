"""
Kronos adapter: bridges ZERO market data into Kronos K-line inputs.

Kronos (github.com/shiyu-coder/Kronos, MIT) predicts future candlesticks from
a DataFrame with columns ['open','high','low','close','volume','amount'] plus
two pandas Series of bar timestamps: `x_timestamp` (history) and `y_timestamp`
(future bar times). Max context is 512 bars. This module produces exactly that
input shape from ZERO's own data layer / yfinance.

Conventions (ZERO house style):
- Every public function is non-raising: failures return an empty
  DataFrame/Series (or an {'error': ...} dict for prepare_kronos_inputs).
- yfinance is imported lazily so offline/feature paths stay importable.
- ZERO's market calendar (config.is_trading_day / NSE_HOLIDAYS / market hours)
  is reused when importable; otherwise we degrade to weekend-skip only.

Timezone policy (all outputs are timezone-naive pandas datetimes):
- Indian market instruments (^NSEI, ^NSEBANK, ^BSESN, *.NS, *.BO):
  tz-aware stamps are converted to Asia/Kolkata, then the tz is dropped.
- Everything else (crypto, gold futures, FX): converted to UTC, tz dropped.
- Daily bars from Yahoo/ZERO arrive as naive session dates and pass through.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger("ZERO_KRONOS_ADAPTER")

# ── Reuse ZERO's market calendar when available ───────────────────────────
try:  # config.py lives at the ZERO project root
    from config import (
        NSE_HOLIDAYS as _NSE_HOLIDAYS,
        is_trading_day as _zero_is_trading_day,
        MARKET_OPEN as _MARKET_OPEN,
        MARKET_CLOSE as _MARKET_CLOSE,
    )
    _HAS_ZERO_CALENDAR = True
except Exception:  # graceful degradation: weekend-skip only
    _NSE_HOLIDAYS = frozenset()
    _zero_is_trading_day = None
    _MARKET_OPEN = dt_time(9, 15)
    _MARKET_CLOSE = dt_time(15, 30)
    _HAS_ZERO_CALENDAR = False

# ── Public constants ──────────────────────────────────────────────────────
MAX_CONTEXT = 512       # Kronos hard limit on history bars
MIN_BARS = 32           # below this a prediction is meaningless
DEFAULT_LOOKBACK = 400  # matches Kronos examples/prediction_example.py

# Display name -> yfinance ticker.
SUPPORTED_SYMBOLS: Dict[str, str] = {
    'NIFTY 50': '^NSEI',
    'BANKNIFTY': '^NSEBANK',
    'SENSEX': '^BSESN',
    'RELIANCE.NS': 'RELIANCE.NS',
    'TCS.NS': 'TCS.NS',
    'HDFCBANK.NS': 'HDFCBANK.NS',
    'USDINR=X': 'USDINR=X',
    'GOLD (GC=F)': 'GC=F',
    'BTC-USD': 'BTC-USD',
    'ETH-USD': 'ETH-USD',
}

# Interval key -> fetch/resample metadata.
# max_lookback_days reflects Yahoo Finance retention limits per interval.
SUPPORTED_INTERVALS: Dict[str, Dict] = {
    '5m':  {'yf': '5m',  'pandas_freq': '5min',  'intraday': True,  'max_lookback_days': 59},
    '15m': {'yf': '15m', 'pandas_freq': '15min', 'intraday': True,  'max_lookback_days': 59},
    '30m': {'yf': '30m', 'pandas_freq': '30min', 'intraday': True,  'max_lookback_days': 59},
    '60m': {'yf': '60m', 'pandas_freq': '60min', 'intraday': True,  'max_lookback_days': 729},
    '1d':  {'yf': '1d',  'pandas_freq': '1D',    'intraday': False, 'max_lookback_days': 3650},
}

_KLINE_COLS = ['timestamps', 'open', 'high', 'low', 'close', 'volume', 'amount']
_OHLC_COLS = ['open', 'high', 'low', 'close']

# yfinance ticker -> key understood by ZERO's data.historical provider (daily only).
_ZERO_KEY_BY_TICKER = {
    '^NSEI': 'NIFTY',
    '^NSEBANK': 'BANKNIFTY',
    '^BSESN': 'SENSEX',
    'USDINR=X': 'USDINR',
}

_INDIAN_INDEX_TICKERS = {'^NSEI', '^NSEBANK', '^BSESN', '^INDIAVIX'}

__all__ = [
    'SUPPORTED_SYMBOLS', 'SUPPORTED_INTERVALS',
    'MAX_CONTEXT', 'MIN_BARS', 'DEFAULT_LOOKBACK',
    'fetch_kline_history', 'make_future_timestamps',
    'prepare_kronos_inputs', 'resample_kline',
]


# ── Small helpers ─────────────────────────────────────────────────────────
def _empty_kline() -> pd.DataFrame:
    """Empty result frame with the canonical Kronos K-line schema."""
    return pd.DataFrame({
        'timestamps': pd.Series([], dtype='datetime64[ns]'),
        'open': pd.Series([], dtype=float),
        'high': pd.Series([], dtype=float),
        'low': pd.Series([], dtype=float),
        'close': pd.Series([], dtype=float),
        'volume': pd.Series([], dtype=float),
        'amount': pd.Series([], dtype=float),
    })


def _empty_ts_series() -> pd.Series:
    return pd.Series(pd.DatetimeIndex([]), name='timestamps')


def _resolve_ticker(symbol: str) -> str:
    """Map a display name to its yfinance ticker; pass raw tickers through."""
    if not symbol:
        return ''
    sym = str(symbol).strip()
    for name, ticker in SUPPORTED_SYMBOLS.items():
        if sym.upper() == name.upper():
            return ticker
    if sym in SUPPORTED_SYMBOLS.values():
        return sym
    return sym  # assume caller passed a raw yfinance ticker


def _is_indian_market(ticker: str) -> bool:
    """NSE/BSE session instruments: 09:15-15:30 IST, NSE holiday calendar."""
    t = (ticker or '').upper()
    return t in _INDIAN_INDEX_TICKERS or t.endswith('.NS') or t.endswith('.BO')


def _is_crypto(ticker: str) -> bool:
    """Yahoo crypto pairs (BTC-USD, ETH-USD, ...): 24/7 continuous trading."""
    return (ticker or '').upper().endswith('-USD')


def _is_nse_trading_day(day) -> bool:
    """Mon-Fri and not an NSE holiday. Reuses config.is_trading_day if present."""
    if _zero_is_trading_day is not None:
        try:
            return bool(_zero_is_trading_day(day))
        except Exception:
            pass
    if day.weekday() >= 5:
        return False
    return day.strftime('%Y-%m-%d') not in _NSE_HOLIDAYS


def _interval_minutes(spec: Dict) -> int:
    return max(1, int(pd.Timedelta(spec['pandas_freq']).total_seconds() // 60))


def _nse_session_slots(day, step_minutes: int) -> list:
    """Bar-start times for one NSE session: 09:15 <= t < 15:30 IST."""
    slots = []
    t = datetime.combine(day, _MARKET_OPEN)
    end = datetime.combine(day, _MARKET_CLOSE)
    while t < end:
        slots.append(pd.Timestamp(t))
        t += timedelta(minutes=step_minutes)
    return slots


def _to_naive_index(idx: pd.DatetimeIndex, ticker: str) -> pd.DatetimeIndex:
    """Apply the module timezone policy to a DatetimeIndex."""
    if getattr(idx, 'tz', None) is not None:
        target = 'Asia/Kolkata' if _is_indian_market(ticker) else 'UTC'
        idx = idx.tz_convert(target).tz_localize(None)
    return idx


def _to_naive_series(s: pd.Series, ticker: str) -> pd.Series:
    s = pd.to_datetime(s, errors='coerce')
    try:
        if getattr(s.dt, 'tz', None) is not None:
            target = 'Asia/Kolkata' if _is_indian_market(ticker) else 'UTC'
            s = s.dt.tz_convert(target).dt.tz_localize(None)
    except Exception:
        pass
    return s


def _normalize_ohlcv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Normalize a yfinance-style frame into the canonical K-line schema.

    Handles MultiIndex columns, mixed-case names, tz-aware indexes, missing
    volume/amount, NaN rows and duplicate/unsorted timestamps.
    """
    if raw is None or raw.empty:
        return _empty_kline()

    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep='first')]

    if not all(c in df.columns for c in _OHLC_COLS):
        logger.debug("normalize: missing OHLC columns, have %s", list(df.columns))
        return _empty_kline()

    # Timestamps: prefer the index; fall back to a timestamps/date column.
    if isinstance(df.index, pd.DatetimeIndex):
        stamps = pd.Series(_to_naive_index(df.index, ticker))
    else:
        col = next((c for c in ('timestamps', 'timestamp', 'date', 'datetime') if c in df.columns), None)
        if col is None:
            return _empty_kline()
        stamps = _to_naive_series(df[col], ticker)

    out = pd.DataFrame({
        'timestamps': stamps.values,
        'open': pd.to_numeric(df['open'], errors='coerce').values,
        'high': pd.to_numeric(df['high'], errors='coerce').values,
        'low': pd.to_numeric(df['low'], errors='coerce').values,
        'close': pd.to_numeric(df['close'], errors='coerce').values,
    })
    if 'volume' in df.columns:
        out['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0.0).values
    else:
        out['volume'] = 0.0
    if 'amount' in df.columns and pd.to_numeric(df['amount'], errors='coerce').notna().any():
        out['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0.0).values
    else:
        out['amount'] = out['close'] * out['volume']  # turnover proxy

    out = out.dropna(subset=['timestamps'] + _OHLC_COLS)
    out = out.sort_values('timestamps')
    out = out.drop_duplicates(subset='timestamps', keep='last').reset_index(drop=True)
    return out[_KLINE_COLS]


def _estimate_fetch_days(spec: Dict, lookback: int, ticker: str) -> int:
    """Calendar days to request from Yahoo so ~lookback bars survive gaps."""
    if not spec['intraday']:
        days = int(lookback * 1.6) + 10  # weekends + holidays headroom
    else:
        minutes = _interval_minutes(spec)
        session_minutes = 375 if _is_indian_market(ticker) else 1440
        bars_per_day = max(1.0, session_minutes / minutes)
        days = math.ceil(lookback / bars_per_day * 1.7) + 3
    return max(2, min(days, int(spec['max_lookback_days'])))


def _fetch_from_zero_provider(ticker: str, lookback: int) -> Optional[pd.DataFrame]:
    """Daily bars via ZERO's own data.historical provider (index/FX keys only)."""
    key = _ZERO_KEY_BY_TICKER.get(ticker)
    if not key:
        return None
    try:
        from data.historical import get_historical_data  # lazy: pulls in config
    except Exception:
        return None
    days = max(10, min(int(lookback * 1.6) + 10, 3650))
    try:
        return get_historical_data(key, period=f"{days}d")
    except Exception as e:
        logger.debug("ZERO historical provider failed for %s: %s", key, e)
        return None


def _fetch_from_yfinance(ticker: str, spec: Dict, lookback: int) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf  # lazy import: keep offline paths importable
    except Exception:
        logger.debug("yfinance not installed; cannot fetch %s", ticker)
        return None
    days = _estimate_fetch_days(spec, lookback, ticker)
    try:
        return yf.download(
            ticker,
            period=f"{days}d",
            interval=spec['yf'],
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logger.debug("yfinance download failed for %s (%s): %s", ticker, spec['yf'], e)
        return None


# ── Public API ────────────────────────────────────────────────────────────
def fetch_kline_history(symbol: str, interval: str = '1d', lookback: int = DEFAULT_LOOKBACK) -> pd.DataFrame:
    """Fetch recent K-lines for a symbol in the Kronos input schema.

    Args:
        symbol: display name from SUPPORTED_SYMBOLS or a raw yfinance ticker.
        interval: one of SUPPORTED_INTERVALS ('5m','15m','30m','60m','1d').
        lookback: number of most-recent bars to keep.

    Returns:
        DataFrame with columns ['timestamps','open','high','low','close',
        'volume','amount'], timezone-naive timestamps, RangeIndex.
        Empty DataFrame (same schema) on any failure.
    """
    try:
        spec = SUPPORTED_INTERVALS.get(interval)
        if spec is None:
            logger.debug("fetch_kline_history: unsupported interval %r", interval)
            return _empty_kline()
        try:
            lookback = max(1, int(lookback))
        except Exception:
            lookback = DEFAULT_LOOKBACK
        ticker = _resolve_ticker(symbol)
        if not ticker:
            logger.debug("fetch_kline_history: empty symbol")
            return _empty_kline()

        raw = None
        if interval == '1d':  # ZERO's own provider first (daily only)
            raw = _fetch_from_zero_provider(ticker, lookback)
        if raw is None or getattr(raw, 'empty', True):
            raw = _fetch_from_yfinance(ticker, spec, lookback)
        if raw is None or getattr(raw, 'empty', True):
            logger.debug("fetch_kline_history: no data for %s @ %s", ticker, interval)
            return _empty_kline()

        df = _normalize_ohlcv(raw, ticker)
        if df.empty:
            return _empty_kline()
        return df.tail(lookback).reset_index(drop=True)
    except Exception as e:
        logger.debug("fetch_kline_history failed for %r: %s", symbol, e)
        return _empty_kline()


def make_future_timestamps(last_ts, pred_len: int, interval: str, symbol: str = '') -> pd.Series:
    """Future bar timestamps continuing from `last_ts` (exclusive).

    Calendar rules by instrument class:
    - crypto (BTC-USD/ETH-USD): 24/7 continuous bars.
    - Indian market ('1d'): next NSE trading days (weekends + NSE_HOLIDAYS
      skipped via ZERO's config helpers when importable, else weekends only).
    - Indian market (intraday): bars stay on the 09:15-15:30 IST session grid
      and roll to the next trading day when the session ends.
    - other symbols: '1d' skips weekends; intraday is continuous.

    Returns a tz-naive pd.Series named 'timestamps' (empty Series on failure).
    """
    try:
        spec = SUPPORTED_INTERVALS.get(interval)
        pred_len = int(pred_len)
        if spec is None or pred_len <= 0:
            return _empty_ts_series()
        ts = pd.Timestamp(last_ts)
        if pd.isna(ts):
            return _empty_ts_series()
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        ticker = _resolve_ticker(symbol)

        if not spec['intraday']:
            out = []
            cur_date, t_of_day = ts.date(), ts.time()
            for _ in range(pred_len):
                cur_date += timedelta(days=1)
                guard = 0
                while guard < 30:
                    if _is_crypto(ticker):
                        break  # 24/7: every calendar day is a bar
                    if _is_indian_market(ticker):
                        if _is_nse_trading_day(cur_date):
                            break
                    elif cur_date.weekday() < 5:  # non-Indian non-crypto: weekend-skip
                        break
                    cur_date += timedelta(days=1)
                    guard += 1
                out.append(pd.Timestamp(datetime.combine(cur_date, t_of_day)))
            return pd.Series(pd.DatetimeIndex(out), name='timestamps')

        # Intraday
        step_minutes = _interval_minutes(spec)
        if not _is_indian_market(ticker):
            step = pd.Timedelta(minutes=step_minutes)
            rng = pd.date_range(start=ts + step, periods=pred_len, freq=step)
            return pd.Series(rng, name='timestamps')

        # Indian intraday: walk the NSE session grid, rolling across sessions.
        out = []
        day = ts.date()
        pending = [s for s in _nse_session_slots(day, step_minutes) if s > ts] \
            if _is_nse_trading_day(day) else []
        guard = 0
        while len(out) < pred_len and guard < 4000:
            if not pending:
                day += timedelta(days=1)
                guard += 1
                if _is_nse_trading_day(day):
                    pending = _nse_session_slots(day, step_minutes)
                continue
            take = min(len(pending), pred_len - len(out))
            out.extend(pending[:take])
            pending = []
        return pd.Series(pd.DatetimeIndex(out), name='timestamps')
    except Exception as e:
        logger.debug("make_future_timestamps failed (%r, %r): %s", interval, symbol, e)
        return _empty_ts_series()


def prepare_kronos_inputs(df: pd.DataFrame, lookback: int, pred_len: int,
                          interval: str = '1d', symbol: str = '') -> Dict:
    """Package a K-line DataFrame into the exact inputs KronosPredictor.predict expects.

    Args:
        df: frame from fetch_kline_history (or any frame with 'timestamps' +
            OHLC columns; volume/amount are synthesized if missing).
        lookback: desired history bars (capped at MAX_CONTEXT=512 and len(df)).
        pred_len: number of future bars to forecast.
        interval / symbol: forwarded to make_future_timestamps.

    Returns:
        {'x_df': DataFrame[open,high,low,close,volume,amount],
         'x_timestamp': pd.Series, 'y_timestamp': pd.Series,
         'meta': {symbol, interval, bars, first_ts, last_ts}}
        or {'error': message} when inputs are unusable (<32 bars, bad args...).
    """
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return {'error': 'no historical data available'}
        if interval not in SUPPORTED_INTERVALS:
            return {'error': f'unsupported interval: {interval!r}'}
        try:
            lookback, pred_len = int(lookback), int(pred_len)
        except Exception:
            return {'error': 'lookback and pred_len must be integers'}
        if pred_len <= 0:
            return {'error': 'pred_len must be >= 1'}

        work = df.copy()
        if 'timestamps' not in work.columns:
            if isinstance(work.index, pd.DatetimeIndex):
                work = work.reset_index()
                work = work.rename(columns={work.columns[0]: 'timestamps'})
            else:
                return {'error': "input df has no 'timestamps' column"}
        if not all(c in work.columns for c in _OHLC_COLS):
            return {'error': f'input df missing OHLC columns {_OHLC_COLS}'}

        ticker = _resolve_ticker(symbol)
        work['timestamps'] = _to_naive_series(work['timestamps'], ticker)
        for c in _OHLC_COLS:
            work[c] = pd.to_numeric(work[c], errors='coerce')
        if 'volume' not in work.columns:
            work['volume'] = 0.0
        work['volume'] = pd.to_numeric(work['volume'], errors='coerce').fillna(0.0)
        if 'amount' not in work.columns:
            work['amount'] = work['close'] * work['volume']
        work['amount'] = pd.to_numeric(work['amount'], errors='coerce').fillna(0.0)

        work = work.dropna(subset=['timestamps'] + _OHLC_COLS).sort_values('timestamps')
        work = work.drop_duplicates(subset='timestamps', keep='last').reset_index(drop=True)

        if len(work) < MIN_BARS:
            return {'error': f'insufficient data: {len(work)} bars (< {MIN_BARS} required)'}
        effective = min(max(lookback, 1), MAX_CONTEXT, len(work))
        if effective < MIN_BARS:
            return {'error': f'lookback {lookback} yields {effective} bars (< {MIN_BARS} required)'}

        tail = work.tail(effective).reset_index(drop=True)
        x_df = tail[['open', 'high', 'low', 'close', 'volume', 'amount']].astype(float)
        # Kronos needs Series (not DatetimeIndex): its featurizer uses .dt accessors.
        x_timestamp = pd.Series(pd.to_datetime(tail['timestamps']).values, name='timestamps')
        last_ts = x_timestamp.iloc[-1]
        y_timestamp = make_future_timestamps(last_ts, pred_len, interval, symbol)
        if len(y_timestamp) != pred_len:
            return {'error': f'could not build {pred_len} future timestamps for {interval!r}'}

        return {
            'x_df': x_df,
            'x_timestamp': x_timestamp,
            'y_timestamp': y_timestamp,
            'meta': {
                'symbol': symbol,
                'interval': interval,
                'bars': int(len(x_df)),
                'first_ts': x_timestamp.iloc[0],
                'last_ts': last_ts,
            },
        }
    except Exception as e:
        logger.debug("prepare_kronos_inputs failed: %s", e)
        return {'error': f'prepare_kronos_inputs failed: {e}'}


def resample_kline(df: pd.DataFrame, target_interval: str) -> pd.DataFrame:
    """Resample a K-line frame to a coarser interval (OHLCV aggregation).

    Aggregation: open=first, high=max, low=min, close=last, volume=sum,
    amount=sum. Bins are anchored at the first timestamp so intraday bars stay
    on the session grid (e.g. NSE 09:15, 09:20, ...). Empty bins are dropped.

    Returns the canonical K-line frame; empty DataFrame on failure.
    """
    try:
        spec = SUPPORTED_INTERVALS.get(target_interval)
        if spec is None or df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return _empty_kline()

        work = df.copy()
        if 'timestamps' not in work.columns:
            if isinstance(work.index, pd.DatetimeIndex):
                work = work.reset_index()
                work = work.rename(columns={work.columns[0]: 'timestamps'})
            else:
                return _empty_kline()
        if not all(c in work.columns for c in _OHLC_COLS):
            return _empty_kline()

        work['timestamps'] = _to_naive_series(work['timestamps'], '')
        work = work.dropna(subset=['timestamps']).sort_values('timestamps')
        work = work.set_index('timestamps')

        agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        for c in ('volume', 'amount'):
            if c in work.columns:
                agg[c] = 'sum'
        try:
            res = work.resample(spec['pandas_freq'], origin='start').agg(agg)
        except TypeError:  # very old pandas without origin=
            res = work.resample(spec['pandas_freq']).agg(agg)

        res = res.dropna(subset=_OHLC_COLS).reset_index()
        res = res.rename(columns={res.columns[0]: 'timestamps'})
        if 'volume' not in res.columns:
            res['volume'] = 0.0
        if 'amount' not in res.columns:
            res['amount'] = res['close'] * res['volume']
        return res[_KLINE_COLS].reset_index(drop=True)
    except Exception as e:
        logger.debug("resample_kline failed (%r): %s", target_interval, e)
        return _empty_kline()
