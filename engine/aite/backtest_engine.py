"""
ZERO AITE vectorized / simple OHLC backtest engine.

Runs genomes on historical bars (data.historical or synthetic offline).
Reuses exam signal + ATR risk model without duplicating OOS gates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from engine.aite import config as cfg
from engine.aite.exam import _simulate, _timestamps, load_market_frame
from engine.aite.indicators import compute_features
from engine.aite.models import BotGenome


def load_bars(symbol: str, bars: int | None = None) -> pd.DataFrame:
    """OHLCV for backtests — historical adapter with synthetic fallback."""
    return load_market_frame(symbol, bars=bars)


def _metrics_from_sim(
    trades: List[Dict[str, Any]],
    equity: np.ndarray,
    rets: np.ndarray,
) -> Dict[str, Any]:
    trade_rets = rets[rets != 0] if rets is not None and len(rets) else np.array([])
    if len(trade_rets) >= 2:
        mu = float(np.mean(trade_rets))
        sd = float(np.std(trade_rets))
        sharpe = float((mu / sd) * np.sqrt(252.0)) if sd > 1e-12 else 0.0
    else:
        sharpe = 0.0

    peak = np.maximum.accumulate(equity) if len(equity) else np.array([1.0])
    dd = (equity - peak) / np.where(peak == 0, 1.0, peak) if len(equity) else np.array([0.0])
    max_dd = float(abs(dd.min())) if len(dd) else 0.0
    total_ret = float(equity[-1] - 1.0) if len(equity) else 0.0
    n_trades = len(trades)
    wins = sum(1 for t in trades if float(t.get("pnl_pct", 0)) > 0)
    hit_rate = (wins / n_trades) if n_trades else 0.0
    avg_pnl = float(np.mean([float(t.get("pnl_pct", 0)) for t in trades])) if trades else 0.0

    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(total_ret, 4),
        "max_dd": round(max_dd, 4),
        "n_trades": n_trades,
        "hit_rate": round(hit_rate, 4),
        "avg_pnl_pct": round(avg_pnl, 4),
        "equity_end": round(float(equity[-1]), 6) if len(equity) else 1.0,
    }


def backtest(
    genome: BotGenome,
    df: pd.DataFrame | None = None,
    commission_bps: float | None = None,
    slippage_bps: float | None = None,
) -> Dict[str, Any]:
    """
    Simple bar-by-bar OHLC backtest for one genome.
    Returns metrics + trades + equity sample. Never raises.
    """
    commission_bps = cfg.COMMISSION_BPS if commission_bps is None else commission_bps
    slippage_bps = cfg.SLIPPAGE_BPS if slippage_bps is None else slippage_bps
    try:
        if df is None:
            df = load_bars(genome.symbol)
        feats = compute_features(df)
        if feats.empty or len(feats) < 40:
            return {
                "bot_id": genome.bot_id,
                "ok": False,
                "reason": "insufficient_bars",
                "trades": [],
                "equity": [],
                "metrics": {
                    "sharpe": 0.0, "total_return": 0.0, "max_dd": 1.0,
                    "n_trades": 0, "hit_rate": 0.0, "avg_pnl_pct": 0.0,
                    "equity_end": 1.0,
                },
            }

        times = _timestamps(df if df is not None else feats)
        if len(times) != len(feats):
            times = [f"bar_{i}" for i in range(len(feats))]

        trades, equity, rets = _simulate(
            feats, genome, times, commission_bps, slippage_bps,
        )
        metrics = _metrics_from_sim(trades, equity, rets)
        step = max(1, len(equity) // 50)
        return {
            "bot_id": genome.bot_id,
            "ok": True,
            "reason": "ok",
            "trades": trades,
            "equity": [round(float(x), 6) for x in equity[::step]],
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "bot_id": genome.bot_id,
            "ok": False,
            "reason": f"backtest_error: {exc}",
            "trades": [],
            "equity": [],
            "metrics": {
                "sharpe": 0.0, "total_return": 0.0, "max_dd": 1.0,
                "n_trades": 0, "hit_rate": 0.0, "avg_pnl_pct": 0.0,
                "equity_end": 1.0,
            },
        }


def backtest_vectorized_signals(
    closes: np.ndarray,
    signals: np.ndarray,
    hold_bars: int = 12,
    commission_bps: float = 2.0,
    slippage_bps: float = 3.0,
) -> Dict[str, Any]:
    """
    Fast vectorized long/flat backtest from precomputed +/-1/0 signals.
    Useful for batch screening without ATR stops.
    """
    n = len(closes)
    if n < 2 or len(signals) != n:
        return {"sharpe": 0.0, "total_return": 0.0, "n_trades": 0, "equity": [1.0]}

    fee = (commission_bps + slippage_bps) / 10000.0
    pos = np.zeros(n, dtype=float)
    entry_i = -1
    side = 0
    for i in range(1, n):
        if side != 0 and (i - entry_i) >= max(1, hold_bars):
            side = 0
        if side == 0 and signals[i] != 0:
            side = int(np.sign(signals[i]))
            entry_i = i
        pos[i] = side

    # Mark-to-market on close-to-close when in position; charge fee on flips
    rets = np.zeros(n, dtype=float)
    pct = np.diff(closes, prepend=closes[0]) / np.where(closes == 0, 1.0, closes)
    rets[1:] = pos[:-1] * pct[1:]
    flips = np.abs(np.diff(pos, prepend=0)) > 0
    rets[flips] -= fee
    equity = np.cumprod(1.0 + rets)
    trade_mask = flips & (pos != 0)
    n_trades = int(np.sum(trade_mask))
    trade_rets = rets[rets != 0]
    if len(trade_rets) >= 2 and float(np.std(trade_rets)) > 1e-12:
        sharpe = float(np.mean(trade_rets) / np.std(trade_rets) * np.sqrt(252.0))
    else:
        sharpe = 0.0
    return {
        "sharpe": round(sharpe, 4),
        "total_return": round(float(equity[-1] - 1.0), 4),
        "n_trades": n_trades,
        "equity": [round(float(x), 6) for x in equity[:: max(1, n // 50)]],
    }


def backtest_batch(
    genomes: List[BotGenome],
    frames: Dict[str, pd.DataFrame] | None = None,
) -> List[Dict[str, Any]]:
    """Backtest many genomes; caches frames by symbol."""
    frames = dict(frames or {})
    results: List[Dict[str, Any]] = []
    for g in genomes:
        if g.symbol not in frames:
            frames[g.symbol] = load_bars(g.symbol)
        results.append(backtest(g, frames[g.symbol]))
    return results


def rank_by_backtest(
    genomes: List[BotGenome],
    frames: Dict[str, pd.DataFrame] | None = None,
    top_k: int | None = None,
) -> Tuple[List[BotGenome], List[Dict[str, Any]]]:
    """Sort genomes by backtest sharpe × (1+return)/(1+dd)."""
    results = backtest_batch(genomes, frames)
    scored: List[Tuple[float, BotGenome, Dict[str, Any]]] = []
    for g, r in zip(genomes, results):
        m = r.get("metrics") or {}
        score = float(m.get("sharpe", 0)) * (1.0 + max(float(m.get("total_return", 0)), -0.5))
        score /= 1.0 + max(float(m.get("max_dd", 0)), 0.0)
        g._bt_score = score  # type: ignore[attr-defined]
        scored.append((score, g, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    if top_k is not None:
        scored = scored[: max(0, top_k)]
    return [g for _, g, _ in scored], [r for _, _, r in scored]
