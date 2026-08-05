"""
ZERO Broker Adapter — Angel One SmartAPI (REST)
================================================
Live adapter for Angel One SmartAPI (https://apiconnect.angelone.in).

Credentials (env only, never logged):
  - ``ANGEL_API_KEY``       (SmartAPI app key, sent as X-PrivateKey)
  - ``ANGEL_ACCESS_TOKEN``  (JWT from the SmartAPI login flow)
  - ``ANGEL_CLIENT_CODE``   (client code, e.g. "A12345")

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

BASE_URL: str = os.environ.get("ZERO_ANGEL_BASE_URL", "https://apiconnect.angelone.in")
ENV_API_KEY: str = "ANGEL_API_KEY"
ENV_ACCESS_TOKEN: str = "ANGEL_ACCESS_TOKEN"
ENV_CLIENT_CODE: str = "ANGEL_CLIENT_CODE"
DEFAULT_EXCHANGE: str = os.environ.get("ZERO_ANGEL_EXCHANGE", "NSE")
DEFAULT_PRODUCT: str = os.environ.get("ZERO_ANGEL_PRODUCT", "INTRADAY")

# Nautilus canonical type -> SmartAPI ordertype
_ORDER_TYPE_MAP = {
    "MARKET": "MARKET",
    "LIMIT": "LIMIT",
    "SL-M": "STOPLOSS_MARKET",
    "SL": "STOPLOSS_LIMIT",
}


class AngelBroker(BrokerAdapter):
    """Angel One SmartAPI REST adapter."""

    name: str = "angel"

    def __init__(self, armed: bool = False) -> None:
        super().__init__(armed)
        self.api_key: str = os.environ.get(ENV_API_KEY, "")
        self.access_token: str = os.environ.get(ENV_ACCESS_TOKEN, "")
        self.client_code: str = os.environ.get(ENV_CLIENT_CODE, "")

    # ── Internals ────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        # VERIFY: SmartAPI expects local/public IP + MAC headers for compliance;
        # static placeholder values are accepted by most setups.
        return {
            "X-PrivateKey": self.api_key,
            "Authorization": f"Bearer {self.access_token}",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _require_creds(self) -> None:
        missing = [v for v, val in (
            (ENV_API_KEY, self.api_key),
            (ENV_ACCESS_TOKEN, self.access_token),
            (ENV_CLIENT_CODE, self.client_code),
        ) if not val]
        if missing:
            raise BrokerError(f"missing credential env vars: {', '.join(missing)}")

    # ── Interface ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Validate env creds and ping GET user profile."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request(
                "GET",
                f"{BASE_URL}/rest/secure/angelbroking/user/v1/getProfile",
                headers=self._headers(),
            )
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            self._connected = bool(resp["ok"] and payload.get("status") is True)
        except Exception:
            self._connected = False
        return self._connected

    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Map a nautilus Order to SmartAPI POST /order/v1/placeOrder."""
        self._check_armed()
        self._audit("place_order", order_summary(order))
        try:
            self._require_creds()
            canonical = self._map_order_type(order.order_type)
            angel_type = _ORDER_TYPE_MAP.get(canonical)
            if angel_type is None:
                return {"broker_order_id": None, "status": "error",
                        "error": f"unsupported order type for Angel: {canonical}", "raw": {}}

            symbol_token = str(kw.get("symbol_token", ""))
            if not symbol_token:
                # VERIFY: SmartAPI requires the instrument token (from the
                # master contract file); a symbol->token map is pending.
                return {"broker_order_id": None, "status": "error",
                        "error": "Angel requires kw symbol_token (instrument master lookup pending)",
                        "raw": {}}

            is_sl = angel_type in ("STOPLOSS_MARKET", "STOPLOSS_LIMIT")
            body: Dict[str, Any] = {
                "variety": "STOPLOSS" if is_sl else "NORMAL",
                "tradingsymbol": order.symbol,
                "symboltoken": symbol_token,
                "transactiontype": enum_val(order.side),       # BUY / SELL
                "exchange": kw.get("exchange", getattr(order, "venue", None) or DEFAULT_EXCHANGE),
                "ordertype": angel_type,
                "producttype": kw.get("product_type", DEFAULT_PRODUCT),
                "duration": map_tif(order.time_in_force),      # DAY / IOC
                # VERIFY: SmartAPI expects prices/qty as strings
                "price": f"{float(order.price or 0):.2f}",
                "triggerprice": f"{float(order.stop_price or 0):.2f}" if is_sl else "0",
                "squareoff": "0",
                "stoploss": "0",
                "quantity": str(int(round(float(order.quantity)))),
            }
            resp = http_request(
                "POST",
                f"{BASE_URL}/rest/secure/angelbroking/order/v1/placeOrder",
                headers=self._headers(),
                json_body=body,
            )
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            data = payload.get("data") or {}
            if resp["ok"] and payload.get("status") is True:
                return {
                    "broker_order_id": str(data.get("orderid", "")),
                    "status": "placed",
                    "raw": payload,
                }
            return {"broker_order_id": str(data.get("orderid", "")), "status": "error",
                    "error": payload.get("message") or resp["text"] or f"HTTP {resp['http_status']}",
                    "raw": payload}
        except Exception as exc:
            return {"broker_order_id": None, "status": "error",
                    "error": f"{type(exc).__name__}: {exc}", "raw": {}}

    def positions(self) -> List[Dict[str, Any]]:
        """GET position book, normalized to the shared adapter shape."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request(
                "GET",
                f"{BASE_URL}/rest/secure/angelbroking/order/v1/getPosition",
                headers=self._headers(),
            )
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            raw = payload.get("data") or []
            out: List[Dict[str, Any]] = []
            for p in raw:
                if not isinstance(p, dict):
                    continue
                try:
                    qty = float(p.get("netqty", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if abs(qty) < 1e-9:
                    continue
                out.append({
                    "symbol": p.get("tradingsymbol", ""),
                    "quantity": qty,
                    "product": p.get("producttype", ""),
                    "raw": p,
                })
            return out
        except Exception:
            return []

    def orders(self) -> List[Dict[str, Any]]:
        """GET order book for the day."""
        self._check_armed()
        try:
            self._require_creds()
            resp = http_request(
                "GET",
                f"{BASE_URL}/rest/secure/angelbroking/order/v1/getOrderBook",
                headers=self._headers(),
            )
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            data = payload.get("data")
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def cancel(self, order_id: str) -> bool:
        """POST /order/v1/cancelOrder {variety, orderid}."""
        self._check_armed()
        self._audit("cancel", {"order_id": order_id})
        try:
            self._require_creds()
            # VERIFY: variety must match the original order (NORMAL assumed)
            resp = http_request(
                "POST",
                f"{BASE_URL}/rest/secure/angelbroking/order/v1/cancelOrder",
                headers=self._headers(),
                json_body={"variety": "NORMAL", "orderid": str(order_id)},
            )
            payload = resp["json"] if isinstance(resp["json"], dict) else {}
            return bool(resp["ok"] and payload.get("status") is True)
        except Exception:
            return False
