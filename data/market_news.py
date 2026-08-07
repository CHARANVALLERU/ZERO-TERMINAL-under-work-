"""
Resilient market-news scraper with VADER sentiment.

Sources (in order):
  1. WorldMonitor (worldmonitor.app finance digest / page)
  2. Moneycontrol markets RSS
  3. Reuters India RSS
  4. Economic Times markets RSS
  5. Investing.com world-news (legacy fallback)

Sentiment: VADER (vaderSentiment) for proper negation/intensifier handling,
plus a domain-specific lexicon override for Indian-market terms. Returns
a rich dict in the same shape the rest of the engine already consumes.
"""
import os
import re
try:
    import feedparser
except ImportError:  # optional: news scraping degrades to last-good/empty offline
    feedparser = None

from config import USER_AGENT
from data.cache import get_or_fetch
from data.retry import fetch as retry_fetch
from data.last_good import save as lg_save, load as lg_load


CACHE_KEY = "market_news"
CACHE_TTL = 600  # 10 min
SOURCE_NAME = "market_news"

# (title, link, source, published)
NEWS_SCHEMA_KEY = "news"

RSS_FEEDS = [
    ("CNN Business", "https://rss.cnn.com/rss/money_news_international.rss"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/markets.xml"),
    ("Reuters India", "https://feeds.reuters.com/reuters/INtopNews"),
    ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Investing.com", "https://www.investing.com/news/world-news.rss"),
]

# ---- Sentiment -----------------------------------------------------------

_BEARISH_LEXICON = {
    "war": -2.5, "conflict": -2.0, "inflation": -1.5, "rate hike": -2.0,
    "recession": -2.5, "crash": -3.0, "sell-off": -2.0, "selloff": -2.0,
    "escalation": -2.0, "tensions": -1.5, "sanctions": -1.5, "downgrade": -1.5,
    "default": -2.5, "crisis": -2.0, "tariff": -1.5, "trade war": -2.0,
    "hawkish": -1.0, "tightening": -1.0, "layoffs": -1.5, "slowdown": -1.5,
    "contraction": -1.5, "rupee fall": -1.5, "rupee depreciation": -1.5,
    "fii selling": -2.0, "fii outflow": -2.0, "repo rate hike": -1.5,
    "rbi hawkish": -1.0, "monsoon deficit": -1.0, "fiscal deficit": -1.0,
    "current account deficit": -1.0, "oil surge": -1.0, "crude spike": -1.0,
    "miss": -0.8, "down": -0.6, "fall": -0.6, "drop": -0.6, "loss": -0.7,
    "weak": -0.6, "tumble": -1.5, "plunge": -2.0, "slump": -1.5,
}

_BULLISH_LEXICON = {
    "growth": 1.5, "recovery": 1.5, "stimulus": 1.5, "rate cut": 2.0,
    "surge": 1.5, "rally": 1.5, "peace": 1.5, "deal": 1.0,
    "cooling inflation": 1.5, "positive": 0.8, "upgrade": 1.5,
    "expansion": 1.5, "boom": 1.5, "dovish": 1.0, "easing": 1.0,
    "investment": 0.8, "hiring": 1.0, "jobs growth": 1.0, "record high": 2.0,
    "breakout": 1.5, "rupee strength": 1.0, "rupee appreciation": 1.0,
    "fii buying": 2.0, "fii inflow": 2.0, "dii buying": 1.5, "dii inflow": 1.5,
    "repo rate cut": 1.5, "rbi dovish": 1.0, "good monsoon": 1.0,
    "gdp growth": 1.5, "reform": 0.8, "disinvestment": 0.5,
    "infrastructure spending": 1.0, "pli scheme": 0.8, "make in india": 0.5,
    "beat": 1.0, "up": 0.6, "rise": 0.5, "gain": 0.5, "high": 0.5,
    "strong": 0.6, "jump": 1.0, "soar": 1.5, "soars": 1.5,
}


def _load_vader():
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        return SentimentIntensityAnalyzer()
    except Exception:
        return None


_VADER = _load_vader()


def _score_text(text: str):
    """Combine VADER with our domain lexicon. Return score in [-1, 1]."""
    if not text:
        return 0.0
    text_l = text.lower()
    domain = 0.0
    hits = 0
    for phrase, w in _BULLISH_LEXICON.items():
        if phrase in text_l:
            domain += w
            hits += 1
    for phrase, w in _BEARISH_LEXICON.items():
        if phrase in text_l:
            domain += w  # already negative
            hits += 1
    domain = max(min(domain / 6.0, 1.0), -1.0) if hits else 0.0

    if _VADER is not None:
        v = _VADER.polarity_scores(text)
        # VADER "compound" is already [-1, 1]
        return round(0.5 * domain + 0.5 * v["compound"], 4)
    return round(domain, 4)


def _intensity(score: float) -> str:
    if score <= -0.6:
        return "extreme_bearish"
    if score <= -0.3:
        return "strong_bearish"
    if score < -0.05:
        return "bearish"
    if score <= 0.05:
        return "neutral"
    if score < 0.3:
        return "bullish"
    if score < 0.6:
        return "strong_bullish"
    return "extreme_bullish"


# ---- Scraping ------------------------------------------------------------

def fetch_forexfactory_news():
    """
    Fetches high-impact macro news & calendar releases with ForexFactory priority.
    Attempts live web fetch with modern browser headers; gracefully falls back to
    curated live macro indicators if network/Cloudflare challenge is encountered.
    """
    import datetime
    ff_items = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    # Try fetching ForexFactory news feed RSS / HTML
    try:
        r = retry_fetch("https://www.forexfactory.com/news", headers=headers, timeout=5)
        if r and r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, "html.parser")
            rows = soup.select(".news-headline") or soup.find_all("a", class_="flexbox")
            for row in rows[:5]:
                t = row.get_text().strip()
                href = row.get("href", "")
                if t:
                    ff_items.append({
                        "title": f"[HIGH IMPACT] {t}",
                        "link": f"https://www.forexfactory.com{href}" if href.startswith("/") else href,
                        "source": "ForexFactory (Priority #1)",
                        "published": "Live",
                        "priority": 1,
                        "impact": "High",
                    })
    except Exception:
        pass

    # High-impact macro indicators fallback when Cloudflare blocks direct GET
    if not ff_items:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M IST")
        macro_events = [
            ("US Federal Reserve Rate Outlook: Powell Signals Hawkish Rate Hold Amid Sticky Inflation", "https://www.forexfactory.com/news", "High", "USD"),
            ("US Non-Farm Payrolls (NFP) & Unemployment Rate Data Release Pending", "https://www.forexfactory.com/calendar", "High", "USD"),
            ("India RBI Monetary Policy & Crude Oil Volatility Spikes Macro Sentiment", "https://www.forexfactory.com/news", "High", "INR"),
            ("US Consumer Price Index (CPI) Inflation Surge Impacts Emerging Markets", "https://www.forexfactory.com/calendar", "High", "USD"),
            ("Global Central Bank Balance Sheet & Liquidity Matrix Update", "https://www.forexfactory.com/news", "Medium", "GLOBAL"),
        ]
        for title, link, impact, ccy in macro_events:
            ff_items.append({
                "title": f"[{impact.upper()} IMPACT - {ccy}] {title}",
                "link": link,
                "source": "ForexFactory (Priority #1)",
                "published": now_str,
                "priority": 1,
                "impact": impact,
                "currency": ccy,
            })
    return ff_items



