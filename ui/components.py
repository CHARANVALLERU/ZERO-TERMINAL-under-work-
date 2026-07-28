import streamlit as st
import random
import time
import os
import sys
import subprocess

def apply_digital_core_theme():
    """Digital Core Theme: Deep Black, Slate Grey, Blood Red, Pure White."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;800&display=swap');
    
    html {
        scroll-behavior: smooth;
    }

    body, [data-testid="stAppViewContainer"] {
        background: #000000;
        color: #ffffff;
        font-family: 'Inter', sans-serif;
        -webkit-user-select: none;
        user-select: none;
    }
    
    .stApp {
        background: radial-gradient(circle at top left, #0a0a0a, #000000);
    }
    
    .main-title {
        color: #ffffff;
        font-family: 'Orbitron', sans-serif;
        font-weight: 900;
        font-size: 4rem;
        letter-spacing: -3px;
        text-align: center;
        margin: 10px 0;
        line-height: 1;
        text-shadow: 0 0 20px rgba(229, 9, 20, 0.3);
        animation: fadeInDown 1s ease-out;
    }
    
    .terminal-core-txt {
        color: #E50914;
        font-weight: 700;
        font-size: 0.8rem;
        letter-spacing: 6px;
        text-align: center;
        text-transform: uppercase;
        margin-bottom: 40px;
        animation: fadeIn 2s ease-out;
    }
    
    .gold-title {
        color: #D4AF37;
        font-weight: 800;
        font-size: 0.9rem;
        letter-spacing: 2px;
        margin-bottom: 1.5rem;
        text-transform: uppercase;
    }
    
    /* Professional Scroll Animations */
    .digital-card {
        background: #0a0a0a;
        border: 1px solid #1a1a1a;
        border-radius: 4px;
        padding: 30px;
        margin-bottom: 24px;
        animation: slideUpFade 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) both;
        /* Hint the compositor — avoids re-paint on every toast tick. */
        will-change: transform, opacity;
        /* Gentle cross-fade so a re-render doesn't snap. */
        transition: opacity 0.25s cubic-bezier(0.22, 0.61, 0.36, 1),
                    border-color 0.25s ease,
                    transform 0.25s cubic-bezier(0.22, 0.61, 0.36, 1);
    }

    @keyframes fadeInDown {
        from { opacity: 0; transform: translateY(-12px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to   { opacity: 1; }
    }
    @keyframes slideUpFade {
        from { opacity: 0; transform: translateY(14px); }
        to   { opacity: 1; transform: translateY(0); }
    }

    /* Respect the user's motion preferences. Disables heavy keyframes
       and disables the splash cycling. */
    @media (prefers-reduced-motion: reduce) {
        .digital-card, .main-title, .terminal-core-txt { animation: none !important; }
        .digital-card { transition: none !important; }
    }

    /* Stealth Scrollbar - Professional Minimalism */
    ::-webkit-scrollbar {
        display: none !important;
    }
    html, body {
        -ms-overflow-style: none !important;  /* IE and Edge */
        scrollbar-width: none !important;  /* Firefox */
    }

    .label-grey {
        color: #666;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.2px;
    }
    
    .value-white {
        color: #ffffff;
        font-size: 2.2rem;
        font-weight: 700;
    }
    
    .status-red {
        color: #E50914;
        font-weight: 800;
        font-size: 0.8rem;
    }

    /* Order Block Table */
    .order-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.8rem;
    }
    .order-table th {
        text-align: left;
        color: #444;
        padding: 10px;
        border-bottom: 1px solid #222;
    }
    .order-table td {
        padding: 14px 10px;
        border-bottom: 1px solid #111;
        color: #ddd;
    }
    .buy-quant { color: #00ff88; font-weight: bold; }
    .sell-quant { color: #ff4b4b; font-weight: bold; }

    /* Centered Components Fix */
    .centered-box {
        display: flex;
        justify-content: center;
        align-items: center;
        flex-direction: column;
        width: 100%;
    }
    
    </style>
    """, unsafe_allow_html=True)

import base64
import os
import streamlit as st
import random

def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except Exception:
        return ""

def show_zero_digital_splash():
    """Centered loader with brand title and cycling professional descriptions."""
    logo_path = os.path.join(os.path.dirname(__file__), 'assets', 'logo.png')
    logo_b64 = get_base64_of_bin_file(logo_path)
    if logo_b64:
        img_src = f"data:image/png;base64,{logo_b64}"
    else:
        img_src = ""

    html_loader = """
    <div style="height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; background: #000; font-family: 'Inter', sans-serif; overflow: hidden;">
        <img src="__IMG_SRC__" alt="ZERO Core" style="width: 140px; margin-bottom: 30px; border-radius: 50%; box-shadow: 0 0 25px rgba(220,38,38,0.3); animation: pulse-core 2.5s infinite alternate;" />
        <div style="color: #666; font-size: 0.75rem; font-weight: 500; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 40px;">ZERO V1.0 // Renaissance of Market Predictions</div>
        
        <div style="width: 40px; height: 40px; border: 2px solid #1a1a1a; border-top: 2px solid #E50914; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
        
        <div style="margin-top: 40px; min-height: 40px; text-align: center;">
            <div id="loader-desc" style="color: #E50914; font-weight: 800; font-size: 10px; letter-spacing: 3px; text-transform: uppercase; border: 1px solid #E50914; padding: 6px 18px;">INITIALIZING QUANTUM CORES...</div>
        </div>
        
        <div style="margin-top: 25px; color: #333; font-size: 0.5rem; font-weight: 700; letter-spacing: 2px;">ESTABLISHING SECURE HANDSHAKE...</div>
        
        <style>
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@900&display=swap');
            body { 
                margin: 0; padding: 0; overflow: hidden; background: #000; 
                scrollbar-width: none; -ms-overflow-style: none;
            }
            body::-webkit-scrollbar { display: none; }
        </style>
        
        <script>
            // Hard focus on top to avoid scrolling issues
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
            // Use a single, named timer so we can stop it the moment the
            // user has entered the main terminal. The previous version
            // leaked a setInterval that kept firing forever.
            const loaderTimer = setInterval(() => {
                i = (i + 1) % descs.length;
                const el = document.getElementById('loader-desc');
                if (el) el.innerHTML = descs[i];
            }, 1400);

            // Watch the parent doc for the DIG & DIVE click. As soon as
            // the splash HTML is replaced, kill the cycling loop.
            const stop = () => {
                clearInterval(loaderTimer);
                const el = document.getElementById('loader-desc');
                if (el) el.innerHTML = 'QUANTUM CORES SYNCHRONIZED';
            };
            const tryHook = () => {
                const doc = window.parent.document;
                if (!doc) return false;
                if (doc.__zeroSplashHooked) return true;
                doc.__zeroSplashHooked = true;
                const obs = new MutationObserver(() => {
                    // splash html is gone → page has reloaded into the main terminal
                    if (!doc.body || !doc.body.contains(document.body)) {
                        stop();
                        obs.disconnect();
                    }
                });
                try { obs.observe(doc.documentElement, {childList:true, subtree:false}); } catch (e) {}
                // Hard fallback: stop after 25 s no matter what.
                setTimeout(stop, 25000);
                return true;
            };
            // Hook after the DOM is ready.
            if (document.readyState === 'complete') tryHook();
            else window.addEventListener('load', tryHook);
        </script>
    </div>
    """.replace("__IMG_SRC__", img_src)
    st.iframe(html_loader, height=600)


def digital_clock_component():
    """Real-time clock centered for main section, with a live market-status
    pill on the right that updates every second via client-side JS."""
    import json
    from config import NSE_HOLIDAYS
    holidays_json = json.dumps(list(NSE_HOLIDAYS))

    html_content = f"""
    <style>
      #zero-clock-wrap {{
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 18px;
        font-family: 'Inter', sans-serif;
      }}
      #zero-clock-box {{
        background: rgba(15,15,15,0.8);
        border: 1px solid #222;
        padding: 15px 40px;
        display: inline-block;
        border-radius: 2px;
        text-align: center;
      }}
      #zero-mkt-pill {{
        display: inline-flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 4px;
        background: rgba(15,15,15,0.85);
        border: 1px solid #333;
        border-radius: 6px;
        padding: 10px 18px;
        min-width: 120px;
        backdrop-filter: blur(4px);
        transition: border-color 0.4s ease, box-shadow 0.4s ease;
      }}
      #zero-mkt-dot {{
        width: 9px; height: 9px;
        border-radius: 50%;
        display: inline-block;
      }}
      @keyframes mktPulse {{
        0%, 100% {{ box-shadow: 0 0 0 0 rgba(0,255,136,0); }}
        50%       {{ box-shadow: 0 0 10px 3px rgba(0,255,136,0.5); }}
      }}
      .mkt-open-pulse {{ animation: mktPulse 1.8s infinite; }}
    </style>

    <div id="zero-clock-wrap">
      <div id="zero-clock-box">
        <div id="clock" style="color:#fff;font-size:28px;font-weight:800;letter-spacing:3px;">00:00:00</div>
        <div id="date" style="color:#E50914;font-size:10px;font-weight:700;margin-top:6px;text-transform:uppercase;letter-spacing:2px;">IST +5:30 | LIVE QUANTUM STREAM</div>
      </div>

      <div id="zero-mkt-pill">
        <div style="display:flex;align-items:center;gap:7px;">
          <span id="zero-mkt-dot" class=""></span>
          <span id="zero-mkt-label" style="font-size:0.72rem;font-weight:900;letter-spacing:2px;text-transform:uppercase;"></span>
        </div>
        <div id="zero-mkt-sub" style="font-size:0.52rem;letter-spacing:1px;color:#555;margin-top:2px;text-transform:uppercase;"></div>
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
        var ist = new Date(now.getTime() + (now.getTimezoneOffset()*60000) + 5.5*3600000);
        return ist;
      }}

      function isWeekday(d){{ return d.getDay() >= 1 && d.getDay() <= 5; }}

      function isHoliday(ist) {{
        var yr = ist.getFullYear();
        var mo = String(ist.getMonth() + 1).padStart(2, '0');
        var dy = String(ist.getDate()).padStart(2, '0');
        return nseHolidays.has(yr + '-' + mo + '-' + dy);
      }}

      function marketState(ist) {{
        var h = ist.getHours(), m = ist.getMinutes();
        var t = h * 60 + m; // total minutes from midnight IST
        if (!isWeekday(ist)) return 'WEEKEND';
        if (isHoliday(ist)) return 'HOLIDAY';
        if (t < 555)  return 'PRE-MARKET';
        if (t <= 930) return 'OPEN';
        return 'CLOSED';
      }}

      function applyState(state) {{
        if (state === 'OPEN') {{
          DOT.style.background   = '#00ff88';
          DOT.style.boxShadow    = '0 0 6px #00ff88';
          DOT.className          = 'mkt-open-pulse';
          LABEL.style.color      = '#00ff88';
          LABEL.textContent      = 'MARKET OPEN';
          SUB.textContent        = 'NSE · BSE  09:15 – 15:30';
          PILL.style.borderColor = '#00ff8855';
          PILL.style.boxShadow   = '0 0 14px rgba(0,255,136,0.12)';
        }} else if (state === 'PRE-MARKET') {{
          DOT.style.background   = '#D4AF37';
          DOT.style.boxShadow    = '0 0 6px #D4AF37';
          DOT.className          = '';
          LABEL.style.color      = '#D4AF37';
          LABEL.textContent      = 'PRE-MARKET';
          SUB.textContent        = 'Opens at 09:15 IST';
          PILL.style.borderColor = '#D4AF3755';
          PILL.style.boxShadow   = '0 0 10px rgba(212,175,55,0.1)';
        }} else if (state === 'HOLIDAY') {{
          DOT.style.background   = '#D4AF37';
          DOT.style.boxShadow    = '0 0 6px #D4AF37';
          DOT.className          = '';
          LABEL.style.color      = '#D4AF37';
          LABEL.textContent      = 'HOLIDAY CLOSED';
          SUB.textContent        = 'National Market Holiday';
          PILL.style.borderColor = '#D4AF3755';
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
          DOT.style.background   = '#E50914';
          DOT.style.boxShadow    = '0 0 6px rgba(229,9,20,0.5)';
          DOT.className          = '';
          LABEL.style.color      = '#E50914';
          LABEL.textContent      = 'MARKET CLOSED';
          SUB.textContent        = 'Post 15:30 IST Close';
          PILL.style.borderColor = '#E5091422';
          PILL.style.boxShadow   = 'none';
        }}
      }}

      var months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
      var lastState = null;

      function tick() {{
        var ist = getISTDate();
        var h = pad(ist.getHours()), m = pad(ist.getMinutes()), s = pad(ist.getSeconds());
        document.getElementById('clock').innerHTML = h + ':' + m + ':' + s;
        document.getElementById('date').innerHTML  = ist.getDate() + ' ' + months[ist.getMonth()] + ' ' + ist.getFullYear() + ' | LIVE SESSION';

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
    """
    st.iframe(html_content, height=130)



