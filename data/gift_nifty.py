"""
Resilient GIFT Nifty scraper.

Sources (in order):
  1. NSE IX direct (best, requires a warm session)
  2. CNBC TV18 gift-nifty page
  3. IG India 50 page (proxy)
  4. Investing.com India 50

All four are wrapped in:
  - data.cache.get_or_fetch (TTL 5 minutes)
  - data.retry.fetch (3 attempts, exp backoff)
  - data.last_good (returns last known value on total failure)
"""
import re
import requests
from bs4 import BeautifulSoup

from config import USER_AGENT
from data.cache import get_or_fetch
from data.retry import fetch as retry_fetch
from data.last_good import save as lg_save, load as lg_load


CACHE_KEY = "gift_nifty_price"
CACHE_TTL = 300  # 5 min — GIFT Nifty ticks every few seconds
SOURCE_NAME = "gift_nifty"


_NSE_SESSION_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
}

_BROWSER_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _parse_price(text: str):
    cleaned = re.sub(r'[^\d.]', '', text or "")
    if not cleaned:
        return None
    try:
        v = float(cleaned)
        # Sanity: GIFT Nifty is in the 15k-30k range. Reject obviously bad parses.
        if 5000 < v < 50000:
            return v
    except ValueError:
        pass
    return None


def _scrape_cnbc():
    r = retry_fetch("https://www.cnbctv18.com/market/gift-nifty/",
                    headers=_BROWSER_HEADERS, timeout=10)
    if not r or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    el = (soup.find('div', {'class': 'price_val'})
          or soup.find('span', {'class': 'last_price'})
          or soup.find(class_=re.compile(r'price|last', re.I)))
    if el:
        return _parse_price(el.get_text())
    return None


def _scrape_ig():
    r = retry_fetch("https://www.ig.com/en/indices/markets-indices/india-50",
                    headers=_BROWSER_HEADERS, timeout=10)
    if not r or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    el = (soup.find('span', {'data-field': 'LTP'})
          or soup.find('div', {'class': 'price-ticket__price'}))
    if el:
        return _parse_price(el.get_text())
    return None


def _scrape_investing():
    r = retry_fetch("https://www.investing.com/indices/india-50",
                    headers=_BROWSER_HEADERS, timeout=10)
    if not r or r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    el = soup.find(class_=re.compile(r'last|lastPrice|price', re.I))
    if el:
        return _parse_price(el.get_text())
    return None


def _scrape_nse_ix():
    # NSE has an IX endpoint that returns JSON for the GIFT Nifty symbol.
    # We need a warm session to set cookies.
    session = requests.Session()
    session.headers.update(_NSE_SESSION_HEADERS)
    try:
        session.get("https://www.nseindia.com/", timeout=8)
    except requests.RequestException:
        return None
    try:
        r = session.get(
            "https://www.nseindia.com/api/marketData/equity?symbol=GIFT",
            timeout=8,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
        # Best-effort: walk to the first price field
        for k in ("lastPrice", "ltp", "price"):
            if k in data and data[k]:
                return _parse_price(str(data[k]))
    except (ValueError, TypeError):
        pass
    return None


def _live_scrape():
    for fn in (_scrape_nse_ix, _scrape_cnbc, _scrape_ig, _scrape_investing):
        try:
            v = fn()
        except Exception:
            v = None
        if v is not None:
            return v
    return None


def get_gift_nifty_price():
    """
    Cached GIFT Nifty price. Returns (price, is_stale: bool).
    On total failure returns last known value with is_stale=True.
    On cold-start failure returns (None, True).
    """
    value, stale = get_or_fetch(CACHE_KEY, CACHE_TTL, _live_scrape)
    if value is not None and not stale:
        lg_save(SOURCE_NAME, value)
    if value is None:
        last, age = lg_load(SOURCE_NAME)
        if last is not None:
            return float(last), True
        return None, True
    return float(value), stale


def compute_premium_delta(nifty_spot_close):
    """Compute the difference between GIFT Nifty and Nifty Spot close."""
    gift, _ = get_gift_nifty_price()
    if gift and nifty_spot_close:
        return gift - nifty_spot_close
    return 0


if __name__ == "__main__":
    p, stale = get_gift_nifty_price()
    print(f"GIFT Nifty Price: {p} (stale={stale})")
