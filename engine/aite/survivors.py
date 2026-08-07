"""
ZERO AITE survivor lifecycle — promote / demote / cut by live edge metrics.

Statuses: candidate → exam → alive ↔ fading → dead
Uses portfolio.detect_fading for cut decisions; edge scores drive promote/demote.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.models import BotGenome
from engine.aite.portfolio import detect_fading


def compute_live_edge(
    bot: BotGenome,
    trades: List[Dict[str, Any]] | None = None,
    lookback: int | None = None,
) -> Dict[str, float]:
    """
    Rolling live-edge metrics from recent trades for one bot.
    edge_score > 0 ⇒ positive edge; < 0 ⇒ fading.
    """
    lookback = lookback or cfg.FADE_LOOKBACK_TRADES
    trades = trades if trades is not None else store.load_trades(500)
    mine = [t for t in trades if t.get("bot_id") == bot.bot_id][-lookback:]

    if not mine:
        return {
            "n_trades": 0.0,
            "hit_rate": 0.0,
            "avg_pnl_pct": 0.0,
            "sum_pnl_pct": 0.0,
            "sharpe_proxy": 0.0,
            "edge_score": 0.0,
        }

    pnls = np.asarray([float(t.get("pnl_pct", 0)) / 100.0 for t in mine], dtype=float)
    n = float(len(pnls))
    hit = float(np.mean(pnls > 0))
    avg = float(np.mean(pnls))
    total = float(np.sum(pnls))
    sd = float(np.std(pnls))
    sharpe_proxy = float((avg / sd) * np.sqrt(max(n, 1.0))) if sd > 1e-12 else 0.0
    # Composite: reward hit-rate + cumulative return + sharpe; scale to ~[-1, 1+]
    edge = 0.40 * (hit - 0.45) + 0.35 * total + 0.25 * np.tanh(sharpe_proxy / 2.0)

    return {
        "n_trades": n,
        "hit_rate": round(hit, 4),
        "avg_pnl_pct": round(avg * 100, 4),
        "sum_pnl_pct": round(total * 100, 4),
        "sharpe_proxy": round(sharpe_proxy, 4),
        "edge_score": round(float(edge), 4),
    }


# Thresholds for promote / demote (relative to zero edge)
PROMOTE_EDGE = 0.02
DEMOTE_EDGE = -0.01
MIN_TRADES_FOR_EDGE = 4


def promote(bot: BotGenome, edge: Dict[str, float] | None = None) -> bool:
    """
    Promote candidate/exam → alive when live edge is positive.
    Returns True if status changed.
    """
    if bot.status not in ("candidate", "exam", "fading"):
        return False
    edge = edge or compute_live_edge(bot)
    # Exam-passed bots may promote with thin trade history; live edge needed otherwise
    if edge["n_trades"] < MIN_TRADES_FOR_EDGE and bot.status != "exam":
        return False
    if bot.status == "exam" or edge["edge_score"] >= PROMOTE_EDGE:
        bot.status = "alive"
        return True
    return False


def demote(bot: BotGenome, edge: Dict[str, float] | None = None) -> bool:
    """
    Demote alive → fading when live edge turns negative.
    Returns True if status changed.
    """
    if bot.status != "alive":
        return False
    edge = edge or compute_live_edge(bot)
    if edge["n_trades"] < MIN_TRADES_FOR_EDGE:
        return False
    if edge["edge_score"] <= DEMOTE_EDGE:
        bot.status = "fading"
        return True
    return False


def cut_bot(bot: BotGenome, reason: str = "cut", *, persist: bool = True) -> bool:
    """Hard-kill a bot (fading or worse)."""
    if bot.status == "dead":
        return False
    bot.status = "dead"
    if persist:
        store.log_event("WARN", f"Cut bot {bot.name}: {reason}", bot_id=bot.bot_id)
    return True


def cut_fading_bots(
    bots: List[BotGenome],
    trades: List[Dict[str, Any]] | None = None,
    *,
    persist: bool = True,
) -> Tuple[List[BotGenome], List[BotGenome]]:
    """
    Cut bots with fading live edge. Returns (kept, killed).
    Uses portfolio.detect_fading + demote status path.
    """
    trades = trades if trades is not None else (store.load_trades(400) if persist else [])
    kept: List[BotGenome] = []
    killed: List[BotGenome] = []

    for b in bots:
        if b.status == "dead":
            killed.append(b)
            continue
        edge = compute_live_edge(b, trades)
        # Soft demote first
        demote(b, edge)
        if b.status == "fading" and detect_fading(b, trades):
            cut_bot(b, reason=f"fading edge={edge['edge_score']}", persist=persist)
            killed.append(b)
        elif detect_fading(b, trades) and edge["n_trades"] >= MIN_TRADES_FOR_EDGE:
            cut_bot(b, reason=f"fade_pnl edge={edge['edge_score']}", persist=persist)
            killed.append(b)
        else:
            kept.append(b)
    return kept, killed


def manage_survivors(
    bots: List[BotGenome],
    trades: List[Dict[str, Any]] | None = None,
    n_target: int | None = None,
    fitness: Dict[str, float] | None = None,
    *,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Full survivor pass: promote strong, demote weak, cut fading, trim to target.
    When ``persist=True``, writes bot statuses to ``db/aite/``. Returns summary dict.
    """
    n_target = n_target if n_target is not None else cfg.TARGET_BOTS
    n_target = max(cfg.MIN_BOTS, min(cfg.MAX_BOTS, int(n_target)))
    trades = trades if trades is not None else (store.load_trades(500) if persist else [])
    fitness = fitness or {}

    promoted: List[str] = []
    demoted: List[str] = []

    for b in bots:
        edge = compute_live_edge(b, trades)
        if promote(b, edge):
            promoted.append(b.bot_id)
        elif demote(b, edge):
            demoted.append(b.bot_id)

    kept, killed = cut_fading_bots(bots, trades, persist=persist)

    # Rank kept for trim: prefer alive, then fitness / edge
    def _rank_key(b: BotGenome) -> Tuple[int, float]:
        edge = compute_live_edge(b, trades)
        fit = float(fitness.get(b.bot_id, getattr(b, "_fit", 0.0) or 0.0))
        status_rank = {"alive": 3, "exam": 2, "fading": 1, "candidate": 0}.get(b.status, 0)
        return (status_rank, fit + edge["edge_score"])

    kept_sorted = sorted(kept, key=_rank_key, reverse=True)
    survivors = kept_sorted[:n_target]
    overflow = kept_sorted[n_target:]
    for b in overflow:
        if b.status != "dead":
            b.status = "candidate"  # park extras, don't kill

    by_id = {b.bot_id: b for b in bots}
    for b in survivors + killed + overflow:
        by_id[b.bot_id] = b

    if persist:
        store.save_bots([b.to_dict() for b in by_id.values()])
        store.log_event(
            "INFO",
            f"Survivors managed: {len(survivors)} kept, {len(killed)} killed, "
            f"{len(promoted)} promoted, {len(demoted)} demoted",
        )

    return {
        "survivors": survivors,
        "killed": killed,
        "promoted": promoted,
        "demoted": demoted,
        "overflow": [b.bot_id for b in overflow],
        "n_survivors": len(survivors),
        "n_killed": len(killed),
    }
