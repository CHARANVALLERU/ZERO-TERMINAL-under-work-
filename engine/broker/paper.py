"""
ZERO Broker Adapter — Paper Broker (DEFAULT)
=============================================
Wraps ``engine/paper_brokerage.py`` (LEAN-style slippage simulator) behind
the :class:`~engine.broker.base.BrokerAdapter` interface.

This is the DEFAULT adapter: no arming required, no network, no credentials.
The paper brokerage is imported lazily inside methods so importing this
module stays cheap and side-effect free.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.broker.base import (
    BrokerAdapter,
    BrokerError,
    enum_val,
    order_summary,
)


class PaperBroker(BrokerAdapter):
    """Paper-trading adapter backed by ``PaperBrokerage``. Armed not required."""

    name: str = "paper"

    def __init__(self, armed: bool = False, initial_capital: Optional[float] = None) -> None:
        super().__init__(armed=True)  # paper always considered armed
        self._initial_capital = initial_capital
        self._brokerage: Any = None  # lazily-loaded PaperBrokerage

    # ── Safety gate: paper trading is always safe ────────────────────────

    def _check_armed(self) -> None:  # noqa: D102 - intentional no-op
        return None

    # ── Lazy delegation ──────────────────────────────────────────────────

    def _get_brokerage(self) -> Any:
        if self._brokerage is None:
            from engine.paper_brokerage import PaperBrokerage  # lazy import

            if self._initial_capital is not None:
                self._brokerage = PaperBrokerage(initial_capital=self._initial_capital)
            else:
                self._brokerage = PaperBrokerage.load()
        return self._brokerage

    # ── Interface ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """'Connect' = load persisted paper state from disk. Always local."""
        self._get_brokerage()
        self._connected = True
        return True

    def place_order(self, order: Any, **kw: Any) -> Dict[str, Any]:
        """Execute a nautilus Order against the paper brokerage.

        Paper fills are immediate and market-priced, so a price must be
        resolvable from (in priority order): ``kw['current_price']``,
        ``order.price``, ``order.stop_price``.
        """
        self._audit("place_order", order_summary(order))
        brokerage = self._get_brokerage()

        try:
            price = kw.get("current_price") or order.price or order.stop_price
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        if price is None or price <= 0:
            return {
                "broker_order_id": getattr(order, "order_id", None),
                "status": "error",
                "error": "paper fill requires current_price (kw), order.price, or order.stop_price",
                "raw": {},
            }

        try:
            report = brokerage.execute_order(
                symbol=order.symbol,
                side=enum_val(order.side),
                quantity=float(order.quantity),
                current_price=float(price),
            )
            brokerage.save_log()
        except Exception as exc:
            return {
                "broker_order_id": getattr(order, "order_id", None),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "raw": {},
            }

        return {
            "broker_order_id": getattr(order, "order_id", None),
            "status": report.get("status", "unknown"),
            "raw": report,
        }

    def positions(self) -> List[Dict[str, Any]]:
        """Normalized open positions from the paper ledger."""
        brokerage = self._get_brokerage()
        out: List[Dict[str, Any]] = []
        for symbol, qty in brokerage.positions.items():
            if abs(float(qty)) < 1e-9:
                continue
            out.append(
                {
                    "symbol": symbol,
                    "quantity": float(qty),
                    "product": "PAPER",
                    "avg_cost": brokerage.avg_cost.get(symbol, 0.0),
                    "raw": {"symbol": symbol, "quantity": qty},
                }
            )
        return out

    def orders(self) -> List[Dict[str, Any]]:
        """Return the paper trade log (each entry is a completed execution)."""
        brokerage = self._get_brokerage()
        return list(brokerage.trade_log)

    def cancel(self, order_id: str) -> bool:
        """Paper fills are synchronous — there is never a resting order."""
        self._audit("cancel", {"order_id": order_id, "result": "no_resting_orders"})
        return False

    def square_off_all(self, current_prices: Optional[Dict[str, float]] = None, **kw: Any) -> Dict[str, Any]:
        """Sell every open paper position. Prices from ``current_prices``
        mapping or fall back to avg cost (slippage still applied)."""
        self._audit("square_off_all", {"positions": "all", "price_source": "avg_cost_or_kw"})
        brokerage = self._get_brokerage()
        result: Dict[str, Any] = {"broker": self.name, "closed": [], "errors": []}
        prices = current_prices or kw.get("prices") or {}

        for symbol, qty in list(brokerage.positions.items()):
            qty = float(qty)
            if abs(qty) < 1e-9:
                continue
            side = "SELL" if qty > 0 else "BUY"
            px = float(prices.get(symbol) or brokerage.avg_cost.get(symbol, 0.0) or 0.0)
            if px <= 0:
                result["errors"].append(f"{symbol}: no price available")
                continue
            report = brokerage.execute_order(symbol, side, abs(qty), px)
            if report.get("status") == "filled":
                result["closed"].append({"symbol": symbol, "qty": abs(qty), "response": report})
            else:
                result["errors"].append(f"{symbol}: {report.get('reason', 'rejected')}")

        try:
            brokerage.save_log()
        except Exception:
            pass
        result["status"] = "ok" if not result["errors"] else "partial"
        return result
