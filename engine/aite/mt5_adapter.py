"""
ZERO AITE MT5 adapter — optional MetaTrader5 with full simulated fill path.

``MetaTrader5`` is lazy-imported only inside :meth:`MT5Adapter.connect`.
If the package is missing, initialize fails, or ``ZERO_AITE_MT5!=1``, every
order uses the in-process sim fill path against :class:`PaperFund`.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.paper_fund import PaperFund, get_paper_fund

_ADAPTER: Optional["MT5Adapter"] = None


def mt5_package_available() -> bool:
    """True if ``MetaTrader5`` can be imported (does not initialize the terminal)."""
    try:
        import MetaTrader5 as _mt5  # noqa: F401  # type: ignore
        return True
    except ImportError:
        return False


class MT5Adapter:
    """Connect + paper orders via MT5 demo, else simulated fills on PaperFund."""

    name: str = "mt5_paper"

    def __init__(self, fund: PaperFund | None = None) -> None:
        self.fund = fund if fund is not None else get_paper_fund()
        self._mt5: Any = None
        self.mode: str = "sim"  # sim | mt5_paper
        self.connected: bool = False
        self.last_error: Optional[str] = None
        self.order_log: List[Dict[str, Any]] = []

    # ── Lifecycle ────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Attempt MT5 initialize when enabled; otherwise stay on sim.

        Never raises. Lazy-imports MetaTrader5 only when ``cfg.MT5_ENABLED``.
        """
        if not cfg.MT5_ENABLED:
            self.mode = "sim"
            self.connected = False
            self.last_error = "ZERO_AITE_MT5!=1 — using simulated fills"
            return False

        try:
            import MetaTrader5 as mt5  # type: ignore  # lazy
        except ImportError:
            self._mt5 = None
            self.mode = "sim"
            self.connected = False
            self.last_error = "MetaTrader5 package not installed — pip install MetaTrader5"
            store.log_event("WARN", self.last_error)
            return False

        self._mt5 = mt5
        try:
            if not mt5.initialize():
                self.last_error = f"mt5.initialize failed: {mt5.last_error()}"
                self.mode = "sim"
                self.connected = False
                store.log_event("WARN", self.last_error)
                return False
            info = mt5.account_info()
            if info is None:
                self.last_error = "mt5.account_info() is None"
                self.mode = "sim"
                self.connected = False
                return False
            # Sync cash from MT5 account balance into ledger display fields
            self.fund.cash = float(info.balance)
            self.fund.equity = float(getattr(info, "equity", info.balance) or info.balance)
            self.fund.save()
            self.mode = "mt5_paper"
            self.connected = True
            self.last_error = None
            store.log_event("INFO", f"MT5 connected login={info.login} bal={info.balance}")
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            self.mode = "sim"
            self.connected = False
            store.log_event("ERROR", f"MT5 connect error: {exc}")
            return False

    def disconnect(self) -> None:
        if self._mt5 is not None and self.connected:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self.connected = False
        if self.mode == "mt5_paper":
            self.mode = "sim"

    def ensure_ready(self) -> str:
        """Return active mode; connect once if MT5 enabled and not yet tried."""
        if self.mode == "mt5_paper" and self.connected:
            return self.mode
        if cfg.MT5_ENABLED and self._mt5 is None and self.last_error is None:
            self.connect()
        return self.mode

    # ── Orders ───────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        *,
        bot_id: str = "",
        bot_name: str = "",
    ) -> Dict[str, Any]:
        """Paper order — MT5 TRADE_ACTION_DEAL when connected, else sim fill."""
        side = side.upper()
        quantity = float(quantity)
        price = float(price)
        if quantity <= 0 or price <= 0:
            return {"status": "rejected", "reason": "invalid qty/price", "mode": self.mode}

        self.ensure_ready()
        if self.mode == "mt5_paper" and self.connected and self._mt5 is not None:
            report = self._order_mt5(symbol, side, quantity, price, bot_id, bot_name)
        else:
            report = self._order_sim(symbol, side, quantity, price, bot_id, bot_name)

        self.order_log.append(report)
        if report.get("status") == "filled":
            store.log_trade(report)
        return report

    def _order_sim(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        bot_id: str,
        bot_name: str,
    ) -> Dict[str, Any]:
        slip = cfg.SLIPPAGE_BPS / 10000.0
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if side == "BUY":
            fill = price * (1.0 + slip)
        elif side == "SELL":
            fill = price * (1.0 - slip)
        else:
            return {"status": "rejected", "reason": f"bad side {side}", "mode": "sim"}

        ledger = self.fund.apply_fill(
            symbol, side, quantity, fill, bot_id=bot_id,
        )
        if not ledger.get("ok"):
            return {
                "status": "rejected",
                "reason": ledger.get("error", "ledger reject"),
                "mode": "sim",
            }

        realized = float(ledger.get("realized_pnl", 0.0) or 0.0)
        report: Dict[str, Any] = {
            "status": "filled",
            "side": side,
            "symbol": symbol,
            "quantity": quantity,
            "market_price": round(price, 4),
            "fill_price": round(fill, 4),
            "entry": round(fill, 4) if side == "BUY" else round(
                float((self.fund.positions.get(symbol) or {}).get("avg_cost", fill)), 4
            ),
            "exit": round(fill, 4) if side == "SELL" else None,
            "entry_time": ts,
            "exit_time": ts if side == "SELL" else None,
            "bot_id": bot_id,
            "bot_name": bot_name,
            "pnl": round(realized, 2),
            "pnl_pct": 0.0,
            "mode": "sim",
            "balance_after": round(self.fund.cash, 2),
            "equity_after": round(self.fund.equity, 2),
        }
        if side == "SELL" and fill > 0 and realized:
            # approximate pct vs fill notional
            notional = fill * quantity
            report["pnl_pct"] = round((realized / notional) * 100.0, 4) if notional else 0.0
        return report

    def _order_mt5(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        bot_id: str,
        bot_name: str,
    ) -> Dict[str, Any]:
        mt5 = self._mt5
        assert mt5 is not None
        mt5_sym = cfg.MT5_SYMBOL_MAP.get(symbol, symbol)
        if not mt5.symbol_select(mt5_sym, True):
            self.last_error = f"symbol_select failed for {mt5_sym}"
            return self._order_sim(symbol, side, quantity, price, bot_id, bot_name)

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
            "comment": f"AITE:{(bot_name or bot_id)[:12]}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = getattr(result, "comment", None) if result is not None else None
            err = err or mt5.last_error()
            self.last_error = str(err)
            store.log_event("ERROR", f"MT5 order failed: {err}")
            return self._order_sim(symbol, side, quantity, price, bot_id, bot_name)

        fill = float(result.price)
        # Mirror fill into local ledger for unified cash/equity reporting
        self.fund.apply_fill(symbol, side, quantity, fill, bot_id=bot_id)
        info = mt5.account_info()
        if info:
            self.fund.cash = float(info.balance)
            self.fund.equity = float(getattr(info, "equity", info.balance) or info.balance)
            self.fund.save()

        return {
            "status": "filled",
            "side": side,
            "symbol": symbol,
            "quantity": quantity,
            "market_price": round(price, 4),
            "fill_price": round(fill, 4),
            "entry": round(fill, 4),
            "exit": None,
            "entry_time": ts,
            "exit_time": None,
            "bot_id": bot_id,
            "bot_name": bot_name,
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "mode": "mt5_paper",
            "ticket": int(result.order),
            "balance_after": round(self.fund.cash, 2),
            "equity_after": round(self.fund.equity, 2),
        }

    # ── Status / positions ───────────────────────────────────────────────

    def positions(self) -> List[Dict[str, Any]]:
        if self.mode == "mt5_paper" and self.connected and self._mt5 is not None:
            try:
                raw = self._mt5.positions_get()
                if raw:
                    out: List[Dict[str, Any]] = []
                    for p in raw:
                        out.append({
                            "symbol": p.symbol,
                            "quantity": float(p.volume),
                            "avg_cost": float(p.price_open),
                            "product": "MT5_PAPER",
                            "raw": {"ticket": int(p.ticket), "profit": float(p.profit)},
                        })
                    return out
            except Exception:
                pass
        return self.fund.positions_list()

    def orders(self) -> List[Dict[str, Any]]:
        return list(self.order_log)

    def status(self) -> Dict[str, Any]:
        snap = self.fund.snapshot()
        return {
            "mode": self.mode,
            "connected": self.connected,
            "mt5_package": mt5_package_available(),
            "mt5_enabled_flag": cfg.MT5_ENABLED,
            "cash": snap["cash"],
            "equity": snap["equity"],
            "paper_fund": snap["paper_fund"],
            "positions": snap["positions"],
            "error": self.last_error,
            "orders_logged": len(self.order_log),
        }


def get_mt5_adapter(fund: PaperFund | None = None) -> MT5Adapter:
    """Process-wide singleton adapter."""
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = MT5Adapter(fund=fund)
    elif fund is not None:
        _ADAPTER.fund = fund
    return _ADAPTER


def reset_mt5_adapter_singleton() -> None:
    """Test helper — drop cached singleton."""
    global _ADAPTER
    if _ADAPTER is not None:
        try:
            _ADAPTER.disconnect()
        except Exception:
            pass
    _ADAPTER = None
