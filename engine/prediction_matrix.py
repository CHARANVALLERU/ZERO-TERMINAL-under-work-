# Heavy data feeds are imported lazily inside generators (avoids KeyError /
# partial-init races when Streamlit reloads concurrent ``data.*`` imports).
from data.gift_nifty import get_gift_nifty_price
from data.adr_tracker import get_adr_delta
from data.options_chain import fetch_nse_option_chain, process_option_chain
from data.historical import get_recent_ohlc_and_atr, get_historical_data
from data.market_news import get_global_news, analyze_sentiment
from engine.opening_predictor import predict_opening_gap, get_opening_price
from engine.range_predictor import calculate_envelopes, predict_high_low, sentiment_adjusted_levels, _predict_high_low_pure
from engine.prediction_ranges import get_range_config, clamp_prediction
from engine.calibrator import Calibrator
from config import (
    is_market_open,
    now_ist,
    NEWS_MATRIX_TTL_SECONDS,
    NEWS_MATRIX_TTL_FLOOR_SECONDS,
    NEWS_OVERLAY_CACHE_CAP,
)


def _get_us_market_summary():
    """Lazy wrapper — keeps ``data.global_feeds`` off the import-time graph."""
    from data.global_feeds import get_us_market_summary
    return get_us_market_summary()

# Mapping from index display name to historical data key
INDEX_HIST_KEYS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX"
}

# Mapping from index display name to options symbol (NSE)
INDEX_OPTIONS_SYMBOLS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": None   # Sensex doesn't have NSE options chain
}


