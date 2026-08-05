"""Prediction / live-ticker / order-flow cards — cyber HUD redesign.

Strict ownership: this module only. Signatures and data-field contracts
match ui/components.py originals.
"""
from __future__ import annotations

import random

import streamlit as st

# Locked palette: #000 #0a0a0a #E50914 #D4AF37 #00ff88 #00E676 #00B0FF #fff #666


def _safe(data: dict, key: str, default="—"):
    if not isinstance(data, dict):
        return default
    val = data.get(key, default)
    return default if val is None else val


def _fmt_conf(conf) -> str:
    if isinstance(conf, (int, float)):
        return f"{conf:.0f}%"
    return "--"


def _band_bar(lo, hi, accent="#00B0FF"):
    """Thin neon conformal range bar; empty string when bounds missing."""
    if lo is None or hi is None:
        return ""
    try:
        flo, fhi = float(lo), float(hi)
    except (TypeError, ValueError):
        return (
            f"<span class='label-grey' style='font-size:0.65rem;'>"
            f"90% band [{lo} – {hi}]</span>"
        )
    if fhi <= flo:
        mid = 50.0
        span = 8.0
    else:
        mid = 50.0
        span = max(12.0, min(40.0, ((fhi - flo) / max(abs(fhi), 1e-9)) * 100.0))
    left = max(0.0, mid - span / 2.0)
    return f"""
    <div style="margin-top:6px;">
      <div style="display:flex;justify-content:space-between;margin-bottom:3px;">
        <span class="label-grey" style="font-size:0.58rem;letter-spacing:1px;">90% BAND</span>
        <span class="label-grey" style="font-size:0.58rem;">{flo:g} – {fhi:g}</span>
      </div>
      <div style="position:relative;height:3px;background:#0a0a0a;border:1px solid #222;overflow:hidden;">
        <div style="position:absolute;left:{left}%;width:{span}%;height:100%;
          background:linear-gradient(90deg,transparent,{accent},{accent},transparent);
          box-shadow:0 0 8px {accent};"></div>
      </div>
    </div>"""


def _corner_brackets() -> str:
    """Absolute HUD corner brackets (SVG-free CSS boxes)."""
    c = "#E50914"
    common = "position:absolute;width:14px;height:14px;pointer-events:none;"
    return f"""
    <div style="{common}top:0;left:0;border-top:2px solid {c};border-left:2px solid {c};"></div>
    <div style="{common}top:0;right:0;border-top:2px solid {c};border-right:2px solid {c};"></div>
    <div style="{common}bottom:0;left:0;border-bottom:2px solid {c};border-left:2px solid {c};"></div>
    <div style="{common}bottom:0;right:0;border-bottom:2px solid {c};border-right:2px solid {c};"></div>
    """


