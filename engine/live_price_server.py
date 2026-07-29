"""
ZERO Live Price Proxy Server
=============================
A lightweight HTTP server that runs on localhost:7701 alongside the Streamlit app.
It polls NSE/BSE exchange APIs every 1 second server-side (no CORS issues),
caches the latest OHLC snapshot, and serves it as JSON so the browser iframe
can fetch from http://localhost:7701/api/price every 100ms without any CORS block.

Architecture:
  ┌─────────────────────────────────────────────────────────┐
  │  Background Thread A: Poll NSE/BSE every 1s → cache     │
  │  Background Thread B: HTTP server on :7701               │
  │    GET /api/price?symbol=NIFTY+50 → returns JSON         │
  │    GET /health                    → returns {"ok": true} │
  └─────────────────────────────────────────────────────────┘
  Browser iframe JS fetches http://localhost:7701/api/price?symbol=...
  every 100ms → instant DOM update with NO Streamlit rerun.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

import requests

logger = logging.getLogger("ZERO_PRICE_SERVER")

# ── Configuration ──────────────────────────────────────────────────────────────
PRICE_SERVER_PORT = int(os.getenv("ZERO_PRICE_SERVER_PORT", "7701"))
POLL_INTERVAL_SECONDS = 1.0          # How often to hit exchange APIs
REQUEST_TIMEOUT = 3                   # Seconds before giving up on an exchange call

NSE_API_URL = "https://www.nseindia.com/api/allIndices"
BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/SensexData/w"

HEADERS_NSE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}
HEADERS_BSE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com/",
}

# NSE index key → display name
NSE_INDEX_MAP = {
    "NIFTY 50": "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
}
BSE_SYMBOL = "SENSEX"

# ── Module-level price cache ───────────────────────────────────────────────────
# Written by the polling thread, read by the HTTP handler — no lock needed
# because Python's GIL guarantees atomic dict assignment for small dicts.
_PRICE_CACHE: Dict[str, Dict[str, Any]] = {
    "NIFTY 50":  {"price": 0, "open": 0, "high": 0, "low": 0, "prev_close": 0, "source": "pending", "updated_ms": 0},
    "BANKNIFTY": {"price": 0, "open": 0, "high": 0, "low": 0, "prev_close": 0, "source": "pending", "updated_ms": 0},
    "SENSEX":    {"price": 0, "open": 0, "high": 0, "low": 0, "prev_close": 0, "source": "pending", "updated_ms": 0},
}

# Track day-specific running high/low so we never go backwards
_DAY_TRACK: Dict[str, Dict[str, Any]] = {
    "NIFTY 50":  {"date": "", "high": 0.0, "low": float("inf"), "open": 0.0},
    "BANKNIFTY": {"date": "", "high": 0.0, "low": float("inf"), "open": 0.0},
    "SENSEX":    {"date": "", "high": 0.0, "low": float("inf"), "open": 0.0},
}

_nse_session: Optional[requests.Session] = None
_server_running = False
_server_thread: Optional[threading.Thread] = None
_poll_thread: Optional[threading.Thread] = None


def _get_nse_session() -> requests.Session:
    global _nse_session
    if _nse_session is None:
        _nse_session = requests.Session()
        try:
            _nse_session.get(
                "https://www.nseindia.com",
                headers={**HEADERS_NSE, "Accept": "text/html"},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception:
            pass
    return _nse_session


def _update_day_track(symbol: str, price: float, open_val: float, high_val: float, low_val: float) -> tuple:
    """Maintain running day-specific High/Low (never goes backwards within a day)."""
    today = datetime.date.today().isoformat()
    track = _DAY_TRACK[symbol]

    if track["date"] != today:
        # New day — reset
        track["date"] = today
        track["high"] = max(price, high_val)
        track["low"]  = min(price, low_val) if low_val > 1 else price
        track["open"] = open_val if open_val > 1 else price
    else:
        if high_val > 0:
            track["high"] = max(track["high"], high_val, price)
        else:
            track["high"] = max(track["high"], price)

        if low_val > 1:
            track["low"] = min(track["low"] if track["low"] > 1 else price, low_val, price)
        else:
            track["low"] = min(track["low"] if track["low"] > 1 else price, price)

        if open_val > 1 and track["open"] == 0:
            track["open"] = open_val

    return track["open"], track["high"], track["low"]


def _poll_nse() -> None:
    """Fetch all indices from NSE API and update cache."""
    session = _get_nse_session()
    try:
        resp = session.get(NSE_API_URL, headers=HEADERS_NSE, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])
        for item in items:
            for symbol, nse_key in NSE_INDEX_MAP.items():
                if item.get("index") == nse_key or item.get("indexSymbol") == nse_key:
                    price     = float(item.get("last", 0) or item.get("indexValue", 0) or 0)
                    open_val  = float(item.get("open", 0) or 0)
                    high_val  = float(item.get("high", 0) or 0)
                    low_val   = float(item.get("low", 0) or 0)
                    prev_c    = float(item.get("previousClose", 0) or 0)

                    if price < 1:
                        continue

                    o, h, l = _update_day_track(symbol, price, open_val, high_val, low_val)
                    _PRICE_CACHE[symbol] = {
                        "price":      round(price, 2),
                        "open":       round(o, 2),
                        "high":       round(h, 2),
                        "low":        round(l, 2),
                        "prev_close": round(prev_c, 2),
                        "source":     "NSE",
                        "updated_ms": int(time.time() * 1000),
                    }
    except requests.exceptions.ConnectionError:
        # Session may have expired — reset for next cycle
        _nse_session = None
    except Exception as exc:
        logger.debug(f"NSE poll error: {exc}")


def _poll_bse() -> None:
    """Fetch SENSEX from BSE API and update cache."""
    try:
        resp = requests.get(BSE_API_URL, headers=HEADERS_BSE, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        def _f(key):
            v = str(data.get(key, "0") or "0").replace(",", "")
            try:
                return float(v)
            except Exception:
                return 0.0

        price     = _f("CurrVal")
        open_val  = _f("OpenVal")
        high_val  = _f("High52") or _f("HighVal")
        low_val   = _f("Low52")  or _f("LowVal")
        prev_c    = _f("PrevClose")

        if price < 1:
            return

        o, h, l = _update_day_track(BSE_SYMBOL, price, open_val, high_val, low_val)
        _PRICE_CACHE[BSE_SYMBOL] = {
            "price":      round(price, 2),
            "open":       round(o, 2),
            "high":       round(h, 2),
            "low":        round(l, 2),
            "prev_close": round(prev_c, 2),
            "source":     "BSE",
            "updated_ms": int(time.time() * 1000),
        }
    except Exception as exc:
        logger.debug(f"BSE poll error: {exc}")


def _fallback_yfinance() -> None:
    """yfinance fallback — used when exchange APIs are down."""
    try:
        import yfinance as yf
        symbols_map = {
            "NIFTY 50":  "^NSEI",
            "BANKNIFTY": "^NSEBANK",
            "SENSEX":    "^BSESN",
        }
        for sym, ticker in symbols_map.items():
            if _PRICE_CACHE[sym]["price"] > 0:
                continue  # Skip if we already have live data
            try:
                df = yf.Ticker(ticker).history(period="1d", interval="1m")
                if df.empty:
                    continue
                latest = df.iloc[-1]
                price  = float(latest["Close"])
                open_v = float(df.iloc[0]["Open"])
                high_v = float(df["High"].max())
                low_v  = float(df["Low"].min())
                o, h, l = _update_day_track(sym, price, open_v, high_v, low_v)
                _PRICE_CACHE[sym] = {
                    "price":      round(price, 2),
                    "open":       round(o, 2),
                    "high":       round(h, 2),
                    "low":        round(l, 2),
                    "prev_close": round(open_v, 2),
                    "source":     "yfinance",
                    "updated_ms": int(time.time() * 1000),
                }
            except Exception:
                pass
    except ImportError:
        pass


def _polling_loop() -> None:
    """Background loop: poll NSE + BSE every POLL_INTERVAL_SECONDS."""
    global _server_running
    logger.info(f"ZERO Price Poller started (interval={POLL_INTERVAL_SECONDS}s)")
    yf_cycle = 0
    while _server_running:
        try:
            _poll_nse()
            _poll_bse()
            # Every 30 cycles (~30s), also try yfinance as gap-fill
            yf_cycle += 1
            if yf_cycle >= 30:
                yf_cycle = 0
                _fallback_yfinance()
        except Exception as exc:
            logger.debug(f"Polling loop error: {exc}")
        time.sleep(POLL_INTERVAL_SECONDS)


# ── Ticker HTML page (served at /ticker?symbol=...) ──────────────────────────
def _build_ticker_html(symbol: str, port: int) -> str:
    """
    Builds the self-contained ticker HTML page.
    Served as a real URL so st.iframe never recreates the iframe on Streamlit reruns.
    JS polls /api/price every 100ms continuously — the loop is never interrupted.
    """
    api_url = f"http://127.0.0.1:{port}/api/price?symbol={symbol.replace(' ', '+')}"
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;background:#0a0a0e;font-family:'Inter',system-ui,sans-serif;overflow:hidden}}

.lp-card{{
  background:linear-gradient(135deg,rgba(8,8,12,1) 0%,rgba(14,12,20,1) 100%);
  border:1px solid rgba(255,255,255,0.07);
  border-radius:10px;
  padding:13px 15px 11px 15px;
  position:relative;overflow:hidden;
  height:calc(100vh - 4px);
}}
.lp-card::before{{
  content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,#E50914,#D4AF37,#00ff88);
}}
.lp-hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.lp-sym{{font-size:.6rem;font-weight:900;letter-spacing:3px;color:#555;text-transform:uppercase}}
.lp-badge{{
  font-size:.48rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  padding:2px 7px;border-radius:3px;transition:all .3s;
  color:#00ff88;background:rgba(0,255,136,.07);border:1px solid rgba(0,255,136,.2);
}}
.lp-badge.err{{color:#E50914;background:rgba(229,9,20,.07);border-color:rgba(229,9,20,.25)}}

.lp-prow{{display:flex;align-items:baseline;gap:10px;margin:4px 0 3px}}
.lp-price{{
  font-size:2.1rem;font-weight:900;letter-spacing:-1px;
  color:#FFF;transition:color .2s;font-variant-numeric:tabular-nums;
}}
.lp-price.up{{color:#00ff88;text-shadow:0 0 18px rgba(0,255,136,.45)}}
.lp-price.dn{{color:#E50914;text-shadow:0 0 18px rgba(229,9,20,.45)}}

.lp-chg{{
  font-size:.82rem;font-weight:700;padding:3px 8px;border-radius:4px;transition:all .2s;
}}
.lp-chg.up{{background:rgba(0,255,136,.12);color:#00ff88}}
.lp-chg.dn{{background:rgba(229,9,20,.12);color:#E50914}}
.lp-chg.flat{{background:rgba(212,175,55,.1);color:#D4AF37}}

.lp-ohlc{{
  display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:5px;
  border-top:1px solid rgba(255,255,255,.055);margin-top:9px;padding-top:9px;
}}
.lp-ohlc-item{{text-align:center}}
.lp-ol{{font-size:.48rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#3a3a3a;margin-bottom:3px}}
.lp-ov{{font-size:.74rem;font-weight:700;font-variant-numeric:tabular-nums;transition:color .2s}}
.lp-ov.g{{color:#00ff88}}.lp-ov.r{{color:#E50914}}.lp-ov.y{{color:#D4AF37}}.lp-ov.w{{color:#888}}

.lp-foot{{display:flex;align-items:center;justify-content:space-between;margin-top:7px}}
.lp-ts{{font-size:.45rem;color:#2d2d2d;letter-spacing:.8px;font-variant-numeric:tabular-nums}}

.lp-dot{{
  width:6px;height:6px;border-radius:50%;background:#00ff88;
  display:inline-block;margin-right:5px;box-shadow:0 0 6px #00ff88;
  animation:lPulse 1.4s infinite;
}}
.lp-dot.err{{background:#E50914;box-shadow:0 0 6px #E50914}}
@keyframes lPulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.35;transform:scale(.7)}}}}

@keyframes fUp{{0%{{background:rgba(0,255,136,.22)}}100%{{background:transparent}}}}
@keyframes fDn{{0%{{background:rgba(229,9,20,.22)}}100%{{background:transparent}}}}
.fu{{animation:fUp .5s ease-out forwards;border-radius:7px}}
.fd{{animation:fDn .5s ease-out forwards;border-radius:7px}}
</style>
</head>
<body>
<div class="lp-card" id="card">
  <div class="lp-hdr">
    <span class="lp-sym">{symbol} &middot; LIVE CMP</span>
    <span class="lp-badge" id="badge">&bull; CONNECTING</span>
  </div>
  <div class="lp-prow">
    <span class="lp-price" id="price">&#8212;</span>
    <span class="lp-chg flat" id="chg">&#8212;</span>
  </div>
  <div class="lp-ohlc">
    <div class="lp-ohlc-item"><div class="lp-ol">OPEN</div><div class="lp-ov y" id="o">&#8212;</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">HIGH</div><div class="lp-ov g" id="h">&#8212;</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">LOW</div><div class="lp-ov r" id="l">&#8212;</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">PREV C</div><div class="lp-ov w" id="p">&#8212;</div></div>
  </div>
  <div class="lp-foot">
    <div style="display:flex;align-items:center">
      <span class="lp-dot" id="dot"></span>
      <span class="lp-ts" id="ts">SYNCING...</span>
    </div>
    <span class="lp-ts" id="lag"></span>
  </div>
</div>

<script>
(function(){{
  var API   = '{api_url}';
  var elP   = document.getElementById('price');
  var elChg = document.getElementById('chg');
  var elO   = document.getElementById('o');
  var elH   = document.getElementById('h');
  var elL   = document.getElementById('l');
  var elPv  = document.getElementById('p');
  var elB   = document.getElementById('badge');
  var elTs  = document.getElementById('ts');
  var elLg  = document.getElementById('lag');
  var elDot = document.getElementById('dot');
  var elCrd = document.getElementById('card');

  var last  = 0, prev = 0, errs = 0;

  function fmt(n){{
    n = parseFloat(n);
    if(!n||isNaN(n)) return '\u2014';
    return n.toLocaleString('en-IN',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  }}

  function ist(){{
    var now=new Date();
    var d=new Date(now.getTime()+(now.getTimezoneOffset()*60000)+5.5*3600000);
    var p=function(x){{return String(x).padStart(2,'0');}};
    return p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds())+'.'+String(d.getMilliseconds()).padStart(3,'0');
  }}

  function apply(d){{
    var price=parseFloat(d.price||0);
    if(!price||isNaN(price)) return;
    var changed=last!==0&&price!==last;
    var dir=price>last?'up':price<last?'dn':'';
    var pv=parseFloat(d.prev_close||0);if(pv>0)prev=pv;
    var op=parseFloat(d.open||0);
    var hi=parseFloat(d.high||0);
    var lo=parseFloat(d.low||0);

    elP.textContent=fmt(price);
    elP.className='lp-price'+(dir?' '+dir:'');

    var ref=prev||op||price;
    if(ref>0){{
      var chg=price-ref,pct=chg/ref*100;
      var arr=chg>=0?'\u25b2':'\u25bc';
      elChg.textContent=arr+' '+fmt(Math.abs(chg))+' ('+pct.toFixed(2)+'%)';
      elChg.className='lp-chg '+(chg>=0?'up':'dn');
    }}

    if(op>0) elO.textContent=fmt(op);
    if(hi>0) elH.textContent=fmt(hi);
    if(lo>1) elL.textContent=fmt(lo);
    if(prev>0) elPv.textContent=fmt(prev);

    var src=d.source||'LIVE';
    var age=d.updated_ms?Date.now()-d.updated_ms:0;
    if(age>10000){{
      elB.textContent='\u25cf STALE ('+Math.round(age/1000)+'s)';
      elB.className='lp-badge err';
    }}else{{
      elB.textContent='\u25cf '+src;
      elB.className='lp-badge';
      elDot.className='lp-dot';
    }}

    if(changed){{
      elCrd.classList.remove('fu','fd');
      void elCrd.offsetWidth;
      elCrd.classList.add(dir==='up'?'fu':'fd');
    }}
    errs=0;last=price;
  }}

  function poll(){{
    var t0=Date.now();
    fetch(API,{{cache:'no-store'}})
      .then(function(r){{if(!r.ok)throw 0;return r.json();}})
      .then(function(d){{
        elLg.textContent='LAG '+(Date.now()-t0)+'ms';
        apply(d);
      }})
      .catch(function(){{
        errs++;
        if(errs>=3){{
          elB.textContent='\u25cf OFFLINE';
          elB.className='lp-badge err';
          elDot.className='lp-dot err';
        }}
      }})
      .finally(function(){{setTimeout(poll,100);}});
  }}

  setInterval(function(){{elTs.textContent=ist()+' IST';}},100);
  poll();
}})();
</script>
</body>
</html>"""


