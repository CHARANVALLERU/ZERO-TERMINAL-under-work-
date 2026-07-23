"""
ZERO Breaking-News Monitor
=========================

Stateful layer over the existing `data.market_news` scraper. Its job:

  1.  Pull the latest global finance/geopolitics headlines (reusing the
      cached, last-good-backed scraper — no new network plumbing).
  2.  Run every item through the news-impact engine.
  3.  Track which headlines have already been *seen* (persisted to
      db/news_seen.json) so the UI can tell **newly-arrived** items apart
      from ones already on screen.
  4.  Surface the freshly-arrived, high-impact items as **breaking alerts**
      that the app turns into device notifications.

Design notes
------------
* Purely additive: if the network is down the scraper returns last-good /
  empty and this module simply reports "no new items" — never raises.
* Dedup key is a stable hash of the headline title, so restarts don't
  re-alert on the same story.
* The seen-store is capped so it can't grow without bound.
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import datetime

from engine.news_impact import assess
from config import NEWS_ALERT_THRESHOLD

SEEN_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "news_seen.json")
_SEEN_CAP = 500


def _news_id(title: str) -> str:
    return hashlib.sha1((title or "").strip().lower().encode("utf-8")).hexdigest()[:16]


def _load_seen():
    if not os.path.exists(SEEN_PATH) or os.path.getsize(SEEN_PATH) == 0:
        return {}
    try:
        with open(SEEN_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_seen(seen: dict):
    # keep only the most recent _SEEN_CAP ids by first-seen timestamp
    if len(seen) > _SEEN_CAP:
        items = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:_SEEN_CAP]
        seen = dict(items)
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    try:
        with open(SEEN_PATH, "w") as f:
            json.dump(seen, f)
    except IOError:
        pass


def _enrich(item, index_levels=None):
    """Attach an impact assessment to a raw news item dict."""
    title = item.get("title") if isinstance(item, dict) else str(item)
    a = assess(title, index_levels=index_levels)
    return {
        "id": _news_id(title),
        "title": title,
        "link": (item.get("link") if isinstance(item, dict) else "") or "",
        "source": (item.get("source") if isinstance(item, dict) else "") or "GLOBAL",
        "published": (item.get("published") if isinstance(item, dict) else "") or "",
        **a,
    }


def get_live_feed(index_levels=None, limit=30):
    """Return the current news feed, each item enriched with impact analysis,
    sorted so the highest-impact stories float to the top. No state mutation —
    safe to call on every UI refresh."""
    from data.market_news import get_global_news
    raw = get_global_news() or []
    enriched = [_enrich(it, index_levels) for it in raw]
    enriched.sort(key=lambda x: x["impact_score"], reverse=True)
    return enriched[:limit]


from config import NEWS_REFRESH_SECONDS
try:
    import streamlit as st
    if st.runtime.exists():
        _cache = st.cache_data(ttl=NEWS_REFRESH_SECONDS, show_spinner=False)
    else:
        def _cache(fn):
            return fn
except Exception:  # keep the data layer importable without Streamlit (CLI/tests/offline)
    def _cache(fn):
        return fn

def _check_breaking_raw(index_levels=None, mark_seen=True):
    """Return only the *newly arrived* high-impact items since the last call.

    Returns:
        {
          "breaking": [ enriched items with is_high_impact and not seen before ],
          "feed":     [ enriched items sorted by impact ],
          "checked_at": iso timestamp,
        }
    """
    from data.market_news import get_global_news
    raw = get_global_news() or []
    seen = _load_seen()
    now_ts = time.time()

    feed = []
    breaking = []
    newly = {}
    for it in raw:
        e = _enrich(it, index_levels)
        feed.append(e)
        if e["id"] not in seen:
            newly[e["id"]] = now_ts
            e["is_new"] = True
            if e["impact_score"] >= NEWS_ALERT_THRESHOLD and e["direction"] != "NEUTRAL":
                breaking.append(e)
        else:
            e["is_new"] = False

    if mark_seen and newly:
        seen.update(newly)
        _save_seen(seen)

    feed.sort(key=lambda x: (x["is_new"], x["impact_score"]), reverse=True)
    breaking.sort(key=lambda x: x["impact_score"], reverse=True)
    return {
        "breaking": breaking,
        "feed": feed,
        "checked_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

@_cache
def _check_breaking_cached(levels_tuple, mark_seen=True):
    levels = dict(levels_tuple) if levels_tuple else None
    return _check_breaking_raw(index_levels=levels, mark_seen=mark_seen)

def check_breaking(index_levels=None, mark_seen=True):
    levels_tuple = tuple(sorted(index_levels.items())) if index_levels else None
    return _check_breaking_cached(levels_tuple, mark_seen)


def reset_seen():
    """Forget all seen headlines (e.g. on a manual 'replay alerts')."""
    _save_seen({})
    if hasattr(_check_breaking_cached, "clear"):
        _check_breaking_cached.clear()


if __name__ == "__main__":
    # Offline demo with synthetic items (network usually blocked in dev).
    import data.market_news as mn
    mn.get_global_news = lambda: [
        {"title": "Breaking: Trump says Iran peace deal is off, tensions escalate",
         "link": "http://x", "source": "Reuters"},
        {"title": "Indian IT sector hits record export milestone", "source": "ET"},
        {"title": "Markets flat ahead of data", "source": "MC"},
    ]
    reset_seen()
    res = check_breaking()
    print("BREAKING ALERTS:")
    for b in res["breaking"]:
        from engine.news_impact import summarize_alert
        print("  •", b["title"])
        print("    ", summarize_alert(b))
    print(f"\nSecond call (all now seen) breaking = "
          f"{len(check_breaking()['breaking'])} (expected 0)")
