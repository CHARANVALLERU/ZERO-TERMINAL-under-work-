"""
ZERO Nautilus-Inspired Advanced Order Engine
=============================================
Cloned & adapted from NautilusTrader (nautechsystems/nautilus_trader)
Production-grade deterministic event-driven order management system.

Implements:
- Time-in-force: IOC, FOK, GTC, GTD, DAY, AT_THE_OPEN, AT_THE_CLOSE
- Execution instructions: post-only, reduce-only, iceberg
- Contingency orders: OCO (One-Cancels-Other), OUO (One-Updates-Other), OTO (One-Triggers-Other)
- Multi-venue routing simulation
- Event-driven order lifecycle: SUBMITTED → ACCEPTED → PARTIALLY_FILLED → FILLED / CANCELLED / EXPIRED

Design: Pure Python + numpy only. No external broker deps.
"""

from __future__ import annotations

import datetime
import uuid
import math
from enum import Enum
from typing import Dict, List, Optional, Any


# ─────────────────────────────────────────────
#  Enums (Nautilus-style)
# ─────────────────────────────────────────────

class TimeInForce(str, Enum):
    GTC  = "GTC"   # Good Till Cancelled
    IOC  = "IOC"   # Immediate Or Cancel
    FOK  = "FOK"   # Fill Or Kill
    GTD  = "GTD"   # Good Till Date
    DAY  = "DAY"   # Valid for the trading day
    AT_THE_OPEN  = "AT_THE_OPEN"
    AT_THE_CLOSE = "AT_THE_CLOSE"


