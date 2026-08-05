"""
BSE (Bombay Stock Exchange) provider — live SENSEX quote only.

Thin wrapper around data.live_index_service.fetch_bse_sensex_live, which
fetches the true last-traded SENSEX price via the Yahoo Finance v8 chart
API (BSE's own api.bseindia.com endpoint is CDN-blocked).

GAP: the existing data layer has no BSE-based historical OHLC fetcher,
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
PRIORITY = env_int("ZERO_BSE_PRIORITY", 20)


class BSEProvider(DataProvider):
    """Live SENSEX quote via the existing BSE/Yahoo-v8 fetcher."""

    name: str = "BSE"
    priority: int = PRIORITY

    supports_ohlc: bool = False
    supports_quote: bool = True
    quote_indexes = frozenset({"SENSEX"})

    def get_ohlc(self, index_key: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Unsupported — no BSE OHLC fetcher exists in the data layer yet.

        Kept as a returning-None stub so the abstract interface is satisfied;
        the registry never calls it because supports_ohlc is False.
        """
        return None

    def get_quote(self, index_name: str) -> Optional[dict]:
        """Live SENSEX quote via fetch_bse_sensex_live.

        Delegates to data.live_index_service.fetch_bse_sensex_live (imported
        lazily to avoid circular imports and import-time network). Adds the
        'ts' key the unified quote contract requires. Never raises.
        """
        if normalize_index_name(index_name) != "SENSEX":
            return None
        try:
            from data import live_index_service  # deferred import by design
            raw = live_index_service.fetch_bse_sensex_live()
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
            "source": raw.get("source", "Yahoo LIVE (SENSEX)"),
            "ts": datetime.datetime.now().isoformat(),
        }
