"""
ZERO AITE scheduler — daily 08:45 IST premarket trigger.

No network / no heavy imports at module load. Premarket is invoked lazily.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

_LOCK = threading.RLock()
_STATE: Dict[str, Any] = {
    "last_premarket_date": None,  # ISO date string when successfully fired
    "last_check_iso": None,
}


def _ist_now() -> datetime:
    """Current time in Asia/Kolkata; falls back to UTC+5:30 if zoneinfo missing."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        return datetime.utcnow() + timedelta(hours=5, minutes=30)


def _premarket_hhmm() -> Tuple[int, int]:
    try:
        from engine.aite import config as cfg

        hh, mm = cfg.PREMARKET_HHMM
        return int(hh), int(mm)
    except Exception:
        return 8, 45


def premarket_window_open(now: Optional[datetime] = None, grace_minutes: int = 30) -> bool:
    """
    True when local IST clock is at/after 08:45 and within grace window
    (default 30 min) so a missed tick still fires once.
    """
    now = now or _ist_now()
    hh, mm = _premarket_hhmm()
    cur = now.timetz() if hasattr(now, "timetz") else now.time()
    # Strip tz for minute-of-day compare
    cur_mins = cur.hour * 60 + cur.minute
    start_mins = hh * 60 + mm
    end_mins = start_mins + int(grace_minutes)
    return start_mins <= cur_mins <= end_mins


def already_ran_today(now: Optional[datetime] = None) -> bool:
    now = now or _ist_now()
    today = now.date().isoformat()
    with _LOCK:
        if _STATE.get("last_premarket_date") == today:
            return True
    # Also honour persisted daemon state if present
    try:
        from engine.aite import store

        st = store.load_daemon_state()
        last = st.get("last_premarket")
        if isinstance(last, str) and last.startswith(today):
            return True
        if last == today:
            return True
    except Exception:
        pass
    return False


def mark_premarket_ran(when: Optional[datetime] = None) -> None:
    when = when or _ist_now()
    iso_date = when.date().isoformat()
    with _LOCK:
        _STATE["last_premarket_date"] = iso_date
        _STATE["last_check_iso"] = when.isoformat()
    try:
        from engine.aite import store

        st = store.load_daemon_state()
        st["last_premarket"] = iso_date
        store.save_daemon_state(st)
    except Exception:
        pass


def should_fire_premarket(now: Optional[datetime] = None) -> bool:
    now = now or _ist_now()
    if already_ran_today(now):
        return False
    return premarket_window_open(now)


def run_scheduled_premarket(force: bool = False) -> Optional[Dict[str, Any]]:
    """
    If due (or ``force``), lazily call ``premarket.run_premarket_brief()``.
    Returns the report dict, or None if skipped / failed.
    """
    now = _ist_now()
    with _LOCK:
        _STATE["last_check_iso"] = now.isoformat()

    if not force and not should_fire_premarket(now):
        return None

    try:
        from engine.aite.premarket import run_premarket_brief

        report = run_premarket_brief(persist=True)
        mark_premarket_ran(now)
        return report if isinstance(report, dict) else {"ok": True, "raw": report}
    except Exception as exc:
        try:
            from engine.aite import store

            store.log_event("ERROR", f"Scheduled premarket failed: {exc}")
        except Exception:
            pass
        return {"error": str(exc), "date": now.date().isoformat()}


def get_scheduler_status() -> Dict[str, Any]:
    now = _ist_now()
    hh, mm = _premarket_hhmm()
    with _LOCK:
        snap = dict(_STATE)
    return {
        "ist_now": now.isoformat(),
        "premarket_hhmm": f"{hh:02d}:{mm:02d}",
        "window_open": premarket_window_open(now),
        "already_ran_today": already_ran_today(now),
        "should_fire": should_fire_premarket(now),
        **snap,
    }
