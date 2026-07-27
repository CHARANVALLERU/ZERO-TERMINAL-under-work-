"""
Persistent last-good-value store. When every live source fails we still
have something to show on the dashboard, and the UI can flag it as stale.

Files: db/last_good/<source>.json -> {"ts": <iso>, "value": <obj>}
"""
import json
import os
import datetime

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'db', 'last_good'))


def _path(source: str) -> str:
    safe = source.replace("/", "_").replace("\\", "_")
    return os.path.join(_ROOT, f"{safe}.json")


def save(source: str, value) -> None:
    os.makedirs(_ROOT, exist_ok=True)
    try:
        with open(_path(source), "w", encoding="utf-8") as f:
            json.dump({"ts": datetime.datetime.now().isoformat(), "value": value}, f)
    except OSError:
        pass


def load(source: str):
    """Return (value, age_seconds) or (None, None) if no record exists."""
    p = _path(source)
    if not os.path.exists(p):
        return None, None
    try:
        with open(p, "r", encoding="utf-8") as f:
            payload = json.load(f)
        ts = datetime.datetime.fromisoformat(payload["ts"])
        age = (datetime.datetime.now() - ts).total_seconds()
        return payload.get("value"), age
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        return None, None
