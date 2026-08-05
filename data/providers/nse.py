"""
NSE (National Stock Exchange) provider — live quotes only.

Thin wrapper around data.live_index_service.fetch_nse_live, which reads
https://www.nseindia.com/api/allIndices for NIFTY 50 and BANKNIFTY.

GAP: the existing data layer has no NSE-based historical OHLC fetcher,
so get_ohlc() is unsupported here (returns None) and the registry skips
this provider for OHLC requests (supports_ohlc = False). Do NOT add a
new scraper here — historical data is served by YFinanceProvider.
"""

from __future__ import annotations

import datetime
from typing import Optional

import pandas as pd

from .base import DataProvider, env_int, normalize_index_name

# Lower value = earlier in the failover chain; env-overridable.
PRIORITY = env_int("ZERO_NSE_PRIORITY", 10)


class NSEProvider(DataProvider):
    """Live quotes for NIFTY 50 / BANKNIFTY from NSE India's official API."""

    name: str = "NSE"
    priority: int = PRIORITY

    supports_ohlc: bool = False
    supports_quote: bool = True
    quote_indexes = frozenset({"NIFTY 50", "BANKNIFTY"})

    def get_ohlc(self, index_key: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Unsupported — no NSE OHLC fetcher exists in the data layer yet.

        Kept as a returning-None stub so the abstract interface is satisfied;
        the registry never calls it because supports_ohlc is False.
        """
        return None

    def get_quote(self, index_name: str) -> Optional[dict]:
        """Live quote for NIFTY 50 / BANKNIFTY via fetch_nse_live.

        Delegates to data.live_index_service.fetch_nse_live (imported lazily
        to avoid circular imports and import-time network). Adds the 'ts'
        key the unified quote contract requires. Never raises.
        """
        name = normalize_index_name(index_name)
        if name not in self.quote_indexes:
            return None
        try:
            from data import live_index_service  # deferred import by design
            raw = live_index_service.fetch_nse_live(name)
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
            "source": raw.get("source", "NSE Official API"),
            "ts": datetime.datetime.now().isoformat(),
        }