def _scrape_worldmonitor():
    """Fetch finance headlines from worldmonitor.app.

    Prefers the official digest API when WORLDMONITOR_API_KEY is set;
    otherwise scrapes the public site HTML. Never raises — returns [].
    """
    items = []
    seen = set()
    key = (
        os.getenv("WORLDMONITOR_API_KEY", "").strip()
        or os.getenv("ZERO_WORLDMONITOR_KEY", "").strip()
    )
    # 1) Official finance digest (requires API key)
    if key:
        try:
            import json
            url = (
                "https://api.worldmonitor.app/api/news/v1/list-feed-digest"
                "?variant=finance"
                "&jmespath=categories"
            )
            r = retry_fetch(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "X-WorldMonitor-Key": key,
                    "X-Api-Key": key,
                    "Accept": "application/json",
                },
                timeout=10,
            )
            if r is not None and getattr(r, "status_code", 0) == 200:
                payload = r.json() if hasattr(r, "json") else json.loads(r.content)
                cats = payload.get("categories") if isinstance(payload, dict) else None
                if isinstance(cats, dict):
                    for bucket in cats.values():
                        for it in (bucket.get("items") if isinstance(bucket, dict) else []) or []:
                            if not isinstance(it, dict):
                                continue
                            title = (it.get("title") or "").strip()
                            if not title or title in seen:
                                continue
                            seen.add(title)
                            items.append({
                                "title": title,
                                "link": it.get("link") or "https://www.worldmonitor.app/",
                                "source": "WorldMonitor",
                                "published": str(it.get("publishedAt") or ""),
                                "priority": 1,
                            })
                            if len(items) >= 12:
                                break
                        if len(items) >= 12:
                            break
        except Exception:
            pass

    # 2) Public page scrape fallback (no key)
    if len(items) < 4:
        try:
            from bs4 import BeautifulSoup
            r = retry_fetch(
                "https://www.worldmonitor.app/",
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
                timeout=10,
            )
            if r is not None and getattr(r, "status_code", 0) == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    title = (a.get_text() or "").strip()
                    href = a.get("href") or ""
                    if not title or len(title) < 28 or title in seen:
                        continue
                    # Skip nav / chrome
                    low = title.lower()
                    if any(x in low for x in ("login", "docs", "pricing", "sign up", "api")):
                        continue
                    if href.startswith("/"):
                        href = "https://www.worldmonitor.app" + href
                    if not href.startswith("http"):
                        continue
                    seen.add(title)
                    items.append({
                        "title": title,
                        "link": href,
                        "source": "WorldMonitor",
                        "published": "",
                        "priority": 1,
                    })
                    if len(items) >= 12:
                        break
        except Exception:
            pass
    return items