def _generate_single_index_prediction(index_name, us_summary, gift_price, adr_data,
                                       news_items, sentiment_data, range_config,
                                       calibrator=None, news_overlay=None, india_vix=None):
    """
    Generates prediction for a single index using its own historical data,
    ATR, and options chain. Predictions are clamped to the allowed range.
    """
    hist_key = INDEX_HIST_KEYS[index_name]
    hist_stats = get_recent_ohlc_and_atr(hist_key)
    
    if not hist_stats:
        return {"error": f"Could not fetch historical data for {index_name}"}
    
    spot_close = hist_stats['close']
    atr = hist_stats['atr']
    
    # Extract sentiment score
    sentiment_score = sentiment_data.get('score', 0) if isinstance(sentiment_data, dict) else 0
    
    # Compute Signals
    # GIFT Nifty premium is only directly applicable to NIFTY 50
    # For BANKNIFTY and SENSEX, scale proportionally
    gift_premium = 0
    if gift_price and spot_close:
        if index_name == "NIFTY 50":
            gift_premium = gift_price - spot_close
        elif index_name == "BANKNIFTY":
            # BANKNIFTY correlates but trades at ~2.4x Nifty levels
            nifty_hist = get_recent_ohlc_and_atr("NIFTY")
            if nifty_hist:
                nifty_close = nifty_hist['close']
                ratio = spot_close / nifty_close if nifty_close else 2.4
                gift_premium = (gift_price - nifty_close) * ratio
        elif index_name == "SENSEX":
            # SENSEX correlates but trades at ~3.2x Nifty levels
            nifty_hist = get_recent_ohlc_and_atr("NIFTY")
            if nifty_hist:
                nifty_close = nifty_hist['close']
                ratio = spot_close / nifty_close if nifty_close else 3.2
                gift_premium = (gift_price - nifty_close) * ratio
    import math
    if gift_premium is None or (isinstance(gift_premium, float) and math.isnan(gift_premium)) or gift_premium != gift_premium:
        gift_premium = 0.0
    if atr is None or (isinstance(atr, float) and math.isnan(atr)) or atr <= 0.0:
        atr = spot_close * 0.01

    adr_weighted = adr_data['weighted_avg'] if adr_data else 0.0
    if adr_weighted is None or (isinstance(adr_weighted, float) and math.isnan(adr_weighted)) or adr_weighted != adr_weighted:
        adr_weighted = 0.0

    vix = us_summary.get('VIX', {}).get('price', 15.0) if us_summary else 15.0
    if vix is None or (isinstance(vix, float) and math.isnan(vix)) or vix != vix:
        vix = 15.0
    
    # Sentiment Adjustment Factor — uses daily news updates
    sentiment_gap_adj = sentiment_score * (atr * 0.2)
    
    # Calculate Opening
    gap = predict_opening_gap(gift_premium, adr_weighted, 1.0)
    gap += sentiment_gap_adj
    pred_open = get_opening_price(spot_close, gap)
    
    # Calculate Range — volatility now comes from the session-IV layer
    # (EGARCH/GJR-GARCH → EWMA → ATR fallback, blended with India VIX).
    # Degrades to the legacy 15.0 default when no data is available.
    _hist_df = None
    _vol_method = 'legacy_default'
    _india_vix_used = None
    try:
        from engine.volatility_forecast import get_session_iv
        _hist_df = get_historical_data(hist_key)
        _vol = get_session_iv(_hist_df, india_vix)
        iv = float(_vol.get('iv') or 15.0)
        _vol_method = _vol.get('method', 'unknown')
        _india_vix_used = _vol.get('vix_used')
    except Exception:
        iv = 15.0
    upper_b, lower_b = calculate_envelopes(pred_open, atr, iv)
    
    # Fetch options chain (if available for this index)
    options_symbol = INDEX_OPTIONS_SYMBOLS.get(index_name)
    options_data = None
    if options_symbol:
        options_data = process_option_chain(fetch_nse_option_chain(options_symbol))
    
    max_call_oi = options_data.get('max_ce_oi_strike') if options_data else None
    max_put_oi = options_data.get('max_pe_oi_strike') if options_data else None
    pcr = options_data.get('pcr', 1.0) if options_data else 1.0
    
    pred_high, pred_low = predict_high_low(upper_b, lower_b, max_call_oi, max_put_oi)

    # Apply News-Driven Support & Resistance Adjustment
    # This uses daily updates from the news insights to modify S/R zones
    pred_high, pred_low = sentiment_adjusted_levels(pred_high, pred_low, sentiment_data, atr)

    # Market-hours branch.
    # * Closed (pre-open / post-close / weekend): full OHLC is the user's
    #   ground truth. The clamp and overlay shift are applied normally.
    # * Open: Open and Close become the live spot (we don't predict what
    #   the market is doing right now). High and Low are re-derived from
    #   the latest news overlay so the band tracks the live tape. The
    #   sentinel `live=True` lets the UI mark these cards.
    _market_open = is_market_open()
    live_spot = pred_open  # fallback

    # Integrate live ticker quote from official exchange source
    live_quote = None
    try:
        from data.live_index_service import get_live_index_quote
        live_quote = get_live_index_quote(index_name)
        if live_quote and live_quote.get("price"):
            live_spot = live_quote["price"]
            if live_quote.get("open"):
                pred_open = live_quote["open"]
            if live_quote.get("high"):
                pred_high = max(pred_high, live_quote["high"])
            if live_quote.get("low"):
                pred_low = min(pred_low, live_quote["low"])
    except Exception:
        pass

    if _market_open:
        pred_open_live = pred_open if live_quote and live_quote.get("open") else live_spot
        pred_close_live = live_spot
    else:
        pred_open_live = None
        pred_close_live = None

    # Clamp to allowed prediction range (±5000 Sensex, ±2000 Nifty/BankNifty)
    pred_open, pred_high, pred_low = clamp_prediction(
        index_name, pred_open, pred_high, pred_low, center=spot_close
    )

    # ------------------------------------------------------------------
    # Real-time Breaking-News Overlay
    # When high-impact news breaks pre-open, shift the whole predicted
    # envelope by the news-impact engine's estimated move for this index.
    # This is what lets a fresh geopolitical shock (e.g. a peace deal
    # collapsing) immediately re-price the forecast, not just the UI.
    # NOTE: applied AFTER the clamp, so a news shock can push the band
    # outside the daily clamp window if the shock warrants it. The UI
    # re-clamps when it re-derives the live high/low on a 60 s tick.
    # ------------------------------------------------------------------
    news_shift_pts = 0.0
    if news_overlay and index_name in news_overlay:
        move_pct = float(news_overlay[index_name].get('move_pct', 0.0) or 0.0)
        news_shift_pts = move_pct / 100.0 * spot_close
        if abs(news_shift_pts) > 0:
            pred_high += news_shift_pts
            pred_low += news_shift_pts
            # Only shift the open with the overlay when the market is
            # closed — when the market is open, the live spot is the
            # truth for the open.
            if not _market_open:
                pred_open += news_shift_pts

    # When the market is open, override O/C with the live spot (or
    # previously-computed pred_open as a proxy if no live spot was
    # injected). High/Low stay engine-driven.
    if _market_open:
        pred_open = pred_open_live
        pred_close = pred_close_live
        side = "Live Session"
    else:
        # Calculate Close & Movement (closed-path heuristic; preserved
        # verbatim from the pre-refactor behavior)
        pcr = options_data.get('pcr', 1.0) if options_data else 1.0
        if pcr > 1.3:
            pred_close = (pred_open + pred_low) / 2
            side = "Bearish (Overbought)"
        elif pcr < 0.7:
            pred_close = (pred_open + pred_high) / 2
            side = "Bullish (Oversold)"
        else:
            pred_close = pred_open + (sentiment_score * atr * 0.1)
            side = "Neutral / Sentiment Driven"

        if sentiment_score > 0.3: side = "Strong Bullish"
        if sentiment_score < -0.3: side = "Strong Bearish"
    
    # ------------------------------------------------------------------
    # Adaptive Calibration Layer
    # Correct the geometric envelope's systematic bias using the learned
    # per-index residual model, and attach conformal (P10/P90-style) bands.
    # The corrector operates on the *raw* geometric prediction; if no model
    # is committed for a leg it is an exact pass-through, so this can only
    # help or no-op, never destabilise the baseline.
    # ------------------------------------------------------------------
    calib = None
    if calibrator is not None:
        feature_row = {
            'prev_close': spot_close,
            'gift_nifty': gift_price,
            'adr_delta': adr_weighted,
            'vix': vix,
            'pcr': (options_data.get('pcr', 1.0) if options_data else 1.0),
            'sentiment_score': sentiment_score,
            'atr': atr,
        }
        raw_pred = {
            'pred_open': pred_open,
            'pred_high': pred_high,
            'pred_low': pred_low,
            'prev_close': spot_close,
        }
        calib = calibrator.apply(index_name, raw_pred, feature_row)
        pred_open = calib['pred_open']
        pred_high = calib['pred_high']
        pred_low = calib['pred_low']

    res = {
        'symbol': index_name,
        'prev_close': round(float(spot_close), 2),
        'pred_open': round(float(pred_open), 2),
        'pred_high': round(float(pred_high), 2),
        'pred_low': round(float(pred_low), 2),
        'pred_close': round(float(pred_close), 2),
        'movement_side': side,
        'gift_nifty': round(float(gift_price), 2) if gift_price else None,
        'vix': round(float(vix), 2),
        'adr_delta': round(float(adr_weighted), 2),
        'pcr': round(float(pcr), 2),
        'sentiment_score': round(float(sentiment_score), 2),
        'sentiment_intensity': sentiment_data.get('intensity', 'neutral') if isinstance(sentiment_data, dict) else 'neutral',
        'sentiment_factors': sentiment_data.get('dominant_factors', []) if isinstance(sentiment_data, dict) else [],
        # Probabilistic bands + engine self-confidence from the calibration layer.
        'open_lo': (calib.get('open_lo') if calib else None),
        'open_hi': (calib.get('open_hi') if calib else None),
        'high_lo': (calib.get('high_lo') if calib else None),
        'high_hi': (calib.get('high_hi') if calib else None),
        'low_lo': (calib.get('low_lo') if calib else None),
        'low_hi': (calib.get('low_hi') if calib else None),
        'confidence': (calib.get('confidence') if calib else None),
        'model': (calib.get('model') if calib else 'baseline'),
        'news_shift_points': round(float(news_shift_pts), 1),
        # Session-IV layer transparency
        'iv_used': round(float(iv), 2),
        'vol_method': _vol_method,
        'india_vix': (round(float(_india_vix_used), 2) if _india_vix_used else None),
    }

    # ------------------------------------------------------------------
    # TradingAgents & QuantDinger Engine Integration
    # Multi-agent reasoning consensus + local-first quant strategy setup
    # ------------------------------------------------------------------
    try:
        from engine.multi_agent_consensus import MultiAgentConsensusEngine
        from engine.quant_dinge_engine import QuantDingerEngine

        consensus_engine = MultiAgentConsensusEngine()
        quant_engine = QuantDingerEngine()

        agent_consensus = consensus_engine.evaluate(
            spot_close=spot_close,
            pred_open=pred_open,
            atr=atr,
            news_items=news_items,
            sentiment_data=sentiment_data,
            us_summary=us_summary,
            option_chain=options_data
        )

        quant_strategy = quant_engine.generate_strategy_setup(
            index_name=index_name,
            spot_close=spot_close,
            pred_open=pred_open,
            pred_high=pred_high,
            pred_low=pred_low,
            pred_close=pred_close,
            atr=atr,
            vix=vix,
            sentiment_score=sentiment_score,
            consensus_score=agent_consensus['consensus_score'],
            option_chain=options_data
        )

        res['agent_consensus'] = agent_consensus
        res['quant_strategy'] = quant_strategy
    except Exception:
        res['agent_consensus'] = None
        res['quant_strategy'] = None

    # ------------------------------------------------------------------
    # Fincept Platform — Quant Team Unified Trade Thesis
    # Runs the QuantTeamOrchestrator (strategist + risk + microstructure)
    # and UnusualWhales-style options flow scoring.
    # ------------------------------------------------------------------
    try:
        from engine.fincept_platform import get_platform
        platform = get_platform()

        fincept_thesis = platform.run_module(
            "quant_team",
            symbol=index_name,
            close=float(spot_close),
            atr=float(atr),
            vix=float(vix),
            capital=100_000.0,
            news_items=news_items,
            options_chain=options_data,
        )

        # Derivatives Greeks for near ATM strike (useful for weekly options)
        if options_data and spot_close > 0:
            atm_strike = round(spot_close / 100) * 100
            try:
                fincept_greeks = platform.run_module(
                    "derivatives",
                    spot=float(spot_close),
                    strike=float(atm_strike),
                    days_to_expiry=7.0,
                    iv=float(vix * 1.2),   # proxy: VIX * 1.2 ~ 30d IV
                )
            except Exception:
                fincept_greeks = None
        else:
            fincept_greeks = None

        # Inter-market signals from US futures / crude / DXY
        try:
            us_fut_chg = 0.0
            crude_chg  = 0.0
            dxy_chg    = 0.0
            if us_summary:
                sp500  = us_summary.get("S&P 500", {})
                crude_ = us_summary.get("Crude Oil", {})
                dxy_   = us_summary.get("DXY", {})
                us_fut_chg = float(sp500.get("change_pct", 0.0) or 0.0)
                crude_chg  = float(crude_.get("change_pct", 0.0) or 0.0)
                dxy_chg    = float(dxy_.get("change_pct", 0.0) or 0.0)

            fincept_intermarket = platform.run_module(
                "macro",
                us_futures_chg=us_fut_chg,
                crude_chg=crude_chg,
                dxy_chg=dxy_chg,
                vix=float(vix),
            )
        except Exception:
            fincept_intermarket = None

        res['fincept_thesis']      = fincept_thesis
        res['fincept_greeks']      = fincept_greeks
        res['fincept_intermarket'] = fincept_intermarket

    except Exception:
        res['fincept_thesis']      = None
        res['fincept_greeks']      = None
        res['fincept_intermarket'] = None

    # ------------------------------------------------------------------
    # Nautilus-Inspired Suggestion Engine
    # Generates paper order suggestions (IOC, FOK, GTC, OCO, OTO etc.)
    # based on the unified consensus from all agents above.
    # ------------------------------------------------------------------
    try:
        from engine.nautilus_order_engine import (
            NautilusOrderEngine, Order, OrderSide, OrderType,
            TimeInForce, ContingencyType, ExecutionInstruction
        )
        _eng = NautilusOrderEngine(slippage_bps=0.5)
        _consensus_score = (res.get('agent_consensus') or {}).get('consensus_score', 0.0)
        _fincept_score   = (res.get('fincept_thesis') or {}).get('final_score', 0.0)
        _blended         = _consensus_score * 0.6 + _fincept_score * 0.4

        if abs(_blended) >= 0.15:
            if _blended > 0:
                _side = OrderSide.BUY
                _tp   = round(pred_high, 2)
                _sl   = round(pred_low, 2)
            else:
                _side = OrderSide.SELL
                _tp   = round(pred_low, 2)
                _sl   = round(pred_high, 2)

            # Suggested aggressive entry: IOC Market order
            _ioc_entry = Order(
                symbol=index_name,
                side=_side,
                order_type=OrderType.MARKET,
                quantity=1.0,
                time_in_force=TimeInForce.IOC,
                tags=["suggested", "aggressive-entry"],
            )
            # Suggested bracket: GTC OCO with TP limit + SL stop
            _tp_order = Order(
                symbol=index_name,
                side=OrderSide.SELL if _blended > 0 else OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=1.0,
                price=_tp,
                time_in_force=TimeInForce.GTC,
                contingency_type=ContingencyType.OCO,
                tags=["take-profit"],
            )
            _sl_order = Order(
                symbol=index_name,
                side=OrderSide.SELL if _blended > 0 else OrderSide.BUY,
                order_type=OrderType.STOP_MARKET,
                quantity=1.0,
                stop_price=_sl,
                time_in_force=TimeInForce.GTC,
                contingency_type=ContingencyType.OCO,
                tags=["stop-loss"],
            )
            _tp_order.linked_order_ids = [_sl_order.order_id]
            _sl_order.linked_order_ids = [_tp_order.order_id]

            res['nautilus_order_suggestion'] = {
                "blended_score":      round(_blended, 4),
                "suggested_side":     _side.value,
                "entry_type":         "IOC Market (Aggressive) / DAY Limit (Patient)",
                "entry_price_guide":  round(pred_open, 2),
                "take_profit":        _tp,
                "stop_loss":          _sl,
                "ioc_entry_id":       _ioc_entry.order_id,
                "tp_order_id":        _tp_order.order_id,
                "sl_order_id":        _sl_order.order_id,
                "contingency":        "OCO (TP + SL bracket)",
                "tif_options":        ["IOC (instant-or-cancel)", "FOK (all-or-nothing)",
                                       "GTC (until cancelled)", "GTD (good-till-date)",
                                       "DAY (today only)", "AT_THE_OPEN", "AT_THE_CLOSE"],
            }
        else:
            res['nautilus_order_suggestion'] = {
                "blended_score":  round(_blended, 4),
                "suggested_side": "NEUTRAL",
                "message":        "Consensus too weak for directional trade. Wait for clarity.",
            }

    except Exception:
        res['nautilus_order_suggestion'] = None

    # ------------------------------------------------------------------
    # TSFM Ensemble Leg (Chronos-2 / Kronos / TimesFM)
    # Optional foundation-model forecast; fully no-op safe when the heavy
    # deps are not installed. Attached alongside the calibrated envelope
    # so the UI can show agreement/disagreement between the two families.
    # ------------------------------------------------------------------
    try:
        from engine.tsfm_predictor import get_forecaster
        if _hist_df is None:
            _hist_df = get_historical_data(hist_key)
        if _hist_df is not None and not getattr(_hist_df, "empty", True):
            _tsfm_fc = get_forecaster().forecast_ohlc(
                _hist_df, horizon=1,
                covariates={'gift_premium': gift_premium, 'vix': vix,
                            'pcr': pcr, 'sentiment': sentiment_score})
            if not isinstance(_tsfm_fc, dict):
                _tsfm_fc = {
                    "status": "error",
                    "error": "tsfm returned non-dict result",
                    "backend": None,
                    "close": {"p10": None, "p50": None, "p90": None},
                }
            else:
                _tsfm_fc = dict(_tsfm_fc)
            # Tag every index so UI/debug never confuse NIFTY vs BANKNIFTY vs SENSEX.
            _tsfm_fc["symbol"] = index_name
            _tsfm_fc["hist_key"] = hist_key
            res["tsfm_forecast"] = _tsfm_fc
            if _tsfm_fc.get("status") == "forecasted":
                res["tsfm_blend"] = get_forecaster().compare_vs_point(_tsfm_fc, res)
            else:
                res["tsfm_blend"] = None
        else:
            # Surface a structured miss — never silently omit the card for one index.
            res["tsfm_forecast"] = {
                "status": "error",
                "error": f"no historical data for {hist_key}",
                "backend": None,
                "symbol": index_name,
                "hist_key": hist_key,
                "close": {"p10": None, "p50": None, "p90": None},
            }
            res["tsfm_blend"] = None
    except Exception as _tsfm_exc:
        res["tsfm_forecast"] = {
            "status": "error",
            "error": str(_tsfm_exc) or _tsfm_exc.__class__.__name__,
            "backend": None,
            "symbol": index_name,
            "hist_key": hist_key,
            "close": {"p10": None, "p50": None, "p90": None},
        }
        res["tsfm_blend"] = None

    # ------------------------------------------------------------------
    # Agent Debate Layer (TradingAgents-style bull/bear → PM verdict)
    # Uses Gemini when an API key is configured; otherwise a deterministic
    # offline fallback built from the consensus factors. Every verdict is
    # logged to db/agent_decisions.jsonl for later accuracy scoring.
    # ------------------------------------------------------------------
    try:
        from engine.agent_debate import debate as _run_agent_debate
        res['agent_debate'] = _run_agent_debate(
            index_name, res,
            news_items=news_items,
            sentiment_data=sentiment_data,
            option_chain=options_data,
        )
    except Exception:
        res['agent_debate'] = None

    return res




