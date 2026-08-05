"""
ZERO Broker Adapter — Fyers (REST API v3)
==========================================
Live adapter for Fyers (https://api-t1.fyers.in / api-t2.fyers.in).

Credentials (env only, never logged):
  - ``FYERS_APP_ID``        (e.g. "XXXXX-100", app id with suffix)
  - ``FYERS_ACCESS_TOKEN``  (JWT from the Fyers auth flow)

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

BASE_URL: str = os.environ.get("ZERO_FYERS_BASE_URL", "https://api-t1.fyers.in/api/v3")
ENV_APP_ID: str = "FYERS_APP_ID"
ENV_ACCESS_TOKEN: str = "FYERS_ACCESS_TOKEN"
DEFAULT_PRODUCT: str = os.environ.get("ZERO_FYERS_PRODUCT", "INTRADAY")

# Nautilus canonical type -> Fyers numeric order type
# VERIFY: Fyers type codes: 1=Limit, 2=Market, 3=Stop(SL-M), 4=StopLimit(SL-L)
_ORDER_TYPE_MAP = {
    "MARKET": 2,
    "LIMIT": 1,
    "SL-M": 3,
    "SL": 4,
}


class FyersBroker(BrokerAdapter):
    """Fyers API v3 REST adapter."""

    name: str = "fyers"

    def __init__(self, armed: bool = False) -> None:
        super().__init__(armed)
        self.app_id: str = os.environ.get(ENV_APP_ID, "")
        self.access_token: str = os.environ.get(ENV_ACCESS_TOKEN, "")

    # ── Internals ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"{self.app_id}:{self.access_token}",
            "Content-Type": "application/json",
        }

    def _require_creds(self) -> None:
        missing = [v for v, val in (
            (ENV_APP_ID, self.app_id),
            (ENV_ACCESS_TOKEN, self.access_token),
        ) if not val]
        if missing:
            raise BrokerError(f"missing credential env vars: {', '.join(missing)}")

    @staticmethod
    def _fyers_symbol(order: Any, kw: Dict[str, Any]) -> str:
        """Fyers wants 'EXCH:SYMBOL-SERIES', e.g. 'NSE:SBIN-EQ'."""
        if kw.get("fyers_symbol"):
            return str(kw["fyers_symbol"])
        exch = kw.get("exchange", getattr(order, "venue", None) or "NSE")
        return f"{exch}:{order.symbol}-EQ"  # VERIFY: series suffix for non-EQ

    # ── Interface ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Validate env creds and ping GET /profile."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/profile", headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            self._connected = bool(resp["ok"] and payload.get("s") == "ok")
        except Exception:
            self._connected = False
        return self._connected

    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Map a nautilus Order to Fyers POST /orders-sync."""
        self._check_armed()
        self._audit("place_order", order_summary(order))
        try:
            self._require_creds()
            canonical = self._map_order_type(order.order_type)
            fyers_type = _ORDER_TYPE_MAP.get(canonical)
            if fyers_type is None:
                return {"broker_order_id": None, "status": "error",
                        "error": f"unsupported order type for Fyers: {canonical}", "raw": {}}

            side = 1 if enum_val(order.side) == "BUY" else -1
            body: Dict[str, Any] = {
                "symbol": self._fyers_symbol(order, kw),
                "qty": int(round(float(order.quantity))),
                "type": fyers_type,
                "side": side,
                "productType": kw.get("product_type", DEFAULT_PRODUCT),
                "limitPrice": float(order.price or 0),
                "stopPrice": float(order.stop_price or 0),
                "validity": map_tif(order.time_in_force),      # DAY / IOC
                "disclosedQty": 0,
                "offlineOrder": False,
                "stopLoss": 0,
                "takeProfit": 0,
                # VERIFY: orderTag max length / allowed chars per Fyers docs
                "orderTag": str(kw.get("tag", "zero"))[:20],
            }
            resp = http_request("POST", f"{BASE_URL}/orders-sync",
                                headers=self._headers(), json_body=body)
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            if resp["ok"] and payload.get("s") == "ok":
                return {
                    "broker_order_id": str(payload.get("id", "")),
                    "status": "placed",
                    "raw": payload,
                }
            return {"broker_order_id": str(payload.get("id", "")), "status": "error",
                    "error": payload.get("message") or resp["text"] or f"HTTP {resp['http_status']}",
                    "raw": payload}
        except Exception as exc:
            return {"broker_order_id": None, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}", "raw": {}}

    def positions(self) -> List[Dict[str, Any]]:
        """GET /positions — netPositions normalized to shared shape."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/positions", headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            net = payload.get("netPositions") or []
            out: List[Dict[str, Any]] = []
            for p in net:
                if not isinstance(p, dict):
                    continue
                qty = float(p.get("netQty", 0) or 0)
                if abs(qty) < 1e-9:
                    continue
                out.append({
                    "symbol": p.get("symbol", ""),
                    "quantity": qty,
                    "product": p.get("productType", ""),
                    "raw": p,
                })
            return out
        except Exception:
            return []

    def orders(self) -> List[Dict[str, Any]]:
        """GET /orders — order book for the day."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request("GET", f"{BASE_URL}/orders", headers=self._headers())
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            book = payload.get("orderBook")
            return book if isinstance(book, list) else []
        except Exception:
            return []

    def cancel(self, order_id: str) -> bool:
        """DELETE /orders with body {"id": order_id}."""
        self._check_armed()
        self._audit("cancel", {"order_id": order_id})
        try:
            self._require_creds()
            resp = http_request("DELETE", f"{BASE_URL}/orders",
                                headers=self._headers(), json_body={"id": order_id})
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            # VERIFY: Fyers cancel returns {"s":"ok"} on success
            return bool(resp["ok"] and payload.get("s") == "ok")
        except Exception:
            return False
