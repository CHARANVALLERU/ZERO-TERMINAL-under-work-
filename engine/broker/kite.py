"""
ZERO Broker Adapter — Zerodha Kite Connect (REST v3)
=====================================================
Live adapter for Kite Connect (https://api.kite.trade).

Credentials (env only, never logged):
  - ``KITE_API_KEY``
  - ``KITE_ACCESS_TOKEN``   (daily token from the Kite login flow)

Safety: every public method calls ``self._check_armed()`` first
(instance ``armed=True`` AND ``ZERO_BROKER_ARMED=1`` required).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from engine.broker.base import (
    BrokerAdapter,
    BrokerError,
    enum_val,
    http_request,
    map_tif,
    order_summary,
)

# ─────────────────────────────────────────────
#  Constants (env-overridable)
# ─────────────────────────────────────────────

BASE_URL: str = os.environ.get("ZERO_KITE_BASE_URL", "https://api.kite.trade")
ENV_API_KEY: str = "KITE_API_KEY"
ENV_ACCESS_TOKEN: str = "KITE_ACCESS_TOKEN"
DEFAULT_EXCHANGE: str = os.environ.get("ZERO_KITE_EXCHANGE", "NSE")
DEFAULT_PRODUCT: str = os.environ.get("ZERO_KITE_PRODUCT", "MIS")
KITE_VERSION: str = "3"

# Nautilus canonical type -> Kite order_type
_ORDER_TYPE_MAP = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "SL-M": "SL-M",
    "SL": "SL",
}


class KiteBroker(BrokerAdapter):
    """Kite Connect v3 REST adapter."""

    name: str = "kite"

    def __init__(self, armed: bool = False) -> None:
        super().__init__(armed)
        self.api_key: str = os.environ.get(ENV_API_KEY, "")
        self.access_token: str = os.environ.get(ENV_ACCESS_TOKEN, "")

    # ── Internals ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}:{self.access_token}",
            "X-Kite-Version": KITE_VERSION,
        }

    def _require_creds(self) -> None:
        missing = [v for v, val in (
            (ENV_API_KEY, self.api_key),
            (ENV_ACCESS_TOKEN, self.access_token),
        ) if not val]
        if missing:
            raise BrokerError(f"missing credential env vars: {', '.join(missing)}")

    # ── Interface ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Validate env creds and ping GET /user/profile."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/user/profile", headers=self._headers())
            data = resp["json"] if isinstance(resp["json"], dict) else {}
            self._connected = bool(resp["ok"] and data.get("status") == "success")
        except Exception:
            self._connected = False
        return self._connected

    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Map a nautilus Order to Kite POST /orders/regular (form-encoded)."""
        self._check_armed()
        self._audit("place_order", order_summary(order))
        try:
            self._require_creds()
            canonical = self._map_order_type(order.order_type)
            kite_type = _ORDER_TYPE_MAP.get(canonical)
            if kite_type is None:
                return {"broker_order_id": None, "status": "error",
                        "error": f"unsupported order type for Kite: {canonical}", "raw": {}}

            variety = kw.get("variety", "regular")
            form: Dict[str, Any] = {
                "tradingsymbol": order.symbol,
                "exchange": kw.get("exchange", getattr(order, "venue", None) or DEFAULT_EXCHANGE),
                "transaction_type": enum_val(order.side),          # BUY / SELL
                "order_type": kite_type,
                "quantity": int(round(float(order.quantity))),
                "product": kw.get("product", DEFAULT_PRODUCT),     # MIS/CNC/NRML
                "validity": map_tif(order.time_in_force),          # DAY / IOC
            }
            if kite_type in ("LIMIT", "SL"):
                form["price"] = float(order.price or 0)
            if kite_type in ("SL", "SL-M"):
                form["trigger_price"] = float(order.stop_price or 0)
            disclosed = getattr(order, "display_qty", None)
            if disclosed and float(disclosed) < float(order.quantity):
                form["disclosed_quantity"] = int(round(float(disclosed)))
            if kw.get("tag"):
                form["tag"] = str(kw["tag"])[:20]

            resp = http_request("POST", f"{BASE_URL}/orders/{variety}",
                                headers=self._headers(), data=form)
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            data = payload.get("data") or {}
            if resp["ok"] and payload.get("status") == "success":
                return {
                    "broker_order_id": str(data.get("order_id", "")),
                    "status": "placed",
                    "raw": payload,
                }
            return {"broker_order_id": str(data.get("order_id", "")), "status": "error",
                    "error": payload.get("message") or resp["text"] or f"HTTP {resp['http_status']}",
                    "raw": payload}
        except Exception as exc:
            return {"broker_order_id": None, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}", "raw": {}}

    def positions(self) -> List[Dict[str, Any]]:
        """GET /portfolio/positions — uses the 'net' book, normalized."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/portfolio/positions",
                                headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            net = (payload.get("data") or {}).get("net") or []
            out: List[Dict[str, Any]] = []
            for p in net:
                if not isinstance(p, dict):
                    continue
                qty = float(p.get("quantity", 0) or 0)
                if abs(qty) < 1e-9:
                    continue
                out.append({
                    "symbol": p.get("tradingsymbol", ""),
                    "quantity": qty,
                    "product": p.get("product", ""),
                    "raw": p,
                })
            return out
        except Exception:
            return []

    def orders(self) -> List[Dict[str, Any]]:
        """GET /orders — full order book for the day."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/orders", headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            data = payload.get("data")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def cancel(self, order_id: str) -> bool:
        """DELETE /orders/{variety}/{order_id} (variety assumed regular)."""
        self._check_armed()
        self._audit("cancel", {"order_id": order_id})
        try:
            self._require_creds()
            resp = http_request("DELETE", f"{BASE_URL}/orders/regular/{order_id}",
                                headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            return bool(resp["ok"] and payload.get("status") == "success")
        except Exception:
            return False
