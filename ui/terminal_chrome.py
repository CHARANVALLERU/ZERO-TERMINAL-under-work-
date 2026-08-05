"""
ZERO Terminal Chrome — cyber HUD wrappers for the TRADING TERMINAL tab.

Pure presentation. No engine logic. Locked palette only.
"""
from __future__ import annotations

import html
import streamlit as st

# Locked palette
_BLACK = "#000"
_SURFACE = "#0a0a0a"
_RED = "#E50914"
_GOLD = "#D4AF37"
_GREEN = "#00ff88"
_GREEN2 = "#00E676"
_CYAN = "#00B0FF"
_WHITE = "#fff"
_MUTED = "#666"

_FONT = "'Orbitron', sans-serif"


def render_terminal_hero() -> None:
    """Big ZERO // QUANTUM TRADING TERMINAL cyber hero with glitch subtitle & status chips."""
    st.markdown(
        f"""
<style>
@keyframes zt-glitch {{
  0%,100% {{ clip-path: inset(0 0 0 0); transform: translate(0); }}
  20% {{ clip-path: inset(12% 0 55% 0); transform: translate(-2px,1px); }}
  40% {{ clip-path: inset(48% 0 18% 0); transform: translate(2px,-1px); }}
  60% {{ clip-path: inset(72% 0 6% 0); transform: translate(-1px,2px); }}
  80% {{ clip-path: inset(28% 0 42% 0); transform: translate(1px,-2px); }}
}}
@keyframes zt-scan {{
  0% {{ background-position: 0 0; }}
  100% {{ background-position: 0 40px; }}
}}
@keyframes zt-pulse {{
  0%,100% {{ opacity: 1; box-shadow: 0 0 6px {_GREEN}; }}
  50% {{ opacity: 0.45; box-shadow: 0 0 2px {_GREEN}; }}
}}
.zt-hero {{
  position: relative;
  background: linear-gradient(180deg, {_SURFACE} 0%, {_BLACK} 100%);
  border: 1px solid {_GOLD}44;
  border-left: 3px solid {_RED};
  padding: 18px 20px 14px;
  margin: 0 0 16px 0;
  overflow: hidden;
}}
.zt-hero::before {{
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg,
    transparent,
    transparent 2px,
    {_CYAN}08 2px,
    {_CYAN}08 3px
  );
  animation: zt-scan 2.4s linear infinite;
  pointer-events: none;
}}
.zt-hero-brand {{
  font-family: {_FONT};
  font-weight: 900;
  font-size: 1.55rem;
  letter-spacing: 3px;
  color: {_WHITE};
  margin: 0;
  line-height: 1.15;
  position: relative;
  z-index: 1;
}}
.zt-hero-brand span.zt-zero {{ color: {_RED}; }}
.zt-hero-brand span.zt-sep {{ color: {_GOLD}; margin: 0 6px; }}
.zt-hero-brand span.zt-title {{ color: {_WHITE}; }}
.zt-glitch {{
  font-family: {_FONT};
  font-size: 0.68rem;
  letter-spacing: 2.5px;
  color: {_CYAN};
  margin: 8px 0 12px;
  position: relative;
  z-index: 1;
  text-transform: uppercase;
}}
.zt-glitch::after {{
  content: attr(data-text);
  position: absolute;
  left: 2px;
  top: 0;
  color: {_RED};
  opacity: 0.55;
  animation: zt-glitch 2.8s infinite linear alternate-reverse;
  pointer-events: none;
}}
.zt-scan-strip {{
  height: 2px;
  margin: 0 0 12px;
  background: linear-gradient(90deg, transparent, {_GREEN}, {_GOLD}, {_CYAN}, transparent);
  position: relative;
  z-index: 1;
}}
.zt-chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  position: relative;
  z-index: 1;
}}
.zt-chip {{
  font-family: {_FONT};
  font-size: 0.55rem;
  font-weight: 800;
  letter-spacing: 1.5px;
  padding: 3px 10px;
  border: 1px solid {_MUTED};
  background: {_BLACK};
  color: {_MUTED};
}}
.zt-chip.live {{
  color: {_GREEN};
  border-color: {_GREEN}88;
}}
.zt-chip.live::before {{
  content: '';
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: {_GREEN};
  margin-right: 6px;
  vertical-align: middle;
  animation: zt-pulse 1.4s ease-in-out infinite;
}}
.zt-chip.local {{
  color: {_CYAN};
  border-color: {_CYAN}66;
}}
.zt-chip.armed {{
  color: {_GOLD};
  border-color: {_GOLD}66;
}}
</style>
<div class="zt-hero">
  <p class="zt-hero-brand">
    <span class="zt-zero">ZERO</span><span class="zt-sep">//</span><span class="zt-title">QUANTUM TRADING TERMINAL</span>
  </p>
  <p class="zt-glitch" data-text="SECURE CHANNEL · SIGNAL FEED ONLINE · HUD MODE ACTIVE">
    SECURE CHANNEL · SIGNAL FEED ONLINE · HUD MODE ACTIVE
  </p>
  <div class="zt-scan-strip"></div>
  <div class="zt-chips">
    <span class="zt-chip live">LIVE</span>
    <span class="zt-chip local">LOCAL</span>
    <span class="zt-chip armed">ARMED-OFF</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_section_header(code: str, title: str, accent: str = "#D4AF37") -> None:
    """Numbered section header, e.g. code='01', title='MULTI-TIMEFRAME XGBOOST'."""
    safe_code = html.escape(str(code))
    safe_title = html.escape(str(title).upper())
    safe_accent = html.escape(accent) if accent.startswith("#") else _GOLD
    st.markdown(
        f"""
<div style="
  display:flex;align-items:center;gap:12px;
  margin:18px 0 10px;padding:8px 0 8px 0;
  border-bottom:1px solid {safe_accent}33;
">
  <span style="
    font-family:{_FONT};font-size:0.7rem;font-weight:900;
    letter-spacing:2px;color:{_BLACK};background:{safe_accent};
    padding:3px 8px;min-width:32px;text-align:center;
  ">{safe_code}</span>
  <span style="
    font-family:{_FONT};font-size:0.85rem;font-weight:800;
    letter-spacing:2px;color:{_WHITE};
  ">{safe_title}</span>
  <span style="
    flex:1;height:1px;
    background:linear-gradient(90deg,{safe_accent}66,transparent);
  "></span>
  <span style="
    font-family:{_FONT};font-size:0.5rem;letter-spacing:1.5px;color:{_MUTED};
  ">SEC</span>
</div>
""",
        unsafe_allow_html=True,
    )


def wrap_expander_hint(title: str) -> str:
    """Return a styled title string for st.expander (plain text; Streamlit strips HTML)."""
    clean = " ".join(str(title).strip().upper().split())
    return f"▸ {clean}"


def render_control_deck_divider(label: str = "V1.1 CONTROL DECK") -> None:
    """Horizontal cyber divider marking the control deck zone."""
    safe = html.escape(str(label).upper())
    st.markdown(
        f"""
<div style="
  display:flex;align-items:center;gap:14px;
  margin:22px 0 14px;padding:0;
">
  <span style="flex:1;height:1px;background:linear-gradient(90deg,transparent,{_RED});"></span>
  <span style="
    font-family:{_FONT};font-size:0.62rem;font-weight:900;
    letter-spacing:3px;color:{_GOLD};
    border:1px solid {_GOLD}55;padding:4px 14px;
    background:{_SURFACE};
  ">{safe}</span>
  <span style="flex:1;height:1px;background:linear-gradient(90deg,{_CYAN},transparent);"></span>
</div>
""",
        unsafe_allow_html=True,
    )


def inject_terminal_micro_interactions() -> None:
    """CSS (+ light JS) for expander hover glow on the trading terminal."""
    st.markdown(
        f"""
<style>
/* Terminal expander chrome */
div[data-testid="stExpander"] {{
  border: 1px solid {_MUTED}55 !important;
  background: {_SURFACE} !important;
  border-radius: 2px !important;
  margin-bottom: 8px !important;
  transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
}}
div[data-testid="stExpander"]:hover {{
  border-color: {_GOLD}99 !important;
  box-shadow: 0 0 12px {_GOLD}22, inset 0 0 20px {_CYAN}08 !important;
}}
div[data-testid="stExpander"] details summary {{
  font-family: {_FONT} !important;
  letter-spacing: 1.2px !important;
  color: {_WHITE} !important;
}}
div[data-testid="stExpander"] details[open] {{
  border-left: 2px solid {_GREEN2} !important;
}}
div[data-testid="stExpander"] details[open] summary {{
  color: {_GREEN} !important;
}}
</style>
<script>
(function() {{
  try {{
    const nodes = window.parent.document.querySelectorAll('[data-testid="stExpander"]');
    nodes.forEach(function(el) {{
      if (el.dataset.ztGlow) return;
      el.dataset.ztGlow = '1';
      el.addEventListener('mouseenter', function() {{
        el.style.borderColor = '{_GOLD}';
      }});
      el.addEventListener('mouseleave', function() {{
        el.style.borderColor = '';
      }});
    }});
  }} catch (e) {{ /* sandbox / no parent */ }}
}})();
</script>
""",
        unsafe_allow_html=True,
    )