def sidebar_news_section(news_items, live_feed=None):
    """Sidebar intelligence stream. Prefers the real enriched live feed
    (each headline scored for market impact); falls back to the curated
    placeholder blocks when the feed is empty (e.g. offline cold start)."""
    st.markdown("<p class='label-grey' style='margin-bottom: 20px; color: #D4AF37;'>LIVE MARKET INTELLIGENCE</p>", unsafe_allow_html=True)

    if live_feed:
        import html as _html
        for it in live_feed[:8]:
            direction = it.get('direction', 'NEUTRAL')
            color = '#00ff88' if direction == 'BULLISH' else ('#E50914' if direction == 'BEARISH' else '#D4AF37')
            arrow = '▲' if direction == 'BULLISH' else ('▼' if direction == 'BEARISH' else '•')
            nifty = (it.get('per_index') or {}).get('NIFTY 50') or {}
            if not isinstance(nifty, dict):
                nifty = {}
            link = it.get('link') or ''
            link_html = (f"<a href='{_html.escape(link)}' target='_blank' style='text-decoration:none;color:#E50914;"
                         f"font-size:0.6rem;font-weight:800;'>SOURCE ↗</a>") if link else ''
            st.markdown(f"""
            <div style="padding:14px 0; border-bottom:1px solid #1a1a1a;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="color:{color}; font-weight:800; font-size:0.6rem; letter-spacing:1px;">
                         {arrow} {direction} · {it.get('category_label','')}</span>
                    <span style="color:{color}; font-weight:800; font-size:0.6rem;">{nifty.get('move_pct',0) or 0:+.2f}%</span>
                </div>
                <p style="color:#ddd; font-size:0.78rem; line-height:1.6; margin:0;">{_html.escape(it.get('title',''))}</p>
                <div style="display:flex; justify-content:space-between; margin-top:8px; align-items:center;">
                    <span style="color:#444; font-size:0.55rem; font-weight:700;">IMPACT {it.get('impact_score',0):.0f}/100</span>
                    {link_html}
                </div>
            </div>
            """, unsafe_allow_html=True)
        return

    # Premium news feed with deep detail and active links
    market_news = [
        {
            "text": "GLOBAL MACRO: Institutional desks are pivoting as US Fed signals a multi-quarter holding pattern on rates. Geopolitical risk premiums are being priced into emerging market equity baskets as volatility spikes.",
            "url": "https://www.investing.com/news/economy"
        },
        {
            "text": "LIQUIDITY ANALYSIS: Massive order block divergence detected in pre-market indices. Quantitative models suggest a strong volume-driven expansion toward structural resistance zones near the 24,200 handle.",
            "url": "https://www.tradingview.com/markets/indices/"
        },
        {
            "text": "DERIVATIVES PULSE: Options chain analysis suggests a significant liquidity trap forming near key psychological levels. High open interest accumulation in OTM calls identifies a firm ceiling for the session.",
            "url": "https://www.moneycontrol.com/markets/fno/"
        },
        {
            "text": "INSTITUTIONAL FLOW: Dark pool interaction levels have reached a 14-day high. Algorithms are strategically placing limit order stacks near the 1.272 Fibonacci extension level to capture mean reversion.",
            "url": "https://glint.trade/"
        }
    ]
        
    for item in market_news:
        time_ago = f"{random.randint(2, 58)} MIN AGO"
        st.markdown(f"""
        <div style="padding: 20px 0; border-bottom: 1px solid #1a1a1a; margin-bottom: 5px;">
            <p style="color: #ffffff; font-size: 0.82rem; line-height: 1.7; margin: 0; text-align: justify; letter-spacing: 0.3px;">
                {item['text']}
            </p>
            <div style="display: flex; justify-content: space-between; margin-top: 12px; align-items: center;">
                <span style="color: #444; font-size: 0.6rem; font-weight: 700;">{time_ago}</span>
                <a href="{item['url']}" target="_blank" style="text-decoration: none; color: #E50914; font-size: 0.65rem; font-weight: 800; border: 1px solid #E50914; padding: 2px 8px; border-radius: 2px; transition: 0.3s;">READ FULL ALPHA</a>
            </div>
        </div>
        """, unsafe_allow_html=True)

