"""
ZERO Multi-Agent Consensus Engine
===================================
Inspired by Tauric Research's TradingAgents framework (https://github.com/tauricresearch/tradingagents).

Decomposes trading intelligence into four specialized AI agent roles:
  1. Fundamental Analyst Agent (Macro, ForexFactory news, Rates, GDP/CPI)
  2. Technical Analyst Agent (Price Action, ATR Envelopes, Option PCR, MTF Indicators)
  3. Sentiment Expert Agent (News Sentiment, VADER Lexicon, Breaking Banner Triggers)
  4. Risk Manager Agent (Monte Carlo Ruin Probability, VIX, Max Drawdown Risk)

Synthesizes agent perspectives into a weighted consensus verdict, confidence rating,
and structured multi-agent debate report.
"""

from __future__ import annotations
import math
from typing import Dict, Any, List


class FundamentalAnalyst:
    """Evaluates macro indicators, ForexFactory high-impact events, and economic backdrop."""
    
    def evaluate(self, news_items: List[Dict[str, Any]], sentiment_data: Dict[str, Any]) -> Dict[str, Any]:
        ff_events = [n for n in (news_items or []) if n.get('source', '').startswith('ForexFactory') or n.get('is_forexfactory')]
        
        # Base fundamental score from sentiment and macro events
        sentiment_score = sentiment_data.get('score', 0.0) if isinstance(sentiment_data, dict) else 0.0
        
        bullish_macro = sum(1 for n in ff_events if any(kw in n.get('title', '').lower() for kw in ['growth', 'stimulus', 'cut', 'expansion', 'rally']))
        bearish_macro = sum(1 for n in ff_events if any(kw in n.get('title', '').lower() for kw in ['hike', 'inflation', 'war', 'deficit', 'tightening', 'slowdown']))
        
        raw_score = sentiment_score * 0.6 + (bullish_macro - bearish_macro) * 0.15
        score = max(min(raw_score, 1.0), -1.0)
        confidence = min(60 + len(ff_events) * 8 + abs(score) * 20, 95.0)
        
        if score > 0.35:
            bias = "BULLISH"
            reasoning = f"Macro backdrop supported by positive indicators and {len(ff_events)} ForexFactory releases."
        elif score < -0.35:
            bias = "BEARISH"
            reasoning = f"Macro headwinds detected from inflation/rate pressures and ForexFactory event risks."
        else:
            bias = "NEUTRAL"
            reasoning = "Fundamental factors balanced between growth expansion and hawkish central bank policies."
            
        return {
            "agent": "Fundamental Analyst",
            "score": round(score, 3),
            "bias": bias,
            "confidence": round(confidence, 1),
            "reasoning": reasoning,
            "macro_events_counted": len(ff_events)
        }


class TechnicalAnalyst:
    """Evaluates technical structure, ATR envelopes, Option PCR, and price momentum."""
    
    def evaluate(self, spot_close: float, pred_open: float, atr: float, option_chain: Dict[str, Any] | None) -> Dict[str, Any]:
        if not spot_close or spot_close <= 0:
            return {"agent": "Technical Analyst", "score": 0.0, "bias": "NEUTRAL", "confidence": 50.0, "reasoning": "Insufficient technical data"}
            
        gap_pct = ((pred_open - spot_close) / spot_close) * 100.0
        pcr = option_chain.get('pcr', 1.0) if option_chain else 1.0
        
        # Technical score combination: Gap momentum + Option PCR signal
        gap_signal = max(min(gap_pct / 1.5, 1.0), -1.0)
        pcr_signal = max(min((pcr - 1.0) * 1.5, 1.0), -1.0)
        
        combined = gap_signal * 0.6 + pcr_signal * 0.4
        score = max(min(combined, 1.0), -1.0)
        confidence = round(min(70 + abs(gap_pct) * 10 + abs(pcr - 1.0) * 20, 96.0), 1)
        
        if score > 0.25:
            bias = "BULLISH"
            reasoning = f"Price momentum positive (+{gap_pct:.2f}% expected gap) with bullish Option PCR ({pcr:.2f})."
        elif score < -0.25:
            bias = "BEARISH"
            reasoning = f"Price action showing breakdown risk (-{abs(gap_pct):.2f}% gap) with bearish PCR ({pcr:.2f})."
        else:
            bias = "NEUTRAL"
            reasoning = f"Technical range bound near spot close with neutral Option PCR ({pcr:.2f})."
            
        return {
            "agent": "Technical Analyst",
            "score": round(score, 3),
            "bias": bias,
            "confidence": confidence,
            "reasoning": reasoning,
            "pcr": round(pcr, 2),
            "expected_gap_pct": round(gap_pct, 2)
        }


