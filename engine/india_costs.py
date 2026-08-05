"""
engine.india_costs — Indian (NSE) transaction-cost model for ZERO.
====================================================================

Precise, configurable per-head statutory costs for the walk-forward
backtester: STT, exchange transaction charges, GST, SEBI turnover fee,
stamp duty, discount-broker brokerage, and adverse slippage.

Design contract (shared conventions):
  * Pure standard library + dataclasses. Always imports; no numpy/pandas,
    no network, no I/O at import time.
  * Every rate is a field on ``IndiaCostModel`` with a sane default;
    callers may override any field via the constructor.
  * Public functions NEVER raise on bad input — they clamp or return
    zeroed results carrying an ``'error'`` key.

Rates are in decimal fractions of turnover unless noted (e.g. 0.001 = 0.1%).
Turnover for options is PREMIUM turnover (qty * premium), matching how
NSE levies STT/txn charges on options.

Typical use by the backtester::

    from engine.india_costs import net_pnl
    result = net_pnl(entry_price=2450.0, exit_price=2462.5, qty=50,
                     segment="equity_intraday", side="long")
    pnl_after_costs = result["net"]

NOTE: verify current rates — Union Budget changes these periodically.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Optional

__all__ = [
    "Segment",
    "IndiaCostModel",
    "DEFAULT_COST_MODEL",
    "compute_trade_cost",
    "net_pnl",
    "apply_to_trades",
    "breakeven_points",
    "options_exercise_stt",
]

Segment = Literal["equity_intraday", "equity_delivery", "futures", "options"]

_SEGMENTS: tuple = ("equity_intraday", "equity_delivery", "futures", "options")
_ORDER_SIDES: tuple = ("buy", "sell")
_TRADE_SIDES: tuple = ("long", "short")
_BPS: float = 1e-4  # one basis point as a decimal fraction


@dataclass
class IndiaCostModel:
    """Configurable Indian brokerage + statutory charge rates.

    All values are decimal fractions of turnover unless stated otherwise.
    Construct with overrides only where needed::

        model = IndiaCostModel(brokerage_flat=0.0, brokerage_pct=0.0003)

    # verify current rates — Union Budget changes these periodically
    """

    # ── STT (Securities Transaction Tax) ────────────────────────────────
    # verify current rates — Union Budget changes these periodically
    stt_delivery: float = 0.001          # equity delivery, BOTH sides
    stt_intraday_sell: float = 0.00025   # equity intraday, sell side only
    stt_futures_sell: float = 0.000125   # futures, sell side only
    stt_options_sell: float = 0.000625   # options, sell side only, on premium
    stt_options_exercise: float = 0.00125  # exercised options, on settlement value

    # ── Exchange transaction charges (NSE, both sides) ──────────────────
    # verify current rates — Union Budget changes these periodically
    txn_equity: float = 0.0000297        # NSE cash segment (~0.00297%)
    txn_futures: float = 0.0000173       # NSE futures (~0.00173%)
    txn_options: float = 0.0003503       # NSE options, on premium (~0.03503%)

    # ── GST ──────────────────────────────────────────────────────────────
    gst_rate: float = 0.18               # on (brokerage + txn + SEBI) ONLY

    # ── SEBI turnover fee ────────────────────────────────────────────────
    sebi_charge: float = 0.000001        # ₹10 per crore of turnover

    # ── Stamp duty (buy side only, per state of the client — NSE rates) ──
    # verify current rates — Union Budget changes these periodically
    stamp_delivery_buy: float = 0.00015  # delivery, buy only
    stamp_intraday_buy: float = 0.00003  # intraday, buy only
    stamp_futures_buy: float = 0.00002   # futures, buy only
    stamp_options_buy: float = 0.00003   # options, buy only, on premium

    # ── Brokerage (discount-broker style) ────────────────────────────────
    brokerage_flat: float = 20.0         # ₹ flat per executed order (per side)
    brokerage_pct: float = 0.0           # optional % of turnover (full-service)

    # ── Slippage ─────────────────────────────────────────────────────────
    slippage_bps: float = 0.5            # basis points, applied adversely per side


DEFAULT_COST_MODEL = IndiaCostModel()


# ── Internal helpers ────────────────────────────────────────────────────────

def _resolve(model: Optional[IndiaCostModel]) -> IndiaCostModel:
    """Return the caller's model, or the shared default (never raises)."""
    return model if isinstance(model, IndiaCostModel) else DEFAULT_COST_MODEL


def _is_finite_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _nn(x: float) -> float:
    """Clamp a computed charge to >= 0 (defends against negative-rate configs)."""
    return x if x > 0.0 else 0.0


def _stt_rate(segment: str, side: str, m: IndiaCostModel) -> float:
    if segment == "equity_delivery":
        return m.stt_delivery  # both sides
    if side != "sell":
        return 0.0             # intraday / F&O: STT only on the sell leg
    if segment == "equity_intraday":
        return m.stt_intraday_sell
    if segment == "futures":
        return m.stt_futures_sell
    return m.stt_options_sell    # options, on premium


