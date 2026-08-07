"""ZERO UI — Agent / QuantDinger / strategy bubble cards (cyber HUD aesthetic).

Strict ownership: this module only. Function names + input dict contracts match
ui/components.py and ui/v11_components.py (debate panel).
"""

from __future__ import annotations

import html as _html
from typing import Any

import streamlit as st

from ui.badge_styles import inject_badge_css, zero_badge, zero_badge_row

# Locked palette
_BG = "#000"
_PANEL = "#0a0a0a"
_RED = "#E50914"
_GOLD = "#D4AF37"
_GREEN = "#00ff88"
_GREEN2 = "#00E676"
_GOLD_ACCENT = "#D4AF37"
_WHITE = "#fff"
_GREY = "#666"

_CSS_INJECTED = False


def _esc(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return _html.escape(str(value), quote=True)


def _num(value: Any, default: float = 0.0, nd: int = 2) -> float:
    try:
        return round(float(value), nd)
    except (TypeError, ValueError):
        return default


def _inject_cyber_css() -> None:
    global _CSS_INJECTED
    if _CSS_INJECTED:
        return
    _CSS_INJECTED = True
    try:
        inject_badge_css()
    except Exception:
        pass
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800;900&display=swap');

.za-hud {{
  position: relative;
  background: {_PANEL};
  border: 1px solid rgba(212,175,55,0.28);
  padding: 16px 18px;
  margin-bottom: 18px;
  overflow: hidden;
  animation: zaReveal 0.5s cubic-bezier(0.22,0.61,0.36,1) both;
}}
.za-hud::before, .za-hud::after {{
  content: '';
  position: absolute;
  width: 14px; height: 14px;
  border: 1px solid {_GOLD};
  pointer-events: none;
  z-index: 2;
}}
.za-hud::before {{ top: 0; left: 0; border-right: 0; border-bottom: 0; }}
.za-hud::after {{ bottom: 0; right: 0; border-left: 0; border-top: 0; }}
.za-hud .za-corner-tr, .za-hud .za-corner-bl {{
  position: absolute; width: 14px; height: 14px;
  border: 1px solid {_GOLD_ACCENT}; pointer-events: none; z-index: 2;
}}
.za-hud .za-corner-tr {{ top: 0; right: 0; border-left: 0; border-bottom: 0; }}
.za-hud .za-corner-bl {{ bottom: 0; left: 0; border-right: 0; border-top: 0; }}
.za-scan {{
  pointer-events: none;
  position: absolute; inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px, rgba(0,0,0,0.18) 2px, rgba(0,0,0,0.18) 4px
  );
  opacity: 0.35; z-index: 1;
}}
.za-body {{ position: relative; z-index: 3; }}

