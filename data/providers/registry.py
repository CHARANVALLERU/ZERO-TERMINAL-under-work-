"""
Health-scored provider registry with FinRobot-style failover.

ProviderRegistry holds an ordered list of DataProvider instances and, for
each request, walks them — sorted by (priority, live health_score) —
until one returns data. Success/failure is recorded per provider and
rolling health is persisted to db/provider_health.json so it survives
restarts. Persistence is strictly best-effort: I/O errors are swallowed
and never crash a data call.

default_registry() is the process-wide singleton wired in the order
NSE -> BSE -> yfinance.

Importable without Streamlit, network, or optional dependencies; the
providers defer their heavy imports into method bodies.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
from typing import Callable, List, Optional, Sequence

import pandas as pd

from .base import DataProvider
from .bse import BSEProvider
from .nse import NSEProvider
from .yfinance_provider import YFinanceProvider

_HEALTH_PATH_DEFAULT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "db", "provider_health.json")
)
# Env-overridable so tests / deployments can relocate the health file.
HEALTH_PATH = os.environ.get("ZERO_PROVIDER_HEALTH_PATH", _HEALTH_PATH_DEFAULT)

_DEFAULT_REGISTRY: Optional["ProviderRegistry"] = None
_REGISTRY_LOCK = threading.Lock()


def _has_data(value) -> bool:
    """A provider result counts as data unless None / empty frame / empty dict."""
    if value is None:
        return False
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, dict):
        return bool(value)
    return True


class ProviderRegistry:
    """Ordered provider list with health-scored failover and persistence."""

    def __init__(
        self,
        providers: Optional[Sequence[DataProvider]] = None,
        health_path: Optional[str] = None,
    ) -> None:
        self._providers: List[DataProvider] = list(providers) if providers else []
        self._health_path: str = health_path or HEALTH_PATH
        self._io_lock = threading.Lock()
        self._load_health()

    # ------------------------------------------------------------------
    # Registry management
    # ------------------------------------------------------------------
    @property
    def providers(self) -> List[DataProvider]:
        return list(self._providers)

    def register(self, provider: DataProvider) -> None:
        """Append a provider (after init it does not inherit saved health)."""
        if provider is not None:
            self._providers.append(provider)

    def _ordered(self) -> List[DataProvider]:
        """Providers sorted by (priority asc, live health desc)."""
        return sorted(self._providers, key=lambda p: (p.priority, -p.health_score()))

    # ------------------------------------------------------------------
    # Public data API — never raises
    # ------------------------------------------------------------------
    def get_ohlc(self, index_key: str, days: int = 60) -> Optional[pd.DataFrame]:
        """First non-empty OHLC frame walking the failover chain, else None."""
        return self._failover(
            lambda p: p.can_ohlc(index_key), "get_ohlc", index_key, days=days
        )

    def get_quote(self, index_name: str) -> Optional[dict]:
        """First non-empty quote dict walking the failover chain, else None."""
        return self._failover(
            lambda p: p.can_quote(index_name), "get_quote", index_name
        )

    def status_report(self) -> List[dict]:
        """Per-provider health snapshot for UI display (failover order)."""
        return [
            {
                "name": p.name,
                "priority": p.priority,
                "health": round(p.health_score(), 3),
                "success": p.success_count,
                "failure": p.failure_count,
                "last_error": p.last_error,
                "supports_ohlc": p.supports_ohlc,
                "supports_quote": p.supports_quote,
            }
            for p in self._ordered()
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _failover(self, can_serve: Callable[[DataProvider], bool], method: str, *args, **kwargs):
        attempted = False
        for provider in self._ordered():
            try:
                eligible = can_serve(provider)
            except Exception:
                eligible = False
            if not eligible:
                continue  # capability gap: skipped without health penalty
            attempted = True
            try:
                value = getattr(provider, method)(*args, **kwargs)
            except Exception as exc:
                provider.record_failure(f"{method} raised {type(exc).__name__}")
                continue
            if not _has_data(value):
                provider.record_failure(f"{method} returned no data")
                continue
            provider.record_success()
            self._save_health()
            return value
        if attempted:
            self._save_health()
        return None

    def _load_health(self) -> None:
        """Seed provider counters from the persisted health file (best-effort)."""
        try:
            with open(self._health_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        for provider in self._providers:
            rec = payload.get(provider.name)
            if isinstance(rec, dict):
                provider.restore_counts(rec.get("success", 0), rec.get("failure", 0))

    def _save_health(self) -> None:
        """Persist rolling health for all providers (best-effort, atomic-ish)."""
        payload = {
            p.name: {
                "success": p.success_count,
                "failure": p.failure_count,
                "health": round(p.health_score(), 4),
                "updated": datetime.datetime.now().isoformat(),
            }
            for p in self._providers
        }
        try:
            with self._io_lock:
                directory = os.path.dirname(self._health_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
                tmp_path = self._health_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2)
                os.replace(tmp_path, self._health_path)
        except OSError:
            pass  # never crash a data call on I/O


def default_registry() -> ProviderRegistry:
    """Process-wide singleton registry: NSE -> BSE -> yfinance order."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = ProviderRegistry(
                    providers=[NSEProvider(), BSEProvider(), YFinanceProvider()]
                )
    return _DEFAULT_REGISTRY
