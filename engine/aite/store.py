"""
ZERO AITE persistence — JSON / JSONL under db/aite/.
Atomic writes, never raises to callers (returns defaults).
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.aite import config as cfg

# When True, write_json / append_jsonl become no-ops (persist=False pipeline).
_NO_PERSIST = threading.local()


def set_persist_enabled(enabled: bool) -> None:
    """Toggle disk writes for the current thread (tests / dry-run)."""
    _NO_PERSIST.disabled = not bool(enabled)


def persist_enabled() -> bool:
    return not bool(getattr(_NO_PERSIST, "disabled", False))


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default if default is not None else {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def write_json(path: Path, payload: Any) -> bool:
    if not persist_enabled():
        return False
    try:
        _atomic_write(path, payload)
        return True
    except Exception:
        return False


def append_jsonl(path: Path, row: Dict[str, Any]) -> bool:
    if not persist_enabled():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        return True
    except Exception:
        return False


def read_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if not path.exists():
            return rows
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows[-limit:]
    except Exception:
        return rows


# ── Domain helpers ───────────────────────────────────────────────────────────

def load_bots() -> List[Dict[str, Any]]:
    data = read_json(cfg.BOTS_PATH, {"bots": []})
    return list(data.get("bots") or [])


def save_bots(bots: List[Dict[str, Any]]) -> bool:
    return write_json(cfg.BOTS_PATH, {"bots": bots, "updated_at": time.time()})


def upsert_bot(bot: Dict[str, Any]) -> bool:
    bots = load_bots()
    bid = bot.get("bot_id")
    found = False
    for i, b in enumerate(bots):
        if b.get("bot_id") == bid:
            bots[i] = bot
            found = True
            break
    if not found:
        bots.append(bot)
    return save_bots(bots)


def load_fund() -> Dict[str, Any]:
    data = read_json(cfg.FUND_PATH, None)
    if not data:
        data = {
            "paper_fund": cfg.DEFAULT_PAPER_FUND,
            "cash": cfg.DEFAULT_PAPER_FUND,
            "equity": cfg.DEFAULT_PAPER_FUND,
            "currency": "INR",
            "updated_at": time.time(),
        }
        write_json(cfg.FUND_PATH, data)
    return data


def save_fund(fund: Dict[str, Any]) -> bool:
    fund["updated_at"] = time.time()
    return write_json(cfg.FUND_PATH, fund)


def load_portfolio() -> Dict[str, Any]:
    return read_json(cfg.PORTFOLIO_PATH, {
        "fund_cash": cfg.DEFAULT_PAPER_FUND,
        "equity": cfg.DEFAULT_PAPER_FUND,
        "bot_ids": [],
        "allocations": {},
        "corr_matrix": {},
        "killed": [],
        "updated_at": time.time(),
    })


def save_portfolio(state: Dict[str, Any]) -> bool:
    state["updated_at"] = time.time()
    return write_json(cfg.PORTFOLIO_PATH, state)


def log_trade(trade: Dict[str, Any]) -> bool:
    trade = dict(trade)
    trade.setdefault("ts", time.time())
    return append_jsonl(cfg.TRADES_PATH, trade)


def load_trades(limit: int = 200) -> List[Dict[str, Any]]:
    return read_jsonl(cfg.TRADES_PATH, limit=limit)


def log_event(level: str, message: str, **extra) -> bool:
    row = {"ts": time.time(), "level": level, "message": message, **extra}
    return append_jsonl(cfg.LOGS_PATH, row)


def load_logs(limit: int = 200) -> List[Dict[str, Any]]:
    return read_jsonl(cfg.LOGS_PATH, limit=limit)


def save_brief(brief: Dict[str, Any]) -> bool:
    return append_jsonl(cfg.BRIEFS_PATH, brief)


def load_briefs(limit: int = 50) -> List[Dict[str, Any]]:
    return read_jsonl(cfg.BRIEFS_PATH, limit=limit)


def save_premarket(report: Dict[str, Any]) -> bool:
    return append_jsonl(cfg.PREMARKET_PATH, report)


def load_premarket(limit: int = 30) -> List[Dict[str, Any]]:
    return read_jsonl(cfg.PREMARKET_PATH, limit=limit)


def load_agents() -> Dict[str, Any]:
    return read_json(cfg.AGENT_STATE_PATH, {"nodes": [], "edges": [], "updated_at": time.time()})


def save_agents(state: Dict[str, Any]) -> bool:
    state["updated_at"] = time.time()
    return write_json(cfg.AGENT_STATE_PATH, state)


def load_daemon_state() -> Dict[str, Any]:
    return read_json(cfg.DAEMON_STATE_PATH, {
        "running": False,
        "started_at": None,
        "last_tick": None,
        "last_breed": None,
        "last_premarket": None,
        "ticks": 0,
    })


def save_daemon_state(state: Dict[str, Any]) -> bool:
    return write_json(cfg.DAEMON_STATE_PATH, state)


def save_idea(idea: Dict[str, Any]) -> bool:
    return append_jsonl(cfg.IDEAS_PATH, idea)


def load_ideas(limit: int = 50) -> List[Dict[str, Any]]:
    return read_jsonl(cfg.IDEAS_PATH, limit=limit)