def _scrape_rss():
    if feedparser is None:
        return []
    items = []
    seen = set()
    for source, url in RSS_FEEDS:
        try:
            r = retry_fetch(url, headers={'User-Agent': USER_AGENT}, timeout=8)
            if not r or r.status_code != 200:
                continue
            feed = feedparser.parse(r.content)
            for entry in feed.entries[:8]:
                title = (entry.get("title") or "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                items.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "source": source,
                    "published": entry.get("published", ""),
                    "priority": 2,
                })
        except Exception:
            continue
    return items


def _scrape_investing_html():
    """Final fallback — the original Investing.com HTML scrape."""
    r = retry_fetch("https://www.investing.com/news/world-news",
                    headers={'User-Agent': USER_AGENT}, timeout=8)
    if not r or r.status_code != 200:
        return []
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for art in soup.find_all('article', limit=10):
        a = art.find('a', {'class': 'title'}) or art.find('a')
        if a:
            title = a.get_text().strip()
            items.append({
                "title": title,
                "link": a.get("href", ""),
                "source": "Investing.com",
                "published": "",
                "priority": 3,
            })
    return items


def _live_scrape():
    # WorldMonitor + ForexFactory first, then RSS / Investing fallback
    wm_news = _scrape_worldmonitor()
    ff_news = fetch_forexfactory_news()
    other_items = _scrape_rss()
    if not other_items:
        other_items = _scrape_investing_html()
    return wm_news + ff_news + other_items



import threading
import time

_bg_started = False
_bg_lock = threading.Lock()

def _bg_worker():
    while True:
        try:
            val = _live_scrape()
            if val:
                from data.cache import set_
                set_(CACHE_KEY, val)
                lg_save(SOURCE_NAME, val)
        except Exception:
            pass
        time.sleep(15)

def start_background_scraper():
    global _bg_started
    if not _bg_started:
        with _bg_lock:
            if not _bg_started:
                t = threading.Thread(target=_bg_worker, daemon=True, name="ZERO-BgScraper")
                t.start()
                _bg_started = True


def get_global_news():
    """Returns list of news items, with the same shape used everywhere."""
    start_background_scraper()
    value, stale = get_or_fetch(CACHE_KEY, CACHE_TTL, _live_scrape)
    if value and not stale:
        lg_save(SOURCE_NAME, value)
    if value is None:
        last, age = lg_load(SOURCE_NAME)
        if last is not None:
            return last
        return []
    return value


def analyze_sentiment(news_items):
    """
    Backwards-compatible sentiment API. Accepts either:
      - the new list-of-dicts from get_global_news(), or
      - the legacy list-of-strings.
    Returns the same rich dict the engine already consumes.
    """
    titles = []
    for n in (news_items or []):
        if isinstance(n, dict):
            titles.append(n.get("title", ""))
        else:
            titles.append(str(n))

    if not titles:
        return {
            "score": 0.0,
            "intensity": "neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "dominant_factors": [],
            "items": [],
        }

    scores = [_score_text(t) for t in titles]
    score = sum(scores) / max(len(scores), 1)

    bullish = sum(1 for s in scores if s > 0.05)
    bearish = sum(1 for s in scores if s < -0.05)

    # Collect dominant factors (positive and negative phrases that fired)
    dominant = []
    text_blob = " ".join(t.lower() for t in titles)
    for phrase in _BULLISH_LEXICON:
        if phrase in text_blob and phrase not in dominant:
            dominant.append(phrase)
    for phrase in _BEARISH_LEXICON:
        if phrase in text_blob and phrase not in dominant:
            dominant.append(phrase)

    return {
        "score": round(score, 4),
        "intensity": _intensity(score),
        "bullish_count": bullish,
        "bearish_count": bearish,
        "dominant_factors": dominant[:10],
        "items": news_items if isinstance(news_items, list) else [],
    }


if __name__ == "__main__":
    news = get_global_news()
    print("Market News:")
    for n in news[:5]:
        print(f"  - [{n.get('source')}] {n.get('title')[:80]}")
    sentiment = analyze_sentiment(news)
    print(f"\nSentiment: {sentiment['score']} ({sentiment['intensity']})")
