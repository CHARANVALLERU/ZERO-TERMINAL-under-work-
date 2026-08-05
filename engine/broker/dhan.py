"""
ZERO Broker Adapter — Dhan (REST v2)
=====================================
Live adapter for Dhan (https://dhanhq.co / api.dhan.co).

Credentials (env only, never logged):
  - ``DHAN_CLIENT_ID``
  - ``DHAN_ACCESS_TOKEN``

Safety: every public method calls ``self._check_armed()`` first
(instance ``armed=True`` AND ``ZERO_BROKER_ARMED=1`` required).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from engine.broker.base import (
    DEFAULT_PRODUCT,
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

BASE_URL: str = os.environ.get("ZERO_DHAN_BASE_URL", "https://api.dhan.co/v2")
ENV_CLIENT_ID: str = "DHAN_CLIENT_ID"
ENV_ACCESS_TOKEN: str = "DHAN_ACCESS_TOKEN"
DEFAULT_EXCHANGE_SEGMENT: str = os.environ.get("ZERO_DHAN_EXCHANGE_SEGMENT", "NSE_EQ")

# Nautilus canonical type -> Dhan v2 orderType
_ORDER_TYPE_MAP = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "SL-M": "STOP_LOSS_MARKET",
    "SL": "STOP_LOSS",
}


class DhanBroker(BrokerAdapter):
    """Dhan v2 REST adapter."""

    name: str = "dhan"

    def __init__(self, armed: bool = False) -> None:
        super().__init__(armed)
        self.client_id: str = os.environ.get(ENV_CLIENT_ID, "")
        self.access_token: str = os.environ.get(ENV_ACCESS_TOKEN, "")

    # ── Internals ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "access-token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _require_creds(self) -> None:
        missing = [v for v, val in (
            (ENV_CLIENT_ID, self.client_id),
            (ENV_ACCESS_TOKEN, self.access_token),
        ) if not val]
        if missing:
            raise BrokerError(f"missing credential env vars: {', '.join(missing)}")

    # ── Interface ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Validate env creds and ping GET /profile."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/profile", headers=self._headers())
            self._connected = bool(resp["ok"])
        except Exception:
            self._connected = False
        return self._connected

    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Map a nautilus Order to Dhan v2 POST /orders."""
        self._check_armed()
        self._audit("place_order", order_summary(order))
        try:
            self._require_creds()
            canonical = self._map_order_type(order.order_type)
            dhan_type = _ORDER_TYPE_MAP.get(canonical)
            if dhan_type is None:
                return {"broker_order_id": None, "status": "error",
                        "error": f"unsupported order type for Dhan: {canonical}", "raw": {}}

            body: Dict[str, Any] = {
                "dhanClientId": self.client_id,
                "transactionType": enum_val(order.side),          # BUY / SELL
                "exchangeSegment": kw.get("exchange_segment", DEFAULT_EXCHANGE_SEGMENT),
                "productType": kw.get("product_type", DEFAULT_PRODUCT),
                "orderType": dhan_type,
                "validity": map_tif(order.time_in_force),         # DAY / IOC
                # VERIFY: Dhan requires its numeric securityId per instrument;
                # caller should pass security_id=... via kw (symbol map pending).
                "securityId": str(kw.get("security_id", "")),
                "tradingSymbol": order.symbol,  # VERIFY: accepted on some segments
                "quantity": int(round(float(order.quantity))),
                "disclosedQuantity": int(round(float(getattr(order, "display_qty", 0) or 0))),
                "price": float(order.price or 0),
                "triggerPrice": float(order.stop_price or 0),
                "afterMarketOrder": bool(kw.get("amo", False)),
            }
            resp = http_request("POST", f"{BASE_URL}/orders",
                                headers=self._headers(), json_body=body)
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            if resp["ok"] and payload.get("orderStatus") not in ("REJECTED",):
                return {
                    "broker_order_id": str(payload.get("orderId", "")),
                    "status": str(payload.get("orderStatus", "PENDING")).lower(),
                    "raw": payload,
                }
            return {"broker_order_id": str(payload.get("orderId", "")), "status": "error",
                    "error": payload.get("message") or resp["text"] or f"HTTP {resp['http_status']}",
                    "raw": payload}
        except Exception as exc:
            return {"broker_order_id": None, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}", "raw": {}}

    def positions(self) -> List[Dict[str, Any]]:
        """GET /positions, normalized to the shared adapter shape."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/positions", headers=self._headers())
            raw = resp["json"] if isinstance(resp["json"], list) else []
            out: List[Dict[str, Any]] = []
            for p in raw:
                if not isinstance(p, dict):
                    continue
                qty = float(p.get("netQty", 0) or 0)
                if abs(qty) < 1e-9:
                    continue
                out.append({
                    "symbol": p.get("tradingSymbol", p.get("securityId", "")),
                    "quantity": qty,
                    "product": p.get("productType", ""),
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
            return resp["json"] if isinstance(resp["json"], list) else []
        except Exception:
            return []

    def cancel(self, order_id: str) -> bool:
        """DELETE /orders/{order-id}."""
        self._check_armed()
        self._audit("cancel", {"order_id": order_id})
        try:
            self._require_creds()
            resp = http_request("DELETE", f"{BASE_URL}/orders/{order_id}",
                                headers=self._headers())
            return bool(resp["ok"])
        except Exception:
            return False
