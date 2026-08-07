"""ZERO cyber sidebar / splash chrome.

Drop-in replacements for splash, digital clock, and ZERO AGI sidebar entry.
Owns only this module — does not mutate ui/components.py or app.py.
"""

from __future__ import annotations

import base64
import json
import os

import streamlit as st

# Locked palette
_BLACK = "#000"
_SURFACE = "#0a0a0a"
_RED = "#E50914"
_GOLD = "#D4AF37"
_NEON = "#00ff88"
_GREEN = "#00E676"
_GOLD_ACCENT = "#D4AF37"
_WHITE = "#fff"
_MUTED = "#666"


def get_base64_of_bin_file(bin_file: str) -> str:
    try:
        with open(bin_file, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""


def show_zero_digital_splash() -> None:
    """Matrix-tinged splash reveal with glitch ZERO wordmark + cycling status."""
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
    logo_b64 = get_base64_of_bin_file(logo_path)
    img_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""

    html_loader = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    margin: 0; overflow: hidden; background: {_BLACK};
    font-family: 'Share Tech Mono', monospace;
    height: 100vh;
  }}
  .stage {{
    position: relative; height: 100vh; width: 100%;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    background:
      radial-gradient(ellipse at 50% 30%, rgba(0,255,136,0.06) 0%, transparent 55%),
      linear-gradient({_BLACK} 50%, transparent 50%),
      linear-gradient(90deg, {_SURFACE}, {_BLACK});
    background-size: 100% 100%, 100% 3px, 100% 100%;
    overflow: hidden;
  }}
  .matrix {{
    position: absolute; inset: 0; pointer-events: none; opacity: 0.18;
    background-image: repeating-linear-gradient(
      0deg, transparent, transparent 2px, rgba(0,255,136,0.04) 2px, rgba(0,255,136,0.04) 4px
    );
    animation: matrix-scroll 12s linear infinite;
  }}
  @keyframes matrix-scroll {{
    from {{ background-position: 0 0; }}
    to   {{ background-position: 0 120px; }}
  }}
  .scan {{
    position: absolute; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, {_NEON}, transparent);
    opacity: 0.35; animation: scan-y 3.2s linear infinite;
  }}
  @keyframes scan-y {{
    0%   {{ top: 0%; }}
    100% {{ top: 100%; }}
  }}
  .logo {{
    width: 120px; height: 120px; border-radius: 50%;
    border: 1px solid rgba(0,255,136,0.35);
    box-shadow: 0 0 40px rgba(229,9,20,0.35), 0 0 24px rgba(0,255,136,0.2);
    object-fit: cover; margin-bottom: 22px;
    animation: pulse-core 2.4s ease-in-out infinite alternate;
    position: relative; z-index: 2;
  }}
  .logo-fallback {{
    width: 120px; height: 120px; border-radius: 50%;
    border: 1px solid {_RED}; display: flex; align-items: center; justify-content: center;
    color: {_RED}; font-family: Orbitron, sans-serif; font-weight: 900; font-size: 1.4rem;
    letter-spacing: 4px; margin-bottom: 22px; z-index: 2;
    box-shadow: 0 0 30px rgba(229,9,20,0.4);
  }}
  @keyframes pulse-core {{
    from {{ box-shadow: 0 0 20px rgba(229,9,20,0.25), 0 0 12px rgba(0,255,136,0.15); }}
    to   {{ box-shadow: 0 0 48px rgba(229,9,20,0.55), 0 0 28px rgba(0,255,136,0.35); }}
  }}
  .wordmark {{
    font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 3.2rem;
    letter-spacing: 0.45em; color: {_WHITE}; position: relative; z-index: 2;
    text-shadow: 0 0 18px rgba(0,255,136,0.35);
    animation: glitch 2.8s infinite;
  }}
  .wordmark::before, .wordmark::after {{
    content: 'ZERO'; position: absolute; left: 0; top: 0;
    width: 100%; overflow: hidden;
  }}
  .wordmark::before {{
    color: {_GOLD_ACCENT}; clip-path: inset(0 0 55% 0);
    transform: translate(-2px, -1px); opacity: 0.85;
    animation: glitch-a 2.2s infinite linear alternate-reverse;
  }}
  .wordmark::after {{
    color: {_RED}; clip-path: inset(45% 0 0 0);
    transform: translate(2px, 1px); opacity: 0.85;
    animation: glitch-b 1.8s infinite linear alternate-reverse;
  }}
  @keyframes glitch {{
    0%, 90%, 100% {{ transform: none; }}
    92% {{ transform: translate(-2px, 1px) skewX(-1deg); }}
    94% {{ transform: translate(2px, -1px); }}
    96% {{ transform: translate(-1px, 2px) skewX(1deg); }}
  }}
  @keyframes glitch-a {{
    0% {{ transform: translate(0); }}
    20% {{ transform: translate(-3px, 1px); }}
    40% {{ transform: translate(2px, -1px); }}
    60% {{ transform: translate(-1px, 2px); }}
    80% {{ transform: translate(3px, 0); }}
  }}
  @keyframes glitch-b {{
    0% {{ transform: translate(0); }}
    25% {{ transform: translate(3px, -1px); }}
    50% {{ transform: translate(-2px, 1px); }}
    75% {{ transform: translate(1px, 2px); }}
  }}
  .tag {{
    margin-top: 14px; color: {_MUTED}; font-size: 0.68rem;
    letter-spacing: 0.28em; text-transform: uppercase; z-index: 2;
  }}
  .ring {{
    margin-top: 36px; width: 42px; height: 42px; border-radius: 50%;
    border: 2px solid {_SURFACE}; border-top-color: {_RED};
    border-right-color: {_NEON}; animation: spin 0.75s linear infinite; z-index: 2;
  }}
  @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  #loader-desc {{
    margin-top: 36px; color: {_RED}; font-weight: 700; font-size: 0.62rem;
    letter-spacing: 0.28em; text-transform: uppercase;
    border: 1px solid rgba(229,9,20,0.55); padding: 8px 18px;
    background: rgba(229,9,20,0.06); z-index: 2;
    box-shadow: 0 0 16px rgba(229,9,20,0.15);
  }}
  .handshake {{
    margin-top: 18px; color: {_MUTED}; font-size: 0.5rem;
    letter-spacing: 0.22em; z-index: 2;
  }}