import datetime
try:
    import streamlit as st
    _cache600 = st.cache_data(ttl=600, show_spinner=False)
except Exception:  # importable for CLI / tests / offline without Streamlit
    def _cache600(fn):
        return fn


def _generate_prediction_matrix_raw(news_overlay=None):
    """
    Compiles all data and runs the predictive algorithm independently for
    each index (NIFTY 50, BANKNIFTY, SENSEX) with News Sentiment.
    
    Returns:
        dict: {
            "NIFTY 50": {pred_open, pred_high, pred_low, ...},
            "BANKNIFTY": {pred_open, pred_high, pred_low, ...},
            "SENSEX": {pred_open, pred_high, pred_low, ...},
            "latest_news": [...],
            "sentiment_data": {...}
        }
    """
    # 1. Fetch shared core data (fetched once, used for all indices)
    us_summary = _get_us_market_summary()
    _gift = get_gift_nifty_price()
    # get_gift_nifty_price() returns (price, is_stale: bool) per its contract.
    gift_price = _gift[0] if isinstance(_gift, tuple) else _gift
    adr_data = get_adr_delta()
    news_items = get_global_news()
    sentiment_data = analyze_sentiment(news_items)

    # 1b. India VIX — fetched once, shared across all three indices.
    # Feeds the volatility-forecast layer (blended with GARCH/EWMA model IV).
    try:
        from data.india_vix import fetch_india_vix
        india_vix_value = fetch_india_vix()
    except Exception:
        india_vix_value = None
    
    # 2. Get range config (auto-refreshes monthly)
    range_config = get_range_config()

    # 2b. Load the adaptive calibration layer (learned residual correction +
    #     conformal bands). Falls back to an identity pass-through if no model
    #     has been trained yet, so the engine still runs on a cold start.
    calibrator = Calibrator.load_or_baseline()

    # 2c. Real-time news overlay. If not supplied by the caller, derive it from
    #     the current high-impact global headlines so a fresh shock is reflected
    #     immediately. Best-effort: any failure degrades to no overlay.
    if news_overlay is None:
        try:
            from engine.news_impact import assess, aggregate_impact
            from config import NEWS_ALERT_THRESHOLD
            fresh = []
            for it in (news_items or []):
                title = it.get('title') if isinstance(it, dict) else str(it)
                a = assess(title)
                if a['impact_score'] >= NEWS_ALERT_THRESHOLD and a['direction'] != 'NEUTRAL':
                    fresh.append(a)
            news_overlay = aggregate_impact(fresh) if fresh else None
        except Exception as _e:
            news_overlay = None
    
    # 3. Generate predictions for each index independently
    result = {
        'latest_news': news_items if news_items else [
            "Market analyzing geopolitical shifts...",
            "USDINR tracking institutional loads..."
        ],
        'sentiment_data': sentiment_data,
        'news_overlay': news_overlay,
    }
    
    for index_name in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
        try:
            idx_prediction = _generate_single_index_prediction(
                index_name, us_summary, gift_price, adr_data,
                news_items, sentiment_data, range_config, calibrator, news_overlay,
                india_vix=india_vix_value
            )
            result[index_name] = idx_prediction
        except Exception as e:
            print(f"Error generating prediction for {index_name}: {e}")
            result[index_name] = {"error": str(e)}
    
    return result