def _txn_rate(segment: str, m: IndiaCostModel) -> float:
    if segment in ("equity_intraday", "equity_delivery"):
        return m.txn_equity
    if segment == "futures":
        return m.txn_futures
    return m.txn_options         # options, on premium


def _stamp_rate(segment: str, side: str, m: IndiaCostModel) -> float:
    if side != "buy":
        return 0.0               # stamp duty is buy-side only
    if segment == "equity_delivery":
        return m.stamp_delivery_buy
    if segment == "equity_intraday":
        return m.stamp_intraday_buy
    if segment == "futures":
        return m.stamp_futures_buy
    return m.stamp_options_buy


def _zero_breakdown(error: Optional[str] = None) -> dict:
    out = {
        "turnover": 0.0,
        "stt": 0.0,
        "txn": 0.0,
        "gst": 0.0,
        "sebi": 0.0,
        "stamp": 0.0,
        "brokerage": 0.0,
        "slippage": 0.0,
        "total": 0.0,
    }
    if error:
        out["error"] = error
    return out


# ── Public API ──────────────────────────────────────────────────────────────

def compute_trade_cost(
    side: Literal["buy", "sell"],
    qty: float,
    price: float,
    segment: Segment,
    model: Optional[IndiaCostModel] = None,
) -> dict:
    """Per-head cost breakdown for ONE executed order (one side).

    Returns {'turnover', 'stt', 'txn', 'gst', 'sebi', 'stamp', 'brokerage',
    'slippage', 'total'} — all in ₹. Slippage is modelled as an adverse
    price move of ``slippage_bps`` and charged in ₹; statutory heads are
    computed on quoted turnover (qty * price). Options use premium turnover.

    Never raises: invalid input returns a zeroed breakdown with 'error'.
    """
    if side not in _ORDER_SIDES:
        return _zero_breakdown(f"invalid side: {side!r}")
    if segment not in _SEGMENTS:
        return _zero_breakdown(f"invalid segment: {segment!r}")
    if not _is_finite_number(qty) or not _is_finite_number(price):
        return _zero_breakdown("qty/price must be finite numbers")
    if qty <= 0 or price <= 0:
        return _zero_breakdown("qty and price must be positive")

    m = _resolve(model)
    qty_f, price_f = float(qty), float(price)
    turnover = qty_f * price_f

    stt = _nn(turnover * _stt_rate(segment, side, m))
    txn = _nn(turnover * _txn_rate(segment, m))
    sebi = _nn(turnover * m.sebi_charge)
    stamp = _nn(turnover * _stamp_rate(segment, side, m))
    brokerage = _nn(m.brokerage_flat + turnover * m.brokerage_pct)
    # GST is levied on (brokerage + exchange txn + SEBI) only — NOT on STT/stamp.
    gst = _nn((brokerage + txn + sebi) * m.gst_rate)
    slippage = _nn(turnover * m.slippage_bps * _BPS)

    total = stt + txn + gst + sebi + stamp + brokerage + slippage
    return {
        "turnover": turnover,
        "stt": stt,
        "txn": txn,
        "gst": gst,
        "sebi": sebi,
        "stamp": stamp,
        "brokerage": brokerage,
        "slippage": slippage,
        "total": total,
    }


def net_pnl(
    entry_price: float,
    exit_price: float,
    qty: float,
    segment: Segment,
    side: Literal["long", "short"] = "long",
    model: Optional[IndiaCostModel] = None,
) -> dict:
    """Round-trip PnL after both legs' costs.

    Returns {'gross_points', 'gross', 'total_costs', 'net', 'cost_drag_pct',
    'entry_cost', 'exit_cost'} — ₹ values; 'cost_drag_pct' is
    total_costs / |gross| * 100 (0.0 when gross == 0). Side-dependent
    treatment falls out naturally: e.g. intraday-equity STT hits only the
    sell leg, stamp duty only the buy leg, options are charged on premium
    turnover. For a short, the entry leg is the sell and the exit leg is
    the buy. Never raises: bad input returns zeros with 'error'.
    """
    zero = {
        "gross_points": 0.0,
        "gross": 0.0,
        "total_costs": 0.0,
        "net": 0.0,
        "cost_drag_pct": 0.0,
    }
    if segment not in _SEGMENTS:
        zero["error"] = f"invalid segment: {segment!r}"
        return zero
    if side not in _TRADE_SIDES:
        zero["error"] = f"invalid side: {side!r}"
        return zero
    if not all(_is_finite_number(v) for v in (entry_price, exit_price, qty)):
        zero["error"] = "entry_price/exit_price/qty must be finite numbers"
        return zero
    if entry_price <= 0 or exit_price <= 0 or qty <= 0:
        zero["error"] = "entry_price, exit_price and qty must be positive"
        return zero

    m = _resolve(model)
    qty_f = float(qty)

    if side == "long":
        entry_side, exit_side = "buy", "sell"
        gross_points = float(exit_price) - float(entry_price)
    else:
        entry_side, exit_side = "sell", "buy"
        gross_points = float(entry_price) - float(exit_price)

    entry_cost = compute_trade_cost(entry_side, qty_f, float(entry_price), segment, m)
    exit_cost = compute_trade_cost(exit_side, qty_f, float(exit_price), segment, m)
    if "error" in entry_cost or "error" in exit_cost:
        zero["error"] = entry_cost.get("error") or exit_cost.get("error")
        return zero

    gross = gross_points * qty_f
    total_costs = entry_cost["total"] + exit_cost["total"]
    net = gross - total_costs
    cost_drag_pct = (total_costs / abs(gross) * 100.0) if gross != 0.0 else 0.0

    return {
        "gross_points": gross_points,
        "gross": gross,
        "total_costs": total_costs,
        "net": net,
        "cost_drag_pct": cost_drag_pct,
        "entry_cost": entry_cost,
        "exit_cost": exit_cost,
    }


