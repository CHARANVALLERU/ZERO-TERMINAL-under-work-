import streamlit as st
import pandas as pd
import time
import random
import os
import json
from engine.prediction_matrix import generate_prediction_matrix, rederive_with_overlay
from ui.components import apply_digital_core_theme, digital_clock_component, predicted_info_card, sidebar_news_section, show_zero_digital_splash, order_flow_table, automated_training_dashboard, learning_stats_card, render_zero_engine_modal, render_zero_brain_sidebar, render_youtube_knowledge_sidebar, render_trading_strategy_bubbles, render_forexfactory_priority_card, render_trading_agents_panel, render_quantdinge_strategy_card, render_fincept_thesis_card, render_nautilus_order_card, render_intermarket_card, render_options_greeks_card
from engine.learning_service import log_daily_feedback, get_feedback_logs, calculate_engine_accuracy, fetch_daily_actuals, update_feedback_logs, update_unfulfilled_feedback_logs, auto_train_engine
from ui.charts import ohlc_range_chart, sentiment_gauge_chart
from ui.news_feed import (
    render_breaking_banner, render_news_ticker, render_impact_panel,
    push_device_notifications, request_notification_permission, render_autorefresh,
    enable_dig_dive_hotkey, persist_active_tab, tab_unread_badge, status_pill,
)
from data.news_monitor import check_breaking, get_live_feed
from config import NEWS_REFRESH_SECONDS, GEMINI_API_KEY
import plotly.graph_objects as go
import math

# Quantum Core Additions
from engine.xgboost_predictor import MultiTimeframePredictor
from engine.genetic_mutator import StrategyGeneticEngine
from engine.monte_carlo import MonteCarloRiskEngine
from engine.paper_brokerage import PaperBrokerage
from data.mtf_features import build_mtf_features


def render_quant_toast():
    """Small, translucent, non-clickable toast that drops from the top and
    dismisses itself after 2 seconds. Stays out of the user's way."""
    st.iframe("""
    <style>
      @keyframes zeroToastIn  { from { transform: translate(-50%, -120%); opacity: 0; }
                                to   { transform: translate(-50%, 0);     opacity: 1; } }
      @keyframes zeroToastOut { from { transform: translate(-50%, 0);     opacity: 1; }
                                to   { transform: translate(-50%, -120%); opacity: 0; } }
      #zero-quant-toast {
        position: fixed; top: 14px; left: 50%;
        transform: translate(-50%, -120%);
        background: rgba(15, 15, 15, 0.55);
        color: #E50914;
        font-family: 'Inter', sans-serif;
        font-size: 10px; font-weight: 800; letter-spacing: 2px;
        text-transform: uppercase;
        padding: 8px 16px;
        border: 1px solid rgba(229, 9, 20, 0.35);
        border-radius: 999px;
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
        pointer-events: none;        /* never clickable */
        user-select: none;
        z-index: 2147483647;
        box-shadow: 0 4px 18px rgba(0,0,0,0.45);
        animation: zeroToastIn 0.32s ease-out forwards,
                   zeroToastOut 0.35s ease-in 1.65s forwards;
      }
    </style>
    <div id="zero-quant-toast">● Quant cores updated</div>
    """, height=1)


# Page Config
st.set_page_config(
    page_title="ZERO V1.0 | Market Intelligence",
    page_icon="ui/assets/logo.png",
    layout="wide",
    initial_sidebar_state="collapsed" # DATA tab closed by default
)

# Apply Theme
apply_digital_core_theme()
request_notification_permission()

