"""Cyber HUD Fincept / Nautilus / Intermarket / Greeks cards — ZERO UI redesign."""

from __future__ import annotations


_PAL = {
    "bg": "#000",
    "panel": "#0a0a0a",
    "red": "#E50914",
    "gold": "#D4AF37",
    "neon": "#00ff88",
    "green": "#00E676",
    "blue": "#00B0FF",
    "white": "#fff",
    "muted": "#666",
}

_HUD_CSS = """
<style>
@keyframes zf-holo-scan{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes zf-bar-grow{from{width:0}to{width:var(--zf-w)}}
@keyframes zf-pulse-glow{0%,100%{box-shadow:0 0 6px var(--zf-glow),0 0 14px var(--zf-glow)}50%{box-shadow:0 0 12px var(--zf-glow),0 0 28px var(--zf-glow)}}
@keyframes zf-stamp{0%{transform:scale(1.35);opacity:0}60%{transform:scale(0.96);opacity:1}100%{transform:scale(1);opacity:1}}
.zf-hud{background:linear-gradient(160deg,#0a0a0a 0%,#000 55%,#0a0a0a 100%);border:1px solid rgba(0,176,255,0.28);
  border-radius:4px;padding:18px;margin:14px 0;position:relative;overflow:hidden;
  box-shadow:inset 0 0 40px rgba(0,176,255,0.04),0 0 24px rgba(0,0,0,0.8)}
.zf-hud::before{content:'';position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,255,136,0.015) 3px);
  opacity:.55}
.zf-hud-title{font-family:'Orbitron',sans-serif;font-size:0.78rem;font-weight:900;letter-spacing:2.5px;
  color:#D4AF37;text-shadow:0 0 12px rgba(212,175,55,0.35)}
.zf-holo-track{height:7px;border-radius:2px;background:rgba(255,255,255,0.06);overflow:hidden;margin-top:8px;
  border:1px solid rgba(255,255,255,0.06)}
.zf-holo-fill{height:100%;border-radius:2px;
  background:linear-gradient(90deg,#00B0FF,#00ff88,#D4AF37,#00B0FF);background-size:200% 100%;
  animation:zf-holo-scan 2.8s linear infinite,zf-bar-grow .9s ease-out forwards;
  box-shadow:0 0 10px rgba(0,255,136,0.55)}
.zf-stamp{display:inline-block;font-family:'Orbitron',sans-serif;font-weight:900;font-size:0.9rem;
  letter-spacing:3px;padding:8px 18px;border:2px solid;border-radius:2px;animation:zf-stamp .45s ease-out;
  text-transform:uppercase}
.zf-stamp-buy{color:#00ff88;border-color:#00ff88;background:rgba(0,255,136,0.08);
  --zf-glow:#00ff88;box-shadow:0 0 16px rgba(0,255,136,0.45),inset 0 0 12px rgba(0,255,136,0.12);
  animation:zf-stamp .45s ease-out,zf-pulse-glow 1.6s ease-in-out infinite}
.zf-stamp-sell{color:#E50914;border-color:#E50914;background:rgba(229,9,20,0.1);
  --zf-glow:#E50914;box-shadow:0 0 16px rgba(229,9,20,0.5),inset 0 0 12px rgba(229,9,20,0.15);
  animation:zf-stamp .45s ease-out,zf-pulse-glow 1.6s ease-in-out infinite}
.zf-chip{display:inline-block;padding:3px 9px;margin:2px;font-size:0.5rem;font-family:'Orbitron',sans-serif;
  letter-spacing:1px;color:#00B0FF;border:1px solid rgba(0,176,255,0.55);border-radius:3px;
  background:rgba(0,176,255,0.08);box-shadow:0 0 8px rgba(0,176,255,0.35);--zf-glow:#00B0FF;
  animation:zf-pulse-glow 2.2s ease-in-out infinite}
.zf-contrib-track{background:rgba(255,255,255,0.05);height:5px;border-radius:2px;overflow:hidden;margin-top:4px}
.zf-contrib-fill{height:100%;border-radius:2px;animation:zf-bar-grow .85s ease-out forwards}
.zf-hex{clip-path:polygon(50% 0%,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%);
  background:linear-gradient(160deg,#0a0a0a,#000);border:none;padding:18px 8px;text-align:center;
  position:relative;min-height:78px;display:flex;flex-direction:column;justify-content:center;align-items:center}
.zf-hex-wrap{background:linear-gradient(135deg,rgba(212,175,55,0.45),rgba(0,176,255,0.35),rgba(0,255,136,0.3));
  clip-path:polygon(50% 0%,93% 25%,93% 75%,50% 100%,7% 75%,7% 25%);padding:1.5px}
.zf-cell{background:rgba(10,10,10,0.9);border:1px solid rgba(0,176,255,0.2);border-radius:3px;
  padding:10px;text-align:center}
.zf-foot{font-size:0.48rem;color:#666;text-align:right;letter-spacing:1.5px;margin-top:10px}
</style>
"""