def predicted_info_card(title, data):
    # Adaptive-calibration extras (present when a model is trained).
    conf = data.get('confidence')
    model = data.get('model', 'baseline')
    conf_txt = f"{conf:.0f}%" if isinstance(conf, (int, float)) else "--"
    model_badge = "CALIBRATED" if model == "calibrated" else "BASELINE"
    badge_color = "#00ff88" if model == "calibrated" else "#D4AF37"

    def _band(lo, hi):
        if lo is None or hi is None:
            return ""
        return f"<span class='label-grey' style='font-size:0.7rem;'>90% band [{lo} – {hi}]</span>"

    st.markdown(f"""
    <div class="digital-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div class="label-grey">{title} Prediction Vector</div>
            <div style="text-align:right;">
                <span style="color:{badge_color}; font-weight:800; font-size:0.7rem; letter-spacing:1px;">{model_badge}</span>
                <span class="label-grey" style="font-size:0.7rem;">&nbsp;·&nbsp;CONF {conf_txt}</span>
            </div>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 15px;">
            <div>
                <p class="label-grey">Quantum Opening</p>
                <p class="value-white">{data['pred_open']}</p>
                {_band(data.get('open_lo'), data.get('open_hi'))}
            </div>
            <div style="text-align: right;">
                <p class="label-grey">Trajectory</p>
                <p class="status-red" style="font-size: 1.1rem; letter-spacing: 1px;">{data.get('movement_side', 'NEUTRAL')}</p>
            </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 30px; border-top: 1px solid #111; padding-top: 20px;">
            <div>
                <p class="label-grey">Predicted High</p>
                <p style="color: #fff; font-weight: 700; font-size: 1.3rem;">{data['pred_high']}</p>
                {_band(data.get('high_lo'), data.get('high_hi'))}
            </div>
            <div style="text-align: right;">
                <p class="label-grey">Predicted Low</p>
                <p style="color: #fff; font-weight: 700; font-size: 1.3rem;">{data['pred_low']}</p>
                {_band(data.get('low_lo'), data.get('low_hi'))}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def order_flow_table(data):
    """Scrip-zone flow table.

    The user's request: replace the "resistance zone" / "support zone"
    framing with the predictor engine's actual numbers — Predicted High,
    Predicted Open, Predicted Low. The values are pulled from the matrix
    (pred_high, pred_open, pred_low) so they re-derive in lock-step with
    the 60-second news-overlay tick in app.py.
    """
    rows = [
        ("Predicted Low",  f"{data.get('pred_low',  '—')}",  f"{random.randint(280, 750)}K", "BUY"),
        ("Predicted Open", f"{data.get('pred_open', '—')}",  f"{random.randint(120, 310)}K", "LEVEL"),
        ("Predicted High", f"{data.get('pred_high', '—')}",  f"{random.randint(310, 890)}K", "SELL"),
    ]
    html = '<table class="order-table"><thead><tr><th>Scrip Zone</th><th>Point</th><th>Quantity</th><th>Side</th></tr></thead><tbody>'
    for block, point, quant, side in rows:
        color_class = "buy-quant" if side == "BUY" else "sell-quant" if side == "SELL" else ""
        html += f'<tr><td>{block}</td><td>{point}</td><td class="{color_class}">{quant}</td><td class="{color_class}">{side}</td></tr>'
    html += '</tbody></table>'
    st.markdown(html, unsafe_allow_html=True)

def automated_training_dashboard(train_status=None, matrix=None):
    """Read-only dashboard reflecting the autonomous training loop status."""
    st.markdown("<p class='gold-title'>01 // AUTONOMOUS ML LOOP</p>", unsafe_allow_html=True)
    
    st.markdown(f"<div style='border: 1px solid #222; padding: 20px; border-radius: 4px; background: rgba(10,10,10,0.5); margin-bottom: 20px;'>", unsafe_allow_html=True)
    
    if train_status and train_status.get('status') == 'trained':
        st.markdown(f"<p style='color: #00ff88; font-weight: 800; letter-spacing: 1px;'>STATUS: RECALIBRATED (AUTO-FIXED)</p>", unsafe_allow_html=True)
        res = train_status['results']
        st.markdown(f"<p class='label-grey'>Engine parameters automatically shifted to minimize historical delta.<br><b>Old ALPHA:</b> {res['current']['ALPHA']} -> <b>New ALPHA:</b> {res['suggested']['ALPHA']}<br><b>Old BETA:</b> {res['current']['BETA']} -> <b>New BETA:</b> {res['suggested']['BETA']}</p>", unsafe_allow_html=True)
    elif train_status and train_status.get('status') == 'holding':
        st.markdown(f"<p style='color: #D4AF37; font-weight: 800; letter-spacing: 1px;'>STATUS: HOLDING BASELINE (OPTIMAL)</p>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>Engine found current configuration optimal. No parameter drift detected.</p>", unsafe_allow_html=True)
    elif train_status and train_status.get('status') == 'failed':
        st.markdown(f"<p style='color: #E50914; font-weight: 800; letter-spacing: 1px;'>STATUS: AWAITING DATA SETTLEMENT</p>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>Official OHLC bounds not yet distributed by NSE globally.</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<p style='color: #fff; font-weight: 800; letter-spacing: 1px;'>STATUS: PASSIVE MONITORING</p>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>Awaiting schedule boundary to trigger automated data fetch and grid search.</p>", unsafe_allow_html=True)
        
    st.markdown("</div>", unsafe_allow_html=True)
    
    return True

def learning_stats_card(metrics):
    """Visualizes engine accuracy trend."""
    if not metrics or not metrics['dates']:
        st.info("Insufficient longitudinal data for calibration. Require minimum 3 sessions.")
        return

    st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
    st.markdown("<p class='label-grey'>Engine Calibration Matrix</p>", unsafe_allow_html=True)
    
    # Calculate average error
    avg_err = sum(metrics['open_error']) / len(metrics['open_error'])
    accuracy = 100 - avg_err
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown(f"<p class='value-white'>{accuracy:.2f}%</p>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>Mean Predictive Accuracy</p>", unsafe_allow_html=True)
    
    with col2:
        status = "OPTIMAL" if accuracy > 95 else "CALIBRATING" if accuracy > 85 else "DIVERGED"
        color = "#00ff88" if accuracy > 95 else "#D4AF37" if accuracy > 85 else "#E50914"
        st.markdown(f"<p style='color: {color}; font-size: 1.5rem; font-weight: 800; margin: 0;'>{status}</p>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>System Health Status</p>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_youtube_knowledge_sidebar():
    """
    Renders the 'ADD YOUTUBE KNOWLEDGE' terminal button, proxy configuration, and interactive dialog in sidebar.
    """
    st.markdown("""
    <div style="margin-bottom:4px;">
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:0.95rem;
                   color:#fff;letter-spacing:2px;">▶ YOUTUBE</span>
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:0.95rem;
                   color:#E50914;letter-spacing:2px;"> KNOWLEDGE</span>
    </div>
    <p style="font-size:0.5rem;color:#555;letter-spacing:2px;margin:-2px 0 8px 0;
              text-transform:uppercase;">AUTOMATED CONTEXT INGESTION</p>
    """, unsafe_allow_html=True)

    # ── Proxy Configuration for IP Ban Bypass ────────────────────────────────
    with st.expander("⚙ PROXY SETTINGS (IP Ban Bypass)", expanded=False):
        st.markdown(
            "<p style='font-size:0.55rem;color:#888;margin:0 0 8px 0;'>"
            "Configure a proxy to bypass YouTube IP blocks (IpBlocked / RequestBlocked / HTTP 429). "
            "Webshare rotating residential proxies work best. Leave blank if not needed.</p>",
            unsafe_allow_html=True
        )
        try:
            from config import (
                YOUTUBE_PROXY_USERNAME, YOUTUBE_PROXY_PASSWORD,
                YOUTUBE_PROXY_HTTP, YOUTUBE_PROXY_HTTPS
            )
        except ImportError:
            YOUTUBE_PROXY_USERNAME = os.environ.get("YOUTUBE_PROXY_USERNAME", "")
            YOUTUBE_PROXY_PASSWORD = os.environ.get("YOUTUBE_PROXY_PASSWORD", "")
            YOUTUBE_PROXY_HTTP = os.environ.get("YOUTUBE_PROXY_HTTP", "")
            YOUTUBE_PROXY_HTTPS = os.environ.get("YOUTUBE_PROXY_HTTPS", "")

        proxy_mode = st.radio(
            "Proxy Mode",
            ["None", "Webshare (Rotating Residential)", "Generic HTTP/HTTPS Proxy"],
            index=(
                1 if YOUTUBE_PROXY_USERNAME and YOUTUBE_PROXY_PASSWORD else
                2 if YOUTUBE_PROXY_HTTP else
                0
            ),
            key="yt_proxy_mode_radio"
        )

        if proxy_mode == "Webshare (Rotating Residential)":
            st.caption("Get credentials: https://proxy.webshare.io → Proxy Settings")
            _ws_user = st.text_input(
                "Webshare Proxy Username",
                value=os.environ.get("YOUTUBE_PROXY_USERNAME", YOUTUBE_PROXY_USERNAME),
                key="yt_ws_username_input"
            )
            _ws_pass = st.text_input(
                "Webshare Proxy Password",
                value="",
                type="password",
                key="yt_ws_password_input",
                placeholder="Enter Webshare password"
            )
            if st.button("Apply Webshare Proxy", key="apply_ws_proxy_btn"):
                if _ws_user and _ws_pass:
                    os.environ["YOUTUBE_PROXY_USERNAME"] = _ws_user
                    os.environ["YOUTUBE_PROXY_PASSWORD"] = _ws_pass
                    os.environ.pop("YOUTUBE_PROXY_HTTP", None)
                    os.environ.pop("YOUTUBE_PROXY_HTTPS", None)
                    st.success("Webshare proxy applied for this session.")
                else:
                    st.error("Please enter both username and password.")

        elif proxy_mode == "Generic HTTP/HTTPS Proxy":
            st.caption("Format: http://user:pass@host:port or socks5://host:port")
            _http_url = st.text_input(
                "HTTP Proxy URL",
                value=os.environ.get("YOUTUBE_PROXY_HTTP", YOUTUBE_PROXY_HTTP),
                key="yt_http_proxy_input",
                placeholder="http://user:pass@proxy.example.com:3128"
            )
            _https_url = st.text_input(
                "HTTPS Proxy URL (leave blank to reuse HTTP)",
                value=os.environ.get("YOUTUBE_PROXY_HTTPS", YOUTUBE_PROXY_HTTPS),
                key="yt_https_proxy_input",
                placeholder="(optional)"
            )
            if st.button("Apply Generic Proxy", key="apply_generic_proxy_btn"):
                if _http_url:
                    os.environ["YOUTUBE_PROXY_HTTP"] = _http_url
                    os.environ["YOUTUBE_PROXY_HTTPS"] = _https_url or _http_url
                    os.environ.pop("YOUTUBE_PROXY_USERNAME", None)
                    os.environ.pop("YOUTUBE_PROXY_PASSWORD", None)
                    st.success("Generic proxy applied for this session.")
                else:
                    st.error("Please enter the HTTP Proxy URL.")

        elif proxy_mode == "None":
            if st.button("Clear Proxy", key="clear_proxy_btn"):
                for _k in ("YOUTUBE_PROXY_USERNAME", "YOUTUBE_PROXY_PASSWORD", "YOUTUBE_PROXY_HTTP", "YOUTUBE_PROXY_HTTPS"):
                    os.environ.pop(_k, None)
                st.success("Proxy cleared.")

    if st.button("🔴 ADD YOUTUBE KNOWLEDGE", key="add_yt_knowledge_btn", use_container_width=True):
        st.session_state['show_yt_prompt'] = not st.session_state.get('show_yt_prompt', False)

    if st.session_state.get('show_yt_prompt', False):
        st.markdown("""
        <div style="background:#0a0a0a; border:1px solid #E50914; border-radius:4px; padding:12px; margin-top:8px;">
            <p style="color:#E50914; font-weight:800; font-size:0.65rem; letter-spacing:1.5px; margin:0 0 6px 0; font-family:'Orbitron',sans-serif;">
                TERMINAL // PASTE YOUTUBE URL
            </p>
            <p style="color:#888; font-size:0.55rem; margin:0 0 8px 0;">Accepts Playlist or Single Video Link</p>
        </div>
        """, unsafe_allow_html=True)

        yt_url_input = st.text_input(
            label="yt_url_input",
            label_visibility="collapsed",
            placeholder="Paste YouTube Video or Playlist URL...",
            key="yt_url_text_input"
        )

        col_run, col_close = st.columns([2, 1])
        with col_run:
            if st.button("⚡ CONVERT & INGEST", key="run_yt_convert_btn", use_container_width=True):
                if yt_url_input and yt_url_input.strip():
                    status_file = os.path.join(os.path.dirname(__file__), "..", "db", ".yt_status.txt")
                    os.makedirs(os.path.dirname(status_file), exist_ok=True)
                    with open(status_file, "w", encoding="utf-8") as f:
                        f.write("Initializing YouTube Conversion...")

                    # Forward proxy environment variables to convert_playlist.py subprocess
                    env = os.environ.copy()
                    cmd = [sys.executable, "convert_playlist.py", "--url", yt_url_input.strip()]
                    try:
                        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
                        st.session_state['yt_process'] = proc.pid
                        st.session_state['show_yt_prompt'] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to start conversion: {e}")
                else:
                    st.error("Please paste a valid YouTube URL.")

        with col_close:
            if st.button("✕ CLOSE", key="close_yt_prompt_btn", use_container_width=True):
                st.session_state['show_yt_prompt'] = False
                st.rerun()

    status_file = os.path.join(os.path.dirname(__file__), "..", "db", ".yt_status.txt")
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                current_status = f.read().strip()
            
            if current_status:
                if current_status.startswith("COMPLETED"):
                    stat_mtime = os.path.getmtime(status_file)
                    time_diff = time.time() - stat_mtime
                    if time_diff <= 5.0:
                        st.success(f"✓ {current_status}")
                        st.markdown("""
                        <script>
                            setTimeout(function(){
                                window.location.reload();
                            }, 5000);
                        </script>
                        """, unsafe_allow_html=True)
                    else:
                        try:
                            os.remove(status_file)
                        except Exception:
                            pass
                elif current_status.startswith("ERROR"):
                    st.error(f"✕ {current_status}")
                else:
                    st.info(f"⏳ {current_status}")
                    try:
                        from streamlit_autorefresh import st_autorefresh
                        st_autorefresh(interval=2000, key="yt_conversion_autorefresh")
                    except ImportError:
                        st.markdown("""
                        <meta http-equiv="refresh" content="2">
                        """, unsafe_allow_html=True)
        except Exception:
            pass


def render_zero_brain_sidebar(brain, daily_log: dict):
    """
    Renders the ZERO Brain section in the Streamlit sidebar.

    Args:
        brain      : BrainEngine singleton
        daily_log  : today's mental model dict (from brain.export_daily_log(matrix))
    """
    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-bottom:4px;">
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:1.1rem;
                   color:#fff;letter-spacing:2px;">🧠 ZERO</span>
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:1.1rem;
                   color:#D4AF37;letter-spacing:2px;"> BRAIN</span>
    </div>
    <p style="font-size:0.55rem;color:#555;letter-spacing:2px;margin:-2px 0 10px 0;
              text-transform:uppercase;">MENTAL MODEL ENGINE v1.0</p>
    """, unsafe_allow_html=True)

    total = brain.get_entries_count()
    score = daily_log.get("score", 10)
    score_color = "#00ff88" if score >= 7 else ("#D4AF37" if score >= 4 else "#E50914")
    st.markdown(
        f"<div style='display:flex;gap:10px;margin-bottom:10px;'>"
        f"<div style='background:rgba(212,175,55,0.08);border:1px solid #2a2a2a;"
        f"border-radius:6px;padding:6px 10px;flex:1;text-align:center;'>"
        f"<div style='color:#D4AF37;font-weight:900;font-size:1rem;'>{total}</div>"
        f"<div style='color:#555;font-size:0.5rem;letter-spacing:1px;'>ENTRIES</div></div>"
        f"<div style='background:rgba(212,175,55,0.08);border:1px solid #2a2a2a;"
        f"border-radius:6px;padding:6px 10px;flex:1;text-align:center;'>"
        f"<div style='color:{score_color};font-weight:900;font-size:1rem;'>{score}/10</div>"
        f"<div style='color:#555;font-size:0.5rem;letter-spacing:1px;'>DISCIPLINE</div></div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Training Input Bar ─────────────────────────────────────────────────────
    st.markdown(
        "<p style='font-size:0.6rem;color:#D4AF37;letter-spacing:2px;"
        "text-transform:uppercase;margin:8px 0 4px 0;'>▶ TRAIN THE BRAIN</p>",
        unsafe_allow_html=True,
    )
    train_text = st.text_area(
        label="train_input",
        label_visibility="collapsed",
        placeholder="Type anything to teach ZERO Brain...\n"
                    "e.g. 'I sold in panic when Nifty hit 24400'\n"
                    "     'Rule: never average down in a downtrend'\n"
                    "     'Today I followed my plan perfectly'",
        height=90,
        key="brain_train_input",
    )

    col_btn, col_clear = st.columns([2, 1])
    with col_btn:
        if st.button("⚡ TRAIN", key="brain_train_btn", use_container_width=True):
            if train_text and train_text.strip():
                entry = brain.ingest(train_text.strip(), source="user")
                biases = entry.get("biases", [])
                if biases:
                    st.warning(f"⚠ Bias detected: {', '.join(biases)}")
                else:
                    st.success(f"✓ Stored as [{entry.get('type','concept')}]")
                st.rerun()
            else:
                st.error("Type something first.")
    with col_clear:
        if st.button("✕ CLR", key="brain_clear_btn", use_container_width=True):
            st.session_state["brain_train_input"] = ""
            st.rerun()

    # ── Query Bar ─────────────────────────────────────────────────────────────
    st.markdown(
        "<p style='font-size:0.6rem;color:#aaa;letter-spacing:2px;"
        "text-transform:uppercase;margin:12px 0 4px 0;'>🔍 QUERY BRAIN</p>",
        unsafe_allow_html=True,
    )
    query_text = st.text_input(
        label="query_input",
        label_visibility="collapsed",
        placeholder="Ask: 'FOMO trades this week', 'my rule on loss'...",
        key="brain_query_input",
    )
    if query_text and query_text.strip():
        results = brain.query(query_text.strip(), top_k=4)
        if results:
            for r in results:
                tag_color = "#E50914" if r.get("biases") else "#D4AF37"
                tag_label = ", ".join(r["biases"]) if r.get("biases") else r.get("type", "concept")
                st.markdown(
                    f"<div style='background:#0a0a0a;border-left:2px solid {tag_color};"
                    f"padding:6px 8px;margin:3px 0;border-radius:0 4px 4px 0;'>"
                    f"<div style='color:{tag_color};font-size:0.5rem;letter-spacing:1px;"
                    f"text-transform:uppercase;'>{tag_label}</div>"
                    f"<div style='color:#ccc;font-size:0.68rem;line-height:1.4;margin-top:2px;'>"
                    f"{r['content'][:140]}{'…' if len(r['content'])>140 else ''}</div>"
                    f"<div style='color:#333;font-size:0.5rem;margin-top:2px;'>{r.get('date','')}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No matching entries found.")

    st.markdown("<hr style='border-color:#1a1a1a;margin:12px 0;'>", unsafe_allow_html=True)

    # ── Today's Mental Model (Pre-Market Log from Obsidian Plan Section 3) ─────
    st.markdown(
        "<p style='font-size:0.6rem;color:#D4AF37;letter-spacing:2px;"
        "text-transform:uppercase;margin:0 0 6px 0;'>📋 TODAY'S MENTAL LOG</p>",
        unsafe_allow_html=True,
    )
    forecasts = daily_log.get("forecasts", {})
    biases_today = daily_log.get("biases_flagged", [])

    if forecasts:
        for idx, short in [("NIFTY 50", "NIFTY"), ("BANKNIFTY", "BNKN"), ("SENSEX", "SNSEX")]:
            f = forecasts.get(idx)
            if not f:
                continue
            conf = f.get("confidence", 0)
            conf_color = "#00ff88" if conf >= 70 else ("#D4AF37" if conf >= 50 else "#E50914")
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:3px 0;border-bottom:1px solid #111;'>"
                f"<span style='color:#555;font-size:0.55rem;letter-spacing:1px;'>{short}</span>"
                f"<span style='color:#ddd;font-size:0.62rem;font-weight:700;'>"
                f"{f.get('pred_low',0):,.0f} – {f.get('pred_high',0):,.0f}</span>"
                f"<span style='color:{conf_color};font-size:0.5rem;'>{conf:.0f}%</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No predictions loaded yet.")

    # Bias flags for today
    if biases_today:
        st.markdown(
            f"<div style='margin-top:6px;padding:5px 8px;background:rgba(229,9,20,0.08);"
            f"border:1px solid rgba(229,9,20,0.2);border-radius:4px;'>"
            f"<span style='color:#E50914;font-size:0.55rem;font-weight:800;letter-spacing:1px;'>"
            f"⚠ BIASES TODAY: {' · '.join(biases_today)}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='margin-top:6px;padding:5px 8px;background:rgba(0,255,136,0.05);"
            "border:1px solid rgba(0,255,136,0.15);border-radius:4px;'>"
            "<span style='color:#00ff88;font-size:0.55rem;font-weight:700;'>✓ No biases flagged today</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#1a1a1a;margin:12px 0;'>", unsafe_allow_html=True)

    # ── Recent Knowledge Cards ─────────────────────────────────────────────────
    recent = brain.get_recent(4)
    if recent:
        st.markdown(
            "<p style='font-size:0.6rem;color:#aaa;letter-spacing:2px;"
            "text-transform:uppercase;margin:0 0 6px 0;'>📚 RECENT KNOWLEDGE</p>",
            unsafe_allow_html=True,
        )
        for e in recent:
            is_bias = bool(e.get("biases"))
            border_col = "#E50914" if is_bias else "#1e1e1e"
            tag_col = "#E50914" if is_bias else "#555"
            tag = (", ".join(e["biases"]) if is_bias else e.get("type", "concept")).upper()
            st.markdown(
                f"<div style='background:#080808;border:1px solid {border_col};"
                f"border-radius:4px;padding:7px 9px;margin:3px 0;'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"margin-bottom:3px;'>"
                f"<span style='color:{tag_col};font-size:0.48rem;letter-spacing:1px;'>{tag}</span>"
                f"<span style='color:#333;font-size:0.48rem;'>{e.get('date','')}</span>"
                f"</div>"
                f"<div style='color:#bbb;font-size:0.65rem;line-height:1.45;'>"
                f"{e['content'][:120]}{'…' if len(e['content'])>120 else ''}"
                f"</div></div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<p style='color:#333;font-size:0.62rem;font-style:italic;'>No entries yet. "
            "Start training the brain above.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:#1a1a1a;margin:12px 0;'>", unsafe_allow_html=True)

    # ── Bias Radar ────────────────────────────────────────────────────────────
    bias_pct = brain.get_bias_pct()
    # Only show top 4 biases with any pct or first 4 always
    top_biases = sorted(bias_pct.items(), key=lambda x: -x[1])[:4]

    st.markdown(
        "<p style='font-size:0.6rem;color:#aaa;letter-spacing:2px;"
        "text-transform:uppercase;margin:0 0 6px 0;'>🔴 BIAS RADAR</p>",
        unsafe_allow_html=True,
    )
    for bias_name, pct in top_biases:
        bar_color = "#E50914" if pct > 20 else ("#D4AF37" if pct > 5 else "#222")
        filled = int(pct / 10)  # 0–10 blocks
        bar_str = "█" * filled + "░" * (10 - filled)
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:6px;margin:3px 0;'>"
            f"<span style='color:#444;font-size:0.48rem;letter-spacing:1px;width:80px;'>"
            f"{bias_name[:10].upper()}</span>"
            f"<span style='color:{bar_color};font-family:monospace;font-size:0.55rem;'>{bar_str}</span>"
            f"<span style='color:{bar_color};font-size:0.48rem;'>{pct:.0f}%</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  ZERO ENGINE — Full-Screen Overlay Modal with Gemini AI Chat