@_cache600
def _generate_prediction_matrix_cached(date_str, news_overlay_tuple):
    news_overlay = None
    if news_overlay_tuple:
        news_overlay = {}
        for idx, data_tuple in news_overlay_tuple:
            news_overlay[idx] = dict(data_tuple)
    return _generate_prediction_matrix_raw(news_overlay=news_overlay)


def generate_prediction_matrix(news_overlay=None):
    date_str = datetime.date.today().isoformat()
    news_overlay_tuple = None
    if news_overlay:
        news_overlay_tuple = tuple(
            (idx, tuple(sorted(data.items())))
            for idx, data in sorted(news_overlay.items())
        )
    return _generate_prediction_matrix_cached(date_str, news_overlay_tuple)


def rederive_with_overlay(matrix, news_overlay):
    """Re-derive pred_high / pred_low (and pred_open / pred_close when the
    market is closed) for every index in an existing matrix using a fresh
    news overlay. Cheap: no network calls, no full re-scrape. Designed to
    be called from a 60-second ticker in the scrip tabs.

    Branching:
      * Market open  → shift pred_high and pred_low only. pred_open and
        pred_close stay pinned to the live spot (we don't predict the
        present).
      * Market closed → shift all four legs (open, close, high, low) so
        the user's pre-open envelope tracks the news tape.

    Returns a NEW matrix dict (immutability rule); the input is untouched.
    The top-level keys (latest_news, sentiment_data, news_overlay) are
    preserved verbatim.
    """
    if not matrix or not isinstance(matrix, dict):
        return matrix
    if not news_overlay:
        return matrix

    from config import is_market_open
    _market_open = is_market_open()

    out = dict(matrix)  # shallow copy; per-index dicts are copied below
    for idx, data in (matrix or {}).items():
        if not isinstance(data, dict) or 'error' in data or 'prev_close' not in data:
            continue
        idx_overlay = news_overlay.get(idx) if isinstance(news_overlay, dict) else None
        if not idx_overlay:
            continue
        try:
            move_pct = float(idx_overlay.get('move_pct', 0.0) or 0.0)
        except (TypeError, ValueError):
            continue
        spot_close = float(data.get('prev_close', 0.0) or 0.0)
        if spot_close <= 0:
            continue
        shift_pts = move_pct / 100.0 * spot_close
        if abs(shift_pts) < 1e-9:
            continue

        new_data = dict(data)
        # Always re-derive high and low — these are the user's primary
        # actionable levels regardless of session state.
        new_data['pred_high'] = round(float(data.get('pred_high', spot_close)) + shift_pts, 2)
        new_data['pred_low']  = round(float(data.get('pred_low',  spot_close)) + shift_pts, 2)
        new_data['news_shift_points'] = round(shift_pts, 1)
        # When the market is closed, also slide open and close so the
        # full pre-open envelope tracks the live tape.
        if not _market_open:
            new_data['pred_open']  = round(float(data.get('pred_open',  spot_close)) + shift_pts, 2)
            new_data['pred_close'] = round(float(data.get('pred_close', spot_close)) + shift_pts, 2)
        out[idx] = new_data
    return out


if __name__ == "__main__":
    import json
    matrix = generate_prediction_matrix()
    for key in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
        print(f"\n{'='*50}")
        print(f"  {key}")
        print(f"{'='*50}")
        if key in matrix:
            for k, v in matrix[key].items():
                print(f"  {k}: {v}")
    print(f"\nSentiment: {matrix.get('sentiment_data')}")
