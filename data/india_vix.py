"""
India VIX fetcher with TTL cache and last-good persistence.

Live source priority:
    1. NSE ``allIndices`` API (session-warmed, same header/retry style as
       ``data/options_chain.py``)
    2. yfinance ticker ``^INDIAVIX`` (lazy import — optional dependency)

Fresh values are cached for ``CACHE_TTL`` seconds (default 15 min) through
``data/cache.py`` and mirrored to ``db/india_vix_last.json`` following the
``data/last_good.py`` payload pattern (``{"ts": <iso>, "value": <float>}``),
so a hard NSE block or an offline machine never blanks the volatility engine.

Never raises. ``fetch_india_vix()`` returns ``None`` only when there is no
cache and no last-good record at all.
"""
from __future__ import annotations

import datetime
import json
import os

import numpy as np

from config import NSE_HEADERS
from data.cache import get_or_fetch
from data.retry import fetch as retry_fetch

# ── Tunables (override via environment) ──────────────────────────────────────
CACHE_KEY = os.environ.get("ZERO_INDIA_VIX_CACHE_KEY", "india_vix:current")
CACHE_TTL = int(os.environ.get("ZERO_INDIA_VIX_CACHE_TTL", "900"))  # 15 minutes
NSE_URL = os.environ.get(
    "ZERO_INDIA_VIX_NSE_URL", "https://www.nseindia.com/api/allIndices"
)
NSE_WARM_URL = os.environ.get(
    "ZERO_INDIA_VIX_WARM_URL", "https://www.nseindia.com/"
)
NSE_INDEX_NAME = os.environ.get("ZERO_INDIA_VIX_INDEX_NAME", "INDIA VIX")
YF_TICKER = os.environ.get("ZERO_INDIA_VIX_TICKER", "^INDIAVIX")
YF_PERIOD = os.environ.get("ZERO_INDIA_VIX_YF_PERIOD", "5d")
MIN_SANE_VIX = float(os.environ.get("ZERO_INDIA_VIX_MIN", "1.0"))
MAX_SANE_VIX = float(os.environ.get("ZERO_INDIA_VIX_MAX", "150.0"))

_LAST_GOOD_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "db", "india_vix_last.json")
)


def _sane(value: float) -> bool:
    """India VIX is a percentage index; reject anything outside a wide band."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return np.isfinite(v) and MIN_SANE_VIX <= v <= MAX_SANE_VIX


# ── Live sources ─────────────────────────────────────────────────────────────

def _fetch_vix_nse() -> float | None:
    """NSE allIndices API. Session-warmed like data/options_chain.py."""
    session_headers = dict(NSE_HEADERS)
    session_headers["Referer"] = "https://www.nseindia.com/market-data/live-equity-market"

    # Warm session with a home-page hit so NSE sets cookies.
    try:
        warm = retry_fetch(NSE_WARM_URL, headers=session_headers, timeout=8)
        _ = warm  # result irrelevant; we only need the cookies
    except Exception:
        pass

    r = retry_fetch(NSE_URL, headers=session_headers, timeout=10)
    if r is None or getattr(r, "status_code", None) != 200:
        return None
    try:
        payload = r.json()
    except ValueError:
        return None
    try:
        rows = payload.get("data", []) or []
        for row in rows:
            name = str(row.get("index", "")).strip().upper()
            if name == NSE_INDEX_NAME.upper():
                v = float(str(row.get("last")).replace(",", ""))
                return v if _sane(v) else None
    except (TypeError, ValueError, AttributeError):
        return None
    return None


def _fetch_vix_yfinance() -> float | None:
    """yfinance ``^INDIAVIX`` last close. Optional dependency, lazily imported."""
    try:
        import yfinance as yf  # lazy import: keep offline paths importable
    except Exception:
        return None
    try:
        df = yf.download(YF_TICKER, period=YF_PERIOD, progress=False,
                         auto_adjust=False)
    except Exception:
        return None
    if df is None or getattr(df, "empty", True):
        return None
    try:
        arr = np.asarray(df["Close"].values, dtype=float).ravel()
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            return None
        v = float(arr[-1])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return v if _sane(v) else None


def _live() -> float | None:
    """Try NSE first, then yfinance."""
    v = _fetch_vix_nse()
    if v is not None:
        return v
    return _fetch_vix_yfinance()


# ── Last-good persistence (db/india_vix_last.json, data/last_good.py style) ──

def _save_last_good(value: float) -> None:
    try:
        os.makedirs(os.path.dirname(_LAST_GOOD_PATH), exist_ok=True)
        with open(_LAST_GOOD_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {"ts": datetime.datetime.now().isoformat(), "value": float(value)},
                f,
            )
    except (OSError, TypeError, ValueError):
        pass


def _load_last_good() -> tuple[float | None, float | None]:
    """Return (value, age_seconds) or (None, None) if no record exists."""
    if not os.path.exists(_LAST_GOOD_PATH):
        return None, None
    try:
        with open(_LAST_GOOD_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        v = float(payload["value"])
        if not _sane(v):
            return None, None
        ts = datetime.datetime.fromisoformat(payload["ts"])
        age = (datetime.datetime.now() - ts).total_seconds()
        return v, age
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, OSError):
        return None, None


# ── Public API ───────────────────────────────────────────────────────────────

def fetch_india_vix() -> float | None:
    """
    Current India VIX value (annualized volatility index, percent units).

    Order of fallbacks: fresh cache -> live (NSE -> yfinance) -> stale cache
    -> db/india_vix_last.json. Never raises; returns None only if no cache
    and no last-good value exists anywhere.
    """
    try:
        value, stale = get_or_fetch(CACHE_KEY, CACHE_TTL, _live)
    except Exception:
        value, stale = None, True

    if value is not None:
        try:
            v = float(value)
        except (TypeError, ValueError):
            v = None
        if v is not None and _sane(v):
            if not stale:
                _save_last_good(v)
            return v

    last, _age = _load_last_good()
    if last is not None:
        return last
    return None


if __name__ == "__main__":
    vix = fetch_india_vix()
    if vix is None:
        print("India VIX unavailable (no live source, cache, or last-good).")
    else:
        print(f"India VIX: {vix:.2f}")