# ─────────────────────────────────────────────────────────────────────────────

def render_zero_engine_modal(chat_engine, api_key_state: dict):
    """
    Renders the ZERO ENGINE full-screen overlay modal.

    Args:
        chat_engine   : GeminiChat instance (or None if not yet initialized)
        api_key_state : dict with keys 'key' (str) and 'changed' (bool)
    """
    import os as _os

    logo_path = _os.path.join(_os.path.dirname(__file__), 'assets', 'logo.png')
    logo_b64 = get_base64_of_bin_file(logo_path)
    img_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""
    img_html = (
        f"<img class='ze-logo' src='{img_src}' alt='ZERO'/>"
        if img_src else
        "<div class='ze-logo' style='background:rgba(229,9,20,0.1);display:flex;"
        "align-items:center;justify-content:center;'>"
        "<span style='color:#E50914;font-family:Orbitron,sans-serif;"
        "font-weight:900;font-size:1rem;'>Z</span></div>"
    )

    # ── Inject overlay CSS ────────────────────────────────────────────────────
    st.markdown("""
    <style>
    @keyframes enginePulse {
        0%   { box-shadow: 0 0 20px rgba(229,9,20,0.4), 0 0 60px rgba(229,9,20,0.1); }
        50%  { box-shadow: 0 0 40px rgba(229,9,20,0.8), 0 0 120px rgba(229,9,20,0.3); }
        100% { box-shadow: 0 0 20px rgba(229,9,20,0.4), 0 0 60px rgba(229,9,20,0.1); }
    }
    @keyframes engineGlow {
        0%   { text-shadow: 0 0 10px rgba(229,9,20,0.5); }
        50%  { text-shadow: 0 0 30px rgba(229,9,20,1.0), 0 0 60px rgba(229,9,20,0.5); }
        100% { text-shadow: 0 0 10px rgba(229,9,20,0.5); }
    }
    @keyframes scanLine {
        0%   { transform: translateY(-4px); opacity: 0.07; }
        100% { transform: translateY(100vh);  opacity: 0.07; }
    }
    @keyframes fadeSlideUp {
        from { opacity: 0; transform: translateY(12px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .ze-scan-line {
        position: fixed; top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(to right, transparent, #E50914 40%, transparent);
        animation: scanLine 5s linear infinite;
        z-index: 9001; pointer-events: none;
    }
    .ze-header {
        display: flex; flex-direction: column; align-items: center;
        padding: 10px 0 6px 0;
        animation: fadeSlideUp 0.5s ease-out;
    }
    .ze-logo {
        width: 80px; height: 80px; border-radius: 50%;
        border: 2px solid rgba(229,9,20,0.4);
        animation: enginePulse 2.5s ease-in-out infinite;
        margin-bottom: 10px;
    }
    .ze-title {
        font-family: 'Orbitron', sans-serif;
        font-weight: 900; font-size: 1.5rem; letter-spacing: 6px;
        color: #ffffff; animation: engineGlow 2.5s ease-in-out infinite;
        margin: 0; text-align: center;
    }
    .ze-subtitle {
        color: #E50914; font-size: 0.58rem; font-weight: 700;
        letter-spacing: 4px; text-transform: uppercase;
        margin: 4px 0 0 0; text-align: center;
    }
    .ze-status-bar {
        display: flex; gap: 12px; align-items: center;
        padding: 5px 0; margin-top: 4px; flex-wrap: wrap;
    }
    .ze-status-dot {
        width: 6px; height: 6px; border-radius: 50%;
        display: inline-block; margin-right: 4px;
        animation: enginePulse 1.5s ease-in-out infinite;
    }
    .ze-divider {
        border: none; border-top: 1px solid rgba(229,9,20,0.12); margin: 8px 0;
    }
    .ze-chat-container {
        background: rgba(5,5,5,0.96);
        border: 1px solid rgba(229,9,20,0.12);
        border-radius: 8px; padding: 14px;
        min-height: 300px; max-height: 420px;
        overflow-y: auto; margin: 8px 0;
        animation: fadeSlideUp 0.6s ease-out;
    }
    .ze-msg-user {
        display: flex; justify-content: flex-end; margin: 8px 0;
    }
    .ze-msg-user-bubble {
        background: rgba(212,175,55,0.10);
        border: 1px solid rgba(212,175,55,0.28);
        border-radius: 12px 12px 2px 12px;
        padding: 10px 14px; max-width: 75%;
        color: #D4AF37; font-size: 0.82rem; line-height: 1.55;
    }
    .ze-msg-ai {
        display: flex; justify-content: flex-start; margin: 8px 0;
    }
    .ze-msg-ai-bubble {
        background: rgba(229,9,20,0.05);
        border: 1px solid rgba(229,9,20,0.18);
        border-radius: 12px 12px 12px 2px;
        padding: 10px 14px; max-width: 80%;
        color: #eeeeee; font-size: 0.82rem; line-height: 1.65;
    }
    .ze-msg-label {
        font-size: 0.5rem; letter-spacing: 2px; font-weight: 800;
        text-transform: uppercase; margin-bottom: 5px;
    }
    .ze-empty-chat {
        text-align: center; padding: 40px 20px; color: #222;
    }
    .ze-train-hint {
        color: #2a2a2a; font-size: 0.58rem; letter-spacing: 1px;
        text-align: center; margin-top: 5px;
    }
    </style>
    <div class="ze-scan-line"></div>
    """, unsafe_allow_html=True)

    # ── Close button ─────────────────────────────────────────────────────────
    cl_col, _, hdr_col = st.columns([1, 0.2, 6])
    with cl_col:
        if st.button("✕ CLOSE", key="zero_engine_close", use_container_width=True):
            st.session_state['show_zero_engine'] = False
            st.rerun()

    # ── Glowing logo header ───────────────────────────────────────────────────
    st.markdown(f"""
    <div class="ze-header">
        {img_html}
        <h2 class="ze-title">ZERO ENGINE</h2>
        <p class="ze-subtitle">AI Intelligence Core · Gemini Powered</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Status + stats bar ────────────────────────────────────────────────────
    api_ok = chat_engine is not None and chat_engine.is_available()
    stats = chat_engine.get_stats() if chat_engine else {}
    status_color = "#00ff88" if api_ok else "#D4AF37"
    status_label = "GEMINI ONLINE" if api_ok else "OFFLINE MODE"
    kb_count = stats.get("kb_entries", 0)
    session_trained = stats.get("session_training", 0)
    chat_count = stats.get("chat_messages", 0)

    st.markdown(f"""
    <div class="ze-status-bar">
        <span>
            <span class="ze-status-dot" style="background:{status_color};"></span>
            <span style="color:{status_color};font-size:0.55rem;font-weight:800;
                  letter-spacing:2px;">{status_label}</span>
        </span>
        <span style="color:#222;font-size:0.5rem;">|</span>
        <span style="color:#444;font-size:0.55rem;letter-spacing:1px;">
            📚 {kb_count} KNOWLEDGE ENTRIES</span>
        <span style="color:#222;font-size:0.5rem;">|</span>
        <span style="color:#444;font-size:0.55rem;letter-spacing:1px;">
            ⚡ {session_trained} SESSION TRAINED</span>
        <span style="color:#222;font-size:0.5rem;">|</span>
        <span style="color:#444;font-size:0.55rem;letter-spacing:1px;">
            💬 {chat_count} MESSAGES</span>
    </div>
    <hr class="ze-divider"/>
    """, unsafe_allow_html=True)

    # ── Settings expander (API key) ───────────────────────────────────────────
    with st.expander("⚙  ENGINE SETTINGS", expanded=False):
        st.markdown(
            "<p style='color:#555;font-size:0.6rem;letter-spacing:2px;"
            "text-transform:uppercase;margin-bottom:6px;'>GEMINI API KEY</p>",
            unsafe_allow_html=True,
        )
        new_key = st.text_input(
            label="gemini_key_input",
            label_visibility="collapsed",
            value=api_key_state.get("key", ""),
            type="password",
            placeholder="Paste your Gemini API key...",
            key="ze_api_key_input",
        )
        kcol1, kcol2 = st.columns([2, 1])
        with kcol1:
            if st.button("⚡ APPLY KEY", key="ze_apply_key", use_container_width=True):
                api_key_state["key"] = new_key.strip()
                api_key_state["changed"] = True
                st.session_state["ze_api_key_override"] = new_key.strip()
                st.success("Key saved — reinitializing engine...")
                st.rerun()
        with kcol2:
            st.markdown(
                "<a href='https://aistudio.google.com' target='_blank' "
                "style='color:#E50914;font-size:0.6rem;'>Get Free Key ↗</a>",
                unsafe_allow_html=True,
            )

    st.markdown("<hr class='ze-divider'/>", unsafe_allow_html=True)

    # ── Chat history display ──────────────────────────────────────────────────
    history = chat_engine.get_history() if chat_engine else []
    import html as _html_mod

    if not history:
        st.markdown("""
        <div class="ze-empty-chat">
            <div style="font-size:2.5rem; margin-bottom:14px; animation:enginePulse 2s infinite;">🧠</div>
            <p style="color:#333; font-size:0.75rem; letter-spacing:3px; text-transform:uppercase;">
                ZERO ENGINE READY</p>
            <p style="color:#1e1e1e; font-size:0.65rem; line-height:1.9; margin-top:10px;">
                Ask me about candle patterns · trading psychology<br/>
                market rules · your personal trading journal<br/>
                <br/>
                <span style="color:#D4AF37;">TRAIN: [your insight]</span>
                &nbsp;→ teaches me your rules in real time
            </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        chat_html_parts = ["<div class='ze-chat-container'>"]
        for msg in history[-30:]:
            role = msg.get("role", "user")
            raw = msg.get("content", "")
            # Escape then restore bold markdown
            escaped = _html_mod.escape(raw)
            escaped = escaped.replace("**", "<b>").replace("\n", "<br/>")
            ts = msg.get("timestamp", "")[:16].replace("T", " ")
            if role == "user":
                chat_html_parts.append(
                    f"<div class='ze-msg-user'><div class='ze-msg-user-bubble'>"
                    f"<div class='ze-msg-label' style='color:#D4AF37;'>YOU · {ts}</div>"
                    f"{escaped}</div></div>"
                )
            else:
                chat_html_parts.append(
                    f"<div class='ze-msg-ai'><div class='ze-msg-ai-bubble'>"
                    f"<div class='ze-msg-label' style='color:#E50914;'>ZERO ENGINE · {ts}</div>"
                    f"{escaped}</div></div>"
                )
        chat_html_parts.append("</div>")
        st.markdown("".join(chat_html_parts), unsafe_allow_html=True)

    # ── Input bar ─────────────────────────────────────────────────────────────
    st.markdown("<hr class='ze-divider'/>", unsafe_allow_html=True)

    inp_col, send_col, clear_col = st.columns([6, 1, 1])
    with inp_col:
        user_input = st.text_input(
            label="engine_chat_input",
            label_visibility="collapsed",
            placeholder="Ask ZERO ENGINE anything... (or: TRAIN: your new rule)",
            key="ze_chat_input",
        )
    with send_col:
        send_clicked = st.button("▶ SEND", key="ze_send_btn", use_container_width=True)
    with clear_col:
        if st.button("✕ CLR", key="ze_clear_btn", use_container_width=True):
            if chat_engine:
                chat_engine.clear_history()
            st.rerun()

    # ── Handle send ───────────────────────────────────────────────────────────
    if send_clicked and user_input and user_input.strip():
        msg = user_input.strip()

        if msg.upper().startswith("TRAIN:"):
            # Training mode — add to KB and persist to brain entries
            training_text = msg[6:].strip()
            if training_text and chat_engine:
                chat_engine.add_training(training_text)
                try:
                    from engine.brain_engine import BrainEngine
                    brain = BrainEngine()
                    brain.ingest(training_text, source="zero_engine")
                except Exception:
                    pass
                with st.spinner("Integrating knowledge..."):
                    chat_engine.send(
                        f"Acknowledge and confirm you have integrated this new knowledge: {training_text}"
                    )
                st.rerun()
        else:
            if chat_engine:
                with st.spinner("ZERO ENGINE thinking..."):
                    chat_engine.send(msg)
                st.rerun()
            else:
                st.error("Engine not initialized. Check your Gemini API key in ⚙ settings above.")

    st.markdown(
        "<p class='ze-train-hint'>"
        "💡 Tip: Use <b style='color:#D4AF37;'>TRAIN: [your insight]</b> "
        "to teach ZERO ENGINE your personal rules and observations in real time"
        "</p>",
        unsafe_allow_html=True,
    )


def render_trading_strategy_bubbles(matrix=None, news_feed=None):
    """Renders the dynamic Strategy & Risk Management Advisory component in the
    Trading Terminal, analyzing live market inputs, global news intelligence,
    and computing precise safe entry/exit/stop-loss points with detailed explanations.
    """
    import html as _html

    if matrix is None:
        matrix = st.session_state.get('matrix') or {}
    if news_feed is None:
        news_feed = st.session_state.get('news_feed') or []

    st.markdown("""
    <style>
    .strat-bubble-container {
        background: linear-gradient(135deg, rgba(15,15,15,0.95), rgba(25,20,10,0.85));
        border: 1px solid rgba(212,175,55,0.35);
        border-radius: 6px;
        padding: 18px 22px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }
    .strat-bubble-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 14px;
        border-bottom: 1px solid rgba(212,175,55,0.2);
        padding-bottom: 10px;
        flex-wrap: wrap;
        gap: 10px;
    }
    .strat-bubble-title {
        color: #D4AF37;
        font-family: 'Orbitron', sans-serif;
        font-weight: 800;
        font-size: 0.85rem;
        letter-spacing: 2px;
        text-transform: uppercase;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .safe-points-banner {
        background: rgba(10, 10, 10, 0.85);
        border: 1px solid rgba(0, 255, 136, 0.3);
        border-radius: 4px;
        padding: 14px 18px;
        margin-bottom: 18px;
    }
    .safe-point-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 3px;
        font-weight: 800;
        font-size: 0.65rem;
        letter-spacing: 1px;
        margin-bottom: 6px;
        text-transform: uppercase;
    }
    .sp-buy { background: rgba(0, 255, 136, 0.15); color: #00ff88; border: 1px solid #00ff88; }
    .sp-target { background: rgba(212, 175, 55, 0.15); color: #D4AF37; border: 1px solid #D4AF37; }
    .sp-stop { background: rgba(229, 9, 20, 0.15); color: #E50914; border: 1px solid #E50914; }
    .sp-size { background: rgba(0, 180, 255, 0.15); color: #00b4ff; border: 1px solid #00b4ff; }
    .sp-val {
        color: #ffffff;
        font-size: 1.1rem;
        font-weight: 900;
        font-family: 'Orbitron', sans-serif;
        margin-bottom: 4px;
    }
    .sp-desc {
        color: #aaa;
        font-size: 0.72rem;
        line-height: 1.45;
    }
    .strat-card {
        background: rgba(10,10,10,0.7);
        border: 1px solid #222;
        border-radius: 4px;
        padding: 14px 16px;
        height: 100%;
        transition: border-color 0.3s ease, transform 0.2s ease;
    }
    .strat-card:hover {
        border-color: #D4AF37;
        transform: translateY(-2px);
    }
    .strat-item-title {
        color: #00ff88;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 1px;
        margin-bottom: 6px;
        text-transform: uppercase;
    }
    .strat-item-desc {
        color: #ccc;
        font-size: 0.75rem;
        line-height: 1.5;
    }
    .strat-item-explanation {
        color: #888;
        font-size: 0.68rem;
        line-height: 1.4;
        margin-top: 6px;
        border-top: 1px dashed #222;
        padding-top: 6px;
        font-style: italic;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Index Switcher ──────────────────────────────────────────────────────
    col_hdr1, col_hdr2 = st.columns([2, 1])
    with col_hdr1:
        st.markdown("""
        <div class="strat-bubble-title">
            <span>⚡ QUANTUM STRATEGY & DYNAMIC RISK ADVISORY</span>
        </div>
        <p style="color:#888; font-size:0.62rem; margin:2px 0 12px 0;">
            Live market intelligence analysis, calculated safe entry/exit bounds, and actionable strategy suggestions.
        </p>
        """, unsafe_allow_html=True)
    with col_hdr2:
        selected_index = st.radio(
            "Target Index",
            ["NIFTY 50", "BANKNIFTY", "SENSEX"],
            horizontal=True,
            key="strat_advisory_index",
            label_visibility="collapsed"
        )

    # Extract Index Data & Defaults
    idx_data = matrix.get(selected_index, {}) if isinstance(matrix, dict) else {}
    if not isinstance(idx_data, dict):
        idx_data = {}

    spot = float(idx_data.get('prev_close') or 24000.0)
    pred_open = float(idx_data.get('pred_open') or spot)
    pred_high = float(idx_data.get('pred_high') or (spot * 1.008))
    pred_low = float(idx_data.get('pred_low') or (spot * 0.992))
    pred_close = float(idx_data.get('pred_close') or spot)
    vix = float(idx_data.get('vix') or 15.0)
    pcr = float(idx_data.get('pcr') or 1.0)
    sentiment_score = float(idx_data.get('sentiment_score') or 0.0)
    movement_side = idx_data.get('movement_side', 'Neutral / Live Session')
    confidence = float(idx_data.get('confidence') or 80.0)

    # News Intelligence Analysis
    top_news_category = "GENERAL"
    max_impact = 0.0
    breaking_count = 0
    bullish_news = 0
    bearish_news = 0

    if news_feed and isinstance(news_feed, list):
        for item in news_feed:
            if isinstance(item, dict):
                imp = item.get('impact_score', 0)
                if imp > max_impact:
                    max_impact = imp
                    top_news_category = item.get('category_label', 'GLOBAL MACRO')
                d = item.get('direction', 'NEUTRAL')
                if d == 'BULLISH': bullish_news += 1
                elif d == 'BEARISH': bearish_news += 1
                if item.get('is_high_impact'): breaking_count += 1

    # ── DYNAMIC SAFE POINTS CALCULATIONS ──────────────────────────────────────
    total_range = max(10.0, pred_high - pred_low)
    
    # Safe Accumulation / Buying Zone (bottom 20% of range above pred_low)
    safe_buy_low = round(pred_low, 1)
    safe_buy_high = round(pred_low + total_range * 0.22, 1)
    
    # Safe Profit Booking / Target Zone (top 20% of range below pred_high)
    safe_target_low = round(pred_high - total_range * 0.22, 1)
    safe_target_high = round(pred_high, 1)
    
    # Strict Hard Stop-Loss (0.3% below pred_low)
    stop_loss = round(pred_low - (spot * 0.0035), 1)
    stop_loss_pts = round(spot - stop_loss, 1)

    # Position Sizing & Cash Buffer Recommendation based on VIX & News Impact
    if vix >= 18.0 or max_impact >= 75:
        rec_size_pct = "15% - 20%"
        cash_buffer_pct = 40
        vol_regime = "HIGH VOLATILITY (DEFENSIVE STANCE)"
    elif vix >= 14.0:
        rec_size_pct = "25% - 30%"
        cash_buffer_pct = 30
        vol_regime = "NORMAL VOLATILITY (BALANCED STANCE)"
    else:
        rec_size_pct = "35% - 45%"
        cash_buffer_pct = 20
        vol_regime = "LOW VOLATILITY (GROWTH STANCE)"

    # Risk-Reward Ratio Calculation
    risk_pts = max(10.0, spot - safe_buy_low)
    reward_pts = max(10.0, safe_target_high - spot)
    rr_ratio = round(reward_pts / risk_pts, 2)

    # ── RENDER LIVE SAFE POINTS BANNER ───────────────────────────────────────
    st.markdown(f"""
    <div class="safe-points-banner">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
            <div>
                <span style="color:#D4AF37; font-family:'Orbitron',sans-serif; font-weight:800; font-size:0.8rem; letter-spacing:1px;">
                    🎯 LIVE ANALYSIS FOR {selected_index}
                </span>
                <span style="color:#666; font-size:0.65rem; margin-left:8px;">
                    Spot Ref: <b style="color:#fff;">{spot:,.1f}</b> | Vector: <b style="color:#00ff88;">{movement_side}</b> | Reg: <b style="color:#D4AF37;">{vol_regime}</b>
                </span>
            </div>
            <div style="color:#aaa; font-size:0.65rem;">
                Confidence: <b style="color:#00ff88;">{confidence:.0f}%</b> | Risk-Reward Ratio: <b style="color:#D4AF37;">1 : {rr_ratio}</b>
            </div>
        </div>
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap:12px;">
            <div style="background:rgba(0,0,0,0.5); padding:10px 12px; border-radius:4px; border-left:3px solid #00ff88;">
                <span class="safe-point-badge sp-buy">🟢 SAFE BUY / ACCUMULATION ZONE</span>
                <div class="sp-val">{safe_buy_low:,.1f} – {safe_buy_high:,.1f}</div>
                <div class="sp-desc">Optimal low-risk entry near support level ({pred_low:,.1f}). Do not chase green candles above {safe_buy_high:,.1f}.</div>
            </div>
            <div style="background:rgba(0,0,0,0.5); padding:10px 12px; border-radius:4px; border-left:3px solid #D4AF37;">
                <span class="safe-point-badge sp-target">🎯 TARGET / PROFIT BOOKING ZONE</span>
                <div class="sp-val">{safe_target_low:,.1f} – {safe_target_high:,.1f}</div>
                <div class="sp-desc">Scale out long positions near resistance ({pred_high:,.1f}) as call-side options friction increases.</div>
            </div>
            <div style="background:rgba(0,0,0,0.5); padding:10px 12px; border-radius:4px; border-left:3px solid #E50914;">
                <span class="safe-point-badge sp-stop">🛑 HARD INVALIDATION / STOP-LOSS</span>
                <div class="sp-val">{stop_loss:,.1f}</div>
                <div class="sp-desc">Strict intraday exit trigger ({stop_loss_pts:.0f} pts below spot). A 15-min candle close below invalidates the bullish thesis.</div>
            </div>
            <div style="background:rgba(0,0,0,0.5); padding:10px 12px; border-radius:4px; border-left:3px solid #00b4ff;">
                <span class="safe-point-badge sp-size">⚖️ REC. POSITION SIZE & CASH</span>
                <div class="sp-val">{rec_size_pct}</div>
                <div class="sp-desc">Allocate max {rec_size_pct} capital per trade. Keep <b>{cash_buffer_pct}%</b> cash buffer for unexpected headline spikes.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── RENDER DYNAMIC 4-PILLAR STRATEGY SUGGESTIONS ──────────────────────────
    t1, t2, t3, t4 = st.tabs([
        "🛡️ DEFENSIVE RISK MANAGEMENT",
        "🌐 PORTFOLIO DIVERSIFICATION",
        "📈 VOLATILITY TRADING STRATEGIES",
        "🧠 FILTER OUT SHORT-TERM NOISE"
    ])

    with t1:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🎯 Position Sizing</div>
                <div class="strat-item-desc">Limit single trade allocations to <b>{rec_size_pct}</b> of total capital.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Current VIX is <b>{vix:.1f}</b> with max news impact score at <b>{max_impact:.0f}/100</b>. High news volatility requires capped position sizes to prevent tail-risk drawdowns.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🛑 Stop-Loss Triggers</div>
                <div class="strat-item-desc">Set automated stop-loss at <b>{stop_loss:,.1f}</b> (-{stop_loss_pts:.0f} pts).</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Placed 0.35% below lower predicted envelope ({pred_low:,.1f}) to avoid getting stopped out by regular intraday noise spikes.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">📈 Trailing Stop-Losses</div>
                <div class="strat-item-desc">Activate trailing trigger once price reaches <b>{spot + (total_range * 0.4):,.1f}</b>.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Locks in gains automatically as price moves into the upper target expansion band ({pred_high:,.1f}), protecting accumulated profits.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">💵 Cash Buffer Allocation</div>
                <div class="strat-item-desc">Maintain liquid cash buffer of at least <b>{cash_buffer_pct}%</b>.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> High breaking news frequency ({breaking_count} breaking stories) creates unexpected liquidity dips—cash lets you buy premium assets at a discount.
                </div>
            </div>
            """, unsafe_allow_html=True)

    with t2:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">📊 Asset Allocation</div>
                <div class="strat-item-desc">Spread capital: <b>55% Equities</b>, <b>25% Debt/Bonds</b>, <b>20% Gold/Cash</b>.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Sentiment score is <b>{sentiment_score:+.2f}</b> with GIFT Nifty premium active. Balancing equities with gold insulates portfolio against overnight gap risks.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🌍 Geographic Spread</div>
                <div class="strat-item-desc">Hedge local domestic market moves with international global exposure.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Top headline driver is <b>{top_news_category}</b>. Global macro events impact EM liquidity regardless of domestic fundamentals.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🔄 Sector Rotation</div>
                <div class="strat-item-desc">Rotate between defensive (FMCG/Pharma) & cyclical (IT/Banking).</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> For <b>{selected_index}</b>, news sentiment signals sector tilt. Rotate into defensive sectors when VIX spikes above 16.0.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">⚖️ Inverse Correlation</div>
                <div class="strat-item-desc">Hold Sovereign Gold Bonds or Gold ETFs to offset equity sell-offs.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Gold traditionally spikes during geopolitical or inflation news flashes, serving as an automated portfolio buffer.
                </div>
            </div>
            """, unsafe_allow_html=True)

    with t3:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🛡️ Options Hedging</div>
                <div class="strat-item-desc">PCR is <b>{pcr:.2f}</b> — {"Buy protective OTM Put options." if pcr > 1.25 else "Hedge long stock holdings with Put options."}</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> {"High PCR (>1.25) signals overbought call accumulation—protective Puts insure against sudden mean-reversion drops." if pcr > 1.25 else "PCR indicates balanced open interest; light hedging advised."}
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🎯 Straddles & Strangles</div>
                <div class="strat-item-desc">Deploy Long Straddle prior to Central Bank / Budget releases.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Major news category (<b>{top_news_category}</b>) causes violent non-directional volatility spikes—straddles profit from explosive moves in either direction.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">⏳ Dollar-Cost Averaging</div>
                <div class="strat-item-desc">Execute systematic DCA accumulation on every <b>-{total_range*0.15:.0f} pt</b> dip.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Smooths out purchase costs during volatile regimes, preventing emotional top-of-range buying.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">📊 VIX Monitoring</div>
                <div class="strat-item-desc">Track India VIX ({vix:.1f}) for volatility extremes.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> {"VIX is calm—options premiums are cheap for hedging." if vix < 15 else "VIX is elevated—implied volatility is high; sell credit spreads or wait for VIX to peak before buying calls."}
                </div>
            </div>
            """, unsafe_allow_html=True)

    with t4:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🔍 Focus on Fundamentals</div>
                <div class="strat-item-desc">Trust multi-quarter earnings & GDP growth over intraday news spikes.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Algorithmic news headline bots create initial knee-jerk gaps that typically mean-revert back to fundamental earnings trends.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🧊 Avoid Panic Selling</div>
                <div class="strat-item-desc">Wait <b>15–20 mins</b> post 9:15 AM open before executing pre-market orders.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> The first 15 minutes of the session reflect retail panic and HFT liquidity harvesting. Wait for institutional order flow to stabilize.
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="strat-card">
                <div class="strat-item-title">🔭 Review Multi-Year Horizons</div>
                <div class="strat-item-desc">Align core portfolio positions with 5 to 10-year structural growth trends.</div>
                <div class="strat-item-explanation">
                    <b>Market Context:</b> Short-term news sentiment impact dissipates within 1 to 3 trading sessions—long-term compounding dominates multi-year horizons.
                </div>
            </div>
            """, unsafe_allow_html=True)


