"""
ZERO AITE activity log — append-only JSONL live feed for UI / agents.

Persists to ``db/aite/activity.jsonl``. Never raises to callers.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store

def _activity_path() -> Path:
    """Lazy path — follows ``cfg.AITE_DB_DIR`` (tests may redirect)."""
    return cfg.AITE_DB_DIR / "activity.jsonl"


def __getattr__(name: str):
    if name == "ACTIVITY_PATH":
        return _activity_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Levels used by the UI feed
LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "AGENT", "TRADE", "BREED", "EXAM", "BRIEF", "IDEA")


def _row(
    message: str,
    *,
    level: str = "INFO",
    source: str = "aite",
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "id": f"act_{uuid.uuid4().hex[:12]}",
        "ts": time.time(),
        "level": (level or "INFO").upper(),
        "source": source,
        "message": str(message)[:2000],
    }
    if agent_id:
        row["agent_id"] = agent_id
    if symbol:
        row["symbol"] = symbol
    if extra:
        row["extra"] = extra
    return row


def log_activity(
    message: str,
    *,
    level: str = "INFO",
    source: str = "aite",
    agent_id: Optional[str] = None,
    symbol: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Append one activity event. Returns the row (even if disk write fails)."""
    payload = extra if extra else None
    row = _row(
        message,
        level=level,
        source=source,
        agent_id=agent_id,
        symbol=symbol,
        extra=payload,
    )
    store.append_jsonl(_activity_path(), row)
    # Mirror significant events into the ZERO vault (best-effort, never raises)
    try:
        from engine.vault_sync import sync_aite_activity
        sync_aite_activity(row)
    except Exception:
        pass
    return row


def read_activity(limit: int = 200, level: Optional[str] = None) -> List[Dict[str, Any]]:
    """Newest-last slice of the activity feed (UI polls this)."""
    rows = store.read_jsonl(_activity_path(), limit=max(1, int(limit)))
    if level:
        lvl = level.upper()
        rows = [r for r in rows if str(r.get("level", "")).upper() == lvl]
    return rows


def tail_activity(since_ts: float = 0.0, limit: int = 100) -> List[Dict[str, Any]]:
    """Events with ``ts > since_ts`` (realtime poll helper)."""
    rows = store.read_jsonl(_activity_path(), limit=max(limit * 3, 300))
    out = [r for r in rows if float(r.get("ts") or 0) > float(since_ts)]
    return out[-limit:]


def clear_activity_for_tests() -> bool:
    """Test helper — truncate the activity file. Not for production UI."""
    try:
        path = _activity_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return True
    except Exception:
        return False