.gold-title {{
  color: {_GOLD}; font-family: 'Orbitron', sans-serif;
  font-weight: 800; font-size: 0.85rem; letter-spacing: 2px;
  text-transform: uppercase; margin: 0 0 6px 0;
}}
.label-grey {{
  color: {_GREY}; font-size: 0.65rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 1.2px; margin: 0;
}}
.digital-card {{
  background: {_PANEL}; border: 1px solid #1a1a1a; border-radius: 2px;
  padding: 12px 14px; margin-bottom: 10px;
  animation: zaReveal 0.45s cubic-bezier(0.22,0.61,0.36,1) both;
}}
.strat-card {{
  background: rgba(10,10,10,0.92); border: 1px solid #222; border-radius: 2px;
  padding: 14px 16px; height: 100%;
  transition: border-color 0.3s ease, transform 0.2s ease;
  animation: zaReveal 0.5s cubic-bezier(0.22,0.61,0.36,1) both;
}}
.strat-card:hover {{ border-color: {_GOLD}; transform: translateY(-2px); }}
.strat-item-title {{
  color: {_GREEN}; font-size: 0.72rem; font-weight: 800;
  letter-spacing: 1px; margin-bottom: 6px; text-transform: uppercase;
  font-family: 'Orbitron', sans-serif;
}}
.strat-item-desc {{ color: #ccc; font-size: 0.75rem; line-height: 1.5; }}
.strat-item-explanation {{
  color: #888; font-size: 0.68rem; line-height: 1.4; margin-top: 6px;
  border-top: 1px dashed #222; padding-top: 6px; font-style: italic;
}}

.za-stagger > *:nth-child(1) {{ animation-delay: 0.05s; }}
.za-stagger > *:nth-child(2) {{ animation-delay: 0.12s; }}
.za-stagger > *:nth-child(3) {{ animation-delay: 0.19s; }}
.za-stagger > *:nth-child(4) {{ animation-delay: 0.26s; }}
.za-stagger > *:nth-child(5) {{ animation-delay: 0.33s; }}
.za-stagger > *:nth-child(6) {{ animation-delay: 0.4s; }}

@keyframes zaReveal {{
  from {{ opacity: 0; transform: translateY(12px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes zaPulse {{
  0%, 100% {{ box-shadow: 0 0 0 0 rgba(229,9,20,0.45); }}
  50% {{ box-shadow: 0 0 12px 2px rgba(229,9,20,0.55); }}
}}
@keyframes zaHolo {{
  0% {{ text-shadow: 0 0 8px rgba(212,175,55,0.4); }}
  50% {{ filter: brightness(1.15); text-shadow: 0 0 16px rgba(212,175,55,0.55); }}
  100% {{ text-shadow: 0 0 8px rgba(212,175,55,0.4); }}
}}
.za-holo-stamp {{
  display: inline-block; font-family: 'Orbitron', sans-serif; font-weight: 900;
  font-size: 1.05rem; letter-spacing: 2px; padding: 6px 14px;
  border: 2px solid {_GOLD}; color: {_GOLD};
  background: linear-gradient(135deg, rgba(212,175,55,0.12), rgba(212,175,55,0.08));
  transform: rotate(-4deg); animation: zaHolo 3.2s ease-in-out infinite;
}}
.za-risk-pulse {{
  display: inline-block; font-family: 'Orbitron', sans-serif; font-weight: 800;
  font-size: 0.72rem; letter-spacing: 1.5px; padding: 4px 10px;
  border: 1px solid {_RED}; color: {_RED}; background: rgba(229,9,20,0.12);
  animation: zaPulse 1.6s ease-in-out infinite;
}}
.za-split {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 12px 0;
}}
.za-bull {{
  background: rgba(0,255,136,0.06); border: 1px solid rgba(0,255,136,0.35);
  padding: 12px; position: relative;
}}
.za-bear {{
  background: rgba(229,9,20,0.06); border: 1px solid rgba(229,9,20,0.4);
  padding: 12px; position: relative;
}}
.za-metric-grid {{
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
  background: {_BG}; padding: 10px; margin-top: 10px;
}}
.za-agent-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px; margin-top: 14px;
}}
.safe-points-banner {{
  background: rgba(10,10,10,0.92); border: 1px solid rgba(0,255,136,0.28);
  padding: 14px 18px; margin-bottom: 18px; position: relative;
}}
.safe-point-badge {{
  display: inline-block; padding: 3px 8px; font-weight: 800; font-size: 0.65rem;
  letter-spacing: 1px; margin-bottom: 6px; text-transform: uppercase;
}}
.sp-buy {{ background: rgba(0,255,136,0.12); color: {_GREEN}; border: 1px solid {_GREEN}; }}
.sp-target {{ background: rgba(212,175,55,0.12); color: {_GOLD}; border: 1px solid {_GOLD}; }}
.sp-stop {{ background: rgba(229,9,20,0.12); color: {_RED}; border: 1px solid {_RED}; }}
.sp-size {{ background: rgba(212,175,55,0.12); color: {_GOLD_ACCENT}; border: 1px solid {_GOLD_ACCENT}; }}
.sp-val {{
  color: {_WHITE}; font-size: 1.05rem; font-weight: 900;
  font-family: 'Orbitron', sans-serif; margin-bottom: 4px;
}}
.sp-desc {{ color: #aaa; font-size: 0.72rem; line-height: 1.45; }}
.strat-bubble-title {{
  color: {_GOLD}; font-family: 'Orbitron', sans-serif; font-weight: 800;
  font-size: 0.85rem; letter-spacing: 2px; text-transform: uppercase;
}}
@media (max-width: 720px) {{
  .za-split, .za-metric-grid {{ grid-template-columns: 1fr 1fr; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .za-hud, .digital-card, .strat-card, .za-holo-stamp, .za-risk-pulse {{
    animation: none !important;
  }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _hud_wrap(inner: str, extra_class: str = "") -> str:
    return (
        f'<div class="za-hud digital-card {extra_class}">'
        f'<span class="za-corner-tr"></span><span class="za-corner-bl"></span>'
        f'<div class="za-scan"></div><div class="za-body">{inner}</div></div>'
    )


# ── TradingAgents Multi-Agent Consensus ─────────────────────────────────────


def render_trading_agents_panel(agent_consensus: dict | None = None):
    """Renders multi-agent collaborative debate and consensus verdict card."""
    if not agent_consensus or not isinstance(agent_consensus, dict):
        return

    _inject_cyber_css()

    verdict = agent_consensus.get("verdict", "NEUTRAL")
    conf = agent_consensus.get("overall_confidence", 50.0)
    debate = agent_consensus.get("debate_summary", "")
    agents = agent_consensus.get("agents", {})

    v_color = (
        _GREEN2
        if "BULLISH" in str(verdict)
        else (_RED if "BEARISH" in str(verdict) else _GOLD)
    )

    agents_html = ""
    for role_key, agent_data in (agents or {}).items():
        if not isinstance(agent_data, dict):
            continue
        name = _esc(agent_data.get("agent", role_key.title()))
        bias = agent_data.get("bias", agent_data.get("risk_rating", "NEUTRAL"))
        agent_conf = agent_data.get("confidence", 50.0)
        reasoning = _esc(agent_data.get("reasoning", ""))
        b_color = (
            _GREEN2
            if bias in ["BULLISH", "LOW"]
            else (_RED if bias in ["BEARISH", "HIGH"] else _GOLD)
        )
        agents_html += f"""
<div class="digital-card za-stagger" style="margin:0;">
  <div style="display:flex;justify-content:space-between;font-size:0.65rem;font-weight:800;color:#aaa;">
    <span class="label-grey">{name.upper()}</span>
    <span style="color:{b_color};">{_esc(bias)} ({_esc(agent_conf)}%)</span>
  </div>
  <p style="font-size:0.62rem;color:#888;margin:4px 0 0 0;line-height:1.3;">{reasoning}</p>
</div>"""

    # Split bull/bear agent columns when biases present
    bulls, bears, others = [], [], []
    for role_key, agent_data in (agents or {}).items():
        if not isinstance(agent_data, dict):
            continue
        bias = str(agent_data.get("bias", agent_data.get("risk_rating", "NEUTRAL")))
        if bias in ("BULLISH", "LOW"):
            bulls.append(agent_data)
        elif bias in ("BEARISH", "HIGH"):
            bears.append(agent_data)
        else:
            others.append(agent_data)

    inner = f"""
<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.08);padding-bottom:10px;margin-bottom:12px;flex-wrap:wrap;gap:10px;">
  <div>
    <p class="gold-title" style="margin:0;">🤖 TRADINGAGENTS MULTI-AGENT CONSENSUS</p>
    <p class="label-grey">ROLES: FUNDAMENTAL · TECHNICAL · SENTIMENT · RISK MANAGER</p>
  </div>
  <div style="text-align:right;">
    {zero_badge(verdict)}
    <div class="label-grey" style="margin-top:6px;">Confidence: <b style="color:{_WHITE};">{_esc(conf)}%</b></div>
  </div>
</div>
<p style="font-size:0.7rem;color:#ccc;line-height:1.5;font-style:italic;background:{_BG};padding:8px 12px;border-left:2px solid {_GOLD};">
  💬 <b style="color:{_GOLD};">Consensus Debate:</b> {_esc(debate)}
</p>
<div class="za-agent-grid za-stagger">{agents_html}</div>
"""
    st.markdown(_hud_wrap(inner), unsafe_allow_html=True)


# ── QuantDinger Strategy Setup ──────────────────────────────────────────────


def render_quantdinge_strategy_card(quant_strategy: dict | None = None):
    """Renders QuantDinger quantitative regime & actionable strategy recommendation."""
    if not quant_strategy or not isinstance(quant_strategy, dict):
        return

    _inject_cyber_css()

    idx = quant_strategy.get("index", "INDEX")
    regime = quant_strategy.get("regime_label", "NEUTRAL")
    strat_name = quant_strategy.get("strategy_name", "Strategy Setup")
    action = quant_strategy.get("action", "HOLD")
    entry = quant_strategy.get("entry_price", 0.0)
    sl = quant_strategy.get("stop_loss", 0.0)
    tp1 = quant_strategy.get("take_profit_1", 0.0)
    tp2 = quant_strategy.get("take_profit_2", 0.0)
    rr = quant_strategy.get("risk_reward_ratio", "1:2")
    win_prob = quant_strategy.get("win_probability_pct", 65.0)
    pos_size = quant_strategy.get("position_size_pct", 3.0)
    desc = quant_strategy.get("description", "")

    act_color = (
        _GREEN2
        if "BUY" in str(action)
        else (_RED if "SELL" in str(action) else _GOLD_ACCENT)
    )

    entry_type = quant_strategy.get("nautilus_entry_order_type", "DAY LIMIT")
    bracket = quant_strategy.get("nautilus_bracket_type", "GTC OCO")
    uw_note = quant_strategy.get("options_flow_note", "")
    pcr_val = quant_strategy.get("pcr", 1.0)

    inner = f"""
<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(212,175,55,0.2);padding-bottom:8px;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
  <div>
    <p class="gold-title" style="color:{_GOLD_ACCENT};margin:0;">⚡ QUANTDINGER ENGINE · {_esc(idx)} STRATEGY</p>
    <p class="label-grey">Regime: <b style="color:{_WHITE};">{_esc(regime)}</b></p>
  </div>
  {zero_badge_row(regime, action)}
</div>
<div style="font-size:0.85rem;font-weight:800;color:{_WHITE};margin-bottom:6px;font-family:'Orbitron',sans-serif;">🎯 {_esc(strat_name)}</div>
<p class="label-grey" style="text-transform:none;letter-spacing:0;color:#aaa;margin-bottom:12px;">{_esc(desc)}</p>
<div class="za-metric-grid za-stagger" style="text-align:center;">
  <div class="strat-card" style="margin:0;">
    <div class="label-grey">ENTRY PRICE</div>
    <div class="sp-val" style="font-size:0.85rem;">{_esc(entry)}</div>
  </div>
  <div class="strat-card" style="margin:0;">
    <div class="label-grey" style="color:{_RED};">STOP LOSS (SL)</div>
    <div class="sp-val" style="font-size:0.85rem;color:{_RED};">{_esc(sl)}</div>
  </div>
  <div class="strat-card" style="margin:0;">
    <div class="label-grey" style="color:{_GREEN2};">TARGET (TP1 / TP2)</div>
    <div class="sp-val" style="font-size:0.85rem;color:{_GREEN2};">{_esc(tp1)} / {_esc(tp2)}</div>
  </div>
  <div class="strat-card" style="margin:0;">
    <div class="label-grey" style="color:{_GOLD};">R:R / WIN PROB</div>
    <div class="sp-val" style="font-size:0.85rem;color:{_GOLD};">{_esc(rr)} · {_esc(win_prob)}%</div>
  </div>
</div>
<div style="background:{_BG};padding:8px 12px;margin-top:8px;font-size:0.6rem;color:#aaa;">
  <b style="color:{_GOLD_ACCENT};">Entry Order:</b> {_esc(entry_type)} &nbsp;·&nbsp;
  <b style="color:{_GOLD};">Bracket:</b> {_esc(bracket)}<br>
  <b style="color:{_GREY};">PCR {_esc(pcr_val)}</b> — {_esc(uw_note)}
</div>
<div class="label-grey" style="text-align:right;margin-top:6px;">Recommended Max Risk Allocation: {_esc(pos_size)}% Portfolio</div>
"""
    st.markdown(_hud_wrap(inner), unsafe_allow_html=True)


# ── ForexFactory Priority #1 ────────────────────────────────────────────────


def render_forexfactory_priority_card(news_feed: list | None = None):
    """Renders ForexFactory Priority #1 Macro Economic News Banner."""
    ff_items = [
        n
        for n in (news_feed or [])
        if isinstance(n, dict)
        and (
            str(n.get("source", "")).startswith("ForexFactory")
            or n.get("is_forexfactory")
            or n.get("priority") == 1
        )
    ]
    if not ff_items:
        return

    _inject_cyber_css()

    cards_html = ""
    for i, item in enumerate(ff_items[:3]):
        title = _esc(item.get("title", ""))
        link = _esc(item.get("link", "#"))
        published = _esc(item.get("published", ""))
        ccy = _esc(item.get("currency", "MACRO"))
        delay = 0.08 * (i + 1)
        cards_html += f"""
<div class="digital-card" style="margin-top:6px;margin-bottom:0;border-left:3px solid {_RED};padding:8px 12px;animation-delay:{delay}s;">
  <div style="font-size:0.75rem;font-weight:600;color:#eee;">
    <span style="color:{_GOLD};font-size:0.65rem;font-weight:800;margin-right:6px;">[{ccy}]</span>
    <a href="{link}" target="_blank" style="color:{_WHITE};text-decoration:none;">{title}</a>
  </div>
  <div class="label-grey" style="margin-top:2px;text-transform:none;">Released / Scheduled: {published}</div>
</div>"""

    inner = f"""
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
  <p class="gold-title" style="color:{_RED};margin:0;">🔴 FOREXFACTORY MACRO FEED · PRIORITY #1</p>
  <span class="za-risk-pulse">HIGH IMPACT CALENDAR</span>
</div>
{cards_html}
"""
    st.markdown(_hud_wrap(inner), unsafe_allow_html=True)


# ── Agent Debate (V1.1 schema) ──────────────────────────────────────────────


def render_agent_debate_panel(debate_data: dict | None) -> None:
    """Render the V1.1 bull/bear/PM agent debate verdict."""
    if not debate_data or not isinstance(debate_data, dict):
        return

    _inject_cyber_css()

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
        _GREEN2 if action == "LONG" else (_RED if action == "SHORT" else _GOLD)
    )
    risk_color = {
        "LOW": _GREEN2,
        "MODERATE": _GOLD,
        "HIGH": _RED,
        "EXTREME": _RED,
    }.get(str(risk_level), _GOLD)

    def _args_list(case: dict) -> str:
        args = case.get("arguments") or []
        if not args:
            return f"<li style='color:{_GREY};'>No explicit arguments</li>"
        return "".join(
            f"<li style='color:#aaa;font-size:0.6rem;line-height:1.4;margin:3px 0;'>{_esc(a)}</li>"
            for a in args[:4]
        )

    risk_notes = "".join(
        f"<li style='color:#888;font-size:0.6rem;line-height:1.4;margin:3px 0;'>{_esc(n)}</li>"
        for n in (risk.get("notes") or [])[:3]
    )

    bull_str = _num(bull.get("strength"), 0.0, 2)
    bear_str = _num(bear.get("strength"), 0.0, 2)
    model_tag = "🟢 LLM" if llm_used else "⚪ heuristic"

    inner = f"""
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:10px;">
  <div>
    <p class="gold-title" style="color:{_GREEN2};margin:0;">🤖 AGENT DEBATE · PM VERDICT</p>
    <p class="label-grey">Model: {_esc(model)} {model_tag}</p>
  </div>
  <div style="text-align:right;">
    {zero_badge(action)}
    <div class="label-grey" style="margin-top:6px;">Conviction {conviction * 100:.0f}%</div>
  </div>
</div>

<div class="za-split za-stagger">
  <div class="za-bull strat-card" style="margin:0;">
    <div class="label-grey" style="color:{_GREEN};">📈 BULL CASE</div>
    <div class="sp-val" style="color:{_GREEN};font-size:0.9rem;">{bull_str:.2f}</div>
    <ul style="margin:0;padding-left:14px;">{_args_list(bull)}</ul>
  </div>
  <div class="za-bear strat-card" style="margin:0;">
    <div class="label-grey" style="color:{_RED};">📉 BEAR CASE</div>
    <div class="sp-val" style="color:{_RED};font-size:0.9rem;">{bear_str:.2f}</div>
    <ul style="margin:0;padding-left:14px;">{_args_list(bear)}</ul>
  </div>
</div>

<div class="digital-card" style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
  <div>
    <div class="label-grey" style="color:{risk_color};">🛡 RISK LEVEL</div>
    <span class="za-risk-pulse" style="border-color:{risk_color};color:{risk_color};margin-top:6px;">{_esc(risk_level)}</span>
    <ul style="margin:8px 0 0 0;padding-left:14px;">{risk_notes or f"<li style='color:{_GREY};font-size:0.6rem;'>—</li>"}</ul>
  </div>
</div>

<div style="background:{_BG};padding:10px;border-left:3px solid {act_color};margin-top:10px;">
  <div style="font-size:0.65rem;color:#ccc;line-height:1.5;"><b style="color:{_GOLD};">Reasoning:</b> {_esc(reasoning)}</div>
  <div class="label-grey" style="margin-top:6px;text-transform:none;"><b>Kill condition:</b> {_esc(kill)}</div>
  <div class="label-grey" style="text-transform:none;"><b>Suggested sizing:</b> {sizing}% of portfolio</div>
</div>
"""
    st.markdown(_hud_wrap(inner), unsafe_allow_html=True)


# ── Quantum Strategy & Dynamic Risk Advisory (bubbles) ──────────────────────


def render_trading_strategy_bubbles(matrix=None, news_feed=None):
    """Renders the dynamic Strategy & Risk Management Advisory component in the
    Trading Terminal, analyzing live market inputs, global news intelligence,
    and computing precise safe entry/exit/stop-loss points with detailed explanations.
    """
    _inject_cyber_css()

    if matrix is None:
        matrix = st.session_state.get("matrix") or {}
    if news_feed is None:
        news_feed = st.session_state.get("news_feed") or []

    col_hdr1, col_hdr2 = st.columns([2, 1])
    with col_hdr1:
        st.markdown(
            """
        <div class="strat-bubble-title gold-title">
            <span>⚡ QUANTUM STRATEGY & DYNAMIC RISK ADVISORY</span>
        </div>
        <p class="label-grey" style="margin:2px 0 12px 0;text-transform:none;letter-spacing:0;color:#888;">
            Live market intelligence analysis, calculated safe entry/exit bounds, and actionable strategy suggestions.
        </p>
        """,
            unsafe_allow_html=True,
        )
    with col_hdr2:
        selected_index = st.radio(
            "Target Index",
            ["NIFTY 50", "BANKNIFTY", "SENSEX"],
            horizontal=True,
            key="strat_advisory_index",
            label_visibility="collapsed",
        )

    idx_data = matrix.get(selected_index, {}) if isinstance(matrix, dict) else {}
    if not isinstance(idx_data, dict):
        idx_data = {}

    spot = float(idx_data.get("prev_close") or 24000.0)
    pred_high = float(idx_data.get("pred_high") or (spot * 1.008))
    pred_low = float(idx_data.get("pred_low") or (spot * 0.992))
    vix = float(idx_data.get("vix") or 15.0)
    pcr = float(idx_data.get("pcr") or 1.0)
    sentiment_score = float(idx_data.get("sentiment_score") or 0.0)
    movement_side = idx_data.get("movement_side", "Neutral / Live Session")
    confidence = float(idx_data.get("confidence") or 80.0)

    top_news_category = "GENERAL"
    max_impact = 0.0
    breaking_count = 0

    if news_feed and isinstance(news_feed, list):
        for item in news_feed:
            if isinstance(item, dict):
                imp = item.get("impact_score", 0) or 0
                try:
                    imp_f = float(imp)
                except (TypeError, ValueError):
                    imp_f = 0.0
                if imp_f > max_impact:
                    max_impact = imp_f
                    top_news_category = item.get("category_label", "GLOBAL MACRO")
                if item.get("is_high_impact"):
                    breaking_count += 1

    total_range = max(10.0, pred_high - pred_low)
    safe_buy_low = round(pred_low, 1)
    safe_buy_high = round(pred_low + total_range * 0.22, 1)
    safe_target_low = round(pred_high - total_range * 0.22, 1)
    safe_target_high = round(pred_high, 1)
    stop_loss = round(pred_low - (spot * 0.0035), 1)
    stop_loss_pts = round(spot - stop_loss, 1)

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

    risk_pts = max(10.0, spot - safe_buy_low)
    reward_pts = max(10.0, safe_target_high - spot)
    rr_ratio = round(reward_pts / risk_pts, 2)

    banner = f"""
<div class="safe-points-banner za-hud digital-card" style="margin-bottom:18px;">
  <span class="za-corner-tr"></span><span class="za-corner-bl"></span>
  <div class="za-scan"></div>
  <div class="za-body">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px;">
      <div>
        <span class="gold-title" style="font-size:0.8rem;">🎯 LIVE ANALYSIS FOR {_esc(selected_index)}</span>
        <span class="label-grey" style="margin-left:8px;text-transform:none;">
          Spot Ref: <b style="color:{_WHITE};">{spot:,.1f}</b> |
          Vector: <b style="color:{_GREEN};">{_esc(movement_side)}</b> |
          Reg: <b style="color:{_GOLD};">{_esc(vol_regime)}</b>
        </span>
      </div>
      <div class="label-grey" style="text-transform:none;">
        Confidence: <b style="color:{_GREEN};">{confidence:.0f}%</b> |
        Risk-Reward Ratio: <b style="color:{_GOLD};">1 : {rr_ratio}</b>
      </div>
    </div>
    <div class="za-metric-grid za-stagger" style="grid-template-columns:repeat(auto-fit,minmax(210px,1fr));background:transparent;padding:0;">
      <div class="strat-card" style="border-left:3px solid {_GREEN};margin:0;">
        <span class="safe-point-badge sp-buy">🟢 SAFE BUY / ACCUMULATION ZONE</span>
        <div class="sp-val">{safe_buy_low:,.1f} – {safe_buy_high:,.1f}</div>
        <div class="sp-desc">Optimal low-risk entry near support level ({pred_low:,.1f}). Do not chase green candles above {safe_buy_high:,.1f}.</div>
      </div>
      <div class="strat-card" style="border-left:3px solid {_GOLD};margin:0;">
        <span class="safe-point-badge sp-target">🎯 TARGET / PROFIT BOOKING ZONE</span>
        <div class="sp-val">{safe_target_low:,.1f} – {safe_target_high:,.1f}</div>
        <div class="sp-desc">Scale out long positions near resistance ({pred_high:,.1f}) as call-side options friction increases.</div>
      </div>
      <div class="strat-card" style="border-left:3px solid {_RED};margin:0;">
        <span class="safe-point-badge sp-stop">🛑 HARD INVALIDATION / STOP-LOSS</span>
        <div class="sp-val">{stop_loss:,.1f}</div>
        <div class="sp-desc">Strict intraday exit trigger ({stop_loss_pts:.0f} pts below spot). A 15-min candle close below invalidates the bullish thesis.</div>
      </div>
      <div class="strat-card" style="border-left:3px solid {_GOLD_ACCENT};margin:0;">
        <span class="safe-point-badge sp-size">⚖️ REC. POSITION SIZE & CASH</span>
        <div class="sp-val">{rec_size_pct}</div>
        <div class="sp-desc">Allocate max {rec_size_pct} capital per trade. Keep <b>{cash_buffer_pct}%</b> cash buffer for unexpected headline spikes.</div>
      </div>
    </div>
  </div>
</div>
"""
    st.markdown(banner, unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(
        [
            "🛡️ DEFENSIVE RISK MANAGEMENT",
            "🌐 PORTFOLIO DIVERSIFICATION",
            "📈 VOLATILITY TRADING STRATEGIES",
            "🧠 FILTER OUT SHORT-TERM NOISE",
        ]
    )

    def _card(title: str, desc: str, explanation: str) -> str:
        return f"""
<div class="strat-card digital-card">
  <div class="strat-item-title">{title}</div>
  <div class="strat-item-desc">{desc}</div>
  <div class="strat-item-explanation">{explanation}</div>
</div>"""

    with t1:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                _card(
                    "🎯 Position Sizing",
                    f"Limit single trade allocations to <b>{rec_size_pct}</b> of total capital.",
                    f"<b>Market Context:</b> Current VIX is <b>{vix:.1f}</b> with max news impact score at <b>{max_impact:.0f}/100</b>. High news volatility requires capped position sizes to prevent tail-risk drawdowns.",
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _card(
                    "🛑 Stop-Loss Triggers",
                    f"Set automated stop-loss at <b>{stop_loss:,.1f}</b> (-{stop_loss_pts:.0f} pts).",
                    f"<b>Market Context:</b> Placed 0.35% below lower predicted envelope ({pred_low:,.1f}) to avoid getting stopped out by regular intraday noise spikes.",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            trail = spot + (total_range * 0.4)
            st.markdown(
                _card(
                    "📈 Trailing Stop-Losses",
                    f"Activate trailing trigger once price reaches <b>{trail:,.1f}</b>.",
                    f"<b>Market Context:</b> Locks in gains automatically as price moves into the upper target expansion band ({pred_high:,.1f}), protecting accumulated profits.",
                ),
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                _card(
                    "💵 Cash Buffer Allocation",
                    f"Maintain liquid cash buffer of at least <b>{cash_buffer_pct}%</b>.",
                    f"<b>Market Context:</b> High breaking news frequency ({breaking_count} breaking stories) creates unexpected liquidity dips—cash lets you buy premium assets at a discount.",
                ),
                unsafe_allow_html=True,
            )

    with t2:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                _card(
                    "📊 Asset Allocation",
                    "Spread capital: <b>55% Equities</b>, <b>25% Debt/Bonds</b>, <b>20% Gold/Cash</b>.",
                    f"<b>Market Context:</b> Sentiment score is <b>{sentiment_score:+.2f}</b> with GIFT Nifty premium active. Balancing equities with gold insulates portfolio against overnight gap risks.",
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _card(
                    "🌍 Geographic Spread",
                    "Hedge local domestic market moves with international global exposure.",
                    f"<b>Market Context:</b> Top headline driver is <b>{_esc(top_news_category)}</b>. Global macro events impact EM liquidity regardless of domestic fundamentals.",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _card(
                    "🔄 Sector Rotation",
                    "Rotate between defensive (FMCG/Pharma) & cyclical (IT/Banking).",
                    f"<b>Market Context:</b> For <b>{_esc(selected_index)}</b>, news sentiment signals sector tilt. Rotate into defensive sectors when VIX spikes above 16.0.",
                ),
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                _card(
                    "⚖️ Inverse Correlation",
                    "Hold Sovereign Gold Bonds or Gold ETFs to offset equity sell-offs.",
                    "<b>Market Context:</b> Gold traditionally spikes during geopolitical or inflation news flashes, serving as an automated portfolio buffer.",
                ),
                unsafe_allow_html=True,
            )

    with t3:
        c1, c2, c3, c4 = st.columns(4)
        put_line = (
            "Buy protective OTM Put options."
            if pcr > 1.25
            else "Hedge long stock holdings with Put options."
        )
        put_ctx = (
            "High PCR (>1.25) signals overbought call accumulation—protective Puts insure against sudden mean-reversion drops."
            if pcr > 1.25
            else "PCR indicates balanced open interest; light hedging advised."
        )
        with c1:
            st.markdown(
                _card(
                    "🛡️ Options Hedging",
                    f"PCR is <b>{pcr:.2f}</b> — {put_line}",
                    f"<b>Market Context:</b> {put_ctx}",
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _card(
                    "🎯 Straddles & Strangles",
                    "Deploy Long Straddle prior to Central Bank / Budget releases.",
                    f"<b>Market Context:</b> Major news category (<b>{_esc(top_news_category)}</b>) causes violent non-directional volatility spikes—straddles profit from explosive moves in either direction.",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _card(
                    "⏳ Dollar-Cost Averaging",
                    f"Execute systematic DCA accumulation on every <b>-{total_range * 0.15:.0f} pt</b> dip.",
                    "<b>Market Context:</b> Smooths out purchase costs during volatile regimes, preventing emotional top-of-range buying.",
                ),
                unsafe_allow_html=True,
            )
        with c4:
            vix_note = (
                "VIX is calm—options premiums are cheap for hedging."
                if vix < 15
                else "VIX is elevated—implied volatility is high; sell credit spreads or wait for VIX to peak before buying calls."
            )
            st.markdown(
                _card(
                    "📊 VIX Monitoring",
                    f"Track India VIX ({vix:.1f}) for volatility extremes.",
                    f"<b>Market Context:</b> {vix_note}",
                ),
                unsafe_allow_html=True,
            )

    with t4:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                _card(
                    "🔍 Focus on Fundamentals",
                    "Trust multi-quarter earnings & GDP growth over intraday news spikes.",
                    "<b>Market Context:</b> Algorithmic news headline bots create initial knee-jerk gaps that typically mean-revert back to fundamental earnings trends.",
                ),
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                _card(
                    "🧊 Avoid Panic Selling",
                    "Wait <b>15–20 mins</b> post 9:15 AM open before executing pre-market orders.",
                    "<b>Market Context:</b> The first 15 minutes of the session reflect retail panic and HFT liquidity harvesting. Wait for institutional order flow to stabilize.",
                ),
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                _card(
                    "🔭 Review Multi-Year Horizons",
                    "Align core portfolio positions with 5 to 10-year structural growth trends.",
                    "<b>Market Context:</b> Short-term news sentiment impact dissipates within 1 to 3 trading sessions—long-term compounding dominates multi-year horizons.",
                ),
                unsafe_allow_html=True,
            )
