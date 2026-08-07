"""
ZERO AITE paper fund — user-sized cash/equity/positions ledger.

Persists to ``db/aite/fund.json`` via :mod:`engine.aite.store`.
Compatible with existing ``paper_fund`` / ``cash`` / ``equity`` keys used by
portfolio construction.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store

_FUND: Optional["PaperFund"] = None


class PaperFund:
    """Cash / equity / positions ledger for AITE paper trading."""

    def __init__(
        self,
        fund_size: float | None = None,
        *,
        currency: str = "INR",
        auto_load: bool = True,
    ) -> None:
        self.currency = currency
        self.paper_fund = float(fund_size if fund_size is not None else cfg.DEFAULT_PAPER_FUND)
        self.cash = self.paper_fund
        self.equity = self.paper_fund
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> {qty, avg_cost, bot_id?}
        self.realized_pnl = 0.0
        self.updated_at = time.time()
        if auto_load:
            self.load()
            if fund_size is not None and abs(float(fund_size) - self.paper_fund) > 1e-9:
                self.set_fund_size(float(fund_size))

    # ── Fund size ────────────────────────────────────────────────────────

    def set_fund_size(self, amount: float, *, reset_positions: bool = False) -> Dict[str, Any]:
        """User sets (or resizes) the paper fund.

        If ``reset_positions`` is True, clears open positions and sets cash=equity=amount.
        Otherwise scales cash by the ratio of new/old fund size (positions unchanged).
        """
        amount = float(amount)
        if amount <= 0:
            return {"ok": False, "error": "fund size must be > 0"}

        old = self.paper_fund or cfg.DEFAULT_PAPER_FUND
        self.paper_fund = amount

        if reset_positions or not self.positions:
            self.positions = {}
            self.cash = amount
            self.equity = amount
            self.realized_pnl = 0.0
        else:
            scale = amount / old if old > 0 else 1.0
            self.cash = round(self.cash * scale, 2)
            self._recompute_equity()

        self.save()
        store.log_event("INFO", f"Paper fund set to {amount:,.2f} {self.currency}")
        return {"ok": True, **self.snapshot()}

    # ── Ledger ops ───────────────────────────────────────────────────────

    def apply_fill(
        self,
        symbol: str,
        side: str,
        quantity: float,
        fill_price: float,
        *,
        bot_id: str = "",
    ) -> Dict[str, Any]:
        """Update cash/positions from a filled order. Returns ledger delta report."""
        side = side.upper()
        quantity = float(quantity)
        fill_price = float(fill_price)
        if quantity <= 0 or fill_price <= 0:
            return {"ok": False, "error": "invalid quantity or fill_price"}

        pos = self.positions.get(symbol) or {"qty": 0.0, "avg_cost": 0.0, "bot_id": bot_id}
        qty = float(pos.get("qty", 0.0))
        avg = float(pos.get("avg_cost", 0.0))

        if side == "BUY":
            cost = fill_price * quantity
            if cost > self.cash + 1e-9:
                return {
                    "ok": False,
                    "error": f"insufficient cash ({self.cash:.2f} < {cost:.2f})",
                }
            self.cash -= cost
            new_qty = qty + quantity
            if new_qty > 0:
                pos["avg_cost"] = ((avg * qty) + (fill_price * quantity)) / new_qty
            pos["qty"] = new_qty
            if bot_id:
                pos["bot_id"] = bot_id
            self.positions[symbol] = pos
            realized = 0.0
        elif side == "SELL":
            if qty + 1e-9 < quantity:
                return {
                    "ok": False,
                    "error": f"insufficient position ({qty} < {quantity})",
                }
            proceeds = fill_price * quantity
            realized = (fill_price - avg) * quantity
            self.cash += proceeds
            self.realized_pnl += realized
            new_qty = qty - quantity
            if new_qty <= 1e-12:
                self.positions.pop(symbol, None)
            else:
                pos["qty"] = new_qty
                self.positions[symbol] = pos
        else:
            return {"ok": False, "error": f"unknown side: {side}"}

        self._recompute_equity()
        self.save()
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "fill_price": round(fill_price, 4),
            "realized_pnl": round(realized, 2),
            "cash": round(self.cash, 2),
            "equity": round(self.equity, 2),
        }

    def mark_to_market(self, prices: Dict[str, float] | None = None) -> float:
        """Recompute equity from cash + marked positions. Persists."""
        self._recompute_equity(prices or {})
        self.save()
        return self.equity

    def _recompute_equity(self, prices: Dict[str, float] | None = None) -> None:
        prices = prices or {}
        mtm = 0.0
        for symbol, pos in self.positions.items():
            qty = float(pos.get("qty", 0.0))
            if abs(qty) < 1e-12:
                continue
            px = float(prices.get(symbol, pos.get("avg_cost", 0.0)) or 0.0)
            mtm += px * qty
        self.equity = round(self.cash + mtm, 2)
        self.updated_at = time.time()

    # ── Views ────────────────────────────────────────────────────────────

    def snapshot(self, prices: Dict[str, float] | None = None) -> Dict[str, Any]:
        prices = prices or {}
        positions_detail: Dict[str, Any] = {}
        unrealized = 0.0
        for symbol, pos in self.positions.items():
            qty = float(pos.get("qty", 0.0))
            if abs(qty) < 1e-12:
                continue
            avg = float(pos.get("avg_cost", 0.0))
            mkt = float(prices.get(symbol, avg) or avg)
            u = (mkt - avg) * qty
            unrealized += u
            positions_detail[symbol] = {
                "qty": round(qty, 4),
                "avg_cost": round(avg, 4),
                "market_price": round(mkt, 4),
                "unrealized_pnl": round(u, 2),
                "bot_id": pos.get("bot_id", ""),
            }
        equity = round(self.cash + sum(
            float(prices.get(s, p.get("avg_cost", 0.0)) or 0.0) * float(p.get("qty", 0.0))
            for s, p in self.positions.items()
        ), 2)
        return {
            "paper_fund": round(self.paper_fund, 2),
            "cash": round(self.cash, 2),
            "equity": equity,
            "currency": self.currency,
            "positions": positions_detail,
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(unrealized, 2),
            "total_pnl": round(self.realized_pnl + unrealized, 2),
            "return_pct": round(
                ((equity - self.paper_fund) / self.paper_fund * 100.0) if self.paper_fund else 0.0,
                4,
            ),
            "updated_at": self.updated_at,
        }

    def positions_list(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for symbol, pos in self.positions.items():
            qty = float(pos.get("qty", 0.0))
            if abs(qty) < 1e-12:
                continue
            out.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_cost": float(pos.get("avg_cost", 0.0)),
                "bot_id": pos.get("bot_id", ""),
                "product": "PAPER",
            })
        return out

    # ── Persistence ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_fund": round(self.paper_fund, 2),
            "cash": round(self.cash, 2),
            "equity": round(self.equity, 2),
            "currency": self.currency,
            "positions": {
                s: {
                    "qty": round(float(p.get("qty", 0.0)), 4),
                    "avg_cost": round(float(p.get("avg_cost", 0.0)), 4),
                    "bot_id": p.get("bot_id", ""),
                }
                for s, p in self.positions.items()
                if abs(float(p.get("qty", 0.0))) > 1e-12
            },
            "realized_pnl": round(self.realized_pnl, 2),
            "updated_at": self.updated_at,
        }

    def save(self) -> bool:
        self.updated_at = time.time()
        return store.save_fund(self.to_dict())

    def load(self) -> "PaperFund":
        data = store.load_fund()
        self.paper_fund = float(data.get("paper_fund", cfg.DEFAULT_PAPER_FUND))
        self.cash = float(data.get("cash", self.paper_fund))
        self.equity = float(data.get("equity", self.cash))
        self.currency = str(data.get("currency", "INR"))
        self.realized_pnl = float(data.get("realized_pnl", 0.0))
        raw_pos = data.get("positions") or {}
        self.positions = {}
        if isinstance(raw_pos, dict):
            for symbol, p in raw_pos.items():
                if isinstance(p, dict):
                    self.positions[symbol] = {
                        "qty": float(p.get("qty", p.get("quantity", 0.0)) or 0.0),
                        "avg_cost": float(p.get("avg_cost", 0.0) or 0.0),
                        "bot_id": str(p.get("bot_id", "") or ""),
                    }
                else:
                    # legacy: symbol -> quantity only
                    self.positions[symbol] = {
                        "qty": float(p or 0.0),
                        "avg_cost": 0.0,
                        "bot_id": "",
                    }
        self.updated_at = float(data.get("updated_at") or time.time())
        return self


def get_paper_fund(fund_size: float | None = None) -> PaperFund:
    """Process-wide singleton ledger (loads ``db/aite/fund.json``)."""
    global _FUND
    if _FUND is None:
        _FUND = PaperFund(fund_size=fund_size, auto_load=True)
    elif fund_size is not None:
        _FUND.set_fund_size(float(fund_size))
    return _FUND


def reset_paper_fund_singleton() -> None:
    """Test helper — drop cached singleton."""
    global _FUND
    _FUND = None
