"""
yfinance provider — live quotes AND historical daily OHLC.

Thin wrapper around the existing data-layer functions:
  * data.live_index_service.fetch_yfinance_fallback  (fast_info live quote)
  * data.historical.get_historical_data              (yf.download OHLCV)

This is the universal fallback in the default registry: it is tried last
(highest priority value) but covers every index the exchange providers
cannot serve, and it is the only provider that serves historical OHLC.

No scrapers are invented here — both methods delegate to existing code,
imported lazily inside the methods to avoid circular imports and to keep
this module importable without yfinance installed.
"""

from __future__ import annotations

import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider, env_int, normalize_index_name

# Lower value = earlier in the failover chain; env-overridable.
PRIORITY = env_int("ZERO_YFINANCE_PRIORITY", 30)

# yfinance `period` buckets: data.historical.get_historical_data accepts a
# period string, so map a requested day count to the nearest valid bucket
# and trim the result back down to `days` rows.
_PERIOD_BUCKETS = (
    (5, "5d"),
    (30, "1mo"),
    (90, "3mo"),
    (180, "6mo"),
    (365, "1y"),
    (730, "2y"),
    (1825, "5y"),
)

# config.TICKERS keys are short names ("NIFTY"); accept display aliases too.
HIST_KEY_ALIASES = {
    "NIFTY 50": "NIFTY",
    "NIFTY50": "NIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
}


def _period_for_days(days: int) -> str:
    """Nearest yfinance period bucket covering at least `days` sessions."""
    for cap, period in _PERIOD_BUCKETS:
        if days <= cap:
            return period
    return "max"


def _hist_key(index_key: str) -> str:
    """Normalise an index key to the short names used by config.TICKERS."""
    key = " ".join(str(index_key).strip().upper().split())
    return HIST_KEY_ALIASES.get(key, key)


def _normalize_ohlc(df: Optional[pd.DataFrame], days: int) -> Optional[pd.DataFrame]:
    """Convert a yfinance frame (DatetimeIndex, Title-case or MultiIndex
    columns) to the canonical date/open/high/low/close[/volume] layout,
    trimmed to the most recent `days` rows. None if unusable."""
    if df is None or df.empty:
        return None
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    out.columns = [str(c).strip().lower() for c in out.columns]
    out = out.reset_index()
    # The first column is whatever the index was named (Date/Datetime/...).
    out = out.rename(columns={out.columns[0]: "date"})
    required = {"date", "open", "high", "low", "close"}
    if not required.issubset(set(out.columns)):
        return None
    keep = [c for c in ("date", "open", "high", "low", "close", "volume") if c in out.columns]
    out = out[keep].dropna(subset=["close"]).tail(days)
    if out.empty:
        return None
    return out.reset_index(drop=True)


class YFinanceProvider(DataProvider):
    """Universal fallback: yfinance quotes (fast_info) + historical OHLC."""

    name: str = "yfinance"
    priority: int = PRIORITY

    supports_ohlc: bool = True
    supports_quote: bool = True
    # No index restriction — serves whatever config.TICKERS /
    # live_index_service.YFINANCE_TICKERS know about.
    quote_indexes = None
    ohlc_indexes = None

    def get_ohlc(self, index_key: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Daily OHLC frame via data.historical.get_historical_data.

        Returns columns date/open/high/low/close[/volume], most recent
        `days` rows, or None on failure. Never raises.
        """
        try:
            days = max(1, int(days or 60))
        except (TypeError, ValueError):
            days = 60
        try:
            from data import historical  # deferred import by design
            df = historical.get_historical_data(_hist_key(index_key), period=_period_for_days(days))
        except Exception:
            return None
        try:
            return _normalize_ohlc(df, days)
        except Exception:
            return None

    def get_quote(self, index_name: str) -> Optional[dict]:
        """Live quote via data.live_index_service.fetch_yfinance_fallback.

        Adds the 'ts' key the unified quote contract requires. Never raises.
        """
        name = normalize_index_name(index_name)
        if not name:
            return None
        try:
            from data import live_index_service  # deferred import by design
            raw = live_index_service.fetch_yfinance_fallback(name)
        except Exception:
            return None
        if not raw:
            return None
        price = raw.get("price")
        if not price or price < 1:
            return None
        return {
            "price": price,
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "prev_close": raw.get("prev_close"),
            "source": raw.get("source", "yfinance fast feed"),
            "ts": datetime.datetime.now().isoformat(),
        }