# ── HTTP Handler ────────────────────────────────────────────────────────────────
class PriceHandler(BaseHTTPRequestHandler):
    """Handles GET requests from the browser iframe."""

    def log_message(self, fmt, *args):  # silence default access log
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body_bytes: bytes, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        if path == "/health":
            self._send_json({"ok": True, "port": PRICE_SERVER_PORT})
            return

        if path == "/api/price":
            symbol = (params.get("symbol", ["NIFTY 50"])[0]).strip()
            data   = _PRICE_CACHE.get(symbol, {})
            if data:
                self._send_json(data)
            else:
                self._send_json({"error": f"Unknown symbol: {symbol}"}, 404)
            return

        if path == "/api/all":
            self._send_json(_PRICE_CACHE)
            return

        if path == "/ticker":
            symbol = (params.get("symbol", ["NIFTY 50"])[0]).strip()
            html   = _build_ticker_html(symbol, PRICE_SERVER_PORT)
            self._send_html(html.encode("utf-8"))
            return

        self._send_json({"error": "Not found"}, 404)



def _run_server() -> None:
    global _server_running
    try:
        server = HTTPServer(("127.0.0.1", PRICE_SERVER_PORT), PriceHandler)
        server.timeout = 1.0
        logger.info(f"ZERO Price Server listening on http://127.0.0.1:{PRICE_SERVER_PORT}")
        while _server_running:
            server.handle_request()
        server.server_close()
    except OSError as e:
        if e.errno == 10048 or e.errno == 98:  # Port already in use
            logger.info(f"ZERO Price Server already running on port {PRICE_SERVER_PORT}")
        else:
            logger.error(f"ZERO Price Server error: {e}")


