"""
ZERO QuantDinger Trading & Strategy Recommendation Engine
============================================================
Inspired by OpenByteInc's QuantDinger framework (https://github.com/OpenByteInc/QuantDinger).

Provides local-first quantitative market regime classification, strategy recommendation,
and dynamic risk parameters (SL/TP, Risk/Reward, Win Probability, Position Sizing).
"""

from __future__ import annotations
import math
from typing import Dict, Any, List


class QuantDingerEngine:
    """
    Local-First Quantitative Trading Engine & Strategy Execution System.
    Analyzes market regimes and produces actionable quantitative strategy setups.
    """
    
    def classify_regime(self, spot_close: float, pred_open: float, pred_high: float,
                        pred_low: float, atr: float, vix: float,
                        sentiment_score: float, option_chain: Dict[str, Any] | None = None) -> str:
        """Determines the quantitative market regime."""
        pcr = option_chain.get('pcr', 1.0) if option_chain else 1.0
        range_pct = ((pred_high - pred_low) / spot_close * 100.0) if spot_close > 0 else 1.5
        gap_pct = ((pred_open - spot_close) / spot_close * 100.0) if spot_close > 0 else 0.0
        
        if vix > 22.0 or range_pct > 2.2:
            return "VOLATILE_RANGEBOUND"
        elif abs(sentiment_score) > 0.4 and vix > 18.0:
            return "MACRO_SHOCK"
        elif gap_pct > 0.35 and pcr >= 1.05 and sentiment_score >= 0.1:
            return "TRENDING_BULLISH"
        elif gap_pct < -0.35 and pcr <= 0.95 and sentiment_score <= -0.1:
            return "TRENDING_BEARISH"
        elif range_pct < 1.0 and vix < 14.0:
            return "LOW_VOL_SQUEEZE"
        else:
            return "NEUTRAL_CONSOLIDATION"

    def generate_strategy_setup(self, index_name: str, spot_close: float,
                                pred_open: float, pred_high: float, pred_low: float,
                                pred_close: float, atr: float, vix: float,
                                sentiment_score: float, consensus_score: float,
                                option_chain: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """
        Generates comprehensive quantitative strategy suggestions with exact
        Entry, Stop Loss, Take Profit 1 & 2, Risk/Reward, and Win Probability.
        """
        regime = self.classify_regime(spot_close, pred_open, pred_high, pred_low, atr, vix, sentiment_score, option_chain)
        
        # Calculate quantitative trade setup
        if consensus_score >= 0.2:
            action = "BUY / CALL OVERLAY"
            direction = "BULLISH"
            entry = round(pred_open, 2)
            sl = round(entry - (atr * 0.85), 2)
            tp1 = round(entry + (atr * 1.2), 2)
            tp2 = round(pred_high, 2)
            risk = round(entry - sl, 2)
            reward = round(tp1 - entry, 2)
            rr_ratio = round(reward / risk, 2) if risk > 0 else 2.0
            
            if regime == "TRENDING_BULLISH":
                strategy_name = "Breakout Momentum Ride"
                win_prob = round(min(68 + consensus_score * 20, 88.0), 1)
                desc = "Enter long at open projection; ride momentum towards daily upper envelope resistance."
            else:
                strategy_name = "Bullish Dip Buy at Support"
                win_prob = round(min(60 + consensus_score * 15, 78.0), 1)
                desc = "Look for liquidity sweep near low projection before building long position."
                
        elif consensus_score <= -0.2:
            action = "SELL / PUT OVERLAY"
            direction = "BEARISH"
            entry = round(pred_open, 2)
            sl = round(entry + (atr * 0.85), 2)
            tp1 = round(entry - (atr * 1.2), 2)
            tp2 = round(pred_low, 2)
            risk = round(sl - entry, 2)
            reward = round(entry - tp1, 2)
            rr_ratio = round(reward / risk, 2) if risk > 0 else 2.0
            
            if regime == "TRENDING_BEARISH":
                strategy_name = "Breakdown Trend Follow"
                win_prob = round(min(67 + abs(consensus_score) * 20, 86.0), 1)
                desc = "Enter short position on open gap down; target lower envelope support boundaries."
            else:
                strategy_name = "Bearish Rally Short at Resistance"
                win_prob = round(min(58 + abs(consensus_score) * 15, 76.0), 1)
                desc = "Fade morning gap up near high envelope resistance with tight stop loss."
                
        else:
            action = "RANGE STRADDLE / SPREAD"
            direction = "NEUTRAL"
            entry = round(spot_close, 2)
            sl = round(pred_low - (atr * 0.4), 2)
            tp1 = round(pred_high, 2)
            tp2 = round(pred_high + (atr * 0.5), 2)
            rr_ratio = 1.8
            win_prob = 62.5
            strategy_name = "Mean Reversion Iron Condor"
            desc = "Sell out-of-the-money options options outside predicted high/low boundaries."

        # Risk Sizing Recommendation
        if vix > 22.0:
            suggested_pos_size_pct = 2.5
            risk_tier = "CONSERVATIVE (High Volatility)"
        elif vix > 16.0:
            suggested_pos_size_pct = 4.0
            risk_tier = "MODERATE (Standard Risk)"
        else:
            suggested_pos_size_pct = 5.0
            risk_tier = "AGGRESSIVE (Low Volatility)"

        # ── Nautilus Order Execution Intelligence ──────────────────────────
        # Recommend order types based on regime + sentiment (cloned from NautilusTrader strategy patterns)
        if regime in ("TRENDING_BULLISH", "TRENDING_BEARISH"):
            # Trending: aggressive IOC entry → GTC OCO bracket
            entry_order_type = "IOC MARKET"
            bracket_type = "GTC OCO (TP Limit + SL Stop)"
            reduce_only_note = "Use REDUCE_ONLY flag if holding existing position"
            post_only_note   = "N/A — aggressive entry needed"
        elif regime in ("VOLATILE_RANGEBOUND", "MACRO_SHOCK"):
            # High vol: DAY limit → tighter contingency
            entry_order_type = "DAY LIMIT at entry_price"
            bracket_type     = "GTD OCO expires at 15:15 IST"
            reduce_only_note = "Consider REDUCE_ONLY for all exit legs"
            post_only_note   = "Use POST_ONLY for limit entries to avoid slippage"
        elif regime == "LOW_VOL_SQUEEZE":
            # Breakout play: OTO chain (entry triggers bracket)
            entry_order_type = "GTC STOP_LIMIT at breakout level"
            bracket_type     = "OTO: Entry fills → OCO bracket auto-activates"
            reduce_only_note = "N/A — fresh entry"
            post_only_note   = "N/A"
        else:
            # Neutral: patient GTC limit
            entry_order_type = "GTC LIMIT at entry_price"
            bracket_type     = "GTC OCO (TP + SL)"
            reduce_only_note = "Standard"
            post_only_note   = "GTC limits passively post — no POST_ONLY flag needed"

        # ── UnusualWhales-style options flow implication ───────────────────
        pcr = (option_chain.get("pcr", 1.0) if option_chain else 1.0)
        if pcr > 1.3:
            uw_note = "PCR>1.3: Heavy put hedging — contrarian bullish signal (smart money hedged)"
        elif pcr < 0.7:
            uw_note = "PCR<0.7: Heavy call buying — momentum continues or exhaustion near"
        else:
            uw_note = "PCR neutral: No strong dark-pool / sweep signal detected"

        return {
            "index": index_name,
            "regime": regime,
            "regime_label": regime.replace("_", " ").title(),
            "strategy_name": strategy_name,
            "action": action,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "risk_reward_ratio": f"1:{rr_ratio}",
            "win_probability_pct": win_prob,
            "position_size_pct": suggested_pos_size_pct,
            "risk_tier": risk_tier,
            "description": desc,
            # Nautilus order execution recommendations
            "nautilus_entry_order_type": entry_order_type,
            "nautilus_bracket_type":     bracket_type,
            "nautilus_reduce_only_note": reduce_only_note,
            "nautilus_post_only_note":   post_only_note,
            # UnusualWhales-style options flow note
            "options_flow_note": uw_note,
            "pcr": round(float(pcr), 3),
        }
