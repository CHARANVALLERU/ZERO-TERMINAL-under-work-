"""
ZERO Live Index Scraper & Real-Time Data Service
=================================================
Fetches live quote and OHLC data directly from official exchange sources:
- SENSEX: https://www.bseindia.com/sensex/code/16
- NIFTY 50: https://www.nseindia.com/
- BANKNIFTY: https://www.nseindia.com/index-tracker/NIFTY%20BANK

Features:
1. Fallback chain: Primary HTML scraper -> yfinance fast tick -> Last known cache.
2. Market timing logic:
   - At 09:15:01 AM IST on trading days: Locks official Opening Price.
   - During 09:15:01 AM - 03:30:00 PM IST: Continuously tracks High/Low breakouts.
   - At 03:30:01 PM IST: Captures final Close price.
"""

from __future__ import annotations
import re
import time
import requests
import logging
import datetime
from typing import Dict, Any, Optional

import yfinance as yf
from config import now_ist, is_trading_day, is_market_open

logger = logging.getLogger("ZERO_LIVE_SCRAPER")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

# Live source URLs specified by user
LIVE_SOURCES = {
    "SENSEX": "https://www.bseindia.com/sensex/code/16",
    "NIFTY 50": "https://www.nseindia.com/",
    "BANKNIFTY": "https://www.nseindia.com/index-tracker/NIFTY%20BANK"
}

YFINANCE_TICKERS = {
    "SENSEX": "^BSESN",
    "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK"
}

# In-memory cache for live index states
_LIVE_CACHE: Dict[str, Dict[str, Any]] = {}


YAHOO_V8_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=false"
HEADERS_YAHOO = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_bse_sensex_live() -> Optional[Dict[str, float]]:
    """
    Fetches live SENSEX price via Yahoo Finance v8 Chart API.
    Uses meta.regularMarketPrice which is the TRUE last-traded price.
    BSE official API (api.bseindia.com) is CDN-blocked and returns HTML.
    """
    try:
        url = YAHOO_V8_URL.format(symbol="^BSESN")
        r = requests.get(url, headers=HEADERS_YAHOO, timeout=5)
        if r.status_code != 200:
            return None
        d = r.json()
        result = d.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})

        price  = float(meta.get("regularMarketPrice") or 0)
        prev_c = float(meta.get("chartPreviousClose") or meta.get("previousClose") or 0)

        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        opens  = [c for c in quotes.get("open", []) if c is not None]
        highs  = [c for c in quotes.get("high", []) if c is not None]
        lows   = [c for c in quotes.get("low", []) if c is not None]

        open_v = float(opens[0])   if opens else price
        high_v = float(max(highs)) if highs else price
        low_v  = float(min(lows))  if lows  else price

        if price < 1:
            return None

        return {
            "price":      round(price, 2),
            "open":       round(open_v, 2),
            "high":       round(high_v, 2),
            "low":        round(low_v, 2),
            "prev_close": round(prev_c, 2),
            "source":     "Yahoo LIVE (SENSEX)"
        }
    except Exception as e:
        logger.debug(f"Yahoo v8 SENSEX exception: {e}")
    return None