def is_server_running() -> bool:
    """Quick check if our price server is reachable."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", PRICE_SERVER_PORT))
            return True
        except Exception:
            return False


def start_price_server() -> bool:
    """
    Start the background price server + polling thread.
    Safe to call multiple times — idempotent.
    Returns True if newly started, False if already running.
    """
    global _server_running, _server_thread, _poll_thread

    if is_server_running():
        logger.debug("Price server already running, skipping start.")
        return False

    _server_running = True

    _poll_thread = threading.Thread(target=_polling_loop, name="ZeroPricePoller", daemon=True)
    _poll_thread.start()

    _server_thread = threading.Thread(target=_run_server, name="ZeroPriceServer", daemon=True)
    _server_thread.start()

    # Seed yfinance immediately so iframe has data on first render
    threading.Thread(target=_fallback_yfinance, daemon=True).start()

    logger.info("ZERO Price Server + Poller threads launched.")
    return True


def stop_price_server() -> None:
    global _server_running
    _server_running = False


def get_cached_price(symbol: str) -> Dict[str, Any]:
    """Return cached price dict for a given symbol (used by Python callers)."""
    return dict(_PRICE_CACHE.get(symbol, {}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_price_server()
    print(f"Price server running on port {PRICE_SERVER_PORT}. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
            print(_PRICE_CACHE)
    except KeyboardInterrupt:
        stop_price_server()
