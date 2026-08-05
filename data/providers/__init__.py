"""
data.providers — unified provider registry with health-scored failover.

Thin, non-breaking wrappers around the existing scrapers in
data.live_index_service and data.historical. Nothing here makes network
calls at import time; heavy imports (requests/yfinance-backed modules)
happen lazily inside provider methods.

Usage:
    from data.providers import default_registry

    df    = default_registry().get_ohlc("NIFTY", days=60)
    quote = default_registry().get_quote("NIFTY 50")
    report = default_registry().status_report()
"""

from .base import DataProvider, normalize_index_name
from .nse import NSEProvider
from .bse import BSEProvider
from .yfinance_provider import YFinanceProvider
from .registry import ProviderRegistry, default_registry

__all__ = [
    "DataProvider",
    "NSEProvider",
    "BSEProvider",
    "YFinanceProvider",
    "ProviderRegistry",
    "default_registry",
    "normalize_index_name",
]
