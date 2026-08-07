"""
ZERO AITE MT5 paper broker — MetaTrader5 package with graceful sim fallback.

Live path (when ZERO_AITE_MT5=1 and MetaTrader5 installed + terminal running):
  initialize → symbol_select → order_send (TRADE_ACTION_DEAL) on demo/paper account.

Fallback: local PaperBrokerage-style fills with slippage (always available).
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store


class MT5PaperBroker:
    """Paper execution via MT5 or in-process simulator."""

    def __init__(self, initial_capital: float | None = None):
        self.initial_capital = float(initial_capital or cfg.DEFAULT_PAPER_FUND)
        self.balance = self.initial_capital
        self.positions: Dict[str, float] = {}
        self.avg_cost: Dict[str, float] = {}
        self.mode = "sim"
        self._mt5 = None
        self._connected = False
        self.last_error: Optional[str] = None
        self._try_connect()

    def _try_connect(self) -> None:
        if not cfg.MT5_ENABLED:
            self.mode = "sim"
            self.last_error = "ZERO_AITE_MT5!=1 — using local paper sim"
            return
        try:
            import MetaTrader5 as mt5  # type: ignore
            self._mt5 = mt5
            if not mt5.initialize():
                self.last_error = f"mt5.initialize failed: {mt5.last_error()}"
                self.mode = "sim"
                self._connected = False
                return
            info = mt5.account_info()
            if info is None:
                self.last_error = "mt5.account_info() is None"
                self.mode = "sim"
                return
            self.balance = float(info.balance)
            self.mode = "mt5_paper"
            self._connected = True
            self.last_error = None
            store.log_event("INFO", f"MT5 connected login={info.login} bal={info.balance}")
        except ImportError:
            self.last_error = "MetaTrader5 package not installed — pip install MetaTrader5"
            self.mode = "sim"
            self._connected = False
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.mode = "sim"
            self._connected = False

    def status(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "connected": self._connected,
            "balance": round(self.balance, 2),
            "positions": dict(self.positions),
            "error": self.last_error,
            "mt5_enabled_flag": cfg.MT5_ENABLED,
        }

    def _resolve_symbol(self, symbol: str) -> str:
        return cfg.MT5_SYMBOL_MAP.get(symbol, symbol)

    def execute(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        bot_id: str = "",
        bot_name: str = "",
    ) -> Dict[str, Any]:
        side = side.upper()
        if quantity <= 0 or price <= 0:
            return {"status": "rejected", "reason": "invalid qty/price", "mode": self.mode}

        if self.mode == "mt5_paper" and self._mt5 is not None:
            return self._execute_mt5(symbol, side, quantity, price, bot_id, bot_name)
        return self._execute_sim(symbol, side, quantity, price, bot_id, bot_name)

    def _execute_sim(
        self, symbol: str, side: str, quantity: float, price: float,
        bot_id: str, bot_name: str,
    ) -> Dict[str, Any]:
        slip = cfg.SLIPPAGE_BPS / 10000.0
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if side == "BUY":
            fill = price * (1.0 + slip)
            cost = fill * quantity
            if cost > self.balance:
                return {"status": "rejected", "reason": "insufficient balance", "mode": "sim"}
            self.balance -= cost
            prev = self.positions.get(symbol, 0.0)
            prev_cost = self.avg_cost.get(symbol, 0.0)
            new_q = prev + quantity
            self.avg_cost[symbol] = ((prev_cost * prev + fill * quantity) / new_q) if new_q else fill
            self.positions[symbol] = new_q
            report = {
                "status": "filled", "side": "BUY", "symbol": symbol,
                "quantity": quantity, "fill_price": round(fill, 4),
                "entry": round(fill, 4), "exit": None,
                "entry_time": ts, "exit_time": None,
                "bot_id": bot_id, "bot_name": bot_name,
                "pnl": 0.0, "pnl_pct": 0.0, "mode": "sim",
                "balance_after": round(self.balance, 2),
            }
        elif side == "SELL":
            held = self.positions.get(symbol, 0.0)
            # Allow short / close: if no position, open short notionally
            fill = price * (1.0 - slip)
            if held >= quantity:
                cost_basis = self.avg_cost.get(symbol, price)
                pnl = (fill - cost_basis) * quantity
                self.balance += fill * quantity
                new_q = held - quantity
                if new_q <= 0:
                    self.positions.pop(symbol, None)
                    self.avg_cost.pop(symbol, None)
                else:
                    self.positions[symbol] = new_q
                report = {
                    "status": "filled", "side": "SELL", "symbol": symbol,
                    "quantity": quantity, "fill_price": round(fill, 4),
                    "entry": round(cost_basis, 4), "exit": round(fill, 4),
                    "entry_time": ts, "exit_time": ts,
                    "bot_id": bot_id, "bot_name": bot_name,
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((fill / cost_basis - 1.0) * 100, 4) if cost_basis else 0.0,
                    "mode": "sim", "balance_after": round(self.balance, 2),
                }
            else:
                # open short / reduce
                self.balance += fill * quantity  # credit short proceeds
                self.positions[symbol] = held - quantity
                self.avg_cost[symbol] = fill
                report = {
                    "status": "filled", "side": "SELL", "symbol": symbol,
                    "quantity": quantity, "fill_price": round(fill, 4),
                    "entry": round(fill, 4), "exit": None,
                    "entry_time": ts, "exit_time": None,
                    "bot_id": bot_id, "bot_name": bot_name,
                    "pnl": 0.0, "pnl_pct": 0.0, "mode": "sim",
                    "balance_after": round(self.balance, 2),
                }
        else:
            return {"status": "rejected", "reason": f"bad side {side}", "mode": "sim"}

        store.log_trade(report)
        return report

    def _execute_mt5(
        self, symbol: str, side: str, quantity: float, price: float,
        bot_id: str, bot_name: str,
    ) -> Dict[str, Any]:
        mt5 = self._mt5
        assert mt5 is not None
        mt5_sym = self._resolve_symbol(symbol)
        if not mt5.symbol_select(mt5_sym, True):
            # fall back to sim on symbol miss
            self.last_error = f"symbol_select failed for {mt5_sym}"
            return self._execute_sim(symbol, side, quantity, price, bot_id, bot_name)

        tick = mt5.symbol_info_tick(mt5_sym)
        order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
        fill_price = float(tick.ask if side == "BUY" else tick.bid) if tick else price
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": mt5_sym,
            "volume": float(quantity),
            "type": order_type,
            "price": fill_price,
            "deviation": 20,
            "magic": 260807,
            "comment": f"AITE:{bot_name[:12]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = getattr(result, "comment", None) or mt5.last_error()
            self.last_error = str(err)
            store.log_event("ERROR", f"MT5 order failed: {err}")
            return self._execute_sim(symbol, side, quantity, price, bot_id, bot_name)

        info = mt5.account_info()
        if info:
            self.balance = float(info.balance)
        report = {
            "status": "filled", "side": side, "symbol": symbol,
            "quantity": quantity, "fill_price": round(float(result.price), 4),
            "entry": round(float(result.price), 4), "exit": None,
            "entry_time": ts, "exit_time": None,
            "bot_id": bot_id, "bot_name": bot_name,
            "pnl": 0.0, "pnl_pct": 0.0, "mode": "mt5_paper",
            "ticket": int(result.order),
            "balance_after": round(self.balance, 2),
        }
        store.log_trade(report)
        return report

    def shutdown(self) -> None:
        if self._mt5 is not None and self._connected:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
            self._connected = False


_BROKER: Optional[MT5PaperBroker] = None


def get_mt5_broker(initial_capital: float | None = None) -> MT5PaperBroker:
    global _BROKER
    if _BROKER is None:
        _BROKER = MT5PaperBroker(initial_capital=initial_capital)
    return _BROKER