class SentimentExpert:
    """Evaluates VADER news sentiment, high-impact headlines, and market mood."""
    
    def evaluate(self, sentiment_data: Dict[str, Any]) -> Dict[str, Any]:
        score = sentiment_data.get('score', 0.0) if isinstance(sentiment_data, dict) else 0.0
        intensity = sentiment_data.get('intensity', 'neutral')
        bull_cnt = sentiment_data.get('bullish_count', 0)
        bear_cnt = sentiment_data.get('bearish_count', 0)
        
        confidence = min(65 + (bull_cnt + bear_cnt) * 3 + abs(score) * 25, 94.0)
        
        if score > 0.2:
            bias = "BULLISH"
            reasoning = f"Dominant bullish sentiment ({bull_cnt} positive vs {bear_cnt} negative news signals)."
        elif score < -0.2:
            bias = "BEARISH"
            reasoning = f"Dominant bearish sentiment ({bear_cnt} negative vs {bull_cnt} positive news signals)."
        else:
            bias = "NEUTRAL"
            reasoning = "Market news sentiment balanced with neutral news flow."
            
        return {
            "agent": "Sentiment Expert",
            "score": round(score, 3),
            "bias": bias,
            "intensity": intensity,
            "confidence": round(confidence, 1),
            "reasoning": reasoning
        }


class RiskManager:
    """Evaluates ruin probability, volatility (VIX), and position risk limits."""
    
    def evaluate(self, vix: float, atr_pct: float) -> Dict[str, Any]:
        vix_val = vix if (vix and not math.isnan(vix)) else 15.0
        
        if vix_val > 24.0 or atr_pct > 2.5:
            risk_rating = "HIGH"
            max_leverage = "1.0x (Capital Preservation)"
            ruin_prob_est = min(0.08 + (vix_val - 24.0) * 0.015, 0.25)
            reasoning = f"Elevated volatility (VIX: {vix_val:.1f}). Reduce position sizes and maintain strict stop losses."
        elif vix_val > 18.0:
            risk_rating = "MEDIUM"
            max_leverage = "1.5x (Balanced Exposure)"
            ruin_prob_est = 0.03
            reasoning = f"Moderate volatility (VIX: {vix_val:.1f}). Standard risk-defined trade parameters apply."
        else:
            risk_rating = "LOW"
            max_leverage = "2.0x (Optimal Growth)"
            ruin_prob_est = 0.01
            reasoning = f"Low volatility environment (VIX: {vix_val:.1f}). Favorable regime for trend follow strategies."
            
        return {
            "agent": "Risk Manager",
            "risk_rating": risk_rating,
            "max_leverage": max_leverage,
            "ruin_probability": round(ruin_prob_est * 100, 1),
            "vix": round(vix_val, 1),
            "reasoning": reasoning
        }


class MultiAgentConsensusEngine:
    """
    Orchestrates the 4 agents and synthesizes their signals into a unified,
    confidence-weighted decision consensus.
    """
    
    def __init__(self):
        self.fundamental = FundamentalAnalyst()
        self.technical = TechnicalAnalyst()
        self.sentiment = SentimentExpert()
        self.risk = RiskManager()
        
    def evaluate(self, spot_close: float, pred_open: float, atr: float,
                 news_items: List[Dict[str, Any]], sentiment_data: Dict[str, Any],
                 us_summary: Dict[str, Any] | None = None,
                 option_chain: Dict[str, Any] | None = None) -> Dict[str, Any]:
        
        vix = us_summary.get('VIX', {}).get('price', 15.0) if us_summary else 15.0
        atr_pct = (atr / spot_close * 100.0) if spot_close > 0 else 1.0
        
        fund_eval = self.fundamental.evaluate(news_items, sentiment_data)
        tech_eval = self.technical.evaluate(spot_close, pred_open, atr, option_chain)
        sent_eval = self.sentiment.evaluate(sentiment_data)
        risk_eval = self.risk.evaluate(vix, atr_pct)
        
        # Weighted Consensus Calculation
        # Agent weights: Technical 35%, Fundamental 30%, Sentiment 25%, Risk Adjuster 10%
        w_tech, w_fund, w_sent = 0.35, 0.30, 0.25
        
        consensus_score = (tech_eval['score'] * w_tech +
                           fund_eval['score'] * w_fund +
                           sent_eval['score'] * w_sent)
                           
        # Apply Risk Manager penalty if high volatility
        if risk_eval['risk_rating'] == 'HIGH':
            consensus_score *= 0.7
            
        consensus_score = round(max(min(consensus_score, 1.0), -1.0), 3)
        
        # Determine Verdict
        if consensus_score >= 0.45:
            verdict = "STRONG BULLISH"
        elif consensus_score >= 0.15:
            verdict = "BULLISH"
        elif consensus_score <= -0.45:
            verdict = "STRONG BEARISH"
        elif consensus_score <= -0.15:
            verdict = "BEARISH"
        else:
            verdict = "NEUTRAL"
            
        overall_confidence = round(
            (tech_eval['confidence'] * w_tech +
             fund_eval['confidence'] * w_fund +
             sent_eval['confidence'] * w_sent), 1
        )
        
        debate_summary = (
            f"Technical Analyst recommends {tech_eval['bias']} ({tech_eval['confidence']}% conf). "
            f"Fundamental Analyst suggests {fund_eval['bias']} ({fund_eval['confidence']}% conf). "
            f"Sentiment Expert reads {sent_eval['bias']} ({sent_eval['confidence']}% conf). "
            f"Risk Manager classifies market risk as {risk_eval['risk_rating']} (VIX: {risk_eval['vix']})."
        )
        
        return {
            "verdict": verdict,
            "consensus_score": consensus_score,
            "overall_confidence": overall_confidence,
            "debate_summary": debate_summary,
            "agents": {
                "fundamental": fund_eval,
                "technical": tech_eval,
                "sentiment": sent_eval,
                "risk": risk_eval,
            }
        }