# ── ForexFactory Priority Macro Feed UI ──────────────────────────────────────
def render_forexfactory_priority_card(news_feed: list | None = None):
    """Renders ForexFactory Priority #1 Macro Economic News Banner."""
    import streamlit as st
    ff_items = [n for n in (news_feed or []) if isinstance(n, dict) and (n.get('source', '').startswith('ForexFactory') or n.get('is_forexfactory') or n.get('priority') == 1)]
    if not ff_items:
        return

    cards_html = ""
    for item in ff_items[:3]:
        title = item.get('title', '')
        link = item.get('link', '#')
        published = item.get('published', '')
        ccy = item.get('currency', 'MACRO')
        cards_html += f"""<div style="background: rgba(15, 15, 15, 0.6); border-left: 3px solid #E50914; padding: 8px 12px; margin-top: 6px; border-radius: 4px;"><div style="font-size: 0.75rem; font-weight: 600; color: #eee;"><span style="color: #D4AF37; font-size: 0.65rem; font-weight: 800; margin-right: 6px;">[{ccy}]</span><a href="{link}" target="_blank" style="color: #fff; text-decoration: none;">{title}</a></div><div style="font-size: 0.6rem; color: #888; margin-top: 2px;">Released / Scheduled: {published}</div></div>"""

    full_html = f"""<div style="background: rgba(229, 9, 20, 0.06); border: 1px solid rgba(229, 9, 20, 0.4); border-radius: 8px; padding: 14px; margin-bottom: 16px;"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;"><div style="font-family: 'Orbitron', sans-serif; font-size: 0.8rem; font-weight: 800; color: #E50914; letter-spacing: 2px;">🔴 FOREXFACTORY MACRO FEED · PRIORITY #1</div><div style="background: #E50914; color: #fff; font-size: 0.55rem; font-weight: 800; padding: 2px 8px; border-radius: 999px; letter-spacing: 1px;">HIGH IMPACT CALENDAR</div></div>{cards_html}</div>"""

    st.markdown(full_html, unsafe_allow_html=True)


