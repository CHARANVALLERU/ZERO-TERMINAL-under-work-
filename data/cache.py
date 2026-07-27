"""
Disk-backed cache with TTL. Used by every scraper so a 503 from NSE
or a stale Investing.com page doesn't blank the dashboard.

Format on disk: one JSON file per key under db/cache/<sha1(key)>.json
with {"ts": <epoch>, "value": <obj>}.
"""
import json
import os
import time
import hashlib
import threading

_LOCK = threading.Lock()
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'db', 'cache'))


def _path(key: str) -> str:
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(_ROOT, f"{h}.json")


def get(key: str, ttl: int = 600):
    """Return cached value if fresh, else None."""
    p = _path(key)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if (time.time() - payload.get("ts", 0)) <= ttl:
            return payload.get("value")
    except (json.JSONDecodeError, OSError):
        return None
    return None


def set_(key: str, value) -> None:
    """Persist a value with the current timestamp. Stale values are still
    useful as last-good fallbacks; that is handled separately by last_good."""
    os.makedirs(_ROOT, exist_ok=True)
    p = _path(key)
    tmp = p + ".tmp"
    with _LOCK:
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"ts": time.time(), "value": value}, f)
            os.replace(tmp, p)
        except OSError:
            pass


def get_or_fetch(key: str, ttl: int, fn):
    """Return cached value if fresh, otherwise call fn() and cache the result.
    If fn() raises or returns None, the previous cached value (even if stale)
    is returned as a last-good fallback so the dashboard never goes blank.
    """
    cached_fresh = get(key, ttl)
    if cached_fresh is not None:
        return cached_fresh, False  # not stale
    try:
        value = fn()
    except Exception:
        value = None
    if value is None:
        stale = get(key, ttl=float("inf"))
        if stale is not None:
            return stale, True  # stale
        return None, True
    set_(key, value)
    return value, False
