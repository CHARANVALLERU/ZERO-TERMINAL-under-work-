"""
ZERO AITE portfolio construction — 10–40 bots that don't all lose together.

Selects correlation-diversified survivors, allocates capital, and cuts fading bots.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.exam import load_market_frame, run_exam
from engine.aite.models import BotGenome, PortfolioState


def _return_series(genome: BotGenome, df) -> np.ndarray:
    exam = run_exam(genome, df)
    trades = exam.trades or []
    if not trades:
        return np.zeros(16)
    # Build sparse return path from trade pnl_pct
    rets = [float(t.get("pnl_pct", 0)) / 100.0 for t in trades]
    return np.asarray(rets, dtype=float)


def pairwise_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or len(b) < 3:
        return 0.0
    n = min(len(a), len(b))
    x, y = a[-n:], b[-n:]
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def select_portfolio(
    candidates: List[BotGenome],
    exams: Dict[str, Any] | None = None,
    target: int | None = None,
    max_corr: float | None = None,
    frames: Dict[str, Any] | None = None,
) -> Tuple[List[BotGenome], Dict[str, Dict[str, float]], List[str]]:
    """
    Greedy quality-diversity selection:
      1. Sort by OOS fitness / status=alive
      2. Add bot if |corr| with all selected < max_corr
      3. Fill to [MIN_BOTS, MAX_BOTS] target
    """
    target = target or cfg.TARGET_BOTS
    target = max(cfg.MIN_BOTS, min(cfg.MAX_BOTS, target))
    max_corr = max_corr if max_corr is not None else cfg.MAX_PAIRWISE_CORR
    frames = frames or {}

    # Prefer alive/exam-passed
    ranked = sorted(
        candidates,
        key=lambda b: (
            1 if b.status in ("alive", "exam") else 0,
            getattr(b, "_fit", 0.0),
        ),
        reverse=True,
    )

    selected: List[BotGenome] = []
    series: Dict[str, np.ndarray] = {}
    corr_matrix: Dict[str, Dict[str, float]] = {}
    rejected: List[str] = []

    for bot in ranked:
        if len(selected) >= target:
            break
        if bot.symbol not in frames:
            frames[bot.symbol] = load_market_frame(bot.symbol)
        s = _return_series(bot, frames[bot.symbol])
        series[bot.bot_id] = s

        ok = True
        for other in selected:
            c = pairwise_corr(s, series[other.bot_id])
            corr_matrix.setdefault(bot.bot_id, {})[other.bot_id] = round(c, 3)
            corr_matrix.setdefault(other.bot_id, {})[bot.bot_id] = round(c, 3)
            if abs(c) >= max_corr:
                ok = False
                rejected.append(f"{bot.name} corr={c:.2f} vs {other.name}")
                break
        if ok:
            bot.status = "alive"
            selected.append(bot)
            corr_matrix.setdefault(bot.bot_id, {})[bot.bot_id] = 1.0

    # If under-filled vs target, relax corr and add best remaining
    if len(selected) < target:
        for bot in ranked:
            if bot in selected:
                continue
            bot.status = "alive"
            selected.append(bot)
            if len(selected) >= target:
                break

    return selected[: min(target, cfg.MAX_BOTS)], corr_matrix, rejected


def allocate(
    bots: List[BotGenome],
    fund: float,
    fitness: Dict[str, float] | None = None,
) -> Dict[str, float]:
    """Inverse-volatility / fitness-weighted allocation capped per bot."""
    fitness = fitness or {}
    if not bots or fund <= 0:
        return {}
    scores = []
    for b in bots:
        scores.append(max(0.05, float(fitness.get(b.bot_id, 1.0))))
    arr = np.asarray(scores, dtype=float)
    weights = arr / arr.sum()
    # Cap
    cap = cfg.MAX_BOT_ALLOC_PCT
    weights = np.minimum(weights, cap)
    weights = weights / weights.sum()
    return {b.bot_id: round(float(fund * w), 2) for b, w in zip(bots, weights)}


def detect_fading(
    bot: BotGenome,
    recent_trades: List[Dict[str, Any]],
) -> bool:
    """True if bot's recent rolling PnL is fading below threshold."""
    mine = [t for t in recent_trades if t.get("bot_id") == bot.bot_id]
    mine = mine[-cfg.FADE_LOOKBACK_TRADES:]
    if len(mine) < max(4, cfg.FADE_LOOKBACK_TRADES // 2):
        return False
    rets = [float(t.get("pnl_pct", 0)) / 100.0 for t in mine]
    return float(np.sum(rets)) < cfg.FADE_PNL_THRESHOLD


def cut_fading(
    bots: List[BotGenome],
    trades: List[Dict[str, Any]] | None = None,
) -> Tuple[List[BotGenome], List[BotGenome]]:
    """Split into (kept, killed). Killed get status=dead for UI death blast."""
    trades = trades if trades is not None else store.load_trades(400)
    kept: List[BotGenome] = []
    killed: List[BotGenome] = []
    for b in bots:
        if detect_fading(b, trades):
            b.status = "dead"
            killed.append(b)
            store.log_event("WARN", f"Cut fading bot {b.name}", bot_id=b.bot_id)
        else:
            if b.status == "fading":
                b.status = "alive"
            kept.append(b)
    return kept, killed


def build_portfolio(
    candidates: List[BotGenome],
    paper_fund: float | None = None,
    target: int | None = None,
) -> PortfolioState:
    """End-to-end: select → allocate → persist."""
    fund_data = store.load_fund()
    fund = float(paper_fund if paper_fund is not None else fund_data.get("paper_fund", cfg.DEFAULT_PAPER_FUND))

    selected, corr, rejected = select_portfolio(candidates, target=target)
    for r in rejected[:20]:
        store.log_event("INFO", f"Portfolio reject: {r}")

    # Fitness from quick re-exam cache
    fitness: Dict[str, float] = {}
    frames: Dict[str, Any] = {}
    for b in selected:
        if b.symbol not in frames:
            frames[b.symbol] = load_market_frame(b.symbol)
        ex = run_exam(b, frames[b.symbol])
        fitness[b.bot_id] = ex.fitness

    allocs = allocate(selected, fund, fitness)
    state = PortfolioState(
        fund_cash=fund,
        equity=fund,
        bot_ids=[b.bot_id for b in selected],
        allocations=allocs,
        corr_matrix=corr,
        killed=[],
    )

    # Persist
    store.save_bots([b.to_dict() for b in selected])
    store.save_portfolio(state.to_dict())
    fund_data["paper_fund"] = fund
    fund_data["cash"] = fund
    fund_data["equity"] = fund
    store.save_fund(fund_data)
    store.log_event("INFO", f"Portfolio built: {len(selected)} bots, fund={fund:,.0f}")
    return state


def rebalance_and_cut() -> Dict[str, Any]:
    """Daemon tick: cut fading, re-allocate remaining."""
    raw = store.load_bots()
    bots = [BotGenome.from_dict(b) for b in raw]
    alive = [b for b in bots if b.status not in ("dead", "candidate")]
    kept, killed = cut_fading(alive)
    fund = store.load_fund()
    capital = float(fund.get("equity") or fund.get("paper_fund") or cfg.DEFAULT_PAPER_FUND)

    # Top up if below MIN_BOTS from candidates
    if len(kept) < cfg.MIN_BOTS:
        candidates = [b for b in bots if b.status in ("candidate", "exam") and b not in kept]
        need = cfg.MIN_BOTS - len(kept)
        kept.extend(candidates[:need])

    fitness = {b.bot_id: 1.0 for b in kept}
    allocs = allocate(kept, capital, fitness)
    port = store.load_portfolio()
    port["bot_ids"] = [b.bot_id for b in kept]
    port["allocations"] = allocs
    port["killed"] = list(port.get("killed") or []) + [b.bot_id for b in killed]
    port["equity"] = capital
    store.save_portfolio(port)

    # Update bot statuses
    all_bots = {b.bot_id: b for b in bots}
    for b in kept:
        all_bots[b.bot_id] = b
    for b in killed:
        all_bots[b.bot_id] = b
    store.save_bots([b.to_dict() for b in all_bots.values()])

    return {
        "kept": len(kept),
        "killed": [b.to_dict() for b in killed],
        "allocations": allocs,
    }
