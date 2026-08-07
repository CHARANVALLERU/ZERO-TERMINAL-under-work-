"""
ZERO AITE file heartbeat — survives Streamlit UI close.

Writes ``db/aite/heartbeat.json`` so external monitors / other processes
can confirm the background daemon is alive.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOCK = threading.RLock()

# Paths resolved lazily so import stays side-effect free (no mkdir/network).
_HEARTBEAT_NAME = "heartbeat.json"


def _heartbeat_path() -> Path:
    from engine.aite import config as cfg

    return cfg.AITE_DB_DIR / _HEARTBEAT_NAME


def write_heartbeat(
    status: str = "alive",
    *,
    pid: Optional[int] = None,
    ticks: int = 0,
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Atomically refresh the on-disk heartbeat. Never raises."""
    try:
        from engine.aite import store

        payload: Dict[str, Any] = {
            "status": status,
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
            "ticks": int(ticks),
        }
        if pid is not None:
            payload["pid"] = int(pid)
        if extra:
            payload.update(extra)
        with _LOCK:
            return bool(store.write_json(_heartbeat_path(), payload))
    except Exception:
        return False


def read_heartbeat() -> Dict[str, Any]:
    """Read heartbeat file; empty dict on missing/corrupt."""
    try:
        from engine.aite import store

        with _LOCK:
            data = store.read_json(_heartbeat_path(), {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def heartbeat_age_seconds() -> Optional[float]:
    """Seconds since last heartbeat write, or None if unknown."""
    hb = read_heartbeat()
    ts = hb.get("ts")
    if ts is None:
        return None
    try:
        return max(0.0, time.time() - float(ts))
    except (TypeError, ValueError):
        return None


def is_heartbeat_fresh(max_age_seconds: float = 120.0) -> bool:
    age = heartbeat_age_seconds()
    if age is None:
        return False
    return age <= float(max_age_seconds)
