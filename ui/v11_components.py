"""
ZERO V1.1 UI Components — Cyberpunk Control Deck
=================================================

Interactive surfaces for the V1.1 intelligence layer, restyled as a
neon HUD / control-deck aesthetic:

  - Session-IV volatility badge (method-colored neon)
  - TSFM ensemble forecast card (glowing quantile range)
  - Agent debate panel (cyber courtroom)
  - Options intelligence card (terminal tables)
  - Broker control panel (armed red/green switch aesthetic)
  - Provider health registry (HUD meters)
  - IC memo generator (launch CTA glow)
  - Backtest statistics panel (cyber chrome)

All components are defensive: they degrade to empty or info blocks
when the underlying V1.1 engine data is missing or an optional leg
is unavailable. Public function names and signatures are locked.
"""
from __future__ import annotations

import os
import datetime
from typing import Any, Dict, List

import streamlit as st
import pandas as pd
import numpy as np


# ── Locked palette ──────────────────────────────────────────────────────────
_P = {
    "void": "#000",
    "panel": "#0a0a0a",
    "crimson": "#E50914",
    "gold": "#D4AF37",
    "neon": "#00ff88",
    "green": "#00E676",
    "cyan": "#00B0FF",
    "white": "#fff",
    "mute": "#666",
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _num(value, default: float | None = None, nd: int = 2) -> Any:
    try:
        v = float(value)
        if default is None and (pd.isna(v) or v in (float("inf"), float("-inf"))):
            return None
        return round(v, nd) if default is None else round(v, nd)
    except (TypeError, ValueError):
        return default


def _safe(value: Any, default: Any = "—") -> Any:
    return value if value is not None else default


def _deck_css() -> str:
    """Shared cyberpunk chrome tokens (injected once per render path)."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap');
.z11-deck {{
  font-family:'Share Tech Mono',monospace;
  background:linear-gradient(145deg,{_P['panel']} 0%,{_P['void']} 100%);
  border:1px solid {_P['mute']}55;
  border-radius:4px;
  padding:16px;
  margin:12px 0;
  position:relative;
  box-shadow:inset 0 0 40px {_P['void']},0 0 12px {_P['mute']}22;
}}
.z11-deck::before {{
  content:'';
  position:absolute;top:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,{_P['cyan']},{_P['neon']},transparent);
  opacity:0.85;
}}
.z11-label {{
  font-family:'Orbitron',sans-serif;
  font-size:0.68rem;font-weight:900;
  letter-spacing:2px;text-transform:uppercase;
}}
.z11-glow-text {{
  text-shadow:0 0 8px currentColor,0 0 18px currentColor;
}}
.z11-meter {{
  height:6px;border-radius:2px;background:{_P['void']};
  border:1px solid {_P['mute']}44;overflow:hidden;
}}
.z11-meter > span {{
  display:block;height:100%;
  box-shadow:0 0 10px currentColor;
}}
.z11-switch {{
  display:inline-flex;align-items:center;gap:12px;
  padding:14px 18px;border-radius:4px;
  font-family:'Orbitron',sans-serif;font-weight:900;
  letter-spacing:2px;font-size:0.85rem;
}}
.z11-cta {{
  display:inline-block;padding:10px 22px;
  font-family:'Orbitron',sans-serif;font-weight:900;
  letter-spacing:2px;font-size:0.7rem;
  border:1px solid {_P['gold']};
  color:{_P['gold']};
  background:linear-gradient(180deg,{_P['gold']}22,{_P['void']});
  box-shadow:0 0 16px {_P['gold']}55,inset 0 0 12px {_P['gold']}18;
  border-radius:2px;text-transform:uppercase;
}}
.z11-term {{
  font-family:'Share Tech Mono',monospace;
  font-size:0.65rem;color:{_P['neon']};
  background:{_P['void']};
  border:1px solid {_P['neon']}33;
  border-radius:2px;padding:8px 10px;
}}
</style>
"""


# ── 1. Session IV volatility badge ──────────────────────────────────────────

def render_session_iv_badge(data: dict | None) -> None:
    """Compact inline badge for the volatility layer used in the prediction."""
    if not data or not isinstance(data, dict):
        return

    iv = data.get("iv_used")
    method = data.get("vol_method", "legacy")
    india_vix = data.get("india_vix")
    if iv is None and method == "legacy_default":
        return

    color = _P["gold"]
    if method == "egarch":
        color = _P["green"]
    elif method == "gjr_garch":
        color = _P["neon"]
    elif method == "ewma":
        color = _P["cyan"]
    elif method == "atr_fallback":
        color = _P["crimson"]

    vix_str = f"India VIX {_num(india_vix, nd=2)} · " if india_vix is not None else ""
    st.markdown(_deck_css() + f"""
<div style="display:inline-flex;align-items:center;gap:10px;
  background:{_P['panel']};border:1px solid {color}66;
  border-radius:2px;padding:8px 14px;margin:8px 0;
  box-shadow:0 0 14px {color}33,inset 0 0 20px {color}0d;">
  <span class="z11-label" style="color:{_P['mute']};">◆ VOL LAYER</span>
  <span class="z11-glow-text" style="font-family:'Orbitron',sans-serif;font-size:0.85rem;color:{color};font-weight:900;">
    IV {_num(iv, nd=2)}
  </span>
  <span style="width:6px;height:6px;border-radius:50%;background:{color};box-shadow:0 0 8px {color};"></span>
  <span style="font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:{_P['mute']};">
    {vix_str}{method}
  </span>
</div>
""", unsafe_allow_html=True)


# ── 2. TSFM ensemble forecast card ──────────────────────────────────────────

def render_tsfm_forecast_card(tsfm_data: dict | None) -> None:
    """Render Chronos-2 / Kronos / TimesFM P10/P50/P90 forecast."""
    if not tsfm_data or not isinstance(tsfm_data, dict):
        return

    status = tsfm_data.get("status")
    if status != "forecasted":
        reason = tsfm_data.get("error") or tsfm_data.get("status") or "unavailable"
        st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['mute']}44;">
  <div class="z11-label" style="color:{_P['cyan']};">◆ TSFM ENSEMBLE</div>
  <p style="font-size:0.65rem;color:{_P['mute']};margin:8px 0 0 0;">
    Optional leg inactive — <span style="color:{_P['crimson']};">{reason}</span>
  </p>
