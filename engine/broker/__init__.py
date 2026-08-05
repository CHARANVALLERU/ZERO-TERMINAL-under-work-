"""
ZERO Broker Adapters
=====================
Uniform adapter layer between the ZERO order engine and execution venues.

- ``PaperBroker``  — DEFAULT. Local slippage simulator, no arming needed.
- ``DhanBroker`` / ``FyersBroker`` / ``KiteBroker`` / ``AngelBroker`` — live
  REST adapters, gated by a two-layer safety mechanism:
  ``armed=True`` at construction AND ``ZERO_BROKER_ARMED=1`` in the env.

Importing this package performs no network calls. Credentials are read from
environment variables only (never hardcoded, never logged, never audited).

Usage::

    from engine.broker import get_broker

    broker = get_broker()                    # paper (default, safe)
    broker = get_broker("kite", armed=True)  # still needs ZERO_BROKER_ARMED=1
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Type

from engine.broker.base import (
    ARM_ENV_VAR,
    AUDIT_LOG_PATH,
    BrokerAdapter,
    BrokerError,
    BrokerNotArmedError,
)
from engine.broker.paper import PaperBroker
from engine.broker.dhan import DhanBroker
from engine.broker.fyers import FyersBroker
from engine.broker.kite import KiteBroker
from engine.broker.angel import AngelBroker

__all__ = [
    "ARM_ENV_VAR",
    "AUDIT_LOG_PATH",
    "BrokerAdapter",
    "BrokerError",
    "BrokerNotArmedError",
    "PaperBroker",
    "DhanBroker",
    "FyersBroker",
    "KiteBroker",
    "AngelBroker",
    "get_broker",
]

# Registry of available adapters by short name.
_BROKER_REGISTRY: Dict[str, Type[BrokerAdapter]] = {
    "paper": PaperBroker,
    "dhan": DhanBroker,
    "fyers": FyersBroker,
    "kite": KiteBroker,
    "angel": AngelBroker,
}

BROKER_NAME_ENV_VAR: str = "ZERO_BROKER_NAME"
"""Optional env override selecting the default adapter for get_broker(None)."""


def get_broker(name: Optional[str] = None, armed: bool = False) -> BrokerAdapter:
    """Factory: return the broker adapter for ``name``.

    - ``None``  -> ``ZERO_BROKER_NAME`` env var if set, else ``'paper'``.
    - ``'paper'`` -> :class:`PaperBroker` (DEFAULT; arming not required).
    - ``'dhan'`` / ``'fyers'`` / ``'kite'`` / ``'angel'`` -> live REST adapter.
      Live adapters are constructed disarmed unless ``armed=True``, and every
      live call additionally requires ``ZERO_BROKER_ARMED=1`` at call time.

    Raises :class:`BrokerError` for an unknown broker name.
    """
    key = (name or os.environ.get(BROKER_NAME_ENV_VAR) or "paper").strip().lower()
    cls = _BROKER_REGISTRY.get(key)
    if cls is None:
        raise BrokerError(
            f"unknown broker '{key}'. Available: {', '.join(sorted(_BROKER_REGISTRY))}"
        )
    return cls(armed=armed)