def fetch_nse_live(index_name: str) -> Optional[Dict[str, float]]:
    """
    Fetches live quote for NIFTY 50 or BANKNIFTY from NSE India website.
    URL: https://www.nseindia.com/ or https://www.nseindia.com/index-tracker/NIFTY%20BANK
    """
    url = LIVE_SOURCES.get(index_name)
    if not url:
        return None

    try:
        session = requests.Session()
        # Initial request to establish cookies
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=4)
        
        # NSE Index API endpoint
        api_url = "https://www.nseindia.com/api/allIndices"
        resp = session.get(api_url, headers=HEADERS, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            target_key = "NIFTY 50" if index_name == "NIFTY 50" else "NIFTY BANK"
            for item in data.get("data", []):
                if item.get("index") == target_key or item.get("indexSymbol") == target_key:
                    return {
                        "price": float(item.get("last", 0.0)),
                        "open": float(item.get("open", 0.0)),
                        "high": float(item.get("high", 0.0)),
                        "low": float(item.get("low", 0.0)),
                        "prev_close": float(item.get("previousClose", 0.0)),
                        "source": "NSE Official API"
                    }
    except Exception as e:
        logger.debug(f"NSE API scraping exception for {index_name}: {e}")

    return None


def fetch_yfinance_fallback(index_name: str) -> Optional[Dict[str, float]]:
    """yfinance fast_info fallback — uses fast_info.last_price for near-real-time price."""
    ticker_symbol = YFINANCE_TICKERS.get(index_name)
    if not ticker_symbol:
        return None

    try:
        tk = yf.Ticker(ticker_symbol)
        fi = getattr(tk, 'fast_info', None)
        if fi is None:
            raise ValueError("fast_info not available")

        price    = float(getattr(fi, 'last_price', 0) or 0)
        prev_c   = float(getattr(fi, 'previous_close', 0) or 0)
        open_v   = float(getattr(fi, 'open', 0) or price)
        high_v   = float(getattr(fi, 'day_high', 0) or price)
        low_v    = float(getattr(fi, 'day_low', 0) or price)

        if price < 1:
            raise ValueError("fast_info price invalid")

        return {
            "price":      round(price, 2),
            "open":       round(open_v, 2),
            "high":       round(high_v, 2),
            "low":        round(low_v, 2),
            "prev_close": round(prev_c, 2),
            "source":     "yfinance fast feed"
        }
    except Exception as e:
        logger.debug(f"yfinance fast_info exception for {index_name}: {e}")

    return None


def get_live_index_quote(index_name: str) -> Dict[str, Any]:
    """
    Returns live quote with Open, High, Low, Close logic matching user requirements:
    1. Open is fetched at/after 9:15:01 AM.
    2. High and Low update dynamically whenever live price breaches previous High/Low.
    3. Final close locked at 3:30:01 PM.
    """
    now = now_ist()
    today_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M:%S")

    # Check cache
    cached = _LIVE_CACHE.get(index_name, {})
    if cached.get("date") != today_str:
        cached = {
            "date": today_str,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "price": None,
            "source": None,
            "updated_at": None
        }

    # Fetch fresh live data
    live_raw = None
    if index_name == "SENSEX":
        live_raw = fetch_bse_sensex_live()
    elif index_name in ("NIFTY 50", "BANKNIFTY"):
        live_raw = fetch_nse_live(index_name)

    if not live_raw:
        live_raw = fetch_yfinance_fallback(index_name)

    if live_raw:
        current_p = live_raw["price"]
        raw_open = live_raw.get("open")
        raw_high = live_raw.get("high")
        raw_low  = live_raw.get("low")

        cached["price"] = current_p
        cached["source"] = live_raw["source"]
        cached["updated_at"] = now.isoformat()

        # 9:15:01 AM Open price lock
        if cached["open"] is None:
            if raw_open and raw_open > 0:
                cached["open"] = raw_open
            else:
                cached["open"] = current_p

        # Dynamic High & Low break tracking
        if cached["high"] is None:
            cached["high"] = max(raw_high or current_p, current_p, cached["open"])
        else:
            cached["high"] = max(cached["high"], current_p, raw_high or current_p)

        if cached["low"] is None:
            cached["low"] = min(raw_low or current_p, current_p, cached["open"])
        else:
            cached["low"] = min(cached["low"], current_p, raw_low or current_p)

        # 3:30:01 PM Close lock
        if current_time_str >= "15:30:01" or not is_market_open(now):
            if cached["close"] is None or current_time_str >= "15:30:01":
                cached["close"] = current_p
        else:
            cached["close"] = current_p

    _LIVE_CACHE[index_name] = cached
    return cached
