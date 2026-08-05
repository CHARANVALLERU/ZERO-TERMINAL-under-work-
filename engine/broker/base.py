"""
ZERO Broker Adapter — Base Interface
=====================================
Abstract broker adapter with a two-layer safety gate and a JSONL audit trail.

Two-layer arming (BOTH must be true for any live call):
  1. Instance-level: ``BrokerAdapter(armed=True)`` constructor flag.
  2. Process-level:  environment variable ``ZERO_BROKER_ARMED=1``.

Every live (non-paper) public method must call ``self._check_armed()`` first.
``BrokerNotArmedError`` is raised otherwise — disarmed-by-default.

Conventions:
  - Credentials come ONLY from environment variables; never logged, never
    written to the audit trail.
  - No network calls at import time.
  - All broker responses are normalized to plain dicts/lists.
"""

from __future__ import annotations

import datetime
import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests

# ─────────────────────────────────────────────
#  Constants (env-overridable)
# ─────────────────────────────────────────────

ARM_ENV_VAR: str = "ZERO_BROKER_ARMED"
"""Env var that must equal '1' for live trading (layer 2 of the safety gate)."""

AUDIT_LOG_PATH: str = os.environ.get(
    "ZERO_BROKER_AUDIT_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "db", "broker_audit.jsonl"),
)
"""Append-only JSONL audit trail for every mutating broker action."""

HTTP_TIMEOUT_SECONDS: float = float(os.environ.get("ZERO_BROKER_HTTP_TIMEOUT", "10"))
"""Timeout applied to every broker REST call."""

DEFAULT_PRODUCT: str = os.environ.get("ZERO_BROKER_PRODUCT", "INTRADAY")
"""Default product type (INTRADAY/MIS-style) used when caller does not override."""


# ─────────────────────────────────────────────
#  Exceptions
# ─────────────────────────────────────────────

class BrokerNotArmedError(Exception):
    """Raised when a live broker call is attempted while the adapter is disarmed."""


class BrokerError(Exception):
    """Generic broker adapter error (config, validation, transport)."""


# ─────────────────────────────────────────────
#  Module helpers
# ─────────────────────────────────────────────

def enum_val(x: Any) -> str:
    """Return the ``.value`` of an enum member, else ``str(x)``. Defensive."""
    return getattr(x, "value", str(x))


def map_tif(tif: Any) -> str:
    """Map a nautilus TimeInForce to the common broker validity strings.

    Only DAY and IOC are broadly supported by Indian broker REST APIs;
    everything else degrades to DAY.  # VERIFY: GTD/GTC support varies.
    """
    return "IOC" if enum_val(tif) == "IOC" else "DAY"


def order_summary(order: Any) -> Dict[str, Any]:
    """Secret-free one-line summary of a nautilus Order for the audit trail."""
    return {
        "order_id": getattr(order, "order_id", None),
        "symbol": getattr(order, "symbol", None),
        "side": enum_val(getattr(order, "side", "")),
        "type": enum_val(getattr(order, "order_type", "")),
        "qty": getattr(order, "quantity", None),
        "price": getattr(order, "price", None),
        "stop_price": getattr(order, "stop_price", None),
        "tif": enum_val(getattr(order, "time_in_force", "")),
        "venue": getattr(order, "venue", None),
    }


