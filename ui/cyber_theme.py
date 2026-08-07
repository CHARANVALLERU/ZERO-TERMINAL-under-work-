"""ZERO Trading Terminal — Cyber / Hacking Theme (Agent 1).

Exports:
  CYBER_CSS                  module-level stylesheet string
  apply_cyber_theme()        inject <style> via st.markdown
  inject_reveal_boot_script() IntersectionObserver staggered reveals

Locked palette + class names — do not rename consumers' classes.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# CSS (also mirrored at ui/static/cyber_theme.css)
# ---------------------------------------------------------------------------

_CSS_PATH = Path(__file__).resolve().parent / "static" / "cyber_theme.css"

_FALLBACK_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;800&display=swap');

:root {
  --zero-black: #000000;
  --zero-red: #E50914;
  --zero-white: #ffffff;
  --zero-gold: #D4AF37;
  --zero-yellow: #FFD600;
  --zero-green: #00ff88;
  --zero-bg: #000000;
  --zero-bg-elev: #0a0a0a;
  --zero-neon: #00ff88;
  --zero-neon-alt: #00E676;
  --zero-muted: rgba(255, 255, 255, 0.40);
  --zero-muted-2: rgba(255, 255, 255, 0.55);
  --zero-border: #1a1a1a;
  --zero-font-display: 'Orbitron', sans-serif;
  --zero-font-body: 'Inter', sans-serif;
}

html { scroll-behavior: smooth; }
::-webkit-scrollbar { display: none !important; }
html, body { -ms-overflow-style: none !important; scrollbar-width: none !important; }

/* Keep Streamlit shell at viewport height (prevents blank black page). */
html, body, #root, .withScreencast, .stApp, [data-testid="stAppViewContainer"] {
  height: 100% !important;
  min-height: 100vh !important;
}

body, [data-testid="stAppViewContainer"] {
  background: var(--zero-bg);
  color: var(--zero-white);
  font-family: var(--zero-font-body);
  -webkit-user-select: none;
  user-select: none;
}

.stApp {
  background-color: var(--zero-bg);
  background-image:
    radial-gradient(ellipse 80% 60% at 50% 0%, rgba(229, 9, 20, 0.08), transparent 55%),
    radial-gradient(ellipse 100% 100% at 50% 50%, transparent 40%, rgba(0, 0, 0, 0.75) 100%),
    linear-gradient(rgba(212, 175, 55, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(212, 175, 55, 0.03) 1px, transparent 1px);
  background-size: 100% 100%, 100% 100%, 48px 48px, 48px 48px;
  background-attachment: fixed;
  position: relative;
  overflow: auto !important;
}
.stApp::before {
  content: "";
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 1;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.12) 2px, rgba(0,0,0,0.12) 4px);
  opacity: 0.35;
  animation: zero-scanline-drift 8s linear infinite;
}
.stApp::after {
  content: "";
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 1;
  background: radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 100%);
}
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stSidebar"],
[data-testid="stBottom"] {
  position: relative;
  z-index: 2;
}
@keyframes zero-scanline-drift { 0% { transform: translateY(0); } 100% { transform: translateY(4px); } }

.main-title {
  color: var(--zero-white);
  font-family: var(--zero-font-display);
  font-weight: 900;
  font-size: 4rem;
  letter-spacing: -3px;
  text-align: center;
  margin: 10px 0;
  line-height: 1;
  text-shadow: 0 0 20px rgba(229,9,20,0.35), 0 0 40px rgba(229,9,20,0.15);
  animation: fadeInDown 1s ease-out;
}
.terminal-core-txt {
  color: var(--zero-red);
  font-weight: 700;
  font-size: 0.8rem;
  letter-spacing: 6px;
  text-align: center;
  text-transform: uppercase;
  margin-bottom: 40px;
  animation: fadeIn 2s ease-out;
  text-shadow: 0 0 12px rgba(229,9,20,0.45);
}
.gold-title {
  color: var(--zero-gold);
  font-family: var(--zero-font-display);
  font-weight: 800;
  font-size: 0.9rem;
  letter-spacing: 2px;
  margin-bottom: 1.5rem;
  text-transform: uppercase;
  position: relative;
  display: inline-block;
  background: linear-gradient(90deg, var(--zero-gold) 0%, #fff6c8 35%, var(--zero-gold) 50%, #fff6c8 65%, var(--zero-gold) 100%);
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gold-shimmer 3.2s linear infinite;
}
@keyframes gold-shimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }

.digital-card {
  background: rgba(10,10,10,0.92);
  border: 1px solid var(--zero-border);
  border-radius: 4px;
  padding: 30px;
  margin-bottom: 24px;
  position: relative;
  will-change: transform, opacity;
  transition: opacity 0.25s cubic-bezier(0.22,0.61,0.36,1), border-color 0.35s ease, box-shadow 0.35s ease, transform 0.25s cubic-bezier(0.22,0.61,0.36,1);
  box-shadow: 0 0 0 1px rgba(229,9,20,0.05) inset;
}
.digital-card:hover {
  border-color: rgba(229,9,20,0.65);
  box-shadow: 0 0 0 1px rgba(229,9,20,0.35), 0 0 18px rgba(229,9,20,0.25), 0 0 36px rgba(212,175,55,0.08);
  animation: neon-border-pulse 1.6s ease-in-out infinite;
}
@keyframes neon-border-pulse {
  0%,100% { box-shadow: 0 0 0 1px rgba(229,9,20,0.35), 0 0 14px rgba(229,9,20,0.22), 0 0 28px rgba(212,175,55,0.06); }
  50% { box-shadow: 0 0 0 1px rgba(229,9,20,0.75), 0 0 22px rgba(229,9,20,0.4), 0 0 40px rgba(212,175,55,0.14); }
}

.label-grey { color: var(--zero-muted); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1.2px; }
.value-white { color: var(--zero-white); font-size: 2.2rem; font-weight: 700; text-shadow: 0 0 16px rgba(255,255,255,0.08); }
.status-red { color: var(--zero-red); font-weight: 800; font-size: 0.8rem; text-shadow: 0 0 10px rgba(229,9,20,0.45); }

.order-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.order-table th { text-align: left; color: #444; padding: 10px; border-bottom: 1px solid #222; font-family: var(--zero-font-display); letter-spacing: 1px; font-size: 0.7rem; }
.order-table td { padding: 14px 10px; border-bottom: 1px solid #111; color: #ddd; }
.order-table tr:hover td { background: rgba(229,9,20,0.04); }
.buy-quant { color: var(--zero-neon); font-weight: bold; text-shadow: 0 0 8px rgba(0,255,136,0.35); }
.sell-quant { color: #ff4b4b; font-weight: bold; text-shadow: 0 0 8px rgba(255,75,75,0.35); }

.centered-box { display: flex; justify-content: center; align-items: center; flex-direction: column; width: 100%; }

.strat-card {
  background: rgba(10,10,10,0.7);
  border: 1px solid #222;
  border-radius: 4px;
  padding: 14px 16px;
  height: 100%;
  transition: border-color 0.3s ease, transform 0.2s ease, box-shadow 0.3s ease;
}
.strat-card:hover { border-color: var(--zero-gold); transform: translateY(-2px); box-shadow: 0 0 16px rgba(212,175,55,0.18); }

/* Never gate visibility on JS — Streamlit reruns recreate DOM nodes. */
@keyframes fadeInDown { from { opacity: 0; transform: translateY(-12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUpFade { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
.reveal-up, .digital-card, [data-reveal] {
  opacity: 1 !important;
  transform: none;
  animation: slideUpFade 0.45s cubic-bezier(0.22,0.61,0.36,1);
}
.reveal-delay-1 { animation-delay: 0.05s; }
.reveal-delay-2 { animation-delay: 0.12s; }
.reveal-delay-3 { animation-delay: 0.2s; }
.reveal-delay-4 { animation-delay: 0.28s; }
.reveal-delay-5 { animation-delay: 0.36s; }
.reveal-up.is-revealed, .digital-card.is-revealed, [data-reveal].is-revealed,
.reveal-up.zero-revealed, .digital-card.zero-revealed, [data-reveal].zero-revealed {
  opacity: 1; transform: none;
}

.zero-glitch { position: relative; display: inline-block; color: var(--zero-white); font-family: var(--zero-font-display); text-shadow: 0 0 8px rgba(229,9,20,0.4); }
.zero-glitch::before, .zero-glitch::after { content: attr(data-text); position: absolute; left: 0; top: 0; width: 100%; overflow: hidden; opacity: 0.8; }
.zero-glitch::before { color: var(--zero-gold); clip-path: inset(0 0 55% 0); transform: translate(-2px,0); animation: glitch-a 2.4s infinite linear alternate-reverse; }
.zero-glitch::after { color: var(--zero-red); clip-path: inset(45% 0 0 0); transform: translate(2px,0); animation: glitch-b 2.1s infinite linear alternate-reverse; }
@keyframes glitch-a { 0%{transform:translate(0)} 20%{transform:translate(-2px,1px)} 40%{transform:translate(2px,-1px)} 60%{transform:translate(-1px,0)} 80%{transform:translate(1px,1px)} 100%{transform:translate(0)} }
@keyframes glitch-b { 0%{transform:translate(0)} 25%{transform:translate(2px,0)} 50%{transform:translate(-2px,1px)} 75%{transform:translate(1px,-1px)} 100%{transform:translate(0)} }

.hud-corners { position: relative; }
.hud-corners::before, .hud-corners::after { content: ""; position: absolute; width: 14px; height: 14px; pointer-events: none; border: 2px solid var(--zero-red); }
.hud-corners::before { top: -1px; left: -1px; border-right: none; border-bottom: none; box-shadow: -2px -2px 8px rgba(229,9,20,0.35); }
.hud-corners::after { bottom: -1px; right: -1px; border-left: none; border-top: none; box-shadow: 2px 2px 8px rgba(229,9,20,0.35); }

.neon-border {
  border: 1px solid rgba(0,255,136,0.55) !important;
  box-shadow: 0 0 10px rgba(0,255,136,0.25), inset 0 0 10px rgba(0,255,136,0.05);
}
.scanlines { position: relative; overflow: hidden; }
.scanlines::after {
  content: ""; pointer-events: none; position: absolute; inset: 0;
  background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px);
  opacity: 0.4;
}
.matrix-grid {
  background-image: linear-gradient(rgba(212,175,55,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(212,175,55,0.06) 1px, transparent 1px);
  background-size: 32px 32px;
}
.cyber-badge {
  display: inline-block; font-family: var(--zero-font-display); font-size: 0.55rem; font-weight: 900;
  letter-spacing: 1.5px; text-transform: uppercase; color: var(--zero-white);
  background: rgba(229,9,20,0.18); border: 1px solid var(--zero-red); padding: 2px 8px; border-radius: 2px;
  box-shadow: 0 0 10px rgba(229,9,20,0.25);
}
.pulse-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--zero-neon); box-shadow: 0 0 8px rgba(0,255,136,0.8);
  animation: pulse-dot 1.4s ease-in-out infinite; vertical-align: middle;
}
@keyframes pulse-dot { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.35); opacity: 0.55; } }

div.stButton > button, button[kind="primary"], button[kind="secondary"], .stDownloadButton > button {
  background: rgba(10,10,10,0.9) !important; color: var(--zero-white) !important;
  border: 1px solid var(--zero-red) !important; border-radius: 2px !important;
  font-family: var(--zero-font-display) !important; font-weight: 700 !important;
  letter-spacing: 1.5px !important; text-transform: uppercase !important;
  box-shadow: 0 0 10px rgba(229,9,20,0.15) !important;
  transition: border-color 0.25s ease, box-shadow 0.25s ease, color 0.25s ease, background 0.25s ease !important;
}
div.stButton > button:hover, button[kind="primary"]:hover, button[kind="secondary"]:hover, .stDownloadButton > button:hover {
  border-color: var(--zero-gold) !important; color: var(--zero-gold) !important;
  background: rgba(212,175,55,0.08) !important; box-shadow: 0 0 18px rgba(212,175,55,0.28) !important;
}

.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #1a1a1a; }
.stTabs [data-baseweb="tab"] {
  font-family: var(--zero-font-display); font-weight: 700; letter-spacing: 1.5px;
  color: var(--zero-muted-2) !important; background: transparent !important; border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
  color: var(--zero-white) !important; border-bottom: 2px solid var(--zero-red) !important;
  box-shadow: 0 4px 14px -2px rgba(229,9,20,0.55); text-shadow: 0 0 10px rgba(229,9,20,0.35);
}

[data-testid="stExpander"] {
  background: rgba(10,10,10,0.85); border: 1px solid #1e1e1e; border-radius: 4px;
  box-shadow: inset 0 0 0 1px rgba(229,9,20,0.05);
}
[data-testid="stExpander"] details summary {
  font-family: var(--zero-font-display); letter-spacing: 1px; color: var(--zero-gold) !important;
}
[data-testid="stExpander"]:hover { border-color: rgba(229,9,20,0.45); box-shadow: 0 0 14px rgba(229,9,20,0.12); }

[data-testid="stMetric"] {
  background: rgba(10,10,10,0.6); border: 1px solid #1a1a1a; border-radius: 4px;
  padding: 10px 12px; box-shadow: 0 0 12px rgba(212,175,55,0.06);
}
[data-testid="stMetricLabel"] {
  color: var(--zero-muted) !important; font-family: var(--zero-font-display);
  letter-spacing: 1px; text-transform: uppercase; font-size: 0.7rem !important;
}
[data-testid="stMetricValue"] {
  color: var(--zero-white) !important; text-shadow: 0 0 14px rgba(0,255,136,0.2);
  font-family: var(--zero-font-display);
}
[data-testid="stMetricDelta"] svg { filter: drop-shadow(0 0 4px rgba(0,255,136,0.4)); }

.stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] > div {
  background: #0a0a0a !important; border-color: #222 !important; color: #fff !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
  border-color: var(--zero-red) !important; box-shadow: 0 0 0 1px rgba(229,9,20,0.4) !important;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0a0a0a 0%, #000 100%);
  border-right: 1px solid rgba(229,9,20,0.25);
}

@media (prefers-reduced-motion: reduce) {
  .digital-card, .main-title, .terminal-core-txt, .gold-title, .zero-glitch,
  .zero-glitch::before, .zero-glitch::after, .pulse-dot, .stApp::before { animation: none !important; }
  .digital-card, .reveal-up, [data-reveal], .strat-card { transition: none !important; }
  .reveal-up, .digital-card, [data-reveal] { opacity: 1 !important; transform: none !important; animation: none !important; }
  .gold-title { -webkit-text-fill-color: var(--zero-gold); background: none; color: var(--zero-gold); }
}
"""


