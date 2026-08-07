"""
ZERO AITE deploy — deploy / swap / retire portfolio bots onto paper or MT5 paper.

Bot ids come from the live portfolio (``db/aite/portfolio.json``).
Every mutation appends one line to ``db/aite/deploys.jsonl``.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.mt5_adapter import MT5Adapter, get_mt5_adapter
from engine.aite.paper_fund import PaperFund, get_paper_fund

VALID_VENUES = frozenset({"paper", "mt5_paper", "mt5"})


def _deploys_path() -> Path:
    """Lazy path — follows ``cfg.AITE_DB_DIR`` (tests may redirect)."""
    return cfg.AITE_DB_DIR / "deploys.jsonl"


def _active_deploy_path() -> Path:
    return cfg.AITE_DB_DIR / "active_deploys.json"


def __getattr__(name: str) -> Path:
    """PEP 562 — ``DEPLOYS_PATH`` / ``ACTIVE_DEPLOY_PATH`` always track cfg."""
    if name == "DEPLOYS_PATH":
        return _deploys_path()
    if name == "ACTIVE_DEPLOY_PATH":
        return _active_deploy_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _normalize_venue(venue: str) -> str:
    v = (venue or "paper").strip().lower()
    if v == "mt5":
        v = "mt5_paper"
    if v not in VALID_VENUES:
        raise ValueError(f"venue must be one of {sorted(VALID_VENUES)}, got {venue!r}")
    return "mt5_paper" if v == "mt5_paper" else "paper"


def _audit(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event_id": f"dep_{uuid.uuid4().hex[:10]}",
        "action": action,
        **payload,
    }
    store.append_jsonl(_deploys_path(), row)
    return row


def _load_active() -> Dict[str, Any]:
    data = store.read_json(_active_deploy_path(), None)
    if not data:
        data = {"deployments": {}, "updated_at": time.time()}
    data.setdefault("deployments", {})
    return data


def _save_active(state: Dict[str, Any]) -> bool:
    state["updated_at"] = time.time()
    return store.write_json(_active_deploy_path(), state)


def _portfolio_bot_ids() -> List[str]:
    port = store.load_portfolio()
    return [str(x) for x in (port.get("bot_ids") or [])]


def _bots_by_id(ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    want = set(ids)
    out: Dict[str, Dict[str, Any]] = {}
    for b in store.load_bots():
        bid = str(b.get("bot_id", ""))
        if bid in want:
            out[bid] = b
    return out


def _resolve_ids(bot_ids: Sequence[str] | None) -> List[str]:
    portfolio_ids = _portfolio_bot_ids()
    if not bot_ids:
        return list(portfolio_ids)
    requested = [str(x) for x in bot_ids]
    allowed = set(portfolio_ids)
    # Prefer portfolio membership; still allow explicit ids that exist as bots
    known = {str(b.get("bot_id")) for b in store.load_bots()}
    resolved: List[str] = []
    for bid in requested:
        if bid in allowed or bid in known:
            resolved.append(bid)
    return resolved


def _venue_handles(venue: str) -> tuple[str, PaperFund, MT5Adapter | None]:
    venue = _normalize_venue(venue)
    fund = get_paper_fund()
    if venue == "mt5_paper":
        adapter = get_mt5_adapter(fund=fund)
        adapter.connect()  # falls back to sim if MT5 unavailable
        return venue, fund, adapter
    return venue, fund, None


def deploy_bots(
    bot_ids: Sequence[str] | None = None,
    venue: str = "paper",
    *,
    note: str = "",
) -> Dict[str, Any]:
    """Deploy portfolio bots to paper or MT5 paper. Ids default to full portfolio."""
    venue, fund, adapter = _venue_handles(venue)
    ids = _resolve_ids(bot_ids)
    if not ids:
        row = _audit("deploy", {
            "ok": False,
            "venue": venue,
            "bot_ids": [],
            "error": "no bot ids from portfolio",
            "note": note,
        })
        return {"ok": False, "error": "no bot ids from portfolio", "audit": row}

    bots = _bots_by_id(ids)
    active = _load_active()
    deployed: List[str] = []
    missing: List[str] = []

    for bid in ids:
        bot = bots.get(bid)
        if not bot:
            missing.append(bid)
            continue
        bot["status"] = "alive"
        bot["deploy_venue"] = venue
        bot["deployed_at"] = time.time()
        store.upsert_bot(bot)
        active["deployments"][bid] = {
            "bot_id": bid,
            "name": bot.get("name", ""),
            "symbol": bot.get("symbol", ""),
            "venue": venue,
            "allocation": float((store.load_portfolio().get("allocations") or {}).get(bid, 0.0)),
            "deployed_at": bot["deployed_at"],
            "status": "active",
        }
        deployed.append(bid)

    _save_active(active)
    mode = adapter.mode if adapter is not None else "sim"
    row = _audit("deploy", {
        "ok": True,
        "venue": venue,
        "mode": mode,
        "bot_ids": deployed,
        "missing": missing,
        "fund_cash": fund.cash,
        "fund_equity": fund.equity,
        "note": note,
    })
    store.log_event("INFO", f"Deployed {len(deployed)} bots → {venue} ({mode})")
    return {
        "ok": True,
        "venue": venue,
        "mode": mode,
        "deployed": deployed,
        "missing": missing,
        "active_count": len([d for d in active["deployments"].values() if d.get("status") == "active"]),
        "audit": row,
    }


def retire_bots(
    bot_ids: Sequence[str],
    venue: str = "paper",
    *,
    square_off: bool = False,
    prices: Dict[str, float] | None = None,
    note: str = "",
) -> Dict[str, Any]:
    """Retire deployed bots (remove from active set). Optionally square-off positions."""
    venue, fund, adapter = _venue_handles(venue)
    ids = [str(x) for x in bot_ids]
    if not ids:
        return {"ok": False, "error": "bot_ids required"}

    bots = _bots_by_id(ids)
    active = _load_active()
    retired: List[str] = []
    fills: List[Dict[str, Any]] = []
    prices = prices or {}

    for bid in ids:
        dep = active["deployments"].get(bid)
        bot = bots.get(bid)
        if bot:
            bot["status"] = "dead" if bot.get("status") == "fading" else bot.get("status", "alive")
            # Mark retired without forcing dead unless already fading
            bot["deploy_venue"] = None
            bot["retired_at"] = time.time()
            if bot.get("status") == "alive":
                bot["status"] = "candidate"
            store.upsert_bot(bot)

        if square_off and bot:
            symbol = str(bot.get("symbol", ""))
            pos = fund.positions.get(symbol)
            if pos and float(pos.get("qty", 0.0)) > 0 and str(pos.get("bot_id", "")) in ("", bid):
                qty = float(pos["qty"])
                px = float(prices.get(symbol) or pos.get("avg_cost") or 0.0)
                if px > 0:
                    if adapter is not None:
                        fills.append(adapter.place_order(symbol, "SELL", qty, px, bot_id=bid, bot_name=bot.get("name", "")))
                    else:
                        fills.append(fund.apply_fill(symbol, "SELL", qty, px, bot_id=bid))

        if dep:
            dep["status"] = "retired"
            dep["retired_at"] = time.time()
            dep["venue"] = venue
            active["deployments"][bid] = dep
        retired.append(bid)

    # Drop retired from portfolio bot_ids
    port = store.load_portfolio()
    port_ids = [x for x in (port.get("bot_ids") or []) if str(x) not in set(ids)]
    port["bot_ids"] = port_ids
    allocs = dict(port.get("allocations") or {})
    for bid in ids:
        allocs.pop(bid, None)
    port["allocations"] = allocs
    killed = list(port.get("killed") or [])
    for bid in ids:
        if bid not in killed:
            killed.append(bid)
    port["killed"] = killed
    store.save_portfolio(port)
    _save_active(active)

    row = _audit("retire", {
        "ok": True,
        "venue": venue,
        "bot_ids": retired,
        "square_off": square_off,
        "fills": len(fills),
        "note": note,
    })
    store.log_event("INFO", f"Retired {len(retired)} bots from {venue}")
    return {
        "ok": True,
        "venue": venue,
        "retired": retired,
        "fills": fills,
        "audit": row,
    }


def swap_bot(
    out_id: str,
    in_id: str,
    venue: str = "paper",
    *,
    square_off: bool = True,
    prices: Dict[str, float] | None = None,
    note: str = "",
) -> Dict[str, Any]:
    """Retire ``out_id`` and deploy ``in_id`` on the same venue."""
    out_id = str(out_id)
    in_id = str(in_id)
    if not out_id or not in_id:
        return {"ok": False, "error": "out_id and in_id required"}
    if out_id == in_id:
        return {"ok": False, "error": "out_id and in_id must differ"}

    venue = _normalize_venue(venue)

    # Ensure in_id is on the portfolio (add if known bot)
    port = store.load_portfolio()
    bot_ids = [str(x) for x in (port.get("bot_ids") or [])]
    bots = _bots_by_id([out_id, in_id])
    if in_id not in bots:
        row = _audit("swap", {
            "ok": False, "venue": venue, "out_id": out_id, "in_id": in_id,
            "error": "in_id not found in bots store", "note": note,
        })
        return {"ok": False, "error": "in_id not found in bots store", "audit": row}

    if in_id not in bot_ids:
        bot_ids.append(in_id)
        port["bot_ids"] = bot_ids
        allocs = dict(port.get("allocations") or {})
        # Transfer allocation from out → in when present
        if out_id in allocs:
            allocs[in_id] = allocs.get(out_id, 0.0)
        port["allocations"] = allocs
        store.save_portfolio(port)

    retire_res = retire_bots(
        [out_id], venue=venue, square_off=square_off, prices=prices, note=f"swap-out:{note}",
    )
    deploy_res = deploy_bots([in_id], venue=venue, note=f"swap-in:{note}")

    row = _audit("swap", {
        "ok": bool(retire_res.get("ok") and deploy_res.get("ok")),
        "venue": venue,
        "out_id": out_id,
        "in_id": in_id,
        "retire_ok": retire_res.get("ok"),
        "deploy_ok": deploy_res.get("ok"),
        "note": note,
    })
    return {
        "ok": bool(retire_res.get("ok") and deploy_res.get("ok")),
        "venue": venue,
        "out_id": out_id,
        "in_id": in_id,
        "retire": retire_res,
        "deploy": deploy_res,
        "audit": row,
    }


def list_deploys(limit: int = 100) -> List[Dict[str, Any]]:
    """Recent audit rows from ``deploys.jsonl``."""
    return store.read_jsonl(_deploys_path(), limit=limit)


def active_deployments() -> Dict[str, Any]:
    """Current active deployment map (+ fund snapshot)."""
    active = _load_active()
    fund = get_paper_fund().snapshot()
    deps = {
        k: v for k, v in (active.get("deployments") or {}).items()
        if v.get("status") == "active"
    }
    return {
        "deployments": deps,
        "count": len(deps),
        "fund": fund,
        "updated_at": active.get("updated_at"),
    }


def get_deploy_adapter(venue: str = "paper") -> Any:
    """Return PaperFund (paper) or MT5Adapter (mt5_paper) ready for orders."""
    venue, fund, adapter = _venue_handles(venue)
    if adapter is not None:
        return adapter
    return fund