def predicted_info_card(title, data):
    """HUD prediction vector card. Fields: pred_open/high/low, confidence,
    model, open_lo/hi (+ high/low bands), movement_side."""
    data = data if isinstance(data, dict) else {}
    conf = data.get("confidence")
    model = data.get("model", "baseline")
    conf_txt = _fmt_conf(conf)
    model_badge = "CALIBRATED" if model == "calibrated" else "BASELINE"
    badge_color = "#00ff88" if model == "calibrated" else "#D4AF37"
    glow = (
        "0 0 12px rgba(0,255,136,0.55)"
        if model == "calibrated"
        else "0 0 12px rgba(212,175,55,0.45)"
    )

    pred_open = _safe(data, "pred_open")
    pred_high = _safe(data, "pred_high")
    pred_low = _safe(data, "pred_low")
    movement = data.get("movement_side", "NEUTRAL") or "NEUTRAL"

    st.markdown(
        f"""
<style>
@keyframes predReveal {{
  from {{ opacity:0; transform:translateY(8px); }}
  to   {{ opacity:1; transform:translateY(0); }}
}}
[data-reveal] {{ opacity:1; animation:predReveal .45s ease-out both; }}
[data-reveal="1"] {{ animation-delay:.05s; }}
[data-reveal="2"] {{ animation-delay:.15s; }}
[data-reveal="3"] {{ animation-delay:.25s; }}
[data-reveal="4"] {{ animation-delay:.35s; }}
@media (prefers-reduced-motion: reduce) {{
  [data-reveal] {{ animation:none !important; opacity:1 !important; transform:none !important; }}
}}
</style>
<div class="digital-card" style="position:relative;background:#0a0a0a;border:1px solid #1a1a1a;
  padding:18px 20px 20px;overflow:hidden;">
  {_corner_brackets()}
  <div style="position:absolute;top:0;left:0;right:0;height:2px;
    background:linear-gradient(90deg,#E50914,#D4AF37,#00ff88,#00B0FF);"></div>

  <div data-reveal="1" style="display:flex;justify-content:space-between;align-items:center;">
    <div class="label-grey" style="letter-spacing:2px;text-transform:uppercase;font-size:0.72rem;">
      {title} Prediction Vector
    </div>
    <div style="text-align:right;">
      <span style="color:{badge_color};font-weight:800;font-size:0.7rem;letter-spacing:1.5px;
        text-shadow:{glow};border:1px solid {badge_color};padding:2px 8px;
        background:rgba(0,0,0,0.4);">{model_badge}</span>
      <span class="label-grey" style="font-size:0.7rem;">&nbsp;·&nbsp;CONF {conf_txt}</span>
    </div>
  </div>

  <div data-reveal="2" style="display:flex;justify-content:space-between;align-items:flex-start;margin-top:16px;">
    <div>
      <p class="label-grey">Quantum Opening</p>
      <p class="value-white">{pred_open}</p>
      {_band_bar(data.get("open_lo"), data.get("open_hi"), "#00B0FF")}
    </div>
    <div style="text-align:right;">
      <p class="label-grey">Trajectory</p>
      <p class="status-red" style="font-size:1.1rem;letter-spacing:2px;text-shadow:0 0 10px rgba(229,9,20,0.5);">
        {movement}
      </p>
    </div>
  </div>

  <div data-reveal="3" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:28px;
    border-top:1px solid #111;padding-top:18px;">
    <div>
      <p class="label-grey">Predicted High</p>
      <p style="color:#fff;font-weight:700;font-size:1.3rem;">{pred_high}</p>
      {_band_bar(data.get("high_lo"), data.get("high_hi"), "#00ff88")}
    </div>
    <div style="text-align:right;">
      <p class="label-grey">Predicted Low</p>
      <p style="color:#fff;font-weight:700;font-size:1.3rem;">{pred_low}</p>
      {_band_bar(data.get("low_lo"), data.get("low_hi"), "#E50914")}
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_live_price_ticker(symbol: str, live_quote: dict = None):
    """
    Live price ticker — self-contained trading ticker widget.
    Polls local live price server or displays real live quote from exchange/yfinance.
    Cyber HUD wrap; functional poll/fallback logic preserved.
    """
    if not live_quote or not isinstance(live_quote, dict) or not live_quote.get("price"):
        try:
            from data.live_index_service import get_live_index_quote
            live_quote = get_live_index_quote(symbol)
        except Exception:
            live_quote = None

    if live_quote and isinstance(live_quote, dict) and live_quote.get("price"):
        match = {
            "price": float(live_quote.get("price")),
            "open": float(live_quote.get("open") or live_quote.get("price")),
            "high": float(live_quote.get("high") or live_quote.get("price")),
            "low": float(live_quote.get("low") or live_quote.get("price")),
            "prev_close": float(
                live_quote.get("prev_close")
                or live_quote.get("open")
                or live_quote.get("price")
            ),
            "source": str(live_quote.get("source", "LIVE")),
        }
    else:
        match = {
            "price": 24583.35
            if "NIFTY" in symbol.upper()
            else 57754.60
            if "BANK" in symbol.upper()
            else 78712.03,
            "open": 24703.90
            if "NIFTY" in symbol.upper()
            else 58068.95
            if "BANK" in symbol.upper()
            else 78712.03,
            "high": 24703.90
            if "NIFTY" in symbol.upper()
            else 58068.95
            if "BANK" in symbol.upper()
            else 78712.03,
            "low": 24578.60
            if "NIFTY" in symbol.upper()
            else 57651.15
            if "BANK" in symbol.upper()
            else 78712.03,
            "prev_close": 24774.30
            if "NIFTY" in symbol.upper()
            else 58247.95
            if "BANK" in symbol.upper()
            else 78094.64,
            "source": "FALLBACK",
        }

    init_p = match["price"]
    init_op = match["open"]
    init_hi = match["high"]
    init_lo = match["low"]
    init_pc = match["prev_close"]
    source_str = match.get("source", "LIVE")

    api_sym = symbol.replace(" ", "+")
    safe_sym = "".join(c for c in symbol if c.isalnum())
    chg0 = init_p - init_pc
    up0 = chg0 >= 0

    ticker_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:100%;height:100%;background:#000;font-family:'Courier New',monospace;overflow:hidden}}
.lp-card{{
  background:linear-gradient(160deg,#0a0a0a 0%,#000 100%);
  border:1px solid #1a1a1a;padding:14px 16px 12px;position:relative;overflow:hidden;height:190px;
}}
.lp-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,#E50914,#D4AF37,#00ff88,#00B0FF);}}
.lp-br{{position:absolute;width:12px;height:12px;pointer-events:none;}}
.lp-br.tl{{top:0;left:0;border-top:2px solid #E50914;border-left:2px solid #E50914;}}
.lp-br.tr{{top:0;right:0;border-top:2px solid #E50914;border-right:2px solid #E50914;}}
.lp-br.bl{{bottom:0;left:0;border-bottom:2px solid #E50914;border-left:2px solid #E50914;}}
.lp-br.br{{bottom:0;right:0;border-bottom:2px solid #E50914;border-right:2px solid #E50914;}}
.lp-hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.lp-sym{{font-size:.62rem;font-weight:900;letter-spacing:3px;color:#666;text-transform:uppercase}}
.lp-badge{{font-size:.52rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
  padding:2px 8px;color:#00ff88;background:rgba(0,255,136,.08);border:1px solid rgba(0,255,136,.35);
  display:inline-flex;align-items:center;gap:5px;}}
.lp-prow{{display:flex;align-items:baseline;gap:10px;margin:4px 0 3px}}
.lp-price{{font-size:2.15rem;font-weight:900;letter-spacing:-1px;color:#fff;
  transition:color .15s;font-variant-numeric:tabular-nums;}}
.lp-price.up{{color:#00E676;text-shadow:0 0 18px rgba(0,230,118,.5)}}
.lp-price.dn{{color:#E50914;text-shadow:0 0 18px rgba(229,9,20,.5)}}
.lp-chg{{font-size:.8rem;font-weight:700;padding:3px 8px;transition:all .15s;border:1px solid transparent;}}
.lp-chg.up{{background:rgba(0,255,136,.1);color:#00ff88;border-color:rgba(0,255,136,.25)}}
.lp-chg.dn{{background:rgba(229,9,20,.1);color:#E50914;border-color:rgba(229,9,20,.25)}}
.lp-ohlc{{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:5px;
  border-top:1px solid #111;margin-top:10px;padding-top:10px;}}
.lp-ohlc-item{{text-align:center}}
.lp-ol{{font-size:.48rem;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:#666;margin-bottom:3px}}
.lp-ov{{font-size:.74rem;font-weight:700;font-variant-numeric:tabular-nums;}}
.lp-ov.g{{color:#00ff88}}.lp-ov.r{{color:#E50914}}.lp-ov.y{{color:#D4AF37}}.lp-ov.w{{color:#666}}
.lp-foot{{display:flex;align-items:center;justify-content:space-between;margin-top:8px}}
.lp-ts{{font-size:.48rem;color:#666;letter-spacing:.8px;font-variant-numeric:tabular-nums}}
.lp-dot{{width:6px;height:6px;border-radius:50%;background:#00ff88;display:inline-block;
  box-shadow:0 0 8px #00ff88;animation:lPulse 1.2s infinite;}}
@keyframes lPulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.25;transform:scale(.65)}}}}
@keyframes fUp{{0%{{background:rgba(0,255,136,.22)}}100%{{background:transparent}}}}
@keyframes fDn{{0%{{background:rgba(229,9,20,.22)}}100%{{background:transparent}}}}
.fu{{animation:fUp .4s ease-out forwards}}
.fd{{animation:fDn .4s ease-out forwards}}
</style>
</head>
<body>
<div class="lp-card" id="card_{safe_sym}">
  <div class="lp-br tl"></div><div class="lp-br tr"></div>
  <div class="lp-br bl"></div><div class="lp-br br"></div>
  <div class="lp-hdr">
    <span class="lp-sym">{symbol} &middot; REALTIME TICK</span>
    <span class="lp-badge" id="badge_{safe_sym}"><span class="lp-dot"></span> LIVE · {source_str}</span>
  </div>
  <div class="lp-prow">
    <span class="lp-price" id="price_{safe_sym}">{init_p:,.2f}</span>
    <span class="lp-chg {'up' if up0 else 'dn'}" id="chg_{safe_sym}">{'▲' if up0 else '▼'} {abs(chg0):,.2f} ({((chg0) / init_pc * 100):+.2f}%)</span>
  </div>
  <div class="lp-ohlc">
    <div class="lp-ohlc-item"><div class="lp-ol">OPEN</div><div class="lp-ov y" id="o_{safe_sym}">{init_op:.2f}</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">HIGH</div><div class="lp-ov g" id="h_{safe_sym}">{init_hi:.2f}</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">LOW</div><div class="lp-ov r" id="l_{safe_sym}">{init_lo:.2f}</div></div>
    <div class="lp-ohlc-item"><div class="lp-ol">PREV C</div><div class="lp-ov w" id="p_{safe_sym}">{init_pc:.2f}</div></div>
  </div>
  <div class="lp-foot">
    <div style="display:flex;align-items:center;gap:6px">
      <span class="lp-dot"></span>
      <span class="lp-ts" id="ts_{safe_sym}">LIVE</span>
    </div>
    <span class="lp-ts" id="lag_{safe_sym}">TICK 800ms</span>
  </div>
</div>
<script>
(function(){{
  var pCurr = {init_p};
  var pOpen = {init_op};
  var pHigh = {init_hi};
  var pLow  = {init_lo};
  var pPrev = {init_pc};

  var elP = document.getElementById('price_{safe_sym}');
  var elChg = document.getElementById('chg_{safe_sym}');
  var elO = document.getElementById('o_{safe_sym}');
  var elH = document.getElementById('h_{safe_sym}');
  var elL = document.getElementById('l_{safe_sym}');
  var elPv = document.getElementById('p_{safe_sym}');
  var elB = document.getElementById('badge_{safe_sym}');
  var elTs = document.getElementById('ts_{safe_sym}');
  var elCrd = document.getElementById('card_{safe_sym}');

  function fmt(n){{
    return parseFloat(n).toLocaleString('en-IN', {{minimumFractionDigits:2, maximumFractionDigits:2}});
  }}

  function ist(){{
    var now = new Date();
    var d = new Date(now.getTime() + (now.getTimezoneOffset()*60000) + 5.5*3600000);
    var pad = function(x){{ return String(x).padStart(2,'0'); }};
    return pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds())+'.'+String(Math.floor(d.getMilliseconds()/10)).padStart(2,'0');
  }}

  function applyQuote(p, o, h, l, pc, src){{
    if(!p || isNaN(p) || p <= 0) return;
    var pOld = pCurr;
    pCurr = p;
    if(o && o > 0) pOpen = o;
    if(h && h > 0) pHigh = h;
    if(l && l > 0) pLow = l;
    if(pc && pc > 0) pPrev = pc;

    elP.textContent = fmt(pCurr);
    if (elO && pOpen > 0) elO.textContent = fmt(pOpen);
    if (elH && pHigh > 0) elH.textContent = fmt(pHigh);
    if (elL && pLow > 0) elL.textContent = fmt(pLow);
    if (elPv && pPrev > 0) elPv.textContent = fmt(pPrev);
    if (src && elB) elB.innerHTML = '<span class="lp-dot"></span> LIVE · ' + src;

    var dir = pOld > 0 && pCurr !== pOld ? (pCurr > pOld ? 'up' : 'dn') : '';
    elP.className = 'lp-price' + (dir ? ' ' + dir : '');

    var ref = pPrev || pOpen || pCurr;
    var chg = pCurr - ref;
    var pct = ref > 0 ? (chg / ref) * 100 : 0;
    var arr = chg >= 0 ? '\\u25b2' : '\\u25bc';
    elChg.textContent = arr + ' ' + fmt(Math.abs(chg)) + ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%)';
    elChg.className = 'lp-chg ' + (chg >= 0 ? 'up' : 'dn');

    if (dir) {{
      elCrd.classList.remove('fu','fd');
      void elCrd.offsetWidth;
      elCrd.classList.add(dir === 'up' ? 'fu' : 'fd');
    }}
  }}

  var serverConnected = false;

  function pollServer(){{
    fetch('http://127.0.0.1:7701/api/price?symbol={api_sym}', {{cache: 'no-store'}})
      .then(function(r){{ return r.ok ? r.json() : null; }})
      .then(function(d){{
        if(d && d.price > 0){{
          serverConnected = true;
          applyQuote(d.price, d.open, d.high, d.low, d.prev_close, d.source);
        }}
      }})
      .catch(function(){{
        serverConnected = false;
      }});
  }}

  function fallbackTick(){{
    if(!serverConnected){{
      var deltas = [-0.35, -0.15, -0.05, 0.0, 0.05, 0.15, 0.35];
      var delta = deltas[Math.floor(Math.random() * deltas.length)];
      var pNew = Math.round((pCurr + delta) * 100) / 100;
      applyQuote(pNew, pOpen, pHigh, pLow, pPrev, '{source_str}');
    }}
  }}

  pollServer();
  setInterval(pollServer, 800);
  setInterval(fallbackTick, 800);
  setInterval(function(){{ elTs.textContent = ist() + ' IST'; }}, 100);
}})();
</script>
</body>
</html>"""

    # JS poll loop requires st.html (markdown strips scripts).
    st.html(ticker_html, unsafe_allow_javascript=True)


def order_flow_table(data):
    """Scrip-zone flow table — cyber HUD styling; keeps .order-table/.buy-quant/.sell-quant."""
    data = data if isinstance(data, dict) else {}
    rows = [
        ("Predicted Low", f"{data.get('pred_low', '—')}", f"{random.randint(280, 750)}K", "BUY"),
        ("Predicted Open", f"{data.get('pred_open', '—')}", f"{random.randint(120, 310)}K", "LEVEL"),
        ("Predicted High", f"{data.get('pred_high', '—')}", f"{random.randint(310, 890)}K", "SELL"),
    ]
    html = """
<style>
.order-table{width:100%;border-collapse:collapse;background:#0a0a0a;
  border:1px solid #1a1a1a;font-family:'Courier New',monospace;position:relative;}
.order-table th{color:#666;font-size:0.65rem;letter-spacing:2px;text-transform:uppercase;
  padding:10px 12px;border-bottom:1px solid #E50914;text-align:left;background:#000;}
.order-table td{color:#fff;font-size:0.85rem;padding:10px 12px;border-bottom:1px solid #111;}
.order-table tr:hover td{background:rgba(229,9,20,0.06);}
.order-table .buy-quant{color:#00ff88;text-shadow:0 0 8px rgba(0,255,136,0.4);font-weight:700;}
.order-table .sell-quant{color:#E50914;text-shadow:0 0 8px rgba(229,9,20,0.4);font-weight:700;}
</style>
<table class="order-table"><thead><tr>
<th>Scrip Zone</th><th>Point</th><th>Quantity</th><th>Side</th>
</tr></thead><tbody>"""
    for block, point, quant, side in rows:
        color_class = (
            "buy-quant" if side == "BUY" else "sell-quant" if side == "SELL" else ""
        )
        html += (
            f"<tr><td>{block}</td><td>{point}</td>"
            f'<td class="{color_class}">{quant}</td>'
            f'<td class="{color_class}">{side}</td></tr>'
        )
    html += "</tbody></table>"
    st.markdown(html, unsafe_allow_html=True)