def _ensure_css():
    import streamlit as st
    if not st.session_state.get("_zf_fincept_hud_css"):
        st.markdown(_HUD_CSS, unsafe_allow_html=True)
        st.session_state["_zf_fincept_hud_css"] = True


def render_fincept_thesis_card(thesis: dict | None = None):
    """Renders the Fincept Platform Quant Team Unified Trade Thesis card (cyber HUD)."""
    import streamlit as st
    if not thesis or not isinstance(thesis, dict) or "error" in thesis:
        return
    _ensure_css()

    symbol = thesis.get("symbol", "INDEX")
    final_score = thesis.get("final_score", 0.0) or 0.0
    verdict = thesis.get("verdict", "⚖️ NEUTRAL")
    strat = thesis.get("quant_strategy") or {}
    risk = thesis.get("risk_analysis") or {}
    micro = thesis.get("microstructure") or {}
    sent = thesis.get("sentiment") or {}
    opt_flow = thesis.get("options_flow") or {}

    score_color = "#00E676" if final_score > 0.2 else ("#E50914" if final_score < -0.2 else "#D4AF37")
    bar_w = int(min(100, abs(final_score) * 100))
    bar_dir = "right" if final_score > 0 else "left"
    bar_bg = "#00ff88" if final_score > 0 else "#E50914"

    alpha_sig = strat.get("signal", "FLAT")
    alpha_col = "#00E676" if alpha_sig == "LONG" else ("#E50914" if alpha_sig == "SHORT" else "#666")
    kelly_pct = risk.get("kelly_pct", 0.0) or 0.0
    pos_val = risk.get("position_value", 0.0) or 0.0
    liq_score = micro.get("liquidity_score", 0.0) or 0.0
    exec_advice = micro.get("execution_advice", "EXECUTE")
    spread_bps = micro.get("spread_bps", 0.0) or 0.0
    flow_score = opt_flow.get("flow_score", 0.0) or 0.0
    flow_interp = opt_flow.get("interpretation", "") or ""
    pcr = opt_flow.get("pcr", 1.0) or 1.0
    sent_score = sent.get("composite_score", 0.0) or 0.0
    sent_int = sent.get("intensity", "neutral")
    alpha_score = strat.get("alpha_score", 0) or 0

    html = f"""
<div class="zf-hud">
  <div style="display:flex;justify-content:space-between;align-items:center;
              border-bottom:1px solid rgba(212,175,55,0.25);padding-bottom:10px;margin-bottom:14px;">
    <div>
      <div class="zf-hud-title">FINCEPT QUANT TEAM · {symbol}</div>
      <div style="font-size:0.55rem;color:#666;margin-top:3px;letter-spacing:1px;">
        UNIFIED TRADE THESIS — Strategist + Risk + Microstructure + Flow
      </div>
    </div>
    <div style="text-align:right;">
      <div style="font-family:'Orbitron',sans-serif;font-size:1.05rem;font-weight:900;color:{score_color};
                  text-shadow:0 0 14px {score_color}88;">
        {'+' if final_score > 0 else ''}{final_score:.3f}
      </div>
      <div style="font-size:0.5rem;color:#666;letter-spacing:1px;">COMPOSITE SCORE</div>
    </div>
  </div>

  <div style="background:rgba(0,0,0,0.55);border-radius:3px;padding:10px 14px;margin-bottom:14px;
              border-left:3px solid {score_color};font-size:0.82rem;font-weight:700;color:#fff;">
    {verdict}
    <div class="zf-holo-track">
      <div class="zf-holo-fill" style="--zf-w:{bar_w}%;width:{bar_w}%;
           background:linear-gradient(90deg,#00B0FF,{bar_bg},#D4AF37);
           float:{'right' if bar_dir == 'left' else 'left'};"></div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
    <div class="zf-cell" style="border-color:rgba(0,176,255,0.35);">
      <div style="font-size:0.48rem;color:#00B0FF;letter-spacing:1.5px;margin-bottom:4px;">QUANT SIGNAL</div>
      <div style="font-size:0.95rem;font-weight:900;color:{alpha_col};text-shadow:0 0 8px {alpha_col}66;">{alpha_sig}</div>
      <div style="font-size:0.55rem;color:#666;margin-top:2px;">α {alpha_score:.3f}</div>
    </div>
    <div class="zf-cell" style="border-color:rgba(212,175,55,0.35);">
      <div style="font-size:0.48rem;color:#D4AF37;letter-spacing:1.5px;margin-bottom:4px;">RISK</div>
      <div style="font-size:0.95rem;font-weight:900;color:#D4AF37;">½K {kelly_pct:.1f}%</div>
      <div style="font-size:0.55rem;color:#666;margin-top:2px;">pos ₹{pos_val:,.0f}</div>
    </div>
    <div class="zf-cell" style="border-color:rgba(0,230,118,0.35);">
      <div style="font-size:0.48rem;color:#00E676;letter-spacing:1.5px;margin-bottom:4px;">LIQUIDITY</div>
      <div style="font-size:0.95rem;font-weight:900;color:#00E676;">{liq_score:.2f}</div>
      <div style="font-size:0.55rem;color:#666;margin-top:2px;">{spread_bps:.1f}bps spread</div>
    </div>
    <div class="zf-cell" style="border-color:rgba(229,9,20,0.35);">
      <div style="font-size:0.48rem;color:#E50914;letter-spacing:1.5px;margin-bottom:4px;">FLOW</div>
      <div style="font-size:0.95rem;font-weight:900;color:#E50914;">{flow_score:+.3f}</div>
      <div style="font-size:0.55rem;color:#666;margin-top:2px;">PCR {pcr:.2f}</div>
    </div>
  </div>

  <div style="background:rgba(0,0,0,0.45);border-radius:3px;padding:9px 12px;font-size:0.62rem;color:#666;margin-bottom:8px;
              border:1px solid rgba(255,255,255,0.04);">
    <b style="color:#D4AF37;">OPTIONS FLOW:</b> <span style="color:#fff;">{flow_interp}</span><br>
    <b style="color:#00B0FF;">EXECUTION:</b> <span style="color:#fff;">{exec_advice}</span> &nbsp;·&nbsp;
    <b style="color:#666;">SENTIMENT:</b> <span style="color:#ccc;">{sent_int} ({sent_score:+.3f})</span>
  </div>
  <div class="zf-foot">FINCEPT PLATFORM · QUANT TEAM ORCHESTRATOR · ZERO ENGINE v4</div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_nautilus_order_card(suggestion: dict | None = None):
    """Renders the Nautilus-inspired order suggestion card with TIF/contingency (cyber HUD)."""
    import streamlit as st
    if not suggestion or not isinstance(suggestion, dict):
        return
    _ensure_css()

    side = suggestion.get("suggested_side", "NEUTRAL")
    blended = suggestion.get("blended_score", 0.0) or 0.0
    entry_px = suggestion.get("entry_price_guide", 0.0) or 0.0
    tp = suggestion.get("take_profit", 0.0) or 0.0
    sl = suggestion.get("stop_loss", 0.0) or 0.0
    entry_type = suggestion.get("entry_type", "") or ""
    contingency = suggestion.get("contingency", "OCO") or "OCO"
    tif_opts = suggestion.get("tif_options", []) or []
    message = suggestion.get("message", "") or ""

    if side == "NEUTRAL":
        st.markdown(f"""
