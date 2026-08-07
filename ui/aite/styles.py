"""
ZERO AITE — cyber palette + panel CSS.
Locked tokens match ui/cyber_theme.py / v11_components.

No fixed/sticky bottom bars — normal document scroll only.
"""
from __future__ import annotations

import streamlit as st

# ── Locked palette ──────────────────────────────────────────────────────────
VOID = "#000000"
PANEL = "#0a0a0a"
CRIMSON = "#E50914"
GOLD = "#D4AF37"
NEON = "#00ff88"
CYAN = "#00B0FF"
WHITE = "#ffffff"
MUTE = "#666666"
BORDER = "#1a1a1a"

AITE_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&family=Inter:wght@400;600&display=swap');

/* Kill sticky/fixed footer overlays that trap scroll past page end */
.stApp footer,
.stApp [data-testid="stBottomBlockContainer"],
.stApp [data-testid="stStatusWidget"],
.aite-fixed-bar,
.aite-sticky-footer,
.aite-bottom-bar {{
  position: static !important;
  bottom: auto !important;
  left: auto !important;
  right: auto !important;
  transform: none !important;
}}
/* Extra bottom breathing room so last controls aren't clipped */
section.main .block-container {{
  padding-bottom: 4rem !important;
  max-width: 100%;
}}
/* Never pin AITE chrome */
.aite-wrap, .aite-card, .aite-log, .aite-agent-node {{
  position: relative !important;
}}

.aite-wrap {{
  font-family: 'Inter', sans-serif;
  color: {WHITE};
}}
.aite-title {{
  font-family: 'Orbitron', sans-serif;
  font-weight: 900;
  font-size: 1.35rem;
  letter-spacing: 3px;
  color: {GOLD};
  text-transform: uppercase;
  margin: 0 0 4px 0;
  text-shadow: 0 0 18px rgba(212,175,55,0.35);
}}
.aite-sub {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.72rem;
  letter-spacing: 2px;
  color: {CRIMSON};
  text-transform: uppercase;
  margin-bottom: 14px;
}}
.aite-card {{
  background: linear-gradient(145deg, {PANEL} 0%, {VOID} 100%);
  border: 1px solid {MUTE}44;
  border-radius: 4px;
  padding: 14px 16px;
  margin: 8px 0 14px 0;
  box-shadow: inset 0 0 36px {VOID}, 0 0 12px {MUTE}18;
}}
.aite-card::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, {GOLD}, {CRIMSON}, transparent);
  opacity: 0.9;
}}
.aite-label {{
  font-family: 'Orbitron', sans-serif;
  font-size: 0.62rem;
  font-weight: 900;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: {GOLD};
  margin: 12px 0 8px 0;
}}
.aite-pill {{
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(0,0,0,0.45);
  border: 1px solid {MUTE}55;
  border-radius: 6px;
  padding: 6px 12px;
  font-family: 'Orbitron', sans-serif;
  font-size: 0.62rem;
  font-weight: 900;
  letter-spacing: 2px;
}}
.aite-dot {{
  width: 8px; height: 8px; border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 8px currentColor;
  animation: aite-dot-pulse 1.4s ease-in-out infinite;
}}
@keyframes aite-dot-pulse {{
  0%, 100% {{ transform: scale(1); opacity: 1; }}
  50% {{ transform: scale(0.72); opacity: 0.55; }}
}}
.aite-flow-line {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.68rem;
  line-height: 1.35;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: {NEON};
  border-left: 2px solid {CRIMSON}66;
  padding-left: 8px;
  margin: 1px 0;
  animation: aite-flow-in 0.45s ease-out both;
}}
.aite-flow-line.done {{ color: {NEON}; border-left-color: {NEON}; }}
.aite-flow-line.active {{ color: {CYAN}; border-left-color: {CYAN};
  box-shadow: inset 40px 0 24px -24px rgba(0,176,255,0.25); }}
.aite-flow-line.pending {{ color: {MUTE}; border-left-color: {BORDER}; }}
.aite-flow-line.fail {{ color: {CRIMSON}; border-left-color: {CRIMSON}; }}
@keyframes aite-flow-in {{
  from {{ opacity: 0; transform: translateX(-10px); }}
  to   {{ opacity: 1; transform: translateX(0); }}
}}
.aite-log {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.7rem;
  max-height: 220px;
  overflow-y: auto;
  background: {VOID};
  border: 1px solid {BORDER};
  padding: 10px 12px;
  border-radius: 3px;
}}
.aite-log-row {{ margin: 2px 0; color: #aaa; }}
.aite-log-row .ts {{ color: {MUTE}; }}
.aite-log-row.info {{ color: {CYAN}; }}
.aite-log-row.warn {{ color: {GOLD}; }}
.aite-log-row.error {{ color: {CRIMSON}; }}
.aite-agent-node {{
  border: 1px solid {BORDER};
  border-left: 3px solid {GOLD};
  background: {PANEL};
  padding: 10px 12px;
  margin: 6px 0;
  border-radius: 3px;
  transition: border-color 0.25s, box-shadow 0.25s;
}}
.aite-agent-node.thinking {{ border-left-color: {CYAN}; box-shadow: 0 0 12px rgba(0,176,255,0.15); }}
.aite-agent-node.working  {{ border-left-color: {NEON}; box-shadow: 0 0 12px rgba(0,255,136,0.15); }}
.aite-agent-node.done     {{ border-left-color: {GOLD}; }}
.aite-agent-node.error    {{ border-left-color: {CRIMSON}; }}
.aite-agent-node.idle     {{ border-left-color: {MUTE}; opacity: 0.75; }}
.aite-agent-role {{
  font-family: 'Orbitron', sans-serif;
  font-size: 0.58rem;
  letter-spacing: 1.5px;
  color: {GOLD};
  text-transform: uppercase;
}}
.aite-agent-msg {{
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.72rem;
  color: #ccc;
  margin-top: 4px;
}}
.aite-metric {{
  font-family: 'Orbitron', sans-serif;
  font-size: 1.1rem;
  color: {NEON};
}}
/* iframe hosts — in-flow only, no sticky chrome */
iframe {{
  display: block;
  max-width: 100%;
}}
</style>
"""


def inject_aite_styles() -> None:
    """Inject AITE panel CSS once per session render."""
    try:
        st.markdown(AITE_CSS, unsafe_allow_html=True)
    except Exception:
        pass


def status_pill(label: str, color: str = NEON) -> str:
    return (
        f"<span class='aite-pill' style='border-color:{color}55;color:{color};'>"
        f"<span class='aite-dot' style='background:{color};color:{color};'></span>"
        f"{label}</span>"
    )
