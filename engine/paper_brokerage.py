"""
ZERO Paper Brokerage
=====================

LEAN-style simulated execution engine.  Processes trade orders with strict
slippage modelling to eliminate unrealistic paper trading profits.

Features:
  - Configurable slippage on both buy and sell sides.
  - Position tracking per symbol.
  - Full execution log with timestamps.
  - Balance and P&L reporting.

Self-contained — no coupling to the live prediction pipeline or UI.
Called by the quant_orchestrator after Monte Carlo risk checks pass.
"""

from __future__ import annotations

import datetime
import os
import json
from typing import Dict, List, Optional

from engine.quant_config import (
    PAPER_INITIAL_CAPITAL,
    PAPER_SLIPPAGE_PCT,
)

# Persistence
_TRADE_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "db", "paper_trades.json"
)


class PaperBrokerage:
    """Slippage-aware paper trading simulator."""

    def __init__(
        self,
        initial_capital: float | None = None,
        slippage_pct: float | None = None,
    ):
        self.initial_capital = initial_capital or PAPER_INITIAL_CAPITAL
        self.balance = self.initial_capital
        self.slippage_pct = slippage_pct or PAPER_SLIPPAGE_PCT
        self.positions: Dict[str, float] = {}      # symbol -> quantity
        self.avg_cost: Dict[str, float] = {}        # symbol -> avg cost basis
        self.trade_log: List[Dict] = []
        self.pnl_closed: float = 0.0                # realized P&L

    # ── Order execution ──────────────────────────────────────────────────

    def execute_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
    ) -> dict:
        """Execute a trade with slippage applied.

        Parameters
        ----------
        symbol : str
            Instrument symbol (e.g. "NIFTY 50").
        side : str
            "BUY" or "SELL".
        quantity : float
            Number of units.
        current_price : float
            Market price before slippage.

        Returns
        -------
        dict
            Execution report with fill price, cost, and updated balance.
        """
        if quantity <= 0 or current_price <= 0:
            return {"status": "rejected", "reason": "invalid quantity or price"}

        side = side.upper()
        timestamp = datetime.datetime.now().isoformat()

        if side == "BUY":
            # Slippage works against the buyer (higher fill)
            fill_price = current_price * (1.0 + self.slippage_pct)
            cost = fill_price * quantity

            if cost > self.balance:
                return {
                    "status": "rejected",
                    "reason": f"insufficient balance ({self.balance:.2f} < {cost:.2f})",
                }

            self.balance -= cost

            # Update position and average cost
            prev_qty = self.positions.get(symbol, 0.0)
            prev_cost = self.avg_cost.get(symbol, 0.0)
            new_qty = prev_qty + quantity
            if new_qty > 0:
                self.avg_cost[symbol] = (
                    (prev_cost * prev_qty + fill_price * quantity) / new_qty
                )
            self.positions[symbol] = new_qty

            report = {
                "status": "filled",
                "side": "BUY",
                "symbol": symbol,
                "quantity": quantity,
                "market_price": round(current_price, 2),
                "fill_price": round(fill_price, 2),
                "cost": round(cost, 2),
                "slippage_applied": round(fill_price - current_price, 4),
                "balance_after": round(self.balance, 2),
                "position_after": round(new_qty, 4),
                "timestamp": timestamp,
            }

        elif side == "SELL":
            held = self.positions.get(symbol, 0.0)
            if held < quantity:
                return {
                    "status": "rejected",
                    "reason": f"insufficient position ({held} < {quantity})",
                }

            # Slippage works against the seller (lower fill)
            fill_price = current_price * (1.0 - self.slippage_pct)
            revenue = fill_price * quantity

            self.balance += revenue

            # Realized P&L
            cost_basis = self.avg_cost.get(symbol, current_price)
            trade_pnl = (fill_price - cost_basis) * quantity
            self.pnl_closed += trade_pnl

            new_qty = held - quantity
            self.positions[symbol] = new_qty
            if new_qty <= 0:
                self.positions.pop(symbol, None)
                self.avg_cost.pop(symbol, None)

            report = {
                "status": "filled",
                "side": "SELL",
                "symbol": symbol,
                "quantity": quantity,
                "market_price": round(current_price, 2),
                "fill_price": round(fill_price, 2),
                "revenue": round(revenue, 2),
                "realized_pnl": round(trade_pnl, 2),
                "slippage_applied": round(current_price - fill_price, 4),
                "balance_after": round(self.balance, 2),
                "position_after": round(new_qty, 4),
                "timestamp": timestamp,
            }

        else:
            return {"status": "rejected", "reason": f"unknown side: {side}"}

        self.trade_log.append(report)
        return report

    # ── Portfolio reporting ───────────────────────────────────────────────

    def portfolio_summary(self, current_prices: Dict[str, float] | None = None) -> dict:
        """Return current portfolio state with unrealized P&L."""
        current_prices = current_prices or {}

        positions_detail = {}
        total_unrealized = 0.0

        for symbol, qty in self.positions.items():
            if qty <= 0:
                continue
            cost_basis = self.avg_cost.get(symbol, 0.0)
            mkt_price = current_prices.get(symbol, cost_basis)
            unrealized = (mkt_price - cost_basis) * qty
            total_unrealized += unrealized
            positions_detail[symbol] = {
                "quantity": round(qty, 4),
                "avg_cost": round(cost_basis, 2),
                "market_price": round(mkt_price, 2),
                "unrealized_pnl": round(unrealized, 2),
            }

        equity = self.balance + sum(
            current_prices.get(s, self.avg_cost.get(s, 0)) * q
            for s, q in self.positions.items()
            if q > 0
        )

        return {
            "cash_balance": round(self.balance, 2),
            "equity": round(equity, 2),
            "positions": positions_detail,
            "realized_pnl": round(self.pnl_closed, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(self.pnl_closed + total_unrealized, 2),
            "return_pct": round(
                (equity - self.initial_capital) / self.initial_capital * 100, 4
            ),
            "total_trades": len(self.trade_log),
        }

    def trade_statistics(self) -> dict:
        """Compute win rate, avg win, avg loss from trade history."""
        sells = [t for t in self.trade_log if t.get("side") == "SELL"]
        if not sells:
            return {
                "win_rate": 0.5,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "n_trades": 0,
            }

        wins = [t["realized_pnl"] for t in sells if t.get("realized_pnl", 0) > 0]
        losses = [abs(t["realized_pnl"]) for t in sells if t.get("realized_pnl", 0) < 0]

        n = len(sells)
        win_rate = len(wins) / n if n > 0 else 0.5
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0

        return {
            "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "n_trades": n,
        }

    # ── Persistence ──────────────────────────────────────────────────────

    def save_log(self):
        """Persist the trade log to disk."""
        os.makedirs(os.path.dirname(_TRADE_LOG_PATH), exist_ok=True)
        payload = {
            "initial_capital": self.initial_capital,
            "balance": round(self.balance, 2),
            "positions": {s: round(q, 4) for s, q in self.positions.items()},
            "avg_cost": {s: round(c, 2) for s, c in self.avg_cost.items()},
            "pnl_closed": round(self.pnl_closed, 2),
            "trades": self.trade_log,
            "saved_at": datetime.datetime.now().isoformat(),
        }
        with open(_TRADE_LOG_PATH, "w") as f:
            json.dump(payload, f, indent=2)

    @classmethod
    def load(cls) -> "PaperBrokerage":
        """Load brokerage state from disk."""
        if not os.path.exists(_TRADE_LOG_PATH):
            return cls()
        try:
            with open(_TRADE_LOG_PATH) as f:
                data = json.load(f)
            broker = cls(initial_capital=data.get("initial_capital", PAPER_INITIAL_CAPITAL))
            broker.balance = data.get("balance", broker.initial_capital)
            broker.positions = data.get("positions", {})
            broker.avg_cost = data.get("avg_cost", {})
            broker.pnl_closed = data.get("pnl_closed", 0.0)
            broker.trade_log = data.get("trades", [])
            return broker
        except (json.JSONDecodeError, IOError):
            return cls()


if __name__ == "__main__":
    print("=== Paper Brokerage ===\n")

    broker = PaperBrokerage(initial_capital=50000)

    # Execute some test trades
    r1 = broker.execute_order("NIFTY 50", "BUY", 10, 24500.0)
    print(f"BUY:  {r1}")

    r2 = broker.execute_order("NIFTY 50", "SELL", 5, 24600.0)
    print(f"SELL: {r2}")

    # Portfolio summary
    summary = broker.portfolio_summary({"NIFTY 50": 24550.0})
    print(f"\nPortfolio: {json.dumps(summary, indent=2)}")

    # Trade stats
    stats = broker.trade_statistics()
    print(f"\nTrade Stats: {stats}")
