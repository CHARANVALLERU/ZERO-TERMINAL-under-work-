"""
Provider abstraction for ZERO's data layer (FinRobot-style).

Every market-data source (NSE, BSE, yfinance, ...) is wrapped by a
DataProvider subclass exposing a uniform interface:

    get_ohlc(index_key, days) -> pd.DataFrame | None
    get_quote(index_name)     -> dict | None

Providers never raise from public methods — they return None on any
failure so the ProviderRegistry failover chain can absorb the error.
Each provider keeps in-memory success/failure counters that feed
health_score(), which the registry uses to re-rank the failover order.

Importable without Streamlit, network, or any optional dependency.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd


def env_int(var_name: str, default: int) -> int:
    """Read an int from the environment without ever raising at import time."""
    try:
        return int(os.environ.get(var_name, "") or default)
    except (TypeError, ValueError):
        return default

# Quote-name aliases: the live-quote scrapers in data.live_index_service
# key on display names ("NIFTY 50") while the historical layer keys on
# short names ("NIFTY"). Normalise once here so all providers agree.
QUOTE_NAME_ALIASES = {
    "NIFTY": "NIFTY 50",
    "NIFTY50": "NIFTY 50",
    "NIFTY 50": "NIFTY 50",
    "BANKNIFTY": "BANKNIFTY",
    "BANK NIFTY": "BANKNIFTY",
    "NIFTY BANK": "BANKNIFTY",
    "SENSEX": "SENSEX",
}


def normalize_index_name(name: str) -> str:
    """Map common aliases to the display names used by data.live_index_service."""
    if not name:
        return ""
    key = " ".join(str(name).strip().upper().split())
    return QUOTE_NAME_ALIASES.get(key, key)


class DataProvider(ABC):
    """Abstract market-data provider with in-memory health tracking.

    Class attributes:
        name:           human-readable provider name (persisted health key).
        priority:       lower value = tried earlier in the failover chain.
        supports_ohlc / supports_quote:
                        capability flags — the registry skips (without any
                        health penalty) a provider lacking the capability.
        quote_indexes / ohlc_indexes:
                        optional frozensets of normalised index names this
                        provider can serve; None means "any index".
    """

    name: str = "abstract"
    priority: int = 100

    supports_ohlc: bool = True
    supports_quote: bool = True

    quote_indexes: Optional[frozenset] = None
    ohlc_indexes: Optional[frozenset] = None

    def __init__(self) -> None:
        self._success: int = 0
        self._failure: int = 0
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Capabilities (implemented by subclasses — must never raise)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_ohlc(self, index_key: str, days: int = 60) -> Optional[pd.DataFrame]:
        """Return daily OHLC frame with columns date/open/high/low/close[/volume],
        or None on failure. Never raises."""
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, index_name: str) -> Optional[dict]:
        """Return {'price','open','high','low','prev_close','source','ts'}
        or None on failure. Never raises."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Health accounting
    # ------------------------------------------------------------------
    @property
    def success_count(self) -> int:
        return self._success

    @property
    def failure_count(self) -> int:
        return self._failure

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def record_success(self) -> None:
        """Increment the success counter and clear the last error."""
        self._success += 1
        self._last_error = None

    def record_failure(self, error: Optional[str] = None) -> None:
        """Increment the failure counter, optionally noting the cause."""
        self._failure += 1
        if error:
            self._last_error = str(error)

    def health_score(self) -> float:
        """Success ratio in [0, 1]; neutral 0.5 prior when no calls yet."""
        total = self._success + self._failure
        if total == 0:
            return 0.5
        return self._success / total

    def restore_counts(self, success: int = 0, failure: int = 0) -> None:
        """Seed counters from persisted health (used by ProviderRegistry)."""
        try:
            self._success = max(0, int(success))
            self._failure = max(0, int(failure))
        except (TypeError, ValueError):
            self._success = 0
            self._failure = 0

    # ------------------------------------------------------------------
    # Capability routing helpers (used by the registry before attempting)
    # ------------------------------------------------------------------
    def can_quote(self, index_name: str) -> bool:
        if not self.supports_quote:
            return False
        if self.quote_indexes is None:
            return True
        return normalize_index_name(index_name) in self.quote_indexes

    def can_ohlc(self, index_key: str) -> bool:
        if not self.supports_ohlc:
            return False
        if self.ohlc_indexes is None:
            return True
        return str(index_key).strip().upper() in self.ohlc_indexes

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} name={self.name!r} "
            f"priority={self.priority} health={self.health_score():.2f}>"
        )