<div class="zf-hud" style="border-color:rgba(102,102,102,0.35);padding:14px 18px;">
  <span class="zf-hud-title" style="font-size:0.7rem;">NAUTILUS ORDER ENGINE</span>
  <span style="font-size:0.68rem;color:#666;margin-left:10px;">{message or 'No directional signal. Wait for setup.'}</span>
  <span style="float:right;color:#666;font-size:0.55rem;letter-spacing:1px;">Blended {blended:.3f}</span>
</div>""", unsafe_allow_html=True)
        return

    stamp_cls = "zf-stamp zf-stamp-buy" if side == "BUY" else "zf-stamp zf-stamp-sell"
    side_color = "#00ff88" if side == "BUY" else "#E50914"

    tif_badges = "".join(f'<span class="zf-chip">{t}</span>' for t in tif_opts)

    html = f"""
<div class="zf-hud" style="border-color:{side_color}55;box-shadow:0 0 28px {side_color}22,inset 0 0 40px rgba(0,176,255,0.04);">
  <div style="display:flex;justify-content:space-between;align-items:center;
              border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:10px;margin-bottom:14px;">
    <div>
      <div class="zf-hud-title" style="color:#00B0FF;text-shadow:0 0 12px rgba(0,176,255,0.4);">NAUTILUS ORDER ENGINE</div>
      <div style="font-size:0.5rem;color:#666;margin-top:3px;letter-spacing:1px;">
        IOC · FOK · GTC · GTD · DAY · OCO · OTO · OUO · ICEBERG · TRAILING STOP
      </div>
    </div>
    <div class="{stamp_cls}">{side}</div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;background:rgba(0,0,0,0.55);
              padding:14px;border-radius:3px;text-align:center;margin-bottom:12px;
              border:1px solid rgba(255,255,255,0.05);">
    <div>
      <div style="font-size:0.48rem;color:#666;letter-spacing:1.5px;margin-bottom:4px;">ENTRY GUIDE</div>
      <div style="font-size:1.05rem;font-weight:900;color:#fff;font-family:'Orbitron',sans-serif;">{entry_px:,.2f}</div>
    </div>
    <div>
      <div style="font-size:0.48rem;color:#E50914;letter-spacing:1.5px;margin-bottom:4px;">STOP LOSS</div>
      <div style="font-size:1.05rem;font-weight:900;color:#E50914;font-family:'Orbitron',sans-serif;
                  text-shadow:0 0 10px rgba(229,9,20,0.45);">{sl:,.2f}</div>
    </div>
    <div>
      <div style="font-size:0.48rem;color:#00E676;letter-spacing:1.5px;margin-bottom:4px;">TAKE PROFIT</div>
      <div style="font-size:1.05rem;font-weight:900;color:#00E676;font-family:'Orbitron',sans-serif;
                  text-shadow:0 0 10px rgba(0,230,118,0.45);">{tp:,.2f}</div>
    </div>
  </div>

  <div style="background:rgba(0,0,0,0.4);border-radius:3px;padding:8px 12px;font-size:0.6rem;
              color:#666;margin-bottom:12px;border:1px solid rgba(255,255,255,0.04);">
    <b style="color:#D4AF37;">Entry Strategy:</b> <span style="color:#fff;">{entry_type}</span><br>
    <b style="color:#00B0FF;">Contingency Chain:</b> <span style="color:#fff;">{contingency}</span> &nbsp;·&nbsp;
    <b style="color:#666;">Signal Strength:</b> <span style="color:{side_color};">{abs(blended):.3f}</span>
  </div>

  <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center;">
    <span style="font-size:0.48rem;color:#666;margin-right:6px;letter-spacing:1px;">TIF OPTIONS:</span>
    {tif_badges}
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_intermarket_card(intermarket: dict | None = None):
    """Renders the cross-asset inter-market signal card (cyber HUD)."""
    import streamlit as st
    if not intermarket or not isinstance(intermarket, dict) or "error" in intermarket:
        return
    _ensure_css()

    score = intermarket.get("net_intermarket_score", 0.0) or 0.0
    direction = intermarket.get("direction", "FLAT OPEN EXPECTED") or "FLAT OPEN EXPECTED"
    risk_tier = intermarket.get("risk_tier", "NORMAL") or "NORMAL"
    contribs = intermarket.get("contributors", {}) or {}

    dir_color = "#00E676" if "UP" in direction else ("#E50914" if "DOWN" in direction else "#D4AF37")
    risk_col = "#E50914" if "HIGH" in risk_tier else ("#D4AF37" if "ELEVATED" in risk_tier else "#00E676")

    def _bar(val, max_val=0.3):
        pct = min(100, abs(val) / max(max_val, 0.001) * 100)
        col = "#00ff88" if val > 0 else "#E50914"
        flt = "left" if val > 0 else "right"
        return (
            f'<div class="zf-contrib-track">'
            f'<div class="zf-contrib-fill" style="--zf-w:{pct:.0f}%;width:{pct:.0f}%;'
            f'background:{col};box-shadow:0 0 8px {col}88;float:{flt};"></div></div>'
        )

    rows = ""
    labels = {
        "us_futures": "US Futures",
        "crude_oil": "Crude Oil",
        "dxy_dollar": "DXY Dollar",
        "vix_factor": "VIX Factor",
    }
    for key, lbl in labels.items():
        v = contribs.get(key, 0.0) or 0.0
        vc = "#00ff88" if v > 0 else "#E50914"
        rows += (
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);">'
            f'<span style="font-size:0.58rem;color:#666;letter-spacing:1px;">{lbl}</span>'
            f'<span style="font-size:0.58rem;font-weight:700;color:{vc};font-family:\'Orbitron\',sans-serif;">{v:+.4f}</span>'
            f'</div>{_bar(v)}'
        )

    html = f"""
<div class="zf-hud" style="border-color:rgba(0,176,255,0.35);">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <span class="zf-hud-title" style="color:#00B0FF;text-shadow:0 0 12px rgba(0,176,255,0.4);">INTER-MARKET ANALYSIS</span>
    <span style="background:{risk_col}22;border:1px solid {risk_col}66;color:{risk_col};
                 font-size:0.48rem;font-weight:700;padding:3px 10px;border-radius:2px;
                 letter-spacing:1.5px;box-shadow:0 0 8px {risk_col}44;">{risk_tier}</span>
  </div>
  <div style="text-align:center;margin-bottom:14px;">
    <div style="font-size:0.55rem;color:#666;letter-spacing:1.5px;">NET CROSS-ASSET SIGNAL</div>
    <div style="font-size:1.35rem;font-weight:900;color:{dir_color};font-family:'Orbitron',sans-serif;
                text-shadow:0 0 16px {dir_color}66;">{score:+.4f}</div>
    <div style="font-size:0.72rem;color:{dir_color};font-weight:700;letter-spacing:1px;">{direction}</div>
    <div class="zf-holo-track" style="max-width:220px;margin:10px auto 0;">
      <div class="zf-holo-fill" style="--zf-w:{min(100, abs(score) / 0.3 * 100):.0f}%;
           width:{min(100, abs(score) / 0.3 * 100):.0f}%;"></div>
    </div>
  </div>
  <div style="background:rgba(0,0,0,0.45);border-radius:3px;padding:10px;border:1px solid rgba(0,176,255,0.12);">
    {rows}
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_options_greeks_card(greeks: dict | None = None):
    """Renders ATM Options Greeks card — hexagonal metric tiles (cyber HUD)."""
    import streamlit as st
    if not greeks or not isinstance(greeks, dict) or "error" in greeks:
        return
    _ensure_css()

    call_price = greeks.get("call_price", 0) or 0
    put_price = greeks.get("put_price", 0) or 0
    iv_pct = greeks.get("iv_pct", 0) or 0
    delta_call = greeks.get("delta_call", 0) or 0
    delta_put = greeks.get("delta_put", 0) or 0
    gamma = greeks.get("gamma", 0) or 0
    theta_daily = greeks.get("theta_daily", 0) or 0
    spot = greeks.get("spot", 0) or 0
    strike = greeks.get("strike", 0) or 0
    dte = greeks.get("days_to_exp", 0) or 0

    tiles = [
        ("CALL PRICE", f"₹{call_price:.1f}", "#00E676"),
        ("PUT PRICE", f"₹{put_price:.1f}", "#E50914"),
        ("IV%", f"{iv_pct:.1f}%", "#D4AF37"),
        ("DELTA C/P", f"{delta_call:.3f} / {delta_put:.3f}", "#00B0FF"),
        ("GAMMA", f"{gamma:.6f}", "#00ff88"),
        ("THETA/DAY", f"{theta_daily:.2f}", "#D4AF37"),
    ]

    hex_html = ""
    for lbl, val, col in tiles:
        hex_html += f"""
    <div class="zf-hex-wrap">
      <div class="zf-hex">
        <div style="font-size:0.42rem;color:#666;letter-spacing:1.5px;margin-bottom:4px;">{lbl}</div>
        <div style="font-size:0.78rem;font-weight:800;color:{col};font-family:'Orbitron',sans-serif;
                    text-shadow:0 0 10px {col}66;line-height:1.2;">{val}</div>
      </div>
    </div>"""

    html = f"""
<div class="zf-hud" style="border-color:rgba(212,175,55,0.35);">
  <div class="zf-hud-title" style="margin-bottom:14px;">OPTIONS GREEKS · ATM WEEKLY</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;justify-items:center;">
    {hex_html}
  </div>
  <div class="zf-foot">
    Spot {spot:,.0f} | Strike {strike:,.0f} | {dte:.0f} DTE
  </div>
</div>"""
    st.markdown(html, unsafe_allow_html=True)