</style>
</head>
<body>
  <div class="stage">
    <div class="matrix"></div>
    <div class="scan"></div>
    {"<img class='logo' src='" + img_src + "' alt='ZERO Core'/>" if img_src else "<div class='logo-fallback'>Z</div>"}
    <div class="wordmark">ZERO</div>
    <div class="tag">V1.0 // RENAISSANCE OF MARKET PREDICTIONS</div>
    <div class="ring"></div>
    <div id="loader-desc">INITIALIZING QUANTUM CORES...</div>
    <div class="handshake">ESTABLISHING SECURE HANDSHAKE...</div>
  </div>
  <script>
    window.parent.scrollTo(0,0);
    const descs = [
      "SYNCHRONIZING GLOBAL ORDER FLOWS...",
      "DECRYPTING ASYMMETRIC PRICE SIGNALS...",
      "MONITORING QUANTUM LIQUIDITY TRAPS...",
      "CALIBRATING VOLATILITY ENVELOPES (ATR 14)...",
      "ANALYZING GEOPOLITICAL SENTIMENT VECTORS...",
      "VERIFYING GIFT NIFTY OPEN INTEREST DELTA...",
      "EXECUTING RECURSIVE QUANTUM ANALYSIS..."
    ];
    let i = 0;
    const loaderTimer = setInterval(() => {{
      i = (i + 1) % descs.length;
      const el = document.getElementById('loader-desc');
      if (el) el.textContent = descs[i];
    }}, 1400);
    const stop = () => {{
      clearInterval(loaderTimer);
      const el = document.getElementById('loader-desc');
      if (el) el.textContent = 'QUANTUM CORES SYNCHRONIZED';
    }};
    const tryHook = () => {{
      const doc = window.parent.document;
      if (!doc) return false;
      if (doc.__zeroSplashHooked) return true;
      doc.__zeroSplashHooked = true;
      const obs = new MutationObserver(() => {{
        if (!doc.body || !doc.body.contains(document.body)) {{
          stop(); obs.disconnect();
        }}
      }});
      try {{ obs.observe(doc.documentElement, {{childList:true, subtree:false}}); }} catch (e) {{}}
      setTimeout(stop, 25000);
      return true;
    }};
    if (document.readyState === 'complete') tryHook();
    else window.addEventListener('load', tryHook);
  </script>