def http_request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Thin ``requests`` wrapper shared by all live adapters.

    Returns ``{"http_status": int, "ok": bool, "json": dict|list|None, "text": str}``.
    Raises :class:`BrokerError` on transport-level failure (never raw
    ``requests`` exceptions) so adapters can convert to error dicts.
    """
    try:
        resp = requests.request(
            method.upper(),
            url,
            headers=headers,
            json=json_body,
            data=data,
            params=params,
            timeout=HTTP_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # requests.RequestException + anything else
        raise BrokerError(f"transport error: {type(exc).__name__}: {exc}") from exc

    parsed: Any = None
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None
    return {
        "http_status": resp.status_code,
        "ok": resp.ok,
        "json": parsed,
        "text": resp.text[:2000] if resp.text else "",
    }


# ─────────────────────────────────────────────
#  Abstract adapter
# ─────────────────────────────────────────────

class BrokerAdapter(ABC):
    """Uniform interface between the ZERO engine and a broker (paper or live)."""

    name: str = "base"

    def __init__(self, armed: bool = False) -> None:
        self.armed: bool = bool(armed)
        self._connected: bool = False

    # ── Safety gate ──────────────────────────────────────────────────────

    def _check_armed(self) -> None:
        """Two-layer gate: instance flag AND process env var must both be set."""
        if not (self.armed and os.environ.get(ARM_ENV_VAR) == "1"):
            raise BrokerNotArmedError(
                f"Broker '{self.name}' is DISARMED. Set armed=True AND "
                f"{ARM_ENV_VAR}=1 to enable live trading."
            )

    # ── Audit trail ──────────────────────────────────────────────────────

    def _audit(self, action: str, payload_summary: Dict[str, Any]) -> None:
        """Append one JSON line to the audit log. I/O failures are swallowed.

        ``payload_summary`` must never contain tokens, API keys, or secrets.
        """
        try:
            os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
            line = {
                "ts": datetime.datetime.now().isoformat(timespec="milliseconds"),
                "broker": self.name,
                "action": action,
                "payload_summary": payload_summary,
            }
            with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, default=str) + "\n")
        except Exception:
            pass  # audit must never break trading flow

    # ── Interface ────────────────────────────────────────────────────────

    @abstractmethod
    def connect(self) -> bool:
        """Validate credentials and ping the broker. Returns True on success."""
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Place a nautilus ``Order``. Returns
        ``{'broker_order_id': str|None, 'status': str, 'raw': dict}``."""
        raise NotImplementedError

    @abstractmethod
    def positions(self) -> List[Dict[str, Any]]:
        """Return open positions normalized to
        ``[{'symbol': str, 'quantity': float, 'product': str, 'raw': dict}]``."""
        raise NotImplementedError

    @abstractmethod
    def orders(self) -> List[Dict[str, Any]]:
        """Return the broker's order book as a list of dicts."""
        raise NotImplementedError

    @abstractmethod
    def cancel(self, order_id: str) -> bool:
        """Cancel a live order by broker order id."""
        raise NotImplementedError

    # ── Shared helpers ───────────────────────────────────────────────────

    @staticmethod
    def _map_order_type(order_type: Any) -> str:
        """Normalize nautilus OrderType to a canonical string:
        MARKET / LIMIT / SL-M / SL.  Adapters translate per broker."""
        t = enum_val(order_type)
        if t == "STOP_MARKET":
            return "SL-M"
        if t == "STOP_LIMIT":
            return "SL"
        return t  # MARKET / LIMIT pass through; exotic types flagged below

    def square_off_all(self) -> Dict[str, Any]:
        """Close every open position with an opposing MARKET order.

        Generic implementation built on ``positions()`` + ``place_order()``.
        Positions are expected in the normalized adapter shape.
        """
        self._check_armed()
        self._audit("square_off_all", {"initiated": True})
        result: Dict[str, Any] = {"broker": self.name, "closed": [], "errors": []}
        try:
            pos_list = self.positions()
        except Exception as exc:
            result["status"] = "error"
            result["errors"].append(f"positions fetch failed: {exc}")
            return result

        from engine.nautilus_order_engine import (  # lazy: avoid import cycle
            Order,
            OrderSide,
            OrderType,
        )

        for pos in pos_list:
            try:
                qty = float(pos.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                continue
            if abs(qty) < 1e-9:
                continue
            symbol = pos.get("symbol", "")
            side = OrderSide.SELL if qty > 0 else OrderSide.BUY
            try:
                closing = Order(symbol, side, OrderType.MARKET, abs(qty))
                resp = self.place_order(closing, square_off=True)
                result["closed"].append({"symbol": symbol, "qty": abs(qty), "response": resp})
            except Exception as exc:
                result["errors"].append(f"{symbol}: {exc}")

        result["status"] = "ok" if not result["errors"] else "partial"
        return result