def _load_css() -> str:
    """Prefer the static CSS file; fall back to embedded string."""
    try:
        if _CSS_PATH.is_file():
            return _CSS_PATH.read_text(encoding="utf-8")
    except OSError:
        pass
    return _FALLBACK_CSS


CYBER_CSS: str = _load_css()

# Progressive-enhancement stagger only — visibility is CSS-owned.
# Runs inside st.iframe → targets parent.document (Streamlit app).
# NOTE: st.iframe rejects height=0; use height=1.
_REVEAL_BOOT_JS = r"""
<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:0;background:transparent;">
<script>
(function () {
  var rootWin = window.parent && window.parent !== window ? window.parent : window;
  var doc = rootWin.document;
  var REDUCE = rootWin.matchMedia && rootWin.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (REDUCE) return;
  var tagged = (rootWin.__ZERO_CYBER_STAGGER__ = rootWin.__ZERO_CYBER_STAGGER__ || new WeakSet());
  var timer = null;

  function collect() {
    return Array.prototype.slice.call(
      doc.querySelectorAll('.digital-card, [data-reveal], .reveal-up')
    );
  }

  function boot() {
    var els = collect();
    els.forEach(function (el, i) {
      if (tagged.has(el)) return;
      tagged.add(el);
      if (!el.classList.contains('reveal-delay-1') &&
          !el.classList.contains('reveal-delay-2') &&
          !el.classList.contains('reveal-delay-3') &&
          !el.classList.contains('reveal-delay-4') &&
          !el.classList.contains('reveal-delay-5')) {
        el.classList.add('reveal-delay-' + ((i % 5) + 1));
      }
      el.classList.add('is-revealed');
      el.classList.add('zero-revealed');
    });
  }

  function schedule() {
    if (timer) return;
    timer = rootWin.setTimeout(function () {
      timer = null;
      try { boot(); } catch (e) {}
    }, 120);
  }

  schedule();
  if (!rootWin.__ZERO_CYBER_REVEAL_MO__ && doc.body) {
    try {
      rootWin.__ZERO_CYBER_REVEAL_MO__ = new rootWin.MutationObserver(schedule);
      rootWin.__ZERO_CYBER_REVEAL_MO__.observe(doc.body, { childList: true, subtree: true });
    } catch (e) {}
  }
})();
</script>
</body></html>
"""


def apply_cyber_theme() -> None:
    """Inject the cyberpunk theme stylesheet into the Streamlit app."""
    css = CYBER_CSS or _FALLBACK_CSS
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def inject_reveal_boot_script() -> None:
    """Inject optional stagger boot via st.iframe (replaces deprecated components.v1.html).

    Uses height=1 — st.iframe rejects height=0. Visibility does not depend on this script.
    """
    try:
        st.iframe(_REVEAL_BOOT_JS, height=1, width="stretch")
    except Exception:
        # Last-resort: CSS-only theme already keeps cards visible.
        pass