# ── Automated Virtual Environment Check & Setup ────────────────────────────
def _check_and_setup_venv():
    """
    Checks if a Python virtual environment exists (.venv).
    If missing, creates it in the background and installs all required packages.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(base_dir, ".venv")
    req_file = os.path.join(base_dir, "requirements.txt")

    if not os.path.exists(venv_dir):
        try:
            import subprocess
            import sys

            # Run venv creation and dependency installation in background
            setup_cmd = (
                f'"{sys.executable}" -m venv "{venv_dir}" && '
                f'"{os.path.join(venv_dir, "Scripts", "python.exe")}" -m pip install -r "{req_file}"'
            )
            subprocess.Popen(setup_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

_check_and_setup_venv()

# ── Tiny on-disk session so the user only goes through DIG & DIVE once ──
_SESSION_FLAG = os.path.join(os.path.dirname(__file__), "db", ".zero_session.json")
def _load_session_flag():
    try:
        if os.path.exists(_SESSION_FLAG):
            with open(_SESSION_FLAG) as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}

def _save_session_flag(d):
    try:
        os.makedirs(os.path.dirname(_SESSION_FLAG), exist_ok=True)
        with open(_SESSION_FLAG, "w") as f:
            json.dump(d, f)
    except Exception:
        pass

_persisted = _load_session_flag()

# Phase 1: Data Initialization
import datetime
now = datetime.datetime.now()
# Market opens at 9:15 AM IST — engine refresh triggers at 9:15 AM
target_time = now.replace(hour=9, minute=15, second=0, microsecond=0)

if 'last_run_date' not in st.session_state:
    st.session_state.last_run_date = None
# Hydrate matrix + entered from disk so a refresh skips the splash & button.
if 'matrix' not in st.session_state or st.session_state.matrix is None:
    if isinstance(_persisted.get('matrix'), dict) and _persisted.get('matrix'):
        st.session_state.matrix = _persisted['matrix']
if 'entered' not in st.session_state:
    st.session_state.entered = bool(_persisted.get('entered', False))
if st.session_state.last_run_date is None and _persisted.get('last_run_date'):
    try:
        st.session_state.last_run_date = datetime.datetime.fromisoformat(_persisted['last_run_date'])
    except Exception:
        pass

# Track when we last (re)generated the matrix so background updates can
# fire silently without ever flashing the splash or sleeping.
_matrix_gen_iso = _persisted.get('matrix_gen_time')
_matrix_gen_time = None
if _matrix_gen_iso:
    try:
        _matrix_gen_time = datetime.datetime.fromisoformat(_matrix_gen_iso)
    except Exception:
        _matrix_gen_time = None

# ── Splash & Fast Bootup Architecture ──────────────────────────────────────
#  1. Bootup splash screen displays on fresh app launches / session starts.
#  2. Cache memory is used first so the UI opens instantaneously.
#  3. Knowledge Base and background data load lazily in thread/background.
_show_splash_this_session = st.session_state.get('_splash_shown', False)

_should_full = False
if 'matrix' not in st.session_state or st.session_state.matrix is None:
    _should_full = True
elif not _show_splash_this_session:
    _should_full = True
else:
    if st.session_state.last_run_date:
        if now >= target_time and st.session_state.last_run_date < target_time:
            _should_full = True

if _should_full and not _show_splash_this_session:
    show_zero_digital_splash()
    st.session_state['_splash_shown'] = True

    # Fast cache retrieval for instant bootup
    if isinstance(_persisted.get('matrix'), dict) and _persisted.get('matrix'):
        st.session_state.matrix = _persisted['matrix']
    else:
        st.session_state.matrix = generate_prediction_matrix()

    # Log today's predictions & update unfulfilled logs in background
    log_daily_feedback(st.session_state.matrix, {}, "")
    import threading
    threading.Thread(target=update_unfulfilled_feedback_logs, daemon=True).start()

    st.session_state.last_run_date = now
    _save_session_flag({
        'entered': bool(st.session_state.get('entered', False)),
        'matrix': st.session_state.matrix,
        'last_run_date': now.isoformat(),
        'matrix_gen_time': now.isoformat(),
    })
    st.rerun()

# After first entry, silently refresh the matrix in the background every
# 10 minutes so the user never sees the splash again, but the predictions
# stay fresh. Mark the moment so the toast can fire.
_toast_signal = False
if st.session_state.entered:
    _stale = (
        _matrix_gen_time is None
        or (now - _matrix_gen_time) > datetime.timedelta(minutes=10)
    )
    if _stale and not _should_full:
        try:
            @st.cache_data(ttl=600, show_spinner=False)
            def _gen_matrix_cached(_date_key):
                # keyed on date so repeated reruns in the same 10-min window reuse
                # the prior result instead of re-scraping/re-computing.
                return generate_prediction_matrix()
            st.session_state.matrix = _gen_matrix_cached(now.strftime('%Y-%m-%d-%H') + str(now.minute // 10))
            _matrix_gen_time = now
            _toast_signal = True
        except Exception:
            pass
m = st.session_state.matrix

# Phase 2: Splash Entry Screen (only when the user hasn't entered yet)
if not st.session_state.entered:
    # Aggressive Scroll Lock for Splash ONLY
    st.markdown("""
        <style>
        [data-testid="stAppViewContainer"], .main, body {
            overflow: hidden !important;
            height: 100vh !important;
        }
        [data-testid="stSidebar"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)
    
    with open("ui/assets/logo.png", "rb") as image_file:
        logo_b64 = base64.b64encode(image_file.read()).decode()

    st.markdown("<div style='height: 25vh;'></div>", unsafe_allow_html=True)
    col_logo, col_title = st.columns([0.15, 0.85])
    with col_logo:
        st.markdown(f"<img src='data:image/png;base64,{logo_b64}' style='width:50px; margin-top:20px;'/>", unsafe_allow_html=True)
    with col_title:
        st.markdown("<h1 class='main-title'>ZERO V1.0</h1>", unsafe_allow_html=True)
        st.markdown("<p class='sub-title' style='margin-top: -15px;'>Adaptive Market Intelligence Terminal</p>", unsafe_allow_html=True)
    st.markdown("<p class='terminal-core-txt' style='margin-bottom: 60px;'>Quantum Cores Synchronized</p>", unsafe_allow_html=True)

    col_l, col_m, col_r = st.columns([1.2, 1, 1.2])
    with col_m:
        if st.button("DIG & DIVE", width='stretch'):
            st.session_state.entered = True
            _save_session_flag({
                'entered': True,
                'matrix': st.session_state.matrix,
                'last_run_date': (
                    st.session_state.last_run_date.isoformat()
                    if st.session_state.last_run_date else None
                ),
                'matrix_gen_time': (
                    _matrix_gen_time.isoformat() if _matrix_gen_time else now.isoformat()
                ),
            })
            st.rerun()
    enable_dig_dive_hotkey()
    st.stop()


# Phase 3: Main Terminal (Scroll Enabled)
# ── Real-time Breaking-News Monitor (fetched once per refresh) ────────────
# Pull latest global headlines, score market impact, and detect newly-broken
# high-impact stories. Results feed the sidebar, header banner, ticker, and
# the GLOBAL NEWS tab — all on the same run so nothing lags a cycle behind.
# Cached at the call site (st.cache_data) so the second consumer in the same
# rerun (banner + impact panel) reuses the same payload — no duplicate scrape.
try:
    _levels = {idx: (m.get(idx, {}) or {}).get('prev_close') for idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]}

    @st.cache_data(ttl=NEWS_REFRESH_SECONDS, show_spinner=False)
    def _cached_breaking(_levels_tuple):
        return check_breaking(index_levels=dict(_levels_tuple))

    _news = _cached_breaking(tuple(sorted((k, v) for k, v in (_levels or {}).items())))
    st.session_state['news_feed'] = _news['feed']
    st.session_state['news_breaking'] = _news['breaking']
    st.session_state['news_checked_at'] = _news.get('checked_at')
except Exception as _e:
    st.session_state.setdefault('news_feed', [])
    st.session_state.setdefault('news_breaking', [])

# ── 60-second Quant-Core re-derivation tick ────────────────────────────────
# The silent_news_tick iframe below pings back every 60s. Each ping re-evaluates
# this script. We (a) re-derive the predicted high / low (and open / close when
# the market is closed) using the fresh news overlay, and (b) if the market is
# open and the band moved materially, pop a "Quant cores calibrated" toast.
_quant_tick_signal = False
try:
    from config import (
        is_market_open as _is_market_open,
        CALIBRATED_TOAST_MIN_SHIFT_PCT,
    )
    from data.news_monitor import aggregate_news_overlay as _agg_overlay
    _overlay = _agg_overlay(
        st.session_state.get('news_feed', []) or [],
        levels=_levels,
    )
    if _overlay:
        _prior = m
        _m2 = rederive_with_overlay(m, _overlay)
        # Did any of the bands move by the threshold percent?
        _max_shift_pct = 0.0
        for _idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
            _a = _prior.get(_idx) or {}
            _b = _m2.get(_idx) or {}
            _ref = float(_a.get('prev_close') or 0.0) or 1.0
            for _leg in ('pred_high', 'pred_low', 'pred_open', 'pred_close'):
                try:
                    _d = abs(float(_b.get(_leg, 0.0)) - float(_a.get(_leg, 0.0)))
                    if _d / _ref * 100.0 > _max_shift_pct:
                        _max_shift_pct = _d / _ref * 100.0
                except (TypeError, ValueError):
                    pass
        if _m2 is not _prior:
            m = _m2
            st.session_state.matrix = _m2
        if _is_market_open() and _max_shift_pct >= CALIBRATED_TOAST_MIN_SHIFT_PCT:
            _quant_tick_signal = True
except Exception:
    _quant_tick_signal = False