</body></html>
    """
    st.iframe(html_loader, height=600)


def digital_clock_component() -> None:
    """HUD chronometer — HH:MM white, SS neon-red; market-status pill via JS tick."""
    from config import NSE_HOLIDAYS

    holidays_json = json.dumps(list(NSE_HOLIDAYS))

    html_content = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&family=Share+Tech+Mono&display=swap');
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: transparent;
    font-family: 'Share Tech Mono', monospace;
  }}
  #zero-clock-wrap {{
    display: flex; align-items: stretch; justify-content: center; gap: 16px;
  }}
  #zero-clock-box {{
    background: linear-gradient(180deg, {_SURFACE} 0%, {_BLACK} 100%);
    border: 1px solid rgba(212,175,55,0.28);
    border-left: 3px solid {_RED};
    padding: 12px 28px 14px;
    text-align: center;
    box-shadow: inset 0 0 24px rgba(212,175,55,0.06), 0 0 18px rgba(229,9,20,0.12);
    position: relative;
    min-width: 220px;
  }}
  #zero-clock-box::before {{
    content: 'CHRONO · IST';
    position: absolute; top: 4px; left: 10px;
    font-size: 0.45rem; letter-spacing: 0.2em; color: {_MUTED};
  }}
  #clock {{
    font-family: 'Orbitron', sans-serif;
    font-weight: 900; font-size: 1.85rem; letter-spacing: 0.18em;
    color: {_WHITE}; margin-top: 10px;
    text-shadow: 0 0 12px rgba(212,175,55,0.25);
  }}
  #clock .sec {{ color: {_RED}; text-shadow: 0 0 10px rgba(229,9,20,0.65); }}
  #date {{
    color: {_GOLD_ACCENT}; font-size: 0.55rem; font-weight: 700;
    margin-top: 8px; letter-spacing: 0.18em; text-transform: uppercase;
  }}
  #zero-mkt-pill {{
    display: inline-flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 4px;
    background: {_SURFACE}; border: 1px solid #222;
    padding: 10px 16px; min-width: 128px;
    transition: border-color 0.4s ease, box-shadow 0.4s ease;
  }}
  #zero-mkt-dot {{
    width: 9px; height: 9px; border-radius: 50%; display: inline-block;
  }}
  @keyframes mktPulse {{
    0%, 100% {{ box-shadow: 0 0 0 0 rgba(0,255,136,0); }}
    50%       {{ box-shadow: 0 0 10px 3px rgba(0,255,136,0.5); }}
  }}
  .mkt-open-pulse {{ animation: mktPulse 1.8s infinite; }}
  .hud-corners {{
    position: absolute; inset: 0; pointer-events: none;
  }}
  .hud-corners::before, .hud-corners::after {{
    content: ''; position: absolute; width: 10px; height: 10px;
    border-color: {_GOLD}; border-style: solid;
  }}
  .hud-corners::before {{ top: 0; left: 0; border-width: 1px 0 0 1px; }}
  .hud-corners::after  {{ bottom: 0; right: 0; border-width: 0 1px 1px 0; }}
</style>
</head>
<body>
  <div id="zero-clock-wrap">
    <div id="zero-clock-box">
      <div class="hud-corners"></div>
      <div id="clock">00:00<span class="sec">:00</span></div>
      <div id="date">IST +5:30 | LIVE QUANTUM STREAM</div>
    </div>
    <div id="zero-mkt-pill">
      <div style="display:flex;align-items:center;gap:7px;">
        <span id="zero-mkt-dot"></span>
        <span id="zero-mkt-label" style="font-size:0.72rem;font-weight:900;letter-spacing:2px;text-transform:uppercase;"></span>
      </div>
      <div id="zero-mkt-sub" style="font-size:0.52rem;letter-spacing:1px;color:{_MUTED};margin-top:2px;text-transform:uppercase;"></div>
    </div>
  </div>
  <script>
  (function() {{
    var DOT   = document.getElementById('zero-mkt-dot');
    var LABEL = document.getElementById('zero-mkt-label');
    var SUB   = document.getElementById('zero-mkt-sub');
    var PILL  = document.getElementById('zero-mkt-pill');
    var nseHolidays = new Set({holidays_json});

    function pad(n){{ return String(n).padStart(2,'0'); }}

    function getISTDate() {{
      var now = new Date();
      return new Date(now.getTime() + (now.getTimezoneOffset()*60000) + 5.5*3600000);
    }}

    function isWeekday(d){{ return d.getDay() >= 1 && d.getDay() <= 5; }}

    function isHoliday(ist) {{
      var yr = ist.getFullYear();
      var mo = String(ist.getMonth() + 1).padStart(2, '0');
      var dy = String(ist.getDate()).padStart(2, '0');
      return nseHolidays.has(yr + '-' + mo + '-' + dy);
    }}

    function marketState(ist) {{
      var t = ist.getHours() * 60 + ist.getMinutes();
      if (!isWeekday(ist)) return 'WEEKEND';
      if (isHoliday(ist)) return 'HOLIDAY';
      if (t < 555)  return 'PRE-MARKET';
      if (t <= 930) return 'OPEN';
      return 'CLOSED';
    }}

    function applyState(state) {{
      if (state === 'OPEN') {{
        DOT.style.background   = '{_NEON}';
        DOT.style.boxShadow    = '0 0 6px {_NEON}';
        DOT.className          = 'mkt-open-pulse';
        LABEL.style.color      = '{_NEON}';
        LABEL.textContent      = 'MARKET OPEN';
        SUB.textContent        = 'NSE · BSE  09:15 – 15:30';
        PILL.style.borderColor = '{_NEON}55';
        PILL.style.boxShadow   = '0 0 14px rgba(0,255,136,0.12)';
      }} else if (state === 'PRE-MARKET') {{
        DOT.style.background   = '{_GOLD}';
        DOT.style.boxShadow    = '0 0 6px {_GOLD}';
        DOT.className          = '';
        LABEL.style.color      = '{_GOLD}';
        LABEL.textContent      = 'PRE-MARKET';
        SUB.textContent        = 'Opens at 09:15 IST';
        PILL.style.borderColor = '{_GOLD}55';
        PILL.style.boxShadow   = '0 0 10px rgba(212,175,55,0.1)';
      }} else if (state === 'HOLIDAY') {{
        DOT.style.background   = '{_GOLD}';
        DOT.style.boxShadow    = '0 0 6px {_GOLD}';
        DOT.className          = '';
        LABEL.style.color      = '{_GOLD}';
        LABEL.textContent      = 'HOLIDAY CLOSED';
        SUB.textContent        = 'National Market Holiday';
        PILL.style.borderColor = '{_GOLD}55';
        PILL.style.boxShadow   = '0 0 10px rgba(212,175,55,0.1)';
      }} else if (state === 'WEEKEND') {{
        DOT.style.background   = '#444';
        DOT.style.boxShadow    = 'none';
        DOT.className          = '';
        LABEL.style.color      = '#555';
        LABEL.textContent      = 'WEEKEND';
        SUB.textContent        = 'Resumes Monday 09:15';
        PILL.style.borderColor = '#222';
        PILL.style.boxShadow   = 'none';
      }} else {{
        DOT.style.background   = '{_RED}';
        DOT.style.boxShadow    = '0 0 6px rgba(229,9,20,0.5)';
        DOT.className          = '';
        LABEL.style.color      = '{_RED}';
        LABEL.textContent      = 'MARKET CLOSED';
        SUB.textContent        = 'Post 15:30 IST Close';
        PILL.style.borderColor = '{_RED}22';
        PILL.style.boxShadow   = 'none';
      }}
    }}

    var months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
    var lastState = null;

    function tick() {{
      var ist = getISTDate();
      var h = pad(ist.getHours()), m = pad(ist.getMinutes()), s = pad(ist.getSeconds());
      document.getElementById('clock').innerHTML =
        h + ':' + m + '<span class="sec">:' + s + '</span>';
      document.getElementById('date').innerHTML =
        ist.getDate() + ' ' + months[ist.getMonth()] + ' ' + ist.getFullYear() + ' | LIVE SESSION';

      var state = marketState(ist);
      if (state !== lastState) {{
        applyState(state);
        lastState = state;
      }}
    }}

    setInterval(tick, 1000);
    tick();
  }})();
  </script>
</body></html>
    """
    st.iframe(html_content, height=130)