</div>
""", unsafe_allow_html=True)
        return

    close = tsfm_data.get("close") or {}
    p10 = _num(close.get("p10"))
    p50 = _num(close.get("p50"))
    p90 = _num(close.get("p90"))
    high = _num(tsfm_data.get("high_p90"))
    low = _num(tsfm_data.get("low_p10"))
    backend = tsfm_data.get("backend", "unknown")
    direction = tsfm_data.get("direction", "flat")
    n_context = tsfm_data.get("n_context", 0)

    dir_color = (
        _P["green"] if direction == "up"
        else (_P["crimson"] if direction == "down" else _P["gold"])
    )

    # Glowing quantile range bar (visual only; values unchanged)
    lo_v = float(p10) if p10 is not None else 0.0
    mid_v = float(p50) if p50 is not None else lo_v
    hi_v = float(p90) if p90 is not None else mid_v
    span = max(hi_v - lo_v, 1e-9)
    mid_pct = max(0.0, min(100.0, ((mid_v - lo_v) / span) * 100.0))

    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['cyan']}44;box-shadow:inset 0 0 40px {_P['void']},0 0 18px {_P['cyan']}22;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
    <div>
      <span class="z11-label z11-glow-text" style="color:{_P['cyan']};">◆ TSFM ENSEMBLE</span>
      <div style="font-size:0.55rem;color:{_P['mute']};margin-top:4px;">
        Backend: <b style="color:{_P['white']};">{backend}</b> · Context: {n_context} bars
      </div>
    </div>
    <div style="background:{dir_color}18;border:1px solid {dir_color};
      color:{dir_color};font-family:'Orbitron',sans-serif;font-size:0.65rem;font-weight:900;
      padding:4px 12px;letter-spacing:2px;box-shadow:0 0 12px {dir_color}44;">
      {direction.upper()}
    </div>
  </div>

  <!-- Glowing P10→P90 range -->
  <div style="margin:8px 0 16px 0;">
    <div style="display:flex;justify-content:space-between;font-size:0.5rem;color:{_P['mute']};margin-bottom:4px;">
      <span>P10</span><span style="color:{_P['white']};">P50</span><span>P90</span>
    </div>
    <div style="position:relative;height:10px;background:{_P['void']};
      border:1px solid {_P['cyan']}33;border-radius:2px;overflow:visible;">
      <div style="position:absolute;left:0;right:0;top:0;bottom:0;
        background:linear-gradient(90deg,{_P['crimson']}88,{_P['gold']}66,{_P['green']}88);
        box-shadow:0 0 14px {_P['cyan']}55;"></div>
      <div style="position:absolute;left:{mid_pct}%;top:-4px;width:3px;height:18px;
        background:{_P['white']};box-shadow:0 0 10px {_P['white']};transform:translateX(-50%);"></div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;margin-bottom:10px;">
    <div style="background:{_P['void']};border:1px solid {_P['crimson']}44;border-radius:2px;padding:10px;">
      <div style="font-size:0.5rem;color:{_P['mute']};letter-spacing:1px;">P10 LOW</div>
      <div class="z11-glow-text" style="font-size:0.9rem;font-weight:800;color:{_P['crimson']};">{_safe(p10)}</div>
    </div>
    <div style="background:{_P['void']};border:1px solid {_P['white']}33;border-radius:2px;padding:10px;">
      <div style="font-size:0.5rem;color:{_P['mute']};letter-spacing:1px;">P50 MEDIAN</div>
      <div class="z11-glow-text" style="font-size:0.9rem;font-weight:800;color:{_P['white']};">{_safe(p50)}</div>
    </div>
    <div style="background:{_P['void']};border:1px solid {_P['green']}44;border-radius:2px;padding:10px;">
      <div style="font-size:0.5rem;color:{_P['mute']};letter-spacing:1px;">P90 HIGH</div>
      <div class="z11-glow-text" style="font-size:0.9rem;font-weight:800;color:{_P['green']};">{_safe(p90)}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;text-align:center;">
    <div style="background:{_P['void']};border:1px solid {_P['green']}33;border-radius:2px;padding:8px;">
      <div style="font-size:0.5rem;color:{_P['mute']};">EST. HIGH P90</div>
      <div style="font-size:0.8rem;font-weight:700;color:{_P['green']};">{_safe(high)}</div>
    </div>
    <div style="background:{_P['void']};border:1px solid {_P['crimson']}33;border-radius:2px;padding:8px;">
      <div style="font-size:0.5rem;color:{_P['mute']};">EST. LOW P10</div>
      <div style="font-size:0.8rem;font-weight:700;color:{_P['crimson']};">{_safe(low)}</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── 3. Agent debate panel ───────────────────────────────────────────────────

def render_agent_debate_panel(debate_data: dict | None) -> None:
    """Render the V1.1 bull/bear/PM agent debate verdict."""
    if not debate_data or not isinstance(debate_data, dict):
        return

    pm = debate_data.get("pm_verdict") or {}
    action = pm.get("action", "WAIT")
    conviction = _num(pm.get("conviction"), 0.0, 2)
    kill = pm.get("kill_condition", "—")
    sizing = _num(pm.get("position_size_hint_pct"), 0.0, 2)
    reasoning = pm.get("reasoning", "")
    llm_used = debate_data.get("llm_used", False)
    model = debate_data.get("model") or "offline heuristic"

    bull = debate_data.get("bull_case") or {}
    bear = debate_data.get("bear_case") or {}
    risk = debate_data.get("risk_assessment") or {}
    risk_level = risk.get("risk_level", "MODERATE")

    act_color = (
        _P["green"] if action == "LONG"
        else (_P["crimson"] if action == "SHORT" else _P["gold"])
    )
    risk_color = {
        "LOW": _P["green"],
        "MODERATE": _P["gold"],
        "HIGH": _P["crimson"],
        "EXTREME": _P["crimson"],
    }.get(risk_level, _P["gold"])

    def _args_list(case: dict) -> str:
        args = case.get("arguments") or []
        if not args:
            return f"<li style='color:{_P['mute']};'>No explicit arguments</li>"
        return "".join(
            f"<li style='color:{_P['mute']};font-size:0.6rem;line-height:1.45;margin:3px 0;'>"
            f"<span style='color:{_P['neon']};'>›</span> {a}</li>"
            for a in args[:4]
        )

    risk_notes = "".join(
        f"<li style='color:{_P['mute']};font-size:0.6rem;line-height:1.45;margin:3px 0;'>"
        f"<span style='color:{risk_color};'>›</span> {n}</li>"
        for n in (risk.get("notes") or [])[:3]
    )

    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['green']}33;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;
    border-bottom:1px solid {_P['mute']}33;padding-bottom:10px;">
    <div>
      <span class="z11-label z11-glow-text" style="color:{_P['green']};">◆ CYBER COURT · PM VERDICT</span>
      <div style="font-size:0.55rem;color:{_P['mute']};margin-top:4px;">
        Model: {model} · {"<span style='color:" + _P['green'] + ";'>LLM ONLINE</span>" if llm_used else "<span style='color:" + _P['mute'] + ";'>HEURISTIC</span>"}
      </div>
    </div>
    <div style="text-align:right;">
      <div class="z11-glow-text" style="font-family:'Orbitron',sans-serif;font-size:1.15rem;font-weight:900;color:{act_color};">
        {action}
      </div>
      <div style="font-size:0.6rem;color:{_P['mute']};">Conviction {conviction*100:.0f}%</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;">
    <!-- Bull courtroom panel -->
    <div style="background:{_P['void']};border:1px solid {_P['green']}44;border-radius:2px;padding:12px;
      box-shadow:inset 0 0 24px {_P['green']}0d;">
      <div class="z11-label" style="color:{_P['green']};font-size:0.55rem;">▣ BULL BENCH</div>
      <div class="z11-glow-text" style="font-size:0.85rem;font-weight:800;color:{_P['white']};margin:6px 0;">
        {bull.get('strength', 0):.2f}
      </div>
      <ul style="margin:0;padding-left:12px;">{_args_list(bull)}</ul>
    </div>
    <!-- Bear courtroom panel -->
    <div style="background:{_P['void']};border:1px solid {_P['crimson']}44;border-radius:2px;padding:12px;
      box-shadow:inset 0 0 24px {_P['crimson']}0d;">
      <div class="z11-label" style="color:{_P['crimson']};font-size:0.55rem;">▣ BEAR BENCH</div>
      <div class="z11-glow-text" style="font-size:0.85rem;font-weight:800;color:{_P['white']};margin:6px 0;">
        {bear.get('strength', 0):.2f}
      </div>
      <ul style="margin:0;padding-left:12px;">{_args_list(bear)}</ul>
    </div>
    <!-- Risk panel -->
    <div style="background:{_P['void']};border:1px solid {risk_color}44;border-radius:2px;padding:12px;">
      <div class="z11-label" style="color:{risk_color};font-size:0.55rem;">▣ RISK TRIBUNAL</div>
      <div class="z11-glow-text" style="font-size:0.95rem;font-weight:800;color:{risk_color};margin:6px 0;">
        {risk_level}
      </div>
      <ul style="margin:0;padding-left:12px;">{risk_notes}</ul>
    </div>
  </div>

  <div style="background:{_P['void']};border-left:3px solid {act_color};border-radius:0 2px 2px 0;padding:12px;">
    <div style="font-size:0.65rem;color:{_P['mute']};line-height:1.5;">
      <b style="color:{_P['gold']};">REASONING</b> — <span style="color:{_P['white']};">{reasoning}</span>
    </div>
    <div style="font-size:0.6rem;color:{_P['mute']};margin-top:8px;">
      <b style="color:{_P['crimson']};">KILL</b>: {kill}
    </div>
    <div style="font-size:0.6rem;color:{_P['mute']};">
      <b style="color:{_P['cyan']};">SIZING</b>: {sizing}% of portfolio
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ── 4. Options intelligence card ───────────────────────────────────────────

def render_options_intelligence_card(options_data: dict | None, data: dict | None) -> None:
    """Render IV smile, OI-change, and multi-leg strategy metrics."""
    if not options_data or not isinstance(options_data, dict):
        return

    oi_intel = options_data.get("options_intelligence") or {}
    smile = oi_intel.get("smile") or {}
    drift = oi_intel.get("drift") or []
    strategies = oi_intel.get("strategies") or {}

    if not smile and not drift and not strategies:
        return

    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['crimson']}44;margin-bottom:0;padding-bottom:8px;">
  <div class="z11-label z11-glow-text" style="color:{_P['crimson']};margin-bottom:4px;">◆ OPTIONS TERMINAL</div>
  <div class="z11-term" style="margin-top:6px;">options://intel · smile · max-pain · multi-leg</div>
</div>
""", unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        if smile and smile.get("status") != "insufficient":
            st.markdown(
                f"""<div class="z11-label" style="color:{_P['mute']};font-size:0.55rem;margin:8px 0 4px;">
                ▸ IV SMILE</div>""",
                unsafe_allow_html=True,
            )
            st.metric("ATM IV", f"{smile.get('atm_iv', 0):.1f}%")
            st.metric("Skew proxy", f"{smile.get('skew_25d_proxy', 0):.3f}")
            st.metric("Curvature", f"{smile.get('curvature', 0):.3f}")
        else:
            st.info("IV smile needs ≥5 valid strikes with IV data.")

    with c2:
        if drift:
            st.markdown(
                f"""<div class="z11-label" style="color:{_P['mute']};font-size:0.55rem;margin:8px 0 4px;">
                ▸ MAX-PAIN DRIFT</div>""",
                unsafe_allow_html=True,
            )
            df = pd.DataFrame([{"Time": d.get("ts"), "Max Pain": d.get("max_pain")} for d in drift[-5:]])
            st.line_chart(df.set_index("Time"), color="#E50914")
        else:
            st.info("No intraday chain snapshots yet.")

    if strategies:
        st.markdown(
            f"""<div class="z11-label" style="color:{_P['mute']};font-size:0.55rem;margin:10px 0 4px;">
            ▸ MULTI-LEG STRATEGIES</div>""",
            unsafe_allow_html=True,
        )
        rows = []
        for name, metrics in strategies.items():
            if isinstance(metrics, dict):
                rows.append({
                    "Strategy": name,
                    "Max Profit": metrics.get("max_profit"),
                    "Max Loss": metrics.get("max_loss"),
                    "Breakevens": ", ".join(str(round(b, 0)) for b in metrics.get("breakevens", [])),
                    "POP": f"{metrics.get('pop_estimate')*100:.0f}%" if metrics.get("pop_estimate") is not None else "—",
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ── 5. Broker control panel ─────────────────────────────────────────────────

def render_broker_control_panel() -> None:
    """Paper/live broker selector + safety gate + armed toggle."""
    armed_env = os.environ.get("ZERO_BROKER_ARMED") == "1"
    switch_bg = _P["green"] if armed_env else _P["crimson"]
    switch_label = "ARMED" if armed_env else "DISARMED"
    armed_val = os.environ.get("ZERO_BROKER_ARMED", "unset")

    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{switch_bg}55;">
  <div class="z11-label z11-glow-text" style="color:{_P['gold']};margin-bottom:12px;">◆ BROKER CONTROL DECK</div>
  <div class="z11-switch" style="background:{switch_bg}18;border:2px solid {switch_bg};
    color:{switch_bg};box-shadow:0 0 24px {switch_bg}44,inset 0 0 20px {switch_bg}14;width:100%;
    justify-content:space-between;box-sizing:border-box;">
    <span>⚡ SAFETY INTERLOCK</span>
    <span class="z11-glow-text">{switch_label}</span>
  </div>
  <div style="font-size:0.55rem;color:{_P['mute']};margin-top:8px;font-family:'Share Tech Mono',monospace;">
    ZERO_BROKER_ARMED={armed_val}
  </div>
</div>
""", unsafe_allow_html=True)

    broker_name = st.selectbox(
        "Adapter",
        ["paper", "dhan", "fyers", "kite", "angel"],
        index=0,
        key="v11_broker_name",
        help="Paper is default. Live adapters require ZERO_BROKER_ARMED=1 + env credentials.",
    )

    if st.button("Connect / Test Broker", key="v11_broker_connect"):
        try:
            from engine.broker import get_broker
            broker = get_broker(broker_name, armed=False)  # never auto-arm here
            ok = broker.connect()
            if ok:
                st.success(f"{broker_name.upper()} connection OK (paper mode)")
            else:
                st.warning("Connection returned false — check credentials / env vars.")
            # Show positions without auto-arming
            pos = broker.positions()
            st.write(f"Positions: {len(pos)}")
        except Exception as e:
            st.error(f"Broker connect failed: {e}")


# ── 6. Provider registry panel ──────────────────────────────────────────────

def render_provider_registry_panel() -> None:
    """Show health-scored NSE/BSE/yfinance provider registry."""
    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['cyan']}44;margin-bottom:8px;">
  <div class="z11-label z11-glow-text" style="color:{_P['cyan']};">◆ DATA PROVIDER HUD</div>
  <div style="font-size:0.55rem;color:{_P['mute']};margin-top:4px;">health meters · priority · capability matrix</div>
</div>
""", unsafe_allow_html=True)

    try:
        from data.providers import default_registry
        reg = default_registry()
        report = reg.status_report()
    except Exception as e:
        st.error(f"Provider registry unavailable: {e}")
        return

    if not report:
        st.info("No provider status yet.")
        return

    # HUD meters
    meter_html = ['<div style="display:grid;gap:8px;margin:8px 0 12px 0;">']
    for r in report:
        name = r.get("name", "?")
        health = float(r.get("health_score", 0) or 0)
        pct = max(0.0, min(100.0, health * 100.0))
        bar_color = (
            _P["green"] if pct >= 70
            else (_P["gold"] if pct >= 40 else _P["crimson"])
        )
        meter_html.append(f"""
<div style="background:{_P['panel']};border:1px solid {_P['mute']}33;border-radius:2px;padding:8px 10px;">
  <div style="display:flex;justify-content:space-between;font-size:0.6rem;margin-bottom:4px;">
    <span style="color:{_P['white']};font-family:'Orbitron',sans-serif;letter-spacing:1px;">{name}</span>
    <span style="color:{bar_color};font-weight:700;">{pct:.0f}%</span>
  </div>
  <div class="z11-meter"><span style="width:{pct}%;background:{bar_color};color:{bar_color};"></span></div>
  <div style="font-size:0.5rem;color:{_P['mute']};margin-top:4px;">
    P{r.get('priority','—')} · ok {r.get('success',0)} · fail {r.get('failure',0)}
    · OHLC {'Y' if r.get('supports_ohlc') else 'N'} · Quote {'Y' if r.get('supports_quote') else 'N'}
  </div>
</div>""")
    meter_html.append("</div>")
    st.markdown(_deck_css() + "".join(meter_html), unsafe_allow_html=True)

    rows = []
    for r in report:
        rows.append({
            "Provider": r.get("name"),
            "Priority": r.get("priority"),
            "Health": f"{r.get('health_score', 0)*100:.0f}%",
            "Success": r.get("success", 0),
            "Failure": r.get("failure", 0),
            "OHLC": "✅" if r.get("supports_ohlc") else "—",
            "Quote": "✅" if r.get("supports_quote") else "—",
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    if st.button("Refresh Provider Health", key="v11_refresh_providers"):
        try:
            q = reg.get_quote("NIFTY 50")
            st.write("NIFTY 50 probe:", q)
            st.rerun()
        except Exception as e:
            st.error(f"Probe failed: {e}")


# ── 7. IC memo generator button ─────────────────────────────────────────────

def render_ic_memo_generator(matrix: dict | None) -> None:
    """One-click daily IC memo generator."""
    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['gold']}55;text-align:center;">
  <div class="z11-label z11-glow-text" style="color:{_P['white']};margin-bottom:10px;">◆ DAILY IC MEMO</div>
  <div class="z11-cta">◈ LAUNCH MEMO SEQUENCE</div>
  <div style="font-size:0.55rem;color:{_P['mute']};margin-top:8px;">
    generate → write → archive today's investment committee memo
  </div>
</div>
""", unsafe_allow_html=True)

    if st.button("Generate & Write Today's IC Memo", key="v11_generate_memo"):
        try:
            from engine.report_generator import memo_from_latest
            debate = None
            try:
                debate = (matrix.get("NIFTY 50") or {}).get("agent_debate")
            except Exception:
                pass
            path = memo_from_latest(matrix=matrix, debate=debate)
            st.success(f"IC memo written: `{path}`")
        except Exception as e:
            st.error(f"Memo generation failed: {e}")


# ── 8. Backtest statistics panel ───────────────────────────────────────────

def render_backtest_stats_panel() -> None:
    """Run and display walk-forward backtest with DM / PSR / DSR."""
    st.markdown(_deck_css() + f"""
<div class="z11-deck" style="border-color:{_P['gold']}44;
  background:linear-gradient(160deg,{_P['panel']} 0%,{_P['void']} 60%,{_P['gold']}0d 100%);">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div class="z11-label z11-glow-text" style="color:{_P['gold']};">◆ STAT VALIDATION CHROME</div>
    <div style="font-size:0.5rem;color:{_P['mute']};letter-spacing:1px;">DM · PSR · DSR</div>
  </div>
  <div style="height:1px;background:linear-gradient(90deg,{_P['gold']},{_P['mute']}00);margin:10px 0 4px;"></div>
  <div style="font-size:0.55rem;color:{_P['mute']};">walk-forward · embargo · cost model</div>
</div>
""", unsafe_allow_html=True)

    embargo = st.number_input("Embargo (rows)", min_value=0, max_value=5, value=0, step=1, key="v11_embargo")
    n_trials = st.number_input("DSR trials (experiment count)", min_value=1, max_value=100, value=10, step=1, key="v11_trials")
    cost_toggle = st.toggle("Apply Indian cost model (gross → net)", value=False, key="v11_costs")

    if st.button("Run Walk-Forward Validation", key="v11_run_wf"):
        try:
            from engine.backtest import walk_forward
            from engine.india_costs import IndiaCostModel
            wf = walk_forward(embargo=int(embargo), n_trials=int(n_trials))
            if not wf:
                st.warning("No feedback logs available for walk-forward validation.")
                return
            st.json(wf)
        except Exception as e:
            st.error(f"Walk-forward failed: {e}")