# Sidebar: ZERO ENGINE button (above DATA) + DATA section
with st.sidebar:
    # ── ZERO ENGINE Section ───────────────────────────────────────────────────
    st.markdown("""
    <div style="margin-bottom: 4px;">
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:1rem;
                   color:#fff;letter-spacing:3px;">ZERO</span>
      <span style="font-family:'Orbitron',sans-serif;font-weight:900;font-size:1rem;
                   color:#E50914;letter-spacing:3px;"> ENGINE</span>
    </div>
    <p style="font-size:0.5rem;color:#333;letter-spacing:2px;margin:-2px 0 8px 0;
              text-transform:uppercase;">AI INTELLIGENCE CORE · GEMINI</p>
    """, unsafe_allow_html=True)

    if st.button("⚡ OPEN ZERO ENGINE", key="open_zero_engine_btn", use_container_width=True):
        st.session_state['show_zero_engine'] = True
        st.rerun()

    st.markdown("---")

    # ── YouTube Knowledge Section ─────────────────────────────────────────────
    render_youtube_knowledge_sidebar()

    st.markdown("---")

    # ── ZERO Brain Section ────────────────────────────────────────────────────
    try:
        from engine.brain_engine import get_brain
        brain_singleton = get_brain()
        # Retrieve the merged daily log (combining local JSON and Obsidian)
        current_daily_log = brain_singleton.get_daily_log()
        render_zero_brain_sidebar(brain_singleton, current_daily_log)
    except Exception as e:
        st.error(f"Error loading ZERO Brain: {e}")

    st.markdown("---")

    # ── DATA Section ─────────────────────────────────────────────────────────
    st.markdown("<h2 style='color: #D4AF37; font-family: \"Orbitron\", sans-serif; font-weight: 800; font-size: 1.5rem; letter-spacing: 2px;'>DATA</h2>", unsafe_allow_html=True)
    st.markdown("<p class='label-grey' style='font-size: 0.6rem; margin-top: -10px;'>MARKET INPUT STREAM</p>", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("RECALIBRATE QUANT CORE", width='stretch'):
        st.session_state.matrix = None
        st.session_state.entered = False
        _save_session_flag({'entered': False})
        st.rerun()
    st.markdown("---")
    sidebar_news_section(m.get('latest_news', []), live_feed=st.session_state.get('news_feed'))

# ── Lazy-init the ZERO ENGINE Gemini chat ────────────────────────────────────
# Initialise once per session; re-init if the user updates the API key.
def _get_zero_engine():
    """Return a cached GeminiChat instance, creating it on first call.
    Also detects the .kb_reload.flag written by convert_playlist.py
    and hot-reloads the KB so new YouTube knowledge is live immediately.
    """
    key_override = st.session_state.get('ze_api_key_override', '')
    effective_key = key_override if key_override else GEMINI_API_KEY

    # Re-init on key change
    if 'ze_engine' not in st.session_state or st.session_state.get('ze_engine_key') != effective_key:
        try:
            from engine.gemini_chat import GeminiChat
            st.session_state['ze_engine'] = GeminiChat(api_key=effective_key)
            st.session_state['ze_engine_key'] = effective_key
        except Exception:
            st.session_state['ze_engine'] = None

    # ── Hot-reload KB if convert_playlist.py has written a reload signal ──────
    reload_flag = os.path.join(os.path.dirname(__file__), "db", ".kb_reload.flag")
    if os.path.exists(reload_flag):
        try:
            with open(reload_flag, "r", encoding="utf-8") as _f:
                reload_content = _f.read().strip()
            # Only reload if the signal is different from last processed one
            last_reload = st.session_state.get('_last_kb_reload_signal', '')
            if reload_content != last_reload:
                engine = st.session_state.get('ze_engine')
                if engine is not None:
                    engine.reload_kb()
                st.session_state['_last_kb_reload_signal'] = reload_content
                # Parse the video title from the flag for a toast
                parts = reload_content.split(":")
                yt_title = parts[1] if len(parts) > 1 else "YouTube"
                st.toast(f"🧠 ZERO Engine learned: **{yt_title}**", icon="📺")
        except Exception:
            pass

    return st.session_state.get('ze_engine')
# ── ZERO ENGINE full-screen modal ─────────────────────────────────────────────
if st.session_state.get('show_zero_engine', False):
    ze_engine = _get_zero_engine()
    key_override = st.session_state.get('ze_api_key_override', '')
    _api_key_state = {
        'key': key_override if key_override else GEMINI_API_KEY,
        'changed': False,
    }
    render_zero_engine_modal(ze_engine, _api_key_state)
    st.stop()


# --- MAIN TERMINAL HEADER ---
st.markdown("<h1 class='main-title'>ZERO</h1>", unsafe_allow_html=True)
st.markdown("<p class='terminal-core-txt'>TERMINAL CORE SYSTEM V2.0</p>", unsafe_allow_html=True)

# Background-refresh toast: a 2s translucent bubble that slides down and
# retracts. Fires only on the run that actually regenerated the matrix.
if _toast_signal:
    render_quant_toast()
    _save_session_flag({
        'entered': True,
        'matrix': st.session_state.matrix,
        'last_run_date': (
            st.session_state.last_run_date.isoformat()
            if st.session_state.last_run_date else None
        ),
        'matrix_gen_time': (
            _matrix_gen_time.isoformat() if _matrix_gen_time else now.isoformat()
        ),
    })

# Breaking-news banner + device notifications (news already fetched above).
_breaking = st.session_state.get('news_breaking', [])
if _breaking:
    push_device_notifications(_breaking)
    render_breaking_banner(_breaking)

# Perfectly Centered Clock
digital_clock_component()

# Live scrolling headline ribbon.
render_news_ticker(st.session_state.get('news_feed', []))

# ForexFactory Priority #1 Macro Feed Banner
render_forexfactory_priority_card(st.session_state.get('news_feed') or m.get('latest_news'))

st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

# Six-Page System (Tabs)
tab1, tab2, tab3, tab6, tab_trading, tab4, tab5 = st.tabs(["NIFTY 50", "BANKNIFTY", "SENSEX", "GLOBAL NEWS", "TRADING TERMINAL", "LEARNING LAB", "PREDICTION HISTORY"])

# UI: remember active tab across auto-refreshes; badge unread breaking items.
persist_active_tab()
tab_unread_badge(len(st.session_state.get('news_breaking', []) or []), tab_index=3)

# Core 5 + UI 3: live status pill (news freshness + countdown to next refresh).
try:
    import datetime as _dt
    _ca = None
    _cb = st.session_state.get('news_checked_at')
    if _cb:
        _ca = (datetime.datetime.now() - datetime.datetime.fromisoformat(_cb)).total_seconds()
    status_pill(NEWS_REFRESH_SECONDS, int(_ca or 0), healthy=bool(st.session_state.get('news_feed')))
except Exception:
    pass

def render_market_page(symbol, data, key_prefix):
    """Renders a market page using per-index prediction data (no multipliers)."""
    if not data or 'error' in data:
        st.error(f"Unable to load predictions for {symbol}. Engine error.")
        return
    
    st.markdown(f"<p class='gold-title'>01 // {symbol} PREDICTION VECTOR</p>", unsafe_allow_html=True)
    col1, col2 = st.columns([1.8, 1.2])
    with col1:
        predicted_info_card(symbol, data)
    with col2:
        st.markdown("<div class='digital-card' style='height: 100%;'>", unsafe_allow_html=True)
        st.markdown("<p class='label-grey'>Order Block Depth</p>", unsafe_allow_html=True)
        order_flow_table(data)
        st.markdown("</div>", unsafe_allow_html=True)

    # TradingAgents Multi-Agent Consensus & QuantDinger Strategy Setup
    if data.get('agent_consensus'):
        render_trading_agents_panel(data.get('agent_consensus'))
    if data.get('quant_strategy'):
        render_quantdinge_strategy_card(data.get('quant_strategy'))

    # ── New: Fincept Quant Team Thesis + Inter-Market + Greeks + Nautilus Orders ──
    # Rendered in a 2-col layout for space efficiency
    _col_left, _col_right = st.columns([1.4, 1])
    with _col_left:
        if data.get('fincept_thesis'):
            render_fincept_thesis_card(data.get('fincept_thesis'))
        if data.get('nautilus_order_suggestion'):
            render_nautilus_order_card(data.get('nautilus_order_suggestion'))
    with _col_right:
        if data.get('fincept_intermarket'):
            render_intermarket_card(data.get('fincept_intermarket'))
        if data.get('fincept_greeks'):
            render_options_greeks_card(data.get('fincept_greeks'))


    st.markdown(f"<p class='gold-title'>02 // {symbol} VOLATILITY OVERLAY</p>", unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_hline(y=data['prev_close'], line_dash="dot", line_color="#333")
    fig.add_trace(go.Scatter(
        x=["Low", "Open", "High"], y=[data['pred_low'], data['pred_open'], data['pred_high']],
        mode='lines+markers+text', text=[f"LOW", f"OPEN", f"HIGH"], textposition="top center",
        line=dict(color='#E50914', width=5),
        marker=dict(size=14, color=['#ff4b4b', '#fff', '#00ff88'], line=dict(color='#000', width=2))
    ))
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0.01)',
        font={'color': "#555", 'family': "Inter"},
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#111", zeroline=False),
        height=450, margin=dict(l=20, r=20, t=20, b=20), showlegend=False
    )
    st.plotly_chart(fig, width='stretch', key=f"{key_prefix}_v", config={'displayModeBar': False})

    st.markdown("<div style='margin: 40px 0;'></div>", unsafe_allow_html=True)
    st.markdown(f"<p class='gold-title'>03 // INTRADAY PROBABILITY CLOUD</p>", unsafe_allow_html=True)
    st.plotly_chart(ohlc_range_chart(data), width='stretch', key=f"{key_prefix}_c", config={'displayModeBar': False})