def apply_to_trades(
    trades: list,
    segment: Segment,
    model: Optional[IndiaCostModel] = None,
) -> list:
    """Annotate a list of trade dicts with costs and net PnL.

    Each trade dict needs entry_price / exit_price / qty; 'side' is
    optional ('long' default, or 'short'). Returns a NEW list of dict
    copies (inputs are not mutated), same order, each with added keys:
    'costs' (₹ total round-trip cost), 'net_pnl' (₹), 'gross_pnl' (₹),
    and 'cost_detail' (full net_pnl breakdown). Trades that fail
    validation get zeroed values plus an 'error' key. Never raises.
    """
    if not isinstance(trades, list):
        return []
    out = []
    for trade in trades:
        if not isinstance(trade, dict):
            out.append({"costs": 0.0, "net_pnl": 0.0, "gross_pnl": 0.0,
                        "error": "trade is not a dict"})
            continue
        result = net_pnl(
            entry_price=trade.get("entry_price"),
            exit_price=trade.get("exit_price"),
            qty=trade.get("qty"),
            segment=segment,
            side=trade.get("side", "long"),
            model=model,
        )
        annotated = dict(trade)
        annotated["costs"] = result["total_costs"]
        annotated["net_pnl"] = result["net"]
        annotated["gross_pnl"] = result["gross"]
        annotated["cost_detail"] = result
        if "error" in result:
            annotated["error"] = result["error"]
        out.append(annotated)
    return out


def breakeven_points(
    price: float,
    qty: float,
    segment: Segment,
    model: Optional[IndiaCostModel] = None,
) -> float:
    """Points a LONG round trip entered at `price` must move to cover costs.

    Solves x such that x*qty == buy_cost(price) + sell_cost(price + x).
    The cost function is affine in the exit price, so the affine solve is
    exact (computed from compute_trade_cost itself — no duplicated rates).
    (A short round trip differs negligibly; both legs' charges are the
    same heads.) Returns 0.0 on invalid input. Never raises.
    """
    if segment not in _SEGMENTS:
        return 0.0
    if not _is_finite_number(price) or not _is_finite_number(qty):
        return 0.0
    if price <= 0 or qty <= 0:
        return 0.0

    m = _resolve(model)
    qty_f, price_f = float(qty), float(price)

    def round_trip_cost_in_points(exit_price: float) -> float:
        buy = compute_trade_cost("buy", qty_f, price_f, segment, m)
        sell = compute_trade_cost("sell", qty_f, exit_price, segment, m)
        if "error" in buy or "error" in sell:
            return float("nan")
        return (buy["total"] + sell["total"]) / qty_f

    g0 = round_trip_cost_in_points(price_f)
    g1 = round_trip_cost_in_points(price_f + 1.0)
    if not (math.isfinite(g0) and math.isfinite(g1)):
        return 0.0
    slope = g1 - g0          # how many extra points of cost per +1 exit point
    denom = 1.0 - slope
    if abs(denom) < 1e-12:   # degenerate config (costs >= 100% of move)
        return g0
    x = g0 / denom
    return x if x > 0.0 else 0.0


def options_exercise_stt(
    settlement_value: float,
    model: Optional[IndiaCostModel] = None,
) -> float:
    """STT (₹) on an exercised option: stt_options_exercise * settlement value.

    Applies when an option is held to expiry and exercised — charged on the
    settlement value, not the premium. Returns 0.0 on invalid input.
    """
    if not _is_finite_number(settlement_value) or settlement_value <= 0:
        return 0.0
    m = _resolve(model)
    return _nn(float(settlement_value) * m.stt_options_exercise)


if __name__ == "__main__":
    # Smoke self-check (no I/O at import; runs only when executed directly).
    _r = net_pnl(100.0, 101.0, 100, "equity_intraday")
    assert _r["gross"] == 100.0 and _r["total_costs"] > 0.0
    assert _r["net"] < _r["gross"]
    _be = breakeven_points(100.0, 100, "equity_intraday")
    assert _be > 0.0
    _bad = compute_trade_cost("hold", -1, 0, "crypto")  # type: ignore[arg-type]
    assert _bad["total"] == 0.0 and "error" in _bad
    _t = apply_to_trades([{"entry_price": 100, "exit_price": 99, "qty": 10,
                           "side": "short"}], "equity_delivery")
    assert _t[0]["net_pnl"] < _t[0]["gross_pnl"]
    print("india_costs self-check OK")
