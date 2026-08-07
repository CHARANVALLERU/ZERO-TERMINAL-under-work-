"""ZERO UI — shared direction / action badge chips.

Surgical CSS for QuantDinge + Agent Debate panels.
Classes: .zero-badge-row, .zero-badge (+ tone modifiers).
"""

from __future__ import annotations

import html as _html
from typing import Any

# Locked palette (match cyber theme)
_GREEN = "#00E676"
_RED = "#E50914"
_GOLD = "#D4AF37"
_YELLOW = "#FFD600"
_BG = "#000000"

_CSS = f"""
.zero-badge-row {{
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}}
.zero-badge {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  max-width: 100%;
  box-sizing: border-box;
  font-family: 'Orbitron', sans-serif;
  font-weight: 900;
  font-size: 0.68rem;
  letter-spacing: 1.2px;
  text-transform: uppercase;
  white-space: nowrap;
  line-height: 1.2;
  padding: 5px 12px;
  border-radius: 2px;
  border: 1px solid {_GOLD};
  color: {_GOLD};
  background: {_BG};
  text-shadow: 0 0 8px rgba(212,175,55,0.35);
}}
.zero-badge-long,
.zero-badge-buy,
.zero-badge-bullish {{
  color: {_GREEN};
  border-color: {_GREEN};
  background: rgba(0,230,118,0.10);
  text-shadow: 0 0 10px rgba(0,230,118,0.45);
}}
.zero-badge-short,
.zero-badge-sell,
.zero-badge-bearish {{
  color: {_RED};
  border-color: {_RED};
  background: rgba(229,9,20,0.12);
  text-shadow: 0 0 10px rgba(229,9,20,0.45);
}}
.zero-badge-neutral,
.zero-badge-wait {{
  color: {_YELLOW};
  border-color: {_YELLOW};
  background: rgba(255,193,7,0.10);
  text-shadow: 0 0 10px rgba(255,193,7,0.40);
}}
.zero-badge-straddle,
.zero-badge-spread,
.zero-badge-gold {{
  color: {_GOLD};
  border-color: {_GOLD};
  background: rgba(212,175,55,0.12);
  text-shadow: 0 0 10px rgba(212,175,55,0.45);
}}
@media (max-width: 520px) {{
  .zero-badge {{
    white-space: normal;
    text-align: center;
    max-width: 11rem;
    font-size: 0.62rem;
    letter-spacing: 1px;
  }}
  .zero-badge-row {{
    justify-content: flex-end;
  }}
}}
"""

_CSS_INJECTED = False


def badge_css() -> str:
    """Return the shared badge stylesheet (idempotent inject helper uses this)."""
    return f"<style>{_CSS}</style>"


def inject_badge_css() -> None:
    """Inject badge CSS once per Streamlit session via st.markdown."""
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    try:
        import streamlit as st
    except ImportError:
        return
    _CSS_INJECTED = True
    st.markdown(badge_css(), unsafe_allow_html=True)


def badge_tone(label: Any) -> str:
    """Map LONG/SHORT/NEUTRAL/STRADDLE/SPREAD/BUY/SELL → CSS tone suffix."""
    s = str(label or "").upper()
    if "STRADDLE" in s or "SPREAD" in s or "CONDOR" in s:
        return "straddle"
    if "LONG" in s or "BUY" in s or "BULL" in s:
        return "long"
    if "SHORT" in s or "SELL" in s or "BEAR" in s or "PUT" in s:
        return "short"
    if "NEUTRAL" in s or "WAIT" in s or "HOLD" in s or "FLAT" in s:
        return "neutral"
    return "gold"


def badge_color(label: Any) -> str:
    """Hex color for inline fallbacks."""
    tone = badge_tone(label)
    return {
        "long": _GREEN,
        "short": _RED,
        "neutral": _YELLOW,
        "straddle": _GOLD,
        "gold": _GOLD,
    }.get(tone, _GOLD)


def zero_badge(label: Any, extra_class: str = "") -> str:
    """Return a single .zero-badge span (HTML-escaped label)."""
    text = _html.escape(str(label if label is not None else ""), quote=True)
    tone = badge_tone(label)
    cls = f"zero-badge zero-badge-{tone}"
    if extra_class:
        cls = f"{cls} {extra_class}"
    return f'<span class="{cls}">{text}</span>'


def zero_badge_row(*labels: Any, extra_class: str = "") -> str:
    """Horizontal flex row of badges (skips empty labels)."""
    chips = "".join(zero_badge(lab) for lab in labels if lab not in (None, ""))
    row_cls = "zero-badge-row"
    if extra_class:
        row_cls = f"{row_cls} {extra_class}"
    return f'<div class="{row_cls}">{chips}</div>'