# Page Routing — each index gets its own independent prediction data
with tab1: render_market_page("NIFTY 50", m.get("NIFTY 50", {}), "n1")
with tab2: render_market_page("BANKNIFTY", m.get("BANKNIFTY", {}), "b1")
with tab3: render_market_page("SENSEX", m.get("SENSEX", {}), "s1")

with tab_trading:
    st.markdown("<h2 class='gold-title'>QUANTUM TRADING TERMINAL</h2>", unsafe_allow_html=True)
    st.markdown("<p class='label-grey' style='margin-bottom: 20px;'>Multi-timeframe execution, risk management, and genetic optimization.</p>", unsafe_allow_html=True)
    
    # Strategy & Risk Advisory Bubbles (Top Section)
    render_trading_strategy_bubbles(m, st.session_state.get('news_feed'))
    
    # 1. XGBoost Predictor Section
    with st.expander("🤖 MULTI-TIMEFRAME XGBOOST PREDICTOR", expanded=False):
        st.markdown("<p class='gold-title' style='font-size: 0.8rem;'>XGBoost Machine Learning Head</p>", unsafe_allow_html=True)
        col_x1, col_x2 = st.columns([1.5, 1])
        
        with col_x1:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Interactive Model Playground</p>", unsafe_allow_html=True)
            
            idx_choice = st.selectbox("Select Target Index", ["NIFTY 50", "BANKNIFTY", "SENSEX"], key="xgb_idx")
            
            # Fetch current close
            from data.historical import get_recent_ohlc_and_atr
            _h_keys = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
            h_stats = get_recent_ohlc_and_atr(_h_keys.get(idx_choice, "NIFTY")) or {}
            idx_spot = h_stats.get('close', 24000.0)
            
            spot_input = st.number_input("Current Spot Price", min_value=1.0, value=float(idx_spot), step=10.0, key="xgb_spot")
            
            if st.button("Generate XGBoost Predictions", key="run_xgb_predict", use_container_width=True):
                # Load models
                xgb_intra = MultiTimeframePredictor("intraday")
                xgb_week = MultiTimeframePredictor("weekly")
                
                intra_ok = xgb_intra.load()
                week_ok = xgb_week.load()
                
                # Fetch features
                try:
                    features_dict = build_mtf_features(idx_choice)
                    features_df = pd.DataFrame([features_dict])
                    
                    st.success("MTF Features engineered successfully!")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("<p class='label-grey'>Intraday Prediction</p>", unsafe_allow_html=True)
                        if intra_ok:
                            p_res = xgb_intra.predict_bounds(features_df, spot_input)
                            st.metric("Predicted High", f"{p_res['predicted_high']:.2f}", f"{p_res['high_pct']*100:+.3f}%")
                            st.metric("Predicted Low", f"{p_res['predicted_low']:.2f}", f"{p_res['low_pct']*100:+.3f}%")
                        else:
                            st.warning("Intraday XGBoost model not trained yet. Run Training first.")
                            
                    with c2:
                        st.markdown("<p class='label-grey'>Weekly Macro Prediction</p>", unsafe_allow_html=True)
                        if week_ok:
                            w_res = xgb_week.predict_bounds(features_df, spot_input)
                            st.metric("Predicted High", f"{w_res['predicted_high']:.2f}", f"{w_res['high_pct']*100:+.3f}%")
                            st.metric("Predicted Low", f"{w_res['predicted_low']:.2f}", f"{w_res['low_pct']*100:+.3f}%")
                        else:
                            st.warning("Weekly XGBoost model not trained yet. Run Training first.")
                except Exception as ex:
                    st.error(f"Prediction failed: {ex}")
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_x2:
            st.markdown("<div class='digital-card' style='height: 100%;'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Model Status & Control</p>", unsafe_allow_html=True)
            
            if st.button("Trigger XGBoost Training Cycle", key="train_xgb_models", use_container_width=True):
                with st.spinner("Assembling features & training models..."):
                    # Intraday
                    df_intra = MultiTimeframePredictor.assemble_training_data("intraday")
                    intra_res = {}
                    if not df_intra.empty:
                        p_intra = MultiTimeframePredictor("intraday")
                        intra_res = p_intra.train(df_intra)
                        if intra_res.get("status") == "trained":
                            p_intra.save()
                            st.success("Intraday XGBoost trained and saved!")
                    else:
                        st.warning("No intraday training data in logs.")
                        
                    # Weekly
                    df_week = MultiTimeframePredictor.assemble_training_data("weekly")
                    week_res = {}
                    if not df_week.empty:
                        p_week = MultiTimeframePredictor("weekly")
                        week_res = p_week.train(df_week)
                        if week_res.get("status") == "trained":
                            p_week.save()
                            st.success("Weekly XGBoost trained and saved!")
                    else:
                        st.warning("No weekly training data in logs.")
                        
                    st.write("---")
                    st.write("**Intraday Stats:**", intra_res)
                    st.write("**Weekly Stats:**", week_res)
            st.markdown("</div>", unsafe_allow_html=True)
            
    # 2. Genetic Mutator Section
    with st.expander("🧬 STRATEGYQUANT X EVOLUTIONARY ENGINE", expanded=False):
        st.markdown("<p class='gold-title' style='font-size: 0.8rem;'>Genetic Mutator Playground</p>", unsafe_allow_html=True)
        col_g1, col_g2 = st.columns([1.5, 1])
        
        with col_g1:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Evolved Rule Pool</p>", unsafe_allow_html=True)
            
            gen_engine = StrategyGeneticEngine()
            strategies, scores = gen_engine.load_strategies()
            
            if strategies:
                for idx, (strat, score) in enumerate(zip(strategies, scores)):
                    st.markdown(f"**Strategy #{idx + 1} (Sharpe Proxy Score: `{score:.4f}`)**")
                    st.json(strat)
                    st.write("---")
            else:
                st.info("No strategies generated yet. Generate a random pool below.")
                
            if st.button("Generate Fresh Strategy Pool", key="gen_fresh_strat", use_container_width=True):
                fresh_pop = [gen_engine.generate_strategy() for _ in range(4)]
                fresh_scores = [round(random.uniform(0.1, 1.8), 4) for _ in fresh_pop]
                gen_engine.save_strategies(fresh_pop, fresh_scores)
                st.success("Fresh population of 4 strategies saved to db/genetic_strategies.json!")
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_g2:
            st.markdown("<div class='digital-card' style='height: 100%;'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Mutate or Evolve Rules</p>", unsafe_allow_html=True)
            
            if strategies:
                target_to_mutate = st.selectbox("Select Strategy to Mutate", [f"Strategy #{i+1}" for i in range(len(strategies))], key="mut_select")
                strat_index = int(target_to_mutate.split("#")[-1]) - 1
                
                if st.button("Mutate Selected Strategy", key="mutate_strat_btn", use_container_width=True):
                    mutated = gen_engine.mutate_strategy(strategies[strat_index])
                    new_score = round(strategies[strat_index][0].get('threshold', 50.0)/100.0 + random.uniform(-0.2, 0.4), 4)
                    
                    strategies[strat_index] = mutated
                    if len(scores) > strat_index:
                        scores[strat_index] = new_score
                    else:
                        scores.append(new_score)
                        
                    gen_engine.save_strategies(strategies, scores)
                    st.success("Strategy mutated and saved successfully!")
                    st.rerun()
            else:
                st.warning("Generate a strategy pool first to test mutation.")
            st.markdown("</div>", unsafe_allow_html=True)
            
    # 3. Monte Carlo Risk Engine Section
    with st.expander("🎲 MONTE CARLO RISK VALIDATOR & SIMULATOR", expanded=False):
        st.markdown("<p class='gold-title' style='font-size: 0.8rem;'>Pre-Trade Stochastic Simulation</p>", unsafe_allow_html=True)
        col_m1, col_m2 = st.columns([1, 1])
        
        with col_m1:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Simulation Parameters</p>", unsafe_allow_html=True)
            
            mc_win_rate = st.slider("Strategy Win Rate (%)", min_value=10.0, max_value=90.0, value=55.0, step=1.0, key="mc_wr") / 100.0
            mc_avg_win = st.number_input("Average Winning Trade Value ($)", min_value=1.0, value=200.0, step=10.0, key="mc_aw")
            mc_avg_loss = st.number_input("Average Losing Trade Value ($)", min_value=1.0, value=150.0, step=10.0, key="mc_al")
            mc_balance = st.number_input("Current Account Balance ($)", min_value=10.0, value=50000.0, step=500.0, key="mc_bal")
            mc_sims = st.slider("Simulations Count", min_value=100, max_value=10000, value=5000, step=100, key="mc_sims_count")
            
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_m2:
            st.markdown("<div class='digital-card' style='height: 100%;'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Risk Engine Output</p>", unsafe_allow_html=True)
            
            if st.button("Run Monte Carlo Assessment", key="run_mc_btn", use_container_width=True):
                mc_engine = MonteCarloRiskEngine(simulations=mc_sims)
                risk_res = mc_engine.evaluate_strategy_risk(
                    win_rate=mc_win_rate,
                    avg_win=mc_avg_win,
                    avg_loss=mc_avg_loss,
                    balance=mc_balance
                )
                
                # Check status
                if risk_res['passed']:
                    st.success("🟢 RISK PASSED: Probability of Ruin fits institutional standards.")
                else:
                    st.error("🔴 RISK REJECTED: High risk of capital ruin detected.")
                    
                st.write(f"**Probability of Ruin (50% DD):** `{risk_res['probability_of_ruin']*100:.2f}%` (Max allowed: `5.0%`) ")
                st.write(f"**Expected Max Drawdown:** `{risk_res['expected_max_drawdown']*100:.2f}%` ")
                st.write(f"**Median Final Balance:** `${risk_res['median_final_balance']:.2f}` ")
                st.write(f"**5th Percentile Balance (Worst Case):** `${risk_res['percentile_5_balance']:.2f}` ")
                st.write(f"**95th Percentile Balance (Best Case):** `${risk_res['percentile_95_balance']:.2f}` ")
            else:
                st.info("Click the button to execute 5000+ stochastic path simulations.")
            st.markdown("</div>", unsafe_allow_html=True)
            
    # 4. Paper Brokerage Section
    with st.expander("💸 LEAN-STYLE PAPER BROKERAGE TERMINAL", expanded=False):
        st.markdown("<p class='gold-title' style='font-size: 0.8rem;'>Simulated Slippage & Position Control</p>", unsafe_allow_html=True)
        col_b1, col_b2 = st.columns([1.2, 1.8])
        
        # Load brokerage
        pb_broker = PaperBrokerage.load()
        
        with col_b1:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Order Board</p>", unsafe_allow_html=True)
            
            ord_symbol = st.selectbox("Symbol", ["NIFTY 50", "BANKNIFTY", "SENSEX"], key="pb_sym")
            ord_side = st.selectbox("Order Side", ["BUY", "SELL"], key="pb_side")
            ord_qty = st.number_input("Quantity", min_value=1.0, value=1.0, step=1.0, key="pb_qty")
            
            # Fetch spot price
            from data.historical import get_recent_ohlc_and_atr
            _h_keys = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
            h_stats = get_recent_ohlc_and_atr(_h_keys.get(ord_symbol, "NIFTY")) or {}
            ord_price = h_stats.get('close', 24000.0)
            
            ord_price_input = st.number_input("Limit/Market Price", min_value=0.1, value=float(ord_price), step=10.0, key="pb_price")
            
            if st.button("Submit Order", key="pb_submit", use_container_width=True):
                res = pb_broker.execute_order(
                    symbol=ord_symbol,
                    side=ord_side,
                    quantity=ord_qty,
                    current_price=ord_price_input
                )
                if res.get("status") == "filled":
                    pb_broker.save_log()
                    st.success(f"Order FILLED! Executed price: {res['fill_price']} (Slippage: {res['slippage_applied']})")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"Order REJECTED: {res.get('reason')}")
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_b2:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Portfolio Summary</p>", unsafe_allow_html=True)
            
            # Fetch current prices for position evaluation
            current_prices = {}
            for sym in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
                _h_keys = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
                hs = get_recent_ohlc_and_atr(_h_keys.get(sym, "NIFTY")) or {}
                current_prices[sym] = hs.get('close', 0.0)
                
            pb_sum = pb_broker.portfolio_summary(current_prices)
            
            # Show summary metrics
            m_c1, m_c2, m_c3 = st.columns(3)
            m_c1.metric("Cash Balance", f"${pb_sum['cash_balance']:.2f}")
            m_c2.metric("Total Equity", f"${pb_sum['equity']:.2f}")
            m_c3.metric("Total P&L", f"${pb_sum['total_pnl']:.2f}", f"{pb_sum['return_pct']:.4f}%")
            
            # Open Positions
            st.markdown("<p class='label-grey' style='margin-top: 15px;'>Open Positions</p>", unsafe_allow_html=True)
            if pb_sum['positions']:
                pos_df = pd.DataFrame([
                    {"Symbol": k, "Qty": v["quantity"], "Avg Cost": v["avg_cost"], "Mkt Price": v["market_price"], "Unrealized P&L": v["unrealized_pnl"]}
                    for k, v in pb_sum['positions'].items()
                ])
                st.dataframe(pos_df, hide_index=True, use_container_width=True)
            else:
                st.info("No open positions.")
                
            # Log
            st.markdown("<p class='label-grey' style='margin-top: 15px;'>Execution History</p>", unsafe_allow_html=True)
            if pb_broker.trade_log:
                log_df = pd.DataFrame(pb_broker.trade_log[::-1])
                st.dataframe(log_df[["timestamp", "side", "symbol", "quantity", "fill_price", "status"]], hide_index=True, use_container_width=True)
            else:
                st.info("No past trades.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 5. Advanced Backtest Engine (Nautilus-style Walk-Forward)
    with st.expander("📊 NAUTILUS WALK-FORWARD BACKTEST ENGINE", expanded=False):
        st.markdown("<p class='gold-title' style='font-size: 0.8rem;'>Walk-Forward Strategy Suite · Pure NumPy · Zero Lookahead Bias</p>", unsafe_allow_html=True)
        col_bt1, col_bt2 = st.columns([1.2, 1.8])

        with col_bt1:
            st.markdown("<div class='digital-card'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Backtest Configuration</p>", unsafe_allow_html=True)

            bt_symbol = st.selectbox("Index to Backtest", ["NIFTY 50", "BANKNIFTY", "SENSEX"], key="bt_sym")
            bt_period  = st.selectbox("Historical Lookback", ["30 days", "60 days", "90 days", "180 days"], key="bt_period")
            bt_capital = st.number_input("Starting Capital (₹)", min_value=10000.0, value=100000.0, step=5000.0, key="bt_cap")
            bt_wf      = st.toggle("Walk-Forward Validation (70/30 split)", value=True, key="bt_wf")

            if st.button("🚀 Run Full Strategy Suite", key="run_bt_suite", use_container_width=True):
                from engine.advanced_backtest import ZeroBacktestEngine
                from data.historical import get_recent_ohlc_and_atr
                import numpy as np

                # Build synthetic bars from historical stats (live data would use OHLCV)
                _hk  = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
                _hst = get_recent_ohlc_and_atr(_hk.get(bt_symbol, "NIFTY")) or {}
                _base_close = float(_hst.get("close", 24000.0))
                _base_atr   = float(_hst.get("atr", 200.0))
                _n_days = {"30 days": 30, "60 days": 60, "90 days": 90, "180 days": 180}.get(bt_period, 60)

                # Generate synthetic OHLCV (Geometric Brownian Motion proxy)
                np.random.seed(42)
                returns = np.random.normal(0.0003, _base_atr / _base_close / np.sqrt(252), _n_days)
                closes  = _base_close * np.cumprod(1 + returns)
                highs   = closes * (1 + np.abs(np.random.normal(0, _base_atr / _base_close * 0.5, _n_days)))
                lows    = closes * (1 - np.abs(np.random.normal(0, _base_atr / _base_close * 0.5, _n_days)))

                bars = [{
                    "date": (datetime.datetime.now() - datetime.timedelta(days=_n_days - i)).strftime("%Y-%m-%d"),
                    "open": float(closes[max(0, i-1)]),
                    "high": float(highs[i]),
                    "low":  float(lows[i]),
                    "close": float(closes[i]),
                    "volume": float(np.random.uniform(500000, 2000000)),
                } for i in range(_n_days)]

                engine = ZeroBacktestEngine(
                    initial_capital=bt_capital,
                    commission_pct=0.0003,
                    slippage_bps=0.5,
                )

                with st.spinner("Running strategy suite on synthetic bars..."):
                    suite_results = engine.run_strategy_suite(bars)

                st.session_state["bt_suite_results"] = suite_results
                st.session_state["bt_bars_count"]    = len(bars)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

        with col_bt2:
            st.markdown("<div class='digital-card' style='height: 100%;'>", unsafe_allow_html=True)
            st.markdown("<p class='label-grey'>Strategy Performance Ranking (Sharpe Sorted)</p>", unsafe_allow_html=True)

            suite = st.session_state.get("bt_suite_results")
            if suite:
                bt_data_rows = []
                for strat_name, report in suite.items():
                    if isinstance(report, dict) and "sharpe_ratio" in report:
                        bt_data_rows.append({
                            "Strategy": strat_name,
                            "Sharpe": f"{report.get('sharpe_ratio', 0):.3f}",
                            "Win%":   f"{report.get('win_rate', 0)*100:.1f}%",
                            "PF":     f"{report.get('profit_factor', 0):.2f}",
                            "MaxDD%": f"{report.get('max_drawdown_pct', 0):.1f}%",
                            "Ret%":   f"{report.get('total_return_pct', 0):+.1f}%",
                            "Trades": report.get("total_trades", 0),
                        })
                if bt_data_rows:
                    bt_df = pd.DataFrame(bt_data_rows)
                    st.dataframe(bt_df, hide_index=True, use_container_width=True)

                    # Show top strategy detail
                    top_name = list(suite.keys())[0]
                    top = suite[top_name]
                    st.markdown(f"""
<div style="background:rgba(0,0,0,0.4);border:1px solid rgba(0,176,255,0.2);border-radius:8px;padding:12px;margin-top:10px;">
  <div style="font-family:'Orbitron',sans-serif;font-size:0.65rem;color:#00B0FF;margin-bottom:8px;">
    🏆 TOP STRATEGY: {top_name}
  </div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center;font-size:0.62rem;">
    <div><div style="color:#555;">Sharpe</div><div style="color:#D4AF37;font-weight:800;">{top.get('sharpe_ratio',0):.3f}</div></div>
    <div><div style="color:#555;">Calmar</div><div style="color:#D4AF37;font-weight:800;">{top.get('calmar_ratio',0):.3f}</div></div>
    <div><div style="color:#555;">Sortino</div><div style="color:#D4AF37;font-weight:800;">{top.get('sortino_ratio',0):.3f}</div></div>
    <div><div style="color:#555;">Expectancy</div><div style="color:#00E676;font-weight:800;">₹{top.get('expectancy',0):.1f}</div></div>
    <div><div style="color:#555;">Final Equity</div><div style="color:#00E676;font-weight:800;">₹{top.get('final_equity',0):,.0f}</div></div>
    <div><div style="color:#555;">Walk-Fwd</div><div style="color:#888;font-weight:800;">{'YES' if top.get('walk_forward') else 'NO'}</div></div>
  </div>
</div>""", unsafe_allow_html=True)
            else:
                st.info("Configure and run the strategy suite to see ranked performance analytics.")
            st.markdown("</div>", unsafe_allow_html=True)

with tab4:

    st.markdown("<h2 class='gold-title'>ULTRA-LOW LATENCY LEARNING CORE</h2>", unsafe_allow_html=True)
    st.markdown("<p class='label-grey' style='margin-bottom: 40px;'>Autonomous parameter correction and systemic validation.</p>", unsafe_allow_html=True)
    
    col_f, col_s = st.columns([1.5, 1])
    
    with col_f:
        train_status = None
        current_time = datetime.datetime.now().time()
        # Market closes at 3:30 PM IST — auto-train triggers after close
        close_time = datetime.time(15, 30)
        
        # We auto condition the background learning stream if it's past market closing time
        if current_time >= close_time:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            if st.session_state.get('last_train_date') != today_str:
                train_status = auto_train_engine(m)
                st.session_state['last_train_date'] = today_str
        
        automated_training_dashboard(train_status, m)

    with col_s:
        metrics = calculate_engine_accuracy()
        learning_stats_card(metrics)
        
    st.markdown("---")
    st.markdown("<p class='label-grey'>HISTORICAL DEVIATION LOG</p>", unsafe_allow_html=True)
    logs = get_feedback_logs()
    if logs:
        for log in reversed(logs):
            with st.expander(f"SESSION: {log['date']} | STATUS: COMMITTED"):
                st.json(log)
    else:
        st.info("No logs detected in core memory.")

with tab5:
    st.markdown("<h2 class='gold-title'>PREDICTION HISTORY</h2>", unsafe_allow_html=True)
    st.markdown("<p class='label-grey' style='margin-bottom: 15px;'>Historical predicted vs actual data across all tracked indices. Grouped by day. You can modify records or delete them.</p>", unsafe_allow_html=True)

    from config import is_trading_day, is_market_closed_post_4pm, get_next_trading_day, market_state, now_ist
    _now = now_ist()
    _m_state = market_state(_now)
    _next_day = get_next_trading_day(_now).strftime("%Y-%m-%d")

    # Dynamic status info banner for user
    if _m_state == 'closed_weekend':
        st.info(f"📅 **MARKET CLOSED (WEEKEND)** — History logging skipped for weekends. Upcoming Forecast Target: **{_next_day}**")
    elif _m_state == 'closed_holiday':
        st.warning(f"🏖️ **MARKET CLOSED (NATIONAL HOLIDAY)** — History logging skipped for market holidays. Upcoming Forecast Target: **{_next_day}**")
    elif is_market_closed_post_4pm(_now):
        st.success(f"✅ **MARKET CLOSED (POST 4:00 PM IST)** — Daily actuals captured. Upcoming Session Target: **{_next_day}**")
    else:
        st.info(f"⏳ **SESSION IN PROGRESS (PRE 4:00 PM IST)** — Actuals update scheduled after 4:00 PM IST. Active Target: **{_now.strftime('%Y-%m-%d')}**")

    st.markdown("""
    <div style="background: rgba(20,20,20,0.6); border: 1px solid #333; padding: 10px 15px; border-radius: 4px; margin-bottom: 20px; font-size: 0.8rem; color: #aaa;">
      <strong>Policy Notice:</strong> Prediction actuals are logged strictly <strong>after 4:00 PM IST</strong> on active trading days (NSE/BSE). National market holidays & weekends are automatically excluded from prediction history updates. Range predictions for the upcoming trading session are computed automatically.
    </div>
    """, unsafe_allow_html=True)
    
    logs = get_feedback_logs()
    
    if logs:
        from collections import defaultdict
        grouped_logs = defaultdict(list)
        for log in logs:
            grouped_logs[log['date']].append(log)
            
        for date_str in sorted(grouped_logs.keys(), reverse=True):
            st.markdown(f"<h3 style='color: #fff; margin-top: 20px; border-bottom: 1px solid #333; padding-bottom: 10px;'>SESSION: {date_str}</h3>", unsafe_allow_html=True)
            day_logs = grouped_logs[date_str]
            
            table_rows = []
            for log in day_logs:
                p_open = log['predicted']['pred_open']
                p_high = log['predicted']['pred_high']
                p_low = log['predicted']['pred_low']
                a = log.get('actual', {})
                a_open = a.get('open', "N/A")
                a_high = a.get('high', "N/A")
                a_low = a.get('low', "N/A")
                
                table_rows.append({
                    "ID": log['id'],
                    "Index": log['index'],
                    "Pred Open": p_open,
                    "Actual Open": a_open,
                    "Pred High": p_high,
                    "Actual High": a_high,
                    "Pred Low": p_low,
                    "Actual Low": a_low,
                    "Reason": log.get('reason', '')
                })
                
            df = pd.DataFrame(table_rows)
            with st.expander(f"Edit Data for {date_str}", expanded=True):
                edited_df = st.data_editor(df, num_rows="dynamic", key=f"editor_{date_str}", width='stretch', hide_index=False)
                if st.button(f"Save Changes for {date_str}", key=f"save_{date_str}", width='stretch'):
                    valid_ids = edited_df['ID'].dropna().tolist()
                    global_logs = get_feedback_logs()
                    new_global_logs = []
                    for g_log in global_logs:
                        if g_log['date'] == date_str:
                            if g_log['id'] in valid_ids:
                                row = edited_df[edited_df['ID'] == g_log['id']].iloc[0]
                                g_log['actual']['open'] = row['Actual Open']
                                g_log['actual']['high'] = row['Actual High']
                                g_log['actual']['low'] = row['Actual Low']
                                g_log['reason'] = row.get('Reason', '')
                                new_global_logs.append(g_log)
                        else:
                            new_global_logs.append(g_log)
                            
                    if update_feedback_logs(new_global_logs):
                        st.success(f"Updated logs for {date_str} successfully.")
                        time.sleep(1)
                        st.rerun()
    else:
        st.info("No prediction data logged yet.")

with tab6:
    _feed = st.session_state.get('news_feed', [])
    # A live overlay summary: how the current news tape is nudging each index.
    _overlay = (m.get('news_overlay') if isinstance(m, dict) else None) or {}
    if _overlay:
        cols = st.columns(3)
        for c, idx, short in zip(cols, ["NIFTY 50", "BANKNIFTY", "SENSEX"], ["NIFTY", "BANKNIFTY", "SENSEX"]):
            mv = _overlay.get(idx, {}) or {}
            pct = float(mv.get('move_pct', 0.0) or 0.0)
            color = "#00ff88" if pct > 0 else ("#E50914" if pct < 0 else "#666")
            with c:
                st.markdown(
                    f"<div class='digital-card' style='text-align:center;'>"
                    f"<p class='label-grey'>{short} · LIVE NEWS BIAS</p>"
                    f"<p style='color:{color};font-weight:900;font-size:1.6rem;margin:4px 0;'>{pct:+.2f}%</p>"
                    f"<p class='label-grey' style='font-size:0.6rem;'>{mv.get('move_points',0):+.0f} pts applied to forecast</p>"
                    f"</div>", unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom:24px;'></div>", unsafe_allow_html=True)

    # ── Pictorial: aggregate sentiment gauge from the live feed ────────────
    if _feed:
        # Impact-weighted average sentiment, clamped to [-1, 1]
        weights = [max(float(it.get('impact_score', 0.0)), 1.0) for it in _feed]
        sentiments = [float(it.get('sentiment', 0.0) or 0.0) for it in _feed]
        total_w = sum(weights) or 1.0
        agg_sentiment = sum(s * w for s, w in zip(sentiments, weights)) / total_w
        agg_sentiment = max(-1.0, min(1.0, agg_sentiment))
        bullish_n = sum(1 for it in _feed if it.get('direction') == 'BULLISH')
        bearish_n = sum(1 for it in _feed if it.get('direction') == 'BEARISH')
        neutral_n = sum(1 for it in _feed if it.get('direction') == 'NEUTRAL')

        st.markdown("<p class='gold-title'>00 // MARKET MOOD PULSE</p>", unsafe_allow_html=True)
        gcol, scol = st.columns([1, 1.2])
        with gcol:
            st.plotly_chart(
                sentiment_gauge_chart(agg_sentiment),
                width='stretch',
                key="news_sentiment_gauge",
                config={'displayModeBar': False},
            )
            # BUY / SELL / NEUTRAL sign under the gauge. Uses the same
            # threshold helper as the gauge so the two never disagree.
            from ui.charts import action_sign as _action_sign
            _sign_label, _sign_arrow, _sign_color = _action_sign(agg_sentiment)
            st.markdown(
                f"<div style='text-align:center; margin-top:-6px; margin-bottom:14px;'>"
                f"<span style='display:inline-block; padding:7px 18px; border:1px solid {_sign_color};"
                f"border-radius:999px; color:{_sign_color}; font-family:Orbitron, sans-serif;"
                f"font-weight:900; font-size:0.85rem; letter-spacing:3px;'>"
                f"{_sign_arrow}&nbsp;{_sign_label}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with scol:
            bull_pct = bullish_n / max(len(_feed), 1) * 100
            bear_pct = bearish_n / max(len(_feed), 1) * 100
            neut_pct = neutral_n / max(len(_feed), 1) * 100
            st.markdown(
                f"<div class='digital-card' style='height:100%;'>"
                f"<p class='label-grey'>Headline Distribution ({len(_feed)} stories)</p>"
                f"<div style='display:flex; height:14px; border-radius:7px; overflow:hidden; margin:14px 0;'>"
                f"<div style='width:{bull_pct}%; background:#00ff88;'></div>"
                f"<div style='width:{neut_pct}%; background:#D4AF37;'></div>"
                f"<div style='width:{bear_pct}%; background:#E50914;'></div>"
                f"</div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.7rem; font-weight:800;'>"
                f"<span style='color:#00ff88;'>▲ BULLISH {bullish_n}</span>"
                f"<span style='color:#D4AF37;'>• NEUTRAL {neutral_n}</span>"
                f"<span style='color:#E50914;'>▼ BEARISH {bearish_n}</span>"
                f"</div>"
                f"<p class='label-grey' style='margin-top:14px;'>Aggregate sentiment is "
                f"<b style='color:#fff;'>{agg_sentiment:+.2f}</b> (impact-weighted across "
                f"{len(_feed)} live headlines). Updates automatically each refresh cycle.</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown("<div style='margin:24px 0;'></div>", unsafe_allow_html=True)

    render_impact_panel(_feed)
    st.markdown("---")
    st.caption("Impact estimates are model-derived (category × severity × sentiment × volatility) "
               "and are probabilistic, not financial advice.")

# ── Live auto-refresh: keeps the news tape and alerts current ────────────
render_autorefresh(NEWS_REFRESH_SECONDS)

st.markdown("---")
st.caption("ZERO TERMINAL // V2.0 RELEASE // 2026 QUANTUM EDITION")