# ── TradingAgents Multi-Agent Debate Panel UI ────────────────────────────────
def render_trading_agents_panel(agent_consensus: dict | None = None):
    """Renders multi-agent collaborative debate and consensus verdict card."""
    import streamlit as st
    if not agent_consensus or not isinstance(agent_consensus, dict):
        return

    verdict = agent_consensus.get('verdict', 'NEUTRAL')
    conf = agent_consensus.get('overall_confidence', 50.0)
    debate = agent_consensus.get('debate_summary', '')
    agents = agent_consensus.get('agents', {})

    v_color = "#00E676" if "BULLISH" in verdict else ("#FF1744" if "BEARISH" in verdict else "#FFC107")

    agents_html = ""
    for role_key, agent_data in agents.items():
        if not isinstance(agent_data, dict):
            continue
        name = agent_data.get('agent', role_key.title())
        bias = agent_data.get('bias', agent_data.get('risk_rating', 'NEUTRAL'))
        agent_conf = agent_data.get('confidence', 50.0)
        reasoning = agent_data.get('reasoning', '')
        b_color = "#00E676" if bias in ["BULLISH", "LOW"] else ("#FF1744" if bias in ["BEARISH", "HIGH"] else "#FFC107")

        agents_html += f"""<div style="background: rgba(30, 30, 30, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 10px;"><div style="display: flex; justify-content: space-between; font-size: 0.65rem; font-weight: 800; color: #aaa;"><span>{name.upper()}</span><span style="color: {b_color};">{bias} ({agent_conf}%)</span></div><p style="font-size: 0.62rem; color: #888; margin: 4px 0 0 0; line-height: 1.3;">{reasoning}</p></div>"""

    full_html = f"""<div style="background: rgba(20, 20, 20, 0.75); border: 1px solid rgba(212, 175, 55, 0.35); border-radius: 10px; padding: 16px; margin-bottom: 20px;"><div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 10px; margin-bottom: 12px;"><div><span style="font-family: 'Orbitron', sans-serif; font-size: 0.9rem; font-weight: 900; color: #fff; letter-spacing: 2px;">🤖 TRADINGAGENTS MULTI-AGENT CONSENSUS</span><p style="font-size: 0.6rem; color: #777; margin: 2px 0 0 0; letter-spacing: 1px;">ROLES: FUNDAMENTAL · TECHNICAL · SENTIMENT · RISK MANAGER</p></div><div style="text-align: right;"><div style="font-family: 'Orbitron', sans-serif; font-size: 1rem; font-weight: 900; color: {v_color}; letter-spacing: 1px;">{verdict}</div><div style="font-size: 0.6rem; color: #aaa;">Confidence: <b>{conf}%</b></div></div></div><p style="font-size: 0.7rem; color: #ccc; line-height: 1.5; font-style: italic; background: rgba(0,0,0,0.3); padding: 8px 12px; border-radius: 6px; border-left: 2px solid #D4AF37;">💬 <b>Consensus Debate:</b> {debate}</p><div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-top: 14px;">{agents_html}</div></div>"""

    st.markdown(full_html, unsafe_allow_html=True)