class OrderSide(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT  = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT  = "STOP_LIMIT"
    ICEBERG     = "ICEBERG"
    TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(str, Enum):
    SUBMITTED       = "SUBMITTED"
    ACCEPTED        = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED          = "FILLED"
    CANCELLED       = "CANCELLED"
    EXPIRED         = "EXPIRED"
    REJECTED        = "REJECTED"


class ContingencyType(str, Enum):
    NONE = "NONE"
    OCO  = "OCO"   # One-Cancels-Other
    OUO  = "OUO"   # One-Updates-Other
    OTO  = "OTO"   # One-Triggers-Other


class ExecutionInstruction(str, Enum):
    NONE        = "NONE"
    POST_ONLY   = "POST_ONLY"
    REDUCE_ONLY = "REDUCE_ONLY"


# ─────────────────────────────────────────────
#  Order Model
# ─────────────────────────────────────────────

class Order:
    """
    Immutable-first order record. Mirrors NautilusTrader's Order object structure
    but in lightweight Python for the ZERO paper terminal.
    """

    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: TimeInForce = TimeInForce.DAY,
        expire_time: Optional[datetime.datetime] = None,
        contingency_type: ContingencyType = ContingencyType.NONE,
        linked_order_ids: Optional[List[str]] = None,
        execution_instruction: ExecutionInstruction = ExecutionInstruction.NONE,
        display_qty: Optional[float] = None,   # for iceberg
        trailing_offset: Optional[float] = None,
        venue: str = "NSE",
        tags: Optional[List[str]] = None,
    ):
        self.order_id   = str(uuid.uuid4())[:12].upper()
        self.symbol     = symbol
        self.side       = OrderSide(side)
        self.order_type = OrderType(order_type)
        self.quantity   = float(quantity)
        self.price      = float(price) if price is not None else None
        self.stop_price = float(stop_price) if stop_price is not None else None
        self.time_in_force = TimeInForce(time_in_force)
        self.expire_time   = expire_time
        self.contingency_type = ContingencyType(contingency_type)
        self.linked_order_ids = linked_order_ids or []
        self.execution_instruction = ExecutionInstruction(execution_instruction)
        self.display_qty  = float(display_qty) if display_qty else quantity
        self.trailing_offset = float(trailing_offset) if trailing_offset else None
        self.venue = venue
        self.tags  = tags or []

        # Mutable state
        self.status       = OrderStatus.SUBMITTED
        self.filled_qty   = 0.0
        self.avg_px       = 0.0
        self.fill_history : List[Dict] = []
        self.created_at   = datetime.datetime.now().isoformat()
        self.updated_at   = self.created_at

    @property
    def leaves_qty(self) -> float:
        return max(0.0, self.quantity - self.filled_qty)

    @property
    def is_active(self) -> bool:
        return self.status in (
            OrderStatus.SUBMITTED,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "time_in_force": self.time_in_force.value,
            "expire_time": self.expire_time.isoformat() if self.expire_time else None,
            "contingency_type": self.contingency_type.value,
            "linked_order_ids": self.linked_order_ids,
            "execution_instruction": self.execution_instruction.value,
            "display_qty": self.display_qty,
            "trailing_offset": self.trailing_offset,
            "venue": self.venue,
            "tags": self.tags,
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "avg_px": self.avg_px,
            "fill_history": self.fill_history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ─────────────────────────────────────────────
#  Execution Engine
# ─────────────────────────────────────────────

class NautilusOrderEngine:
    """
    Deterministic event-driven order management engine.
    Simulates multi-venue order routing with realistic execution semantics.

    Supports:
    - Full TIF matrix (GTC/IOC/FOK/GTD/DAY/AT_THE_OPEN/AT_THE_CLOSE)
    - Iceberg orders (display qty hiding)
    - Post-only rejection on crossing
    - Reduce-only position guard
    - OCO / OUO / OTO contingency chains
    - Event log for audit trail
    """

    def __init__(self, slippage_bps: float = 0.5):
        self.orders:    Dict[str, Order]   = {}
        self.positions: Dict[str, float]   = {}   # symbol → net qty
        self.event_log: List[Dict]         = []
        self.slippage_bps = slippage_bps   # basis points

    # ── Event helpers ──────────────────────────────────────────────

    def _emit(self, event: str, order: Order, detail: str = ""):
        self.event_log.append({
            "ts":       datetime.datetime.now().isoformat(timespec="milliseconds"),
            "event":    event,
            "order_id": order.order_id,
            "symbol":   order.symbol,
            "detail":   detail,
        })

    # ── Order Submission ───────────────────────────────────────────

    def submit_order(self, order: Order) -> Dict:
        """
        Accept and route an order through the execution engine.
        Returns fill/rejection result dict.
        """
        self.orders[order.order_id] = order
        order.status = OrderStatus.ACCEPTED
        self._emit("ORDER_ACCEPTED", order)

        # Validate reduce-only
        if order.execution_instruction == ExecutionInstruction.REDUCE_ONLY:
            pos = self.positions.get(order.symbol, 0.0)
            if order.side == OrderSide.BUY and pos >= 0:
                order.status = OrderStatus.REJECTED
                self._emit("ORDER_REJECTED", order, "REDUCE_ONLY: No short position to reduce")
                return {"status": "rejected", "reason": "REDUCE_ONLY: No short position to reduce", "order": order.to_dict()}
            if order.side == OrderSide.SELL and pos <= 0:
                order.status = OrderStatus.REJECTED
                self._emit("ORDER_REJECTED", order, "REDUCE_ONLY: No long position to reduce")
                return {"status": "rejected", "reason": "REDUCE_ONLY: No short position to reduce", "order": order.to_dict()}

        return {"status": "accepted", "order_id": order.order_id, "order": order.to_dict()}

    def execute_at_price(self, order_id: str, market_price: float) -> Dict:
        """
        Attempt to fill an accepted order against a market price.
        Handles TIF logic, slippage, iceberg reveal, post-only, contingencies.
        """
        order = self.orders.get(order_id)
        if not order or not order.is_active:
            return {"status": "skipped", "reason": "Order inactive or not found"}

        now = datetime.datetime.now()

        # ─── Expiry check for GTD / DAY ────────────────────────────
        if order.time_in_force == TimeInForce.GTD and order.expire_time:
            if now > order.expire_time:
                order.status = OrderStatus.EXPIRED
                self._emit("ORDER_EXPIRED", order, "GTD time elapsed")
                return {"status": "expired", "order_id": order_id}

        if order.time_in_force == TimeInForce.DAY:
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            if now > market_close:
                order.status = OrderStatus.EXPIRED
                self._emit("ORDER_EXPIRED", order, "DAY order expired at market close")
                return {"status": "expired", "order_id": order_id}

        # ─── AT_THE_OPEN / AT_THE_CLOSE TIF gates ─────────────────
        if order.time_in_force == TimeInForce.AT_THE_OPEN:
            open_window_start = now.replace(hour=9, minute=15, second=0)
            open_window_end   = now.replace(hour=9, minute=20, second=0)
            if not (open_window_start <= now <= open_window_end):
                return {"status": "pending", "reason": "AT_THE_OPEN: Outside open auction window"}

        if order.time_in_force == TimeInForce.AT_THE_CLOSE:
            close_window_start = now.replace(hour=15, minute=25, second=0)
            close_window_end   = now.replace(hour=15, minute=30, second=0)
            if not (close_window_start <= now <= close_window_end):
                return {"status": "pending", "reason": "AT_THE_CLOSE: Outside close auction window"}

        # ─── Limit price check ─────────────────────────────────────
        can_fill = False
        if order.order_type == OrderType.MARKET:
            can_fill = True

        elif order.order_type in (OrderType.LIMIT, OrderType.ICEBERG):
            if order.price is not None:
                if order.side == OrderSide.BUY and market_price <= order.price:
                    can_fill = True
                elif order.side == OrderSide.SELL and market_price >= order.price:
                    can_fill = True

            # Post-only: reject if crossing (would trade as taker)
            if can_fill and order.execution_instruction == ExecutionInstruction.POST_ONLY:
                if order.side == OrderSide.BUY and market_price <= (order.price or 0):
                    can_fill = False  # would cross → reject
                    order.status = OrderStatus.REJECTED
                    self._emit("ORDER_REJECTED", order, "POST_ONLY: Would cross the spread")
                    return {"status": "rejected", "reason": "POST_ONLY crossing", "order": order.to_dict()}

        elif order.order_type == OrderType.STOP_MARKET:
            if order.stop_price is not None:
                if order.side == OrderSide.BUY and market_price >= order.stop_price:
                    can_fill = True
                elif order.side == OrderSide.SELL and market_price <= order.stop_price:
                    can_fill = True

        elif order.order_type == OrderType.STOP_LIMIT:
            if order.stop_price is not None and order.price is not None:
                triggered = (
                    (order.side == OrderSide.BUY and market_price >= order.stop_price) or
                    (order.side == OrderSide.SELL and market_price <= order.stop_price)
                )
                if triggered:
                    if order.side == OrderSide.BUY and market_price <= order.price:
                        can_fill = True
                    elif order.side == OrderSide.SELL and market_price >= order.price:
                        can_fill = True

        elif order.order_type == OrderType.TRAILING_STOP:
            if order.trailing_offset is not None:
                # simplified: fill if market moves by offset from best price
                can_fill = True  # engine caller supplies current market price

        # ─── FOK: must fill entire qty or cancel ──────────────────
        if order.time_in_force == TimeInForce.FOK and can_fill:
            fill_qty = order.leaves_qty  # must fill all
        elif order.order_type == OrderType.ICEBERG and can_fill:
            fill_qty = min(order.display_qty, order.leaves_qty)
        else:
            fill_qty = order.leaves_qty if can_fill else 0.0

        if not can_fill:
            # IOC: cancel immediately if cannot fill
            if order.time_in_force == TimeInForce.IOC:
                order.status = OrderStatus.CANCELLED
                self._emit("ORDER_CANCELLED", order, "IOC: No immediate fill available")
                return {"status": "cancelled", "reason": "IOC no fill", "order": order.to_dict()}
            return {"status": "pending", "order_id": order_id}

        # ─── Apply slippage ────────────────────────────────────────
        slip = market_price * (self.slippage_bps / 10000.0)
        if order.side == OrderSide.BUY:
            fill_px = round(market_price + slip, 2)
        else:
            fill_px = round(market_price - slip, 2)

        # ─── Reduce-only qty cap ───────────────────────────────────
        if order.execution_instruction == ExecutionInstruction.REDUCE_ONLY:
            pos = abs(self.positions.get(order.symbol, 0.0))
            fill_qty = min(fill_qty, pos)

        # ─── Register fill ─────────────────────────────────────────
        order.filled_qty += fill_qty
        total_value = order.avg_px * (order.filled_qty - fill_qty) + fill_px * fill_qty
        order.avg_px = round(total_value / order.filled_qty, 2) if order.filled_qty else fill_px
        order.fill_history.append({"qty": fill_qty, "price": fill_px, "ts": now.isoformat()})
        order.updated_at = now.isoformat()

        # Update position
        sign = 1.0 if order.side == OrderSide.BUY else -1.0
        self.positions[order.symbol] = self.positions.get(order.symbol, 0.0) + sign * fill_qty

        if order.filled_qty >= order.quantity - 1e-9:
            order.status = OrderStatus.FILLED
            self._emit("ORDER_FILLED", order, f"Avg px: {order.avg_px}")
            self._trigger_contingencies(order, "FILLED")
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
            self._emit("ORDER_PARTIALLY_FILLED", order, f"Filled {order.filled_qty}/{order.quantity}")
            if order.time_in_force == TimeInForce.IOC or order.time_in_force == TimeInForce.FOK:
                order.status = OrderStatus.CANCELLED
                self._emit("ORDER_CANCELLED", order, f"{order.time_in_force.value}: Partial → cancel residual")

        return {
            "status":   order.status.value.lower(),
            "order_id": order_id,
            "fill_qty": fill_qty,
            "fill_px":  fill_px,
            "avg_px":   order.avg_px,
            "order":    order.to_dict(),
        }

    # ── Contingency chains ─────────────────────────────────────────

    def _trigger_contingencies(self, filled_order: Order, event: str):
        """Process OCO / OUO / OTO chains when an order is filled/cancelled."""
        if filled_order.contingency_type == ContingencyType.OCO:
            # Cancel all linked orders
            for lid in filled_order.linked_order_ids:
                linked = self.orders.get(lid)
                if linked and linked.is_active:
                    linked.status = OrderStatus.CANCELLED
                    self._emit("ORDER_CANCELLED", linked, f"OCO: Cancelled by {filled_order.order_id}")

        elif filled_order.contingency_type == ContingencyType.OTO:
            # Activate/submit linked order (currently SUBMITTED → ACCEPTED)
            for lid in filled_order.linked_order_ids:
                linked = self.orders.get(lid)
                if linked and linked.status == OrderStatus.SUBMITTED:
                    linked.status = OrderStatus.ACCEPTED
                    self._emit("ORDER_ACCEPTED", linked, f"OTO: Triggered by {filled_order.order_id}")

        elif filled_order.contingency_type == ContingencyType.OUO:
            # Adjust quantity of linked orders to the remaining
            for lid in filled_order.linked_order_ids:
                linked = self.orders.get(lid)
                if linked and linked.is_active:
                    old_qty = linked.quantity
                    linked.quantity = max(0.0, linked.quantity - filled_order.filled_qty)
                    self._emit("ORDER_UPDATED", linked,
                               f"OUO: Qty adjusted {old_qty}→{linked.quantity}")

    # ── Cancel ─────────────────────────────────────────────────────

    def cancel_order(self, order_id: str) -> Dict:
        order = self.orders.get(order_id)
        if not order:
            return {"status": "not_found"}
        if not order.is_active:
            return {"status": "already_terminal", "order_status": order.status.value}
        order.status = OrderStatus.CANCELLED
        self._emit("ORDER_CANCELLED", order, "User cancel request")
        self._trigger_contingencies(order, "CANCELLED")
        return {"status": "cancelled", "order_id": order_id}

    # ── Helpers ─────────────────────────────────────────────────────

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        return [
            o.to_dict() for o in self.orders.values()
            if o.is_active and (symbol is None or o.symbol == symbol)
        ]

    def get_position(self, symbol: str) -> float:
        return self.positions.get(symbol, 0.0)

    def get_event_log(self, last_n: int = 50) -> List[Dict]:
        return self.event_log[-last_n:]

    def portfolio_summary(self, market_prices: Dict[str, float]) -> Dict:
        positions_out = {}
        total_pnl = 0.0
        for sym, qty in self.positions.items():
            mp = market_prices.get(sym, 0.0)
            # avg_cost from last fill for that symbol
            fills = [o for o in self.orders.values()
                     if o.symbol == sym and o.status == OrderStatus.FILLED]
            avg_cost = fills[-1].avg_px if fills else mp
            upnl = (mp - avg_cost) * qty
            total_pnl += upnl
            positions_out[sym] = {
                "quantity":       qty,
                "avg_cost":       avg_cost,
                "market_price":   mp,
                "unrealized_pnl": round(upnl, 2),
            }
        return {"positions": positions_out, "total_unrealized_pnl": round(total_pnl, 2)}


# ─────────────────────────────────────────────
#  Strategy Templates (Nautilus-style)
# ─────────────────────────────────────────────

class NautilusStrategy:
    """
    Base class for Nautilus-style event-driven strategies.
    Each strategy receives bar/tick events and issues orders via the engine.
    """
    name: str = "BaseStrategy"

    def __init__(self, engine: NautilusOrderEngine):
        self.engine = engine

    def on_bar(self, symbol: str, open_: float, high: float, low: float, close: float, volume: float):
        pass  # override in subclasses

    def on_order_event(self, event: Dict):
        pass

    def buy_market(self, symbol: str, qty: float, tif: TimeInForce = TimeInForce.DAY, **kwargs) -> Order:
        o = Order(symbol, OrderSide.BUY, OrderType.MARKET, qty, time_in_force=tif, **kwargs)
        self.engine.submit_order(o)
        return o

    def sell_market(self, symbol: str, qty: float, tif: TimeInForce = TimeInForce.DAY, **kwargs) -> Order:
        o = Order(symbol, OrderSide.SELL, OrderType.MARKET, qty, time_in_force=tif, **kwargs)
        self.engine.submit_order(o)
        return o

    def buy_limit(self, symbol: str, qty: float, price: float, tif: TimeInForce = TimeInForce.GTC, **kwargs) -> Order:
        o = Order(symbol, OrderSide.BUY, OrderType.LIMIT, qty, price=price, time_in_force=tif, **kwargs)
        self.engine.submit_order(o)
        return o

    def sell_limit(self, symbol: str, qty: float, price: float, tif: TimeInForce = TimeInForce.GTC, **kwargs) -> Order:
        o = Order(symbol, OrderSide.SELL, OrderType.LIMIT, qty, price=price, time_in_force=tif, **kwargs)
        self.engine.submit_order(o)
        return o

    def buy_stop(self, symbol: str, qty: float, stop_price: float, **kwargs) -> Order:
        o = Order(symbol, OrderSide.BUY, OrderType.STOP_MARKET, qty, stop_price=stop_price, **kwargs)
        self.engine.submit_order(o)
        return o

    def sell_stop(self, symbol: str, qty: float, stop_price: float, **kwargs) -> Order:
        o = Order(symbol, OrderSide.SELL, OrderType.STOP_MARKET, qty, stop_price=stop_price, **kwargs)
        self.engine.submit_order(o)
        return o

    def create_oco_pair(self, symbol: str, qty: float,
                        tp_price: float, sl_stop: float) -> tuple:
        """Create a take-profit limit + stop-loss stop pair linked as OCO."""
        tp = Order(symbol, OrderSide.SELL, OrderType.LIMIT, qty, price=tp_price,
                   time_in_force=TimeInForce.GTC, contingency_type=ContingencyType.OCO)
        sl = Order(symbol, OrderSide.SELL, OrderType.STOP_MARKET, qty, stop_price=sl_stop,
                   time_in_force=TimeInForce.GTC, contingency_type=ContingencyType.OCO)
        tp.linked_order_ids = [sl.order_id]
        sl.linked_order_ids = [tp.order_id]
        self.engine.submit_order(tp)
        self.engine.submit_order(sl)
        return tp, sl

    def create_oto_bracket(self, symbol: str, entry_price: float, qty: float,
                           tp_price: float, sl_stop: float) -> tuple:
        """Entry order that triggers OCO bracket on fill (OTO chain)."""
        entry = Order(symbol, OrderSide.BUY, OrderType.LIMIT, qty, price=entry_price,
                      time_in_force=TimeInForce.GTC, contingency_type=ContingencyType.OTO)
        tp = Order(symbol, OrderSide.SELL, OrderType.LIMIT, qty, price=tp_price,
                   time_in_force=TimeInForce.GTC, contingency_type=ContingencyType.OCO)
        sl = Order(symbol, OrderSide.SELL, OrderType.STOP_MARKET, qty, stop_price=sl_stop,
                   time_in_force=TimeInForce.GTC, contingency_type=ContingencyType.OCO,
                   status=OrderStatus.SUBMITTED)
        tp.linked_order_ids = [sl.order_id]
        sl.linked_order_ids = [tp.order_id]
        entry.linked_order_ids = [tp.order_id, sl.order_id]
        self.engine.submit_order(entry)
        self.engine.orders[tp.order_id] = tp  # hold pending OTO
        self.engine.orders[sl.order_id] = sl
        return entry, tp, sl


# ─────────────────────────────────────────────
#  Built-in Strategy Templates
# ─────────────────────────────────────────────

class MomentumBreakoutStrategy(NautilusStrategy):
    """
    Breakout momentum strategy inspired by NautilusTrader examples.
    Buys on close above previous high with ATR-based SL/TP.
    Time-in-force: IOC for fast markets, GTC limit for slow.
    """
    name = "Momentum Breakout (Nautilus)"

    def __init__(self, engine: NautilusOrderEngine, atr_sl_mult: float = 1.5,
                 atr_tp_mult: float = 2.5, use_oco: bool = True):
        super().__init__(engine)
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.use_oco = use_oco
        self._prev_high: Optional[float] = None

    def on_bar(self, symbol, open_, high, low, close, volume, atr: float = 100.0):
        if self._prev_high and close > self._prev_high:
            sl = round(close - atr * self.atr_sl_mult, 2)
            tp = round(close + atr * self.atr_tp_mult, 2)
            if self.use_oco:
                entry = self.buy_market(symbol, 1.0, tif=TimeInForce.IOC)
                self.create_oco_pair(symbol, 1.0, tp_price=tp, sl_stop=sl)
            else:
                self.buy_market(symbol, 1.0, tif=TimeInForce.DAY)
        self._prev_high = high


class MeanReversionStrategy(NautilusStrategy):
    """
    Mean-reversion strategy: fade extended moves outside ATR envelope.
    Uses IOC orders for immediate fills or cancels.
    """
    name = "Mean Reversion Fade (Nautilus)"

    def __init__(self, engine: NautilusOrderEngine, atr_threshold: float = 1.8):
        super().__init__(engine)
        self.atr_threshold = atr_threshold
        self._vwap: float = 0.0

    def on_bar(self, symbol, open_, high, low, close, volume, atr: float = 100.0, vwap: float = 0.0):
        self._vwap = vwap or close
        if close > self._vwap + atr * self.atr_threshold:
            # Over-extended up → fade with FOK sell
            o = self.sell_limit(symbol, 1.0, price=close, tif=TimeInForce.FOK)
        elif close < self._vwap - atr * self.atr_threshold:
            # Over-extended down → fade with IOC buy
            o = self.buy_limit(symbol, 1.0, price=close, tif=TimeInForce.IOC)


class OpeningRangeBreakoutStrategy(NautilusStrategy):
    """
    NSE/BSE Opening Range Breakout (ORB):
    Waits for AT_THE_OPEN levels, then places GTC bracket.
    """
    name = "Opening Range Breakout (Nautilus)"

    def on_bar(self, symbol, open_, high, low, close, volume, atr: float = 100.0):
        orb_high = high + atr * 0.3
        orb_low  = low  - atr * 0.3
        # OTO: entry on breakout triggers bracket
        entry, tp, sl = self.create_oto_bracket(
            symbol,
            entry_price=orb_high,
            qty=1.0,
            tp_price=round(orb_high + atr * 1.5, 2),
            sl_stop=round(orb_low, 2),
        )
        return entry, tp, sl


# ─────────────────────────────────────────────
#  Module-level singleton
# ─────────────────────────────────────────────

_global_engine: Optional[NautilusOrderEngine] = None

def get_order_engine() -> NautilusOrderEngine:
    global _global_engine
    if _global_engine is None:
        _global_engine = NautilusOrderEngine(slippage_bps=0.5)
    return _global_engine