def render_sidebar_brand_block() -> None:
    """Compact cyber brand strip for sidebar chrome."""
    st.markdown(
        f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&display=swap');
  .zero-brand-strip {{
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; margin: 0 0 10px 0;
    background: linear-gradient(90deg, {_SURFACE} 0%, {_BLACK} 100%);
    border: 1px solid rgba(0,255,136,0.22);
    border-left: 3px solid {_RED};
    box-shadow: 0 0 16px rgba(0,255,136,0.08);
    position: relative;
  }}
  .zero-brand-strip::after {{
    content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 2px;
    background: linear-gradient({_NEON}, {_GOLD_ACCENT}); opacity: 0.55;
  }}
  .zero-brand-mark {{
    font-family: 'Orbitron', sans-serif; font-weight: 900;
    font-size: 1.05rem; letter-spacing: 0.28em; color: {_WHITE};
    text-shadow: 0 0 10px rgba(229,9,20,0.45);
  }}
  .zero-brand-mark span {{ color: {_RED}; }}
  .zero-brand-sub {{
    font-size: 0.48rem; letter-spacing: 0.22em; color: {_MUTED};
    text-transform: uppercase; margin-top: 2px;
  }}
  .zero-brand-dot {{
    width: 8px; height: 8px; border-radius: 50%;
    background: {_NEON}; box-shadow: 0 0 8px {_NEON};
    animation: brandPulse 1.6s ease-in-out infinite;
    flex-shrink: 0;
  }}
  @keyframes brandPulse {{
    0%, 100% {{ opacity: 0.55; transform: scale(0.9); }}
    50%       {{ opacity: 1; transform: scale(1.15); }}
  }}
</style>
<div class="zero-brand-strip">
  <div class="zero-brand-dot"></div>
  <div>
    <div class="zero-brand-mark">ZER<span>O</span></div>
    <div class="zero-brand-sub">CORE // CYBER TERMINAL</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_zero_agi_sidebar() -> None:
    """ZERO AGI sidebar entry — neon green pulse ring; opens AGI via session_state."""
    st.markdown(
        f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@700;900&display=swap');
  .zero-agi-head {{
    margin-bottom: 4px;
    font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 1.0rem;
    letter-spacing: 2px;
  }}
  .zero-agi-head .z {{ color: {_WHITE}; }}
  .zero-agi-head .a {{ color: {_NEON}; text-shadow: 0 0 10px rgba(0,255,136,0.45); }}
  .zero-agi-sub {{
    font-size: 0.5rem; color: {_MUTED}; letter-spacing: 2px;
    margin: -2px 0 8px 0; text-transform: uppercase;
  }}
  /* Marker element-container collapses; next sibling gets the pulse ring */
  [data-testid="stSidebar"] .element-container:has(> div > .zero-agi-gate),
  [data-testid="stSidebar"] .element-container:has(.zero-agi-gate) {{
    margin: 0 !important; padding: 0 !important; min-height: 0 !important;
  }}
  [data-testid="stSidebar"] .zero-agi-gate {{ height: 0; overflow: hidden; margin: 0; padding: 0; }}
  [data-testid="stSidebar"] .element-container:has(.zero-agi-gate) + .element-container {{
    position: relative; border-radius: 8px; padding: 3px !important;
    background: linear-gradient(135deg, {_NEON}, {_GREEN}, {_GOLD_ACCENT}, {_NEON});
    background-size: 300% 300%;
    animation: agiRingHue 2.4s ease-in-out infinite, agiRingGlow 1.8s ease-in-out infinite;
  }}
  [data-testid="stSidebar"] .element-container:has(.zero-agi-gate) + .element-container .stButton > button {{
    width: 100%;
    border: 1px solid rgba(0,255,136,0.35) !important;
    background: linear-gradient(180deg, {_SURFACE} 0%, {_BLACK} 100%) !important;
    color: {_NEON} !important;
    font-family: 'Orbitron', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: 0.14em !important;
  }}
  @keyframes agiRingHue {{
    0%, 100% {{ background-position: 0% 50%; }}
    50%       {{ background-position: 100% 50%; }}
  }}
  @keyframes agiRingGlow {{
    0%, 100% {{ box-shadow: 0 0 8px rgba(0,255,136,0.25), 0 0 0 0 rgba(0,230,118,0.4); }}
    50%       {{ box-shadow: 0 0 22px rgba(0,255,136,0.55), 0 0 0 5px rgba(0,230,118,0); }}
  }}
</style>
<div class="zero-agi-head">
  <span class="z">ZERO</span><span class="a"> AGI</span>
</div>
<p class="zero-agi-sub">LIVE CHART VISION · STRATEGY ANALYZER</p>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="zero-agi-gate" aria-hidden="true"></div>', unsafe_allow_html=True)

    if st.button("ZERO AGI", key="open_zero_agi_btn"):
        st.session_state["show_zero_agi"] = True
        st.rerun()