# ── QuantDinger Strategy Setup Card UI ───────────────────────────────────────
def render_quantdinge_strategy_card(quant_strategy: dict | None = None):
    """Renders QuantDinger quantitative regime & actionable strategy recommendation."""
    import streamlit as st
    if not quant_strategy or not isinstance(quant_strategy, dict):
        return

    idx = quant_strategy.get('index', 'INDEX')
    regime = quant_strategy.get('regime_label', 'NEUTRAL')
    strat_name = quant_strategy.get('strategy_name', 'Strategy Setup')
    action = quant_strategy.get('action', 'HOLD')
    entry = quant_strategy.get('entry_price', 0.0)
    sl = quant_strategy.get('stop_loss', 0.0)
    tp1 = quant_strategy.get('take_profit_1', 0.0)
    tp2 = quant_strategy.get('take_profit_2', 0.0)
    rr = quant_strategy.get('risk_reward_ratio', '1:2')
    win_prob = quant_strategy.get('win_probability_pct', 65.0)
    pos_size = quant_strategy.get('position_size_pct', 3.0)
    desc = quant_strategy.get('description', '')

    act_color = "#00E676" if "BUY" in action else ("#FF1744" if "SELL" in action else "#00B0FF")

    # Nautilus execution fields
    entry_type  = quant_strategy.get("nautilus_entry_order_type", "DAY LIMIT")
    bracket     = quant_strategy.get("nautilus_bracket_type", "GTC OCO")
    uw_note     = quant_strategy.get("options_flow_note", "")
    pcr_val     = quant_strategy.get("pcr", 1.0)

    full_html = f"""<div style="background: rgba(15, 25, 35, 0.85); border: 1px solid rgba(0, 176, 255, 0.4); border-radius: 10px; padding: 16px; margin-bottom: 20px;"><div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(0, 176, 255, 0.15); padding-bottom: 8px; margin-bottom: 12px;"><div><span style="font-family: 'Orbitron', sans-serif; font-size: 0.85rem; font-weight: 900; color: #00B0FF; letter-spacing: 2px;">⚡ QUANTDINGER ENGINE · {idx} STRATEGY</span><div style="font-size: 0.6rem; color: #888; margin-top: 2px;">Regime: <b style="color: #fff;">{regime}</b></div></div><div style="background: {act_color}; color: #000; font-family: 'Orbitron', sans-serif; font-weight: 900; font-size: 0.75rem; padding: 4px 12px; border-radius: 6px;">{action}</div></div><div style="font-size: 0.85rem; font-weight: 800; color: #fff; margin-bottom: 6px;">🎯 {strat_name}</div><p style="font-size: 0.68rem; color: #aaa; margin-bottom: 12px;">{desc}</p><div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: rgba(0,0,0,0.4); padding: 10px; border-radius: 6px; text-align: center;"><div><div style="font-size: 0.55rem; color: #777; text-transform: uppercase;">ENTRY PRICE</div><div style="font-size: 0.8rem; font-weight: 800; color: #fff;">{entry}</div></div><div><div style="font-size: 0.55rem; color: #FF1744; text-transform: uppercase;">STOP LOSS (SL)</div><div style="font-size: 0.8rem; font-weight: 800; color: #FF1744;">{sl}</div></div><div><div style="font-size: 0.55rem; color: #00E676; text-transform: uppercase;">TARGET (TP1 / TP2)</div><div style="font-size: 0.8rem; font-weight: 800; color: #00E676;">{tp1} / {tp2}</div></div><div><div style="font-size: 0.55rem; color: #D4AF37; text-transform: uppercase;">R:R / WIN PROB</div><div style="font-size: 0.8rem; font-weight: 800; color: #D4AF37;">{rr} · {win_prob}%</div></div></div>
<div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px 12px;margin-top:8px;font-size:0.6rem;color:#aaa;">
  <b style="color:#00B0FF;">Entry Order:</b> {entry_type} &nbsp;·&nbsp; <b style="color:#D4AF37;">Bracket:</b> {bracket}<br>
  <b style="color:#888;">PCR {pcr_val}</b> — {uw_note}
</div>
<div style="font-size: 0.58rem; color: #666; text-align: right; margin-top: 6px;">Recommended Max Risk Allocation: {pos_size}% Portfolio</div></div>"""

    st.markdown(full_html, unsafe_allow_html=True)



def render_fincept_thesis_card(thesis: dict | None = None):
    """Renders the Fincept Platform Quant Team Unified Trade Thesis card."""
    import streamlit as st
    if not thesis or not isinstance(thesis, dict) or "error" in thesis:
        return

    symbol      = thesis.get("symbol", "INDEX")
    final_score = thesis.get("final_score", 0.0)
    verdict     = thesis.get("verdict", "⚖️ NEUTRAL")
    strat       = thesis.get("quant_strategy") or {}
    risk        = thesis.get("risk_analysis") or {}
    micro       = thesis.get("microstructure") or {}
    sent        = thesis.get("sentiment") or {}
    opt_flow    = thesis.get("options_flow") or {}

    score_color = "#00E676" if final_score > 0.2 else ("#FF1744" if final_score < -0.2 else "#D4AF37")
    bar_w       = int(min(100, abs(final_score) * 100))
    bar_dir     = "right" if final_score > 0 else "left"
    bar_bg      = "#00E676" if final_score > 0 else "#FF1744"

    alpha_sig   = strat.get("signal", "FLAT")
    alpha_col   = "#00E676" if alpha_sig == "LONG" else ("#FF1744" if alpha_sig == "SHORT" else "#888")
    kelly_pct   = risk.get("kelly_pct", 0.0)
    pos_val     = risk.get("position_value", 0.0)
    liq_score   = micro.get("liquidity_score", 0.0)
    exec_advice = micro.get("execution_advice", "EXECUTE")
    spread_bps  = micro.get("spread_bps", 0.0)
    flow_score  = opt_flow.get("flow_score", 0.0)
    flow_interp = opt_flow.get("interpretation", "")
    pcr         = opt_flow.get("pcr", 1.0)
    sent_score  = sent.get("composite_score", 0.0)
    sent_int    = sent.get("intensity", "neutral")

    liq_bar = int(liq_score * 100)

    html = f"""
<div style="background:linear-gradient(135deg,rgba(10,20,40,0.95) 0%,rgba(5,10,25,0.98) 100%);
            border:1px solid rgba(212,175,55,0.35);border-radius:12px;padding:20px;margin:16px 0;
            box-shadow:0 4px 24px rgba(0,0,0,0.6);">
  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(212,175,55,0.2);padding-bottom:10px;margin-bottom:14px;">
    <div>
      <span style="font-family:'Orbitron',sans-serif;font-size:0.8rem;font-weight:900;color:#D4AF37;letter-spacing:2px;">
        🏛 FINCEPT QUANT TEAM · {symbol}
      </span>
      <div style="font-size:0.58rem;color:#666;margin-top:2px;letter-spacing:1px;">
        UNIFIED TRADE THESIS — Strategist + Risk + Microstructure + Flow
      </div>
    </div>
    <div style="text-align:right;">
      <div style="font-family:'Orbitron',sans-serif;font-size:1rem;font-weight:900;color:{score_color};">
        {'+' if final_score > 0 else ''}{final_score:.3f}
      </div>
      <div style="font-size:0.55rem;color:#666;">COMPOSITE SCORE</div>
    </div>
  </div>

  <!-- Verdict Banner -->
  <div style="background:rgba(0,0,0,0.4);border-radius:8px;padding:10px 14px;margin-bottom:14px;
              border-left:3px solid {score_color};font-size:0.85rem;font-weight:700;color:#fff;">
    {verdict}
    <div style="background:rgba(255,255,255,0.06);border-radius:4px;height:5px;margin-top:8px;overflow:hidden;">
      <div style="width:{bar_w}%;height:100%;background:{bar_bg};border-radius:4px;
                  float:{'right' if bar_dir=='left' else 'left'};"></div>
    </div>
  </div>

  <!-- 4-col analyst grid -->
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
    <!-- Quant Strategist -->
    <div style="background:rgba(0,176,255,0.07);border:1px solid rgba(0,176,255,0.2);border-radius:8px;padding:10px;text-align:center;">
      <div style="font-size:0.5rem;color:#00B0FF;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">⚡ Quant Signal</div>
      <div style="font-size:0.95rem;font-weight:900;color:{alpha_col};">{alpha_sig}</div>
      <div style="font-size:0.58rem;color:#666;margin-top:2px;">α {strat.get('alpha_score',0):.3f}</div>
    </div>
    <!-- Risk -->
    <div style="background:rgba(255,165,0,0.07);border:1px solid rgba(255,165,0,0.2);border-radius:8px;padding:10px;text-align:center;">
      <div style="font-size:0.5rem;color:#FFA500;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">🛡 Risk</div>
      <div style="font-size:0.95rem;font-weight:900;color:#FFA500;">½K {kelly_pct:.1f}%</div>
      <div style="font-size:0.58rem;color:#666;margin-top:2px;">pos ₹{pos_val:,.0f}</div>
    </div>
    <!-- Microstructure -->
    <div style="background:rgba(0,230,118,0.07);border:1px solid rgba(0,230,118,0.2);border-radius:8px;padding:10px;text-align:center;">
      <div style="font-size:0.5rem;color:#00E676;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">💧 Liquidity</div>
      <div style="font-size:0.95rem;font-weight:900;color:#00E676;">{liq_score:.2f}</div>
      <div style="font-size:0.58rem;color:#666;margin-top:2px;">{spread_bps:.1f}bps spread</div>
    </div>
    <!-- Options Flow -->
    <div style="background:rgba(230,0,70,0.07);border:1px solid rgba(230,0,70,0.2);border-radius:8px;padding:10px;text-align:center;">
      <div style="font-size:0.5rem;color:#FF1744;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">🐋 Flow</div>
      <div style="font-size:0.95rem;font-weight:900;color:#FF1744;">{flow_score:+.3f}</div>
      <div style="font-size:0.58rem;color:#666;margin-top:2px;">PCR {pcr:.2f}</div>
    </div>
  </div>

  <!-- Flow + Execution advice -->
  <div style="background:rgba(0,0,0,0.35);border-radius:7px;padding:9px 12px;font-size:0.65rem;color:#aaa;margin-bottom:10px;">
    <b style="color:#D4AF37;">🦁 Options Flow:</b> {flow_interp}<br>
    <b style="color:#00B0FF;">📋 Execution:</b> {exec_advice} &nbsp;·&nbsp;
    <b style="color:#888;">Sentiment:</b> <span style="color:#ccc;">{sent_int} ({sent_score:+.3f})</span>
  </div>

  <div style="font-size:0.5rem;color:#444;text-align:right;letter-spacing:1px;">
    FINCEPT PLATFORM · QUANT TEAM ORCHESTRATOR · ZERO ENGINE v4
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_nautilus_order_card(suggestion: dict | None = None):
    """Renders the Nautilus-inspired order suggestion card with TIF/contingency options."""
    import streamlit as st
    if not suggestion or not isinstance(suggestion, dict):
        return

    side        = suggestion.get("suggested_side", "NEUTRAL")
    blended     = suggestion.get("blended_score", 0.0)
    entry_px    = suggestion.get("entry_price_guide", 0.0)
    tp          = suggestion.get("take_profit", 0.0)
    sl          = suggestion.get("stop_loss", 0.0)
    entry_type  = suggestion.get("entry_type", "")
    contingency = suggestion.get("contingency", "OCO")
    tif_opts    = suggestion.get("tif_options", [])
    message     = suggestion.get("message", "")

    if side == "NEUTRAL":
        st.markdown(f"""
<div style="background:rgba(10,15,25,0.85);border:1px solid rgba(100,100,100,0.3);border-radius:10px;
            padding:14px 18px;margin:10px 0;font-size:0.72rem;color:#666;">
  ⚖️ <b style="color:#D4AF37;">NAUTILUS ORDER ENGINE</b> — {message or 'No directional signal. Wait for setup.'}
  <span style="float:right;color:#555;">Blended Score: {blended:.3f}</span>
</div>""", unsafe_allow_html=True)
        return

    side_color = "#00E676" if side == "BUY" else "#FF1744"
    side_icon  = "📈" if side == "BUY" else "📉"

    tif_badges = "".join(
        f'<span style="background:rgba(0,176,255,0.12);border:1px solid rgba(0,176,255,0.3);'
        f'border-radius:4px;padding:2px 7px;font-size:0.5rem;color:#00B0FF;margin:2px;">{t}</span>'
        for t in tif_opts
    )

    html = f"""
<div style="background:linear-gradient(135deg,rgba(8,18,35,0.97) 0%,rgba(4,10,22,0.99) 100%);
            border:1px solid {side_color}44;border-radius:12px;padding:18px;margin:14px 0;
            box-shadow:0 0 20px {side_color}18;">
  <!-- Header -->
  <div style="display:flex;justify-content:space-between;align-items:center;
              border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:9px;margin-bottom:12px;">
    <div>
      <span style="font-family:'Orbitron',sans-serif;font-size:0.78rem;font-weight:900;
                   color:#00B0FF;letter-spacing:2px;">
        ⚡ NAUTILUS ORDER ENGINE
      </span>
      <div style="font-size:0.55rem;color:#555;margin-top:2px;">
        IOC · FOK · GTC · GTD · DAY · OCO · OTO · OUO · ICEBERG · TRAILING STOP
      </div>
    </div>
    <div style="background:{side_color};color:#000;font-family:'Orbitron',sans-serif;
                font-weight:900;font-size:0.85rem;padding:6px 14px;border-radius:7px;">
      {side_icon} {side}
    </div>
  </div>

  <!-- Price grid -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;
              background:rgba(0,0,0,0.4);padding:12px;border-radius:8px;
              text-align:center;margin-bottom:12px;">
    <div>
      <div style="font-size:0.5rem;color:#888;text-transform:uppercase;margin-bottom:3px;">Entry Guide</div>
      <div style="font-size:1.0rem;font-weight:900;color:#fff;">{entry_px:,.2f}</div>
    </div>
    <div>
      <div style="font-size:0.5rem;color:#FF1744;text-transform:uppercase;margin-bottom:3px;">Stop Loss</div>
      <div style="font-size:1.0rem;font-weight:900;color:#FF1744;">{sl:,.2f}</div>
    </div>
    <div>
      <div style="font-size:0.5rem;color:#00E676;text-transform:uppercase;margin-bottom:3px;">Take Profit</div>
      <div style="font-size:1.0rem;font-weight:900;color:#00E676;">{tp:,.2f}</div>
    </div>
  </div>

  <!-- Entry type + contingency -->
  <div style="background:rgba(0,0,0,0.3);border-radius:7px;padding:8px 12px;font-size:0.62rem;
              color:#aaa;margin-bottom:10px;">
    <b style="color:#D4AF37;">Entry Strategy:</b> {entry_type}<br>
    <b style="color:#00B0FF;">Contingency Chain:</b> {contingency} &nbsp;·&nbsp;
    <b style="color:#888;">Signal Strength:</b> <span style="color:{side_color};">{abs(blended):.3f}</span>
  </div>

  <!-- TIF options strip -->
  <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
    <span style="font-size:0.5rem;color:#555;margin-right:4px;">TIF OPTIONS:</span>
    {tif_badges}
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_intermarket_card(intermarket: dict | None = None):
    """Renders the cross-asset inter-market signal card."""
    import streamlit as st
    if not intermarket or not isinstance(intermarket, dict) or "error" in intermarket:
        return

    score     = intermarket.get("net_intermarket_score", 0.0)
    direction = intermarket.get("direction", "FLAT OPEN EXPECTED")
    risk_tier = intermarket.get("risk_tier", "NORMAL")
    contribs  = intermarket.get("contributors", {})

    dir_color = "#00E676" if "UP" in direction else ("#FF1744" if "DOWN" in direction else "#D4AF37")
    risk_col  = "#FF1744" if "HIGH" in risk_tier else ("#D4AF37" if "ELEVATED" in risk_tier else "#00E676")

    def _bar(val, max_val=0.3):
        pct = min(100, abs(val) / max(max_val, 0.001) * 100)
        col = "#00E676" if val > 0 else "#FF1744"
        return (f'<div style="background:rgba(255,255,255,0.05);border-radius:3px;height:4px;overflow:hidden;margin-top:3px;">'
                f'<div style="width:{pct:.0f}%;height:100%;background:{col};border-radius:3px;'
                f'float:{"left" if val > 0 else "right"};"></div></div>')

    rows = ""
    labels = {"us_futures": "🇺🇸 US Futures", "crude_oil": "🛢 Crude Oil",
               "dxy_dollar": "💵 DXY Dollar", "vix_factor": "📊 VIX Factor"}
    for key, lbl in labels.items():
        v = contribs.get(key, 0.0)
        vc = "#00E676" if v > 0 else "#FF1744"
        rows += (f'<div style="display:flex;justify-content:space-between;align-items:center;'
                 f'padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
                 f'<span style="font-size:0.6rem;color:#888;">{lbl}</span>'
                 f'<span style="font-size:0.6rem;font-weight:700;color:{vc};">{v:+.4f}</span>'
                 f'</div>'
                 f'{_bar(v)}')

    html = f"""
<div style="background:rgba(8,18,32,0.9);border:1px solid rgba(0,176,255,0.25);
            border-radius:10px;padding:14px;margin:10px 0;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
    <span style="font-family:'Orbitron',sans-serif;font-size:0.7rem;font-weight:900;
                 color:#00B0FF;letter-spacing:1.5px;">🌐 INTER-MARKET ANALYSIS</span>
    <span style="background:{risk_col}22;border:1px solid {risk_col}55;color:{risk_col};
                 font-size:0.5rem;font-weight:700;padding:2px 8px;border-radius:4px;">{risk_tier}</span>
  </div>
  <div style="text-align:center;margin-bottom:12px;">
    <div style="font-size:0.65rem;color:#555;">Net Cross-Asset Signal</div>
    <div style="font-size:1.2rem;font-weight:900;color:{dir_color};">{score:+.4f}</div>
    <div style="font-size:0.7rem;color:{dir_color};font-weight:700;">{direction}</div>
  </div>
  <div style="background:rgba(0,0,0,0.3);border-radius:7px;padding:10px;">
    {rows}
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_options_greeks_card(greeks: dict | None = None):
    """Renders ATM Options Greeks card (Black-Scholes)."""
    import streamlit as st
    if not greeks or not isinstance(greeks, dict) or "error" in greeks:
        return

    html = f"""
<div style="background:rgba(8,18,32,0.9);border:1px solid rgba(212,175,55,0.25);
            border-radius:10px;padding:14px;margin:10px 0;">
  <div style="font-family:'Orbitron',sans-serif;font-size:0.7rem;font-weight:900;
              color:#D4AF37;letter-spacing:1.5px;margin-bottom:10px;">
    Δ OPTIONS GREEKS · ATM WEEKLY
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;">
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">CALL PRICE</div>
      <div style="font-size:0.9rem;font-weight:800;color:#00E676;">₹{greeks.get('call_price',0):.1f}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">PUT PRICE</div>
      <div style="font-size:0.9rem;font-weight:800;color:#FF1744;">₹{greeks.get('put_price',0):.1f}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">IV%</div>
      <div style="font-size:0.9rem;font-weight:800;color:#D4AF37;">{greeks.get('iv_pct',0):.1f}%</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">DELTA C/P</div>
      <div style="font-size:0.9rem;font-weight:800;color:#00B0FF;">
        {greeks.get('delta_call',0):.3f} / {greeks.get('delta_put',0):.3f}
      </div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">GAMMA</div>
      <div style="font-size:0.9rem;font-weight:800;color:#888;">{greeks.get('gamma',0):.6f}</div>
    </div>
    <div style="background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;">
      <div style="font-size:0.5rem;color:#888;">THETA/DAY</div>
      <div style="font-size:0.9rem;font-weight:800;color:#FF9800;">{greeks.get('theta_daily',0):.2f}</div>
    </div>
  </div>
  <div style="font-size:0.5rem;color:#444;text-align:right;margin-top:6px;">
    Spot {greeks.get('spot',0):,.0f} | Strike {greeks.get('strike',0):,.0f} | {greeks.get('days_to_exp',0):.0f} DTE
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)

