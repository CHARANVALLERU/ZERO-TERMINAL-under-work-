"""
ZERO Fincept-Inspired Developer Platform & Research Dashboard Engine
=====================================================================
Inspired by Fincept Terminal (Fincept-Corporation/FinceptTerminal):
- State-of-the-art financial intelligence platform
- Institutional-grade analytics, AI automation, unlimited data connectivity
- Quant team workflows, research dashboards, sentiment workflows, market data tools

This module provides:
1. ResearchDashboardEngine  - Quant research workflow orchestration
2. SentimentWorkflowEngine  - Multi-source sentiment aggregation pipeline
3. MarketDataToolkit        - NSE/BSE/global market data tools
4. QuantTeamOrchestrator    - Multi-role analyst team simulation (like Fincept quant/dev teams)
5. DeveloperPlatformCore    - Modular analytics platform logic
"""

from __future__ import annotations

import datetime
import math
from typing import Dict, List, Optional, Any
import numpy as np


# ─────────────────────────────────────────────
#  Research Dashboard Engine
# ─────────────────────────────────────────────

class ResearchDashboardEngine:
    """
    Fincept Terminal-inspired research workflow engine.
    Coordinates equity research, portfolio analytics, and derivatives analysis.
    """

    def run_equity_analysis(self, symbol: str, close: float, atr: float,
                             sentiment_score: float, pe_ratio: Optional[float] = None,
                             roe: Optional[float] = None, debt_equity: Optional[float] = None) -> Dict:
        """
        Institutional-grade equity research snapshot.
        Combines technical, fundamental, and sentiment layers.
        """
        # Technical score
        tech_score = 0.0
        if atr > 0 and close > 0:
            atr_pct = atr / close * 100
            tech_score += min(1.0, 1.0 - atr_pct / 3.0)  # lower ATR = more stable

        # Fundamental score
        fund_score = 0.0
        if pe_ratio is not None:
            if pe_ratio < 15:
                fund_score += 0.5
            elif pe_ratio < 25:
                fund_score += 0.25
        if roe is not None:
            if roe > 20:
                fund_score += 0.3
            elif roe > 12:
                fund_score += 0.15
        if debt_equity is not None:
            if debt_equity < 0.5:
                fund_score += 0.2

        # Composite score
        composite = (tech_score * 0.4 + fund_score * 0.35 +
                     max(-1, min(1, sentiment_score)) * 0.25)
        composite = max(0.0, min(1.0, composite))

        if composite > 0.7:
            rating = "STRONG BUY"
            color  = "#00ff88"
        elif composite > 0.5:
            rating = "BUY"
            color  = "#4caf50"
        elif composite > 0.35:
            rating = "HOLD"
            color  = "#D4AF37"
        elif composite > 0.2:
            rating = "REDUCE"
            color  = "#D4AF37"
        else:
            rating = "SELL"
            color  = "#E50914"

        return {
            "symbol":          symbol,
            "composite_score": round(composite, 4),
            "rating":          rating,
            "rating_color":    color,
            "technical_score": round(tech_score, 4),
            "fundamental_score": round(fund_score, 4),
            "sentiment_score": round(sentiment_score, 4),
            "pe_ratio":        pe_ratio,
            "roe":             roe,
            "debt_equity":     debt_equity,
            "generated_at":    datetime.datetime.now().isoformat(timespec="seconds"),
        }

    def run_portfolio_analytics(self, positions: List[Dict],
                                market_prices: Dict[str, float]) -> Dict:
        """
        Institutional portfolio analytics: sector exposure, concentration, HHI.
        """
        total_value = 0.0
        sector_exposure: Dict[str, float] = {}
        pos_values = []

        for p in positions:
            sym = p.get("symbol", "UNKNOWN")
            qty = float(p.get("quantity", 0))
            mp  = market_prices.get(sym, float(p.get("avg_cost", 0)))
            val = qty * mp
            total_value += val
            sector = p.get("sector", "Unknown")
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + val
            pos_values.append({"symbol": sym, "value": val, "weight": 0.0})

        if total_value > 0:
            for pv in pos_values:
                pv["weight"] = round(pv["value"] / total_value * 100, 2)
            for k in sector_exposure:
                sector_exposure[k] = round(sector_exposure[k] / total_value * 100, 2)

        # Herfindahl-Hirschman Index (portfolio concentration)
        weights = [pv["weight"] / 100 for pv in pos_values]
        hhi = round(sum(w**2 for w in weights), 4)

        return {
            "total_value":     round(total_value, 2),
            "num_positions":   len(positions),
            "sector_exposure": sector_exposure,
            "position_weights": pos_values,
            "hhi_concentration": hhi,
            "hhi_interpretation": (
                "Highly Concentrated" if hhi > 0.25 else
                "Moderately Concentrated" if hhi > 0.15 else
                "Well Diversified"
            ),
        }

    def run_derivatives_analysis(self, spot: float, strike: float,
                                  time_to_expiry_days: float, iv: float,
                                  risk_free: float = 0.065) -> Dict:
        """
        Options Greeks calculator using Black-Scholes (pure math, no scipy).
        """
        def _phi(x):
            """Standard normal CDF via erf."""
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

        def _phi_prime(x):
            return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

        if spot <= 0 or strike <= 0 or time_to_expiry_days <= 0 or iv <= 0:
            return {"error": "Invalid inputs for Greeks calculation"}

        T = time_to_expiry_days / 252.0
        S, K, r, sigma = spot, strike, risk_free, iv / 100.0

        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        call_price = S * _phi(d1) - K * math.exp(-r * T) * _phi(d2)
        put_price  = K * math.exp(-r * T) * _phi(-d2) - S * _phi(-d1)

        delta_call = _phi(d1)
        delta_put  = delta_call - 1.0
        gamma      = _phi_prime(d1) / (S * sigma * math.sqrt(T))
        theta_call = (-(S * _phi_prime(d1) * sigma) / (2 * math.sqrt(T))
                      - r * K * math.exp(-r * T) * _phi(d2)) / 252
        vega       = S * _phi_prime(d1) * math.sqrt(T) / 100.0

        return {
            "spot":        spot,
            "strike":      strike,
            "days_to_exp": time_to_expiry_days,
            "iv_pct":      iv,
            "call_price":  round(call_price, 2),
            "put_price":   round(put_price, 2),
            "delta_call":  round(delta_call, 4),
            "delta_put":   round(delta_put, 4),
            "gamma":       round(gamma, 6),
            "theta_daily": round(theta_call, 4),
            "vega_per1pct": round(vega, 4),
            "d1": round(d1, 4), "d2": round(d2, 4),
        }


# ─────────────────────────────────────────────
#  Sentiment Workflow Engine
# ─────────────────────────────────────────────

class SentimentWorkflowEngine:
    """
    Fincept-style multi-source sentiment aggregation pipeline.
    Ingests news feeds, social data, and options flow to produce a
    unified market sentiment score with confidence intervals.
    """

    # Extended lexicon beyond market_news.py (Fincept-level depth)
    _UNUSUAL_WHALES_BEARISH = [
        "put sweep", "massive puts", "bearish flow", "dark pool sell",
        "high vol put", "block trade sell", "unusual puts", "gamma exposure negative",
        "institutional selling", "hedge fund short", "vix spike", "credit spread widen",
    ]
    _UNUSUAL_WHALES_BULLISH = [
        "call sweep", "massive calls", "bullish flow", "dark pool buy",
        "high vol call", "block trade buy", "unusual calls", "gamma exposure positive",
        "institutional buying", "hedge fund long", "put/call low", "credit spread tighten",
    ]
    _INVO_SENTIMENT_SIGNALS = [
        ("rate cut expected",    0.8), ("fed pivot",          0.7),
        ("soft landing",         0.6), ("earnings beat",      0.5),
        ("buyback announce",     0.5), ("m&a deal",           0.4),
        ("rate hike",           -0.7), ("fed hawkish",       -0.6),
        ("recession risk",      -0.8), ("earnings miss",     -0.5),
        ("guidance cut",        -0.6), ("layoff wave",       -0.4),
    ]

    def analyze_news_feed(self, news_items: List[Dict]) -> Dict:
        """
        Enhanced sentiment analysis incorporating unusual-whales-style
        options flow signals and Invo-style macro signals.
        """
        scores   = []
        bullish  = 0
        bearish  = 0
        signals  = []

        for item in news_items:
            title = (item.get("title") or "").lower()
            base_score = float(item.get("sentiment", 0.0) or 0.0)

            # Unusual Whales flow detection
            uw_bull = sum(1 for kw in self._UNUSUAL_WHALES_BULLISH if kw in title)
            uw_bear = sum(1 for kw in self._UNUSUAL_WHALES_BEARISH if kw in title)
            flow_adj = (uw_bull - uw_bear) * 0.15

            # Invo macro signal
            invo_adj = 0.0
            for phrase, weight in self._INVO_SENTIMENT_SIGNALS:
                if phrase in title:
                    invo_adj += weight * 0.1
                    signals.append({"phrase": phrase, "weight": weight})

            final_score = max(-1.0, min(1.0, base_score + flow_adj + invo_adj))
            scores.append(final_score)

            if final_score > 0.1:
                bullish += 1
            elif final_score < -0.1:
                bearish += 1

        if not scores:
            return {
                "composite_score": 0.0,
                "confidence":      0.5,
                "bullish_count":   0,
                "bearish_count":   0,
                "signals":         [],
                "intensity":       "neutral",
            }

        arr  = np.array(scores)
        mean = float(np.mean(arr))
        std  = float(np.std(arr)) if len(arr) > 1 else 0.3
        # Confidence = 1 - std (tighter consensus = higher confidence)
        confidence = round(max(0.3, min(0.99, 1.0 - std)), 4)

        intensity_map = [
            (0.6,  "extreme_bullish"), (0.3,  "strong_bullish"),
            (0.1,  "bullish"),         (-0.1, "neutral"),
            (-0.3, "bearish"),         (-0.6, "strong_bearish"),
        ]
        intensity = "extreme_bearish"
        for threshold, label in intensity_map:
            if mean >= threshold:
                intensity = label
                break

        return {
            "composite_score": round(mean, 4),
            "confidence":      confidence,
            "bullish_count":   bullish,
            "bearish_count":   bearish,
            "neutral_count":   len(scores) - bullish - bearish,
            "signals":         signals[:10],
            "intensity":       intensity,
            "score_p10":       round(float(np.percentile(arr, 10)), 4),
            "score_p90":       round(float(np.percentile(arr, 90)), 4),
        }

    def compute_unusual_whales_score(self, options_chain: Optional[Dict]) -> Dict:
        """
        Derives an options-flow sentiment score from options chain data
        in the style of UnusualWhales dark-pool / sweep monitoring.
        """
        if not options_chain:
            return {"flow_score": 0.0, "interpretation": "No options data"}

        pcr = float(options_chain.get("pcr", 1.0) or 1.0)
        max_call_oi = float(options_chain.get("max_ce_oi_strike", 0) or 0)
        max_put_oi  = float(options_chain.get("max_pe_oi_strike", 0) or 0)
        total_ce    = float(options_chain.get("total_call_oi", 0) or 0)
        total_pe    = float(options_chain.get("total_put_oi", 0) or 0)

        # PCR-based flow score: pcr > 1.2 = bearish hedge (paradoxically bullish contrarian)
        pcr_score = max(-1.0, min(1.0, (1.0 - pcr) * 1.5))

        # OI concentration score
        if max_call_oi > 0 and max_put_oi > 0:
            oi_ratio = max_call_oi / max_put_oi
            oi_score = max(-1.0, min(1.0, (oi_ratio - 1.0) * 0.8))
        else:
            oi_score = 0.0

        flow_score = pcr_score * 0.6 + oi_score * 0.4

        if flow_score > 0.4:
            interp = "🦁 Strong Bullish Flow (Smart Money Buying)"
        elif flow_score > 0.15:
            interp = "📈 Moderate Bullish Options Flow"
        elif flow_score < -0.4:
            interp = "🐻 Strong Bearish Hedging (Smart Money Selling)"
        elif flow_score < -0.15:
            interp = "📉 Moderate Bearish Options Flow"
        else:
            interp = "⚖️ Neutral / Mixed Options Flow"

        return {
            "flow_score":      round(flow_score, 4),
            "pcr":             round(pcr, 3),
            "pcr_signal":      round(pcr_score, 4),
            "oi_signal":       round(oi_score, 4),
            "interpretation":  interp,
            "max_call_strike": max_call_oi,
            "max_put_strike":  max_put_oi,
        }


# ─────────────────────────────────────────────
#  Market Data Toolkit
# ─────────────────────────────────────────────

class MarketDataToolkit:
    """
    Fincept-style market data tools: economic indicators,
    sector rotation, inter-market analysis, currency signals.
    """

    @staticmethod
    def compute_market_breadth(advances: int, declines: int,
                               unchanged: int = 0) -> Dict:
        """
        A/D ratio, McClellan Oscillator proxy, and breadth interpretation.
        """
        total = advances + declines + unchanged or 1
        ad_ratio = advances / max(declines, 1)
        breadth_pct = (advances - declines) / total * 100

        if ad_ratio > 2.0:
            signal = "STRONG BREADTH (Broad Rally)"
        elif ad_ratio > 1.3:
            signal = "POSITIVE BREADTH"
        elif ad_ratio > 0.75:
            signal = "NEUTRAL BREADTH"
        elif ad_ratio > 0.5:
            signal = "WEAK BREADTH"
        else:
            signal = "BREADTH COLLAPSE (Broad Sell-off)"

        return {
            "advances":     advances,
            "declines":     declines,
            "unchanged":    unchanged,
            "ad_ratio":     round(ad_ratio, 3),
            "breadth_pct":  round(breadth_pct, 2),
            "signal":       signal,
        }

    @staticmethod
    def compute_intermarket_signals(us_futures_chg_pct: float,
                                    crude_chg_pct: float,
                                    dxy_chg_pct: float,
                                    vix: float) -> Dict:
        """
        Cross-asset signal for Indian market open direction.
        Based on Fincept-style inter-market correlation model.
        """
        # Correlation priors for Nifty
        # US futures: +0.85 corr with Nifty gap
        # Crude: -0.4 corr (India is oil importer)
        # DXY: -0.55 corr (strong dollar = FII outflow)
        # VIX: -0.70 corr

        nifty_signal = (
            us_futures_chg_pct * 0.55 +
            crude_chg_pct      * (-0.25) +
            dxy_chg_pct        * (-0.35) +
            max(0, 18 - vix)   * 0.02    # low VIX = bullish
        )

        risk_tier = "HIGH RISK" if vix > 24 else ("ELEVATED" if vix > 18 else "LOW RISK")

        if nifty_signal > 0.5:
            direction = "STRONG GAP UP EXPECTED"
        elif nifty_signal > 0.15:
            direction = "MODERATE GAP UP EXPECTED"
        elif nifty_signal < -0.5:
            direction = "STRONG GAP DOWN EXPECTED"
        elif nifty_signal < -0.15:
            direction = "MODERATE GAP DOWN EXPECTED"
        else:
            direction = "FLAT OPEN EXPECTED"

        return {
            "net_intermarket_score": round(nifty_signal, 4),
            "direction":             direction,
            "risk_tier":             risk_tier,
            "contributors": {
                "us_futures":  round(us_futures_chg_pct * 0.55, 4),
                "crude_oil":   round(crude_chg_pct * (-0.25), 4),
                "dxy_dollar":  round(dxy_chg_pct * (-0.35), 4),
                "vix_factor":  round(max(0, 18 - vix) * 0.02, 4),
            },
        }

    @staticmethod
    def sector_rotation_matrix(sector_returns: Dict[str, float]) -> List[Dict]:
        """
        Ranks sectors by momentum score for rotation strategy (Fincept-style).
        Returns sorted sector list with momentum tier.
        """
        if not sector_returns:
            return []

        values = list(sector_returns.values())
        mean_r = float(np.mean(values))
        std_r  = float(np.std(values)) if len(values) > 1 else 1.0

        ranked = []
        for sector, ret in sector_returns.items():
            z = (ret - mean_r) / std_r if std_r else 0
            tier = ("LEADING" if z > 1.0 else
                    "IMPROVING" if z > 0 else
                    "LAGGING" if z > -1.0 else "TRAILING")
            ranked.append({
                "sector":       sector,
                "return_pct":   round(ret, 2),
                "z_score":      round(z, 3),
                "tier":         tier,
                "action":       "OVERWEIGHT" if z > 0.5 else
                                "NEUTRAL" if z > -0.5 else "UNDERWEIGHT",
            })
        ranked.sort(key=lambda x: x["z_score"], reverse=True)
        return ranked


# ─────────────────────────────────────────────
#  Quant Team Orchestrator (Fincept quant/dev teams model)
# ─────────────────────────────────────────────

class QuantTeamOrchestrator:
    """
    Fincept Terminal-inspired quant team simulation.
    Models three specialist roles producing independent research reports
    that get merged into a unified trade thesis.

    Roles:
    1. Quant Strategist   - Alpha signal generation, factor models
    2. Risk Analyst       - Drawdown risk, position sizing, stress testing
    3. Market Microstructure Specialist - Order flow, liquidity, spread analysis
    """

    def __init__(self):
        self.research_engine   = ResearchDashboardEngine()
        self.sentiment_engine  = SentimentWorkflowEngine()
        self.market_toolkit    = MarketDataToolkit()

    def quant_strategist_report(self, symbol: str, close: float, atr: float,
                                 returns_30d: Optional[List[float]] = None) -> Dict:
        """Alpha signal generation with factor exposures."""
        # Momentum factor
        mom_score = 0.0
        if returns_30d and len(returns_30d) >= 5:
            arr = np.array(returns_30d)
            mom_score = float(np.mean(arr[-5:])) / float(np.std(arr) or 0.01)
            mom_score = max(-2.0, min(2.0, mom_score))

        # Volatility factor (lower = better quality)
        vol_factor = -min(1.0, atr / close * 100 / 2.0) if close > 0 else 0.0

        alpha_score = mom_score * 0.6 + vol_factor * 0.4

        return {
            "role":          "Quant Strategist",
            "symbol":        symbol,
            "alpha_score":   round(alpha_score, 4),
            "momentum_factor": round(mom_score, 4),
            "volatility_factor": round(vol_factor, 4),
            "signal":        "LONG" if alpha_score > 0.3 else
                             "SHORT" if alpha_score < -0.3 else "FLAT",
            "confidence":    round(min(0.95, 0.5 + abs(alpha_score) * 0.2), 4),
        }

    def risk_analyst_report(self, close: float, atr: float, vix: float,
                             capital: float, max_risk_pct: float = 0.02) -> Dict:
        """Position sizing, Kelly criterion, and stress test."""
        if close <= 0 or atr <= 0:
            return {"error": "Invalid inputs"}

        # Kelly criterion (simplified half-Kelly)
        win_rate = 0.55  # assumed base
        rr_ratio = 1.5   # assumed base
        kelly_pct = max(0, (win_rate * rr_ratio - (1 - win_rate)) / rr_ratio)
        half_kelly = kelly_pct * 0.5

        # Risk-adjusted position size
        risk_per_trade = capital * max_risk_pct
        position_size  = risk_per_trade / atr
        position_size  = round(min(position_size, capital * half_kelly / close), 4)

        # Stress test: what if atr triples?
        stress_loss = position_size * atr * 3

        return {
            "role":               "Risk Analyst",
            "kelly_pct":          round(half_kelly * 100, 2),
            "position_size_units": round(position_size, 2),
            "position_value":     round(position_size * close, 2),
            "max_risk_amount":    round(risk_per_trade, 2),
            "stress_loss_3x_atr": round(stress_loss, 2),
            "vix_regime":         "HIGH" if vix > 24 else "NORMAL" if vix > 15 else "LOW",
            "recommended_leverage": 1.0 if vix > 24 else 1.5 if vix > 18 else 2.0,
        }

    def microstructure_report(self, bid: float, ask: float, spot: float,
                               avg_daily_volume: float, order_qty: float) -> Dict:
        """Market microstructure: spread, market impact, liquidity score."""
        spread_pts  = ask - bid
        spread_bps  = spread_pts / spot * 10000 if spot > 0 else 0
        market_impact_bps = (order_qty / max(avg_daily_volume, 1)) ** 0.6 * 100
        total_cost_bps = spread_bps / 2 + market_impact_bps
        liquidity_score = round(max(0.0, 1.0 - total_cost_bps / 50.0), 4)

        return {
            "role":                "Microstructure Specialist",
            "bid":                 bid,
            "ask":                 ask,
            "spread_points":       round(spread_pts, 2),
            "spread_bps":          round(spread_bps, 2),
            "market_impact_bps":   round(market_impact_bps, 2),
            "total_cost_bps":      round(total_cost_bps, 2),
            "liquidity_score":     liquidity_score,
            "execution_advice":    ("EXECUTE" if liquidity_score > 0.7 else
                                   "USE LIMIT ORDER" if liquidity_score > 0.4 else
                                   "SPLIT ORDER / ALGO EXECUTION"),
        }

    def unified_trade_thesis(self, symbol: str, close: float, atr: float,
                              vix: float, capital: float,
                              news_items: Optional[List] = None,
                              options_chain: Optional[Dict] = None) -> Dict:
        """
        Merge all analyst reports into a single trade thesis.
        This is the 'quant core team' output shown in the Trading Terminal.
        """
        strat_rep = self.quant_strategist_report(symbol, close, atr)
        risk_rep  = self.risk_analyst_report(close, atr, vix, capital)
        micro_rep = self.microstructure_report(
            bid=close - atr * 0.05, ask=close + atr * 0.05,
            spot=close, avg_daily_volume=capital / close * 10, order_qty=1.0
        )
        sent_rep  = (self.sentiment_engine.analyze_news_feed(news_items)
                     if news_items else {"composite_score": 0.0, "intensity": "neutral"})
        uw_rep    = self.sentiment_engine.compute_unusual_whales_score(options_chain)

        # Composite verdict
        alpha     = strat_rep.get("alpha_score", 0.0)
        flow      = uw_rep.get("flow_score", 0.0)
        sentiment = sent_rep.get("composite_score", 0.0)
        liq       = micro_rep.get("liquidity_score", 0.5)

        final_score = alpha * 0.4 + flow * 0.3 + sentiment * 0.2 + (liq - 0.5) * 0.1
        final_score = max(-1.0, min(1.0, final_score))

        verdict = (
            "🟢 STRONG LONG THESIS"   if final_score > 0.5 else
            "📈 MODERATE LONG BIAS"   if final_score > 0.2 else
            "🔴 STRONG SHORT THESIS"  if final_score < -0.5 else
            "📉 MODERATE SHORT BIAS"  if final_score < -0.2 else
            "⚖️ NEUTRAL — WAIT FOR SETUP"
        )

        return {
            "symbol":         symbol,
            "final_score":    round(final_score, 4),
            "verdict":        verdict,
            "quant_strategy": strat_rep,
            "risk_analysis":  risk_rep,
            "microstructure": micro_rep,
            "sentiment":      sent_rep,
            "options_flow":   uw_rep,
            "generated_at":   datetime.datetime.now().isoformat(timespec="seconds"),
        }


# ─────────────────────────────────────────────
#  Developer Platform Core (Fincept modular architecture)
# ─────────────────────────────────────────────

class DeveloperPlatformCore:
    """
    Fincept Terminal's architectural pattern: plugin-style modular analytics
    where each module is independently callable and composable.

    Modules:
    - equity_module:       Equity research + screening
    - portfolio_module:    Portfolio analytics + HHI
    - derivatives_module:  Options Greeks + payoff analysis
    - macro_module:        Macro indicators + regime detection
    """

    def __init__(self):
        self.research   = ResearchDashboardEngine()
        self.quant_team = QuantTeamOrchestrator()

    def run_module(self, module: str, **kwargs) -> Dict:
        """Dispatch analytics request to the appropriate module."""
        dispatch = {
            "equity":      self._equity_module,
            "portfolio":   self._portfolio_module,
            "derivatives": self._derivatives_module,
            "macro":       self._macro_module,
            "quant_team":  self._quant_team_module,
        }
        fn = dispatch.get(module)
        if fn is None:
            return {"error": f"Unknown module '{module}'. Available: {list(dispatch.keys())}"}
        try:
            return fn(**kwargs)
        except Exception as e:
            return {"error": str(e), "module": module}

    def _equity_module(self, symbol: str, close: float, atr: float,
                       sentiment_score: float = 0.0, **kwargs) -> Dict:
        return self.research.run_equity_analysis(symbol, close, atr, sentiment_score, **kwargs)

    def _portfolio_module(self, positions: List[Dict],
                          market_prices: Dict[str, float], **kwargs) -> Dict:
        return self.research.run_portfolio_analytics(positions, market_prices)

    def _derivatives_module(self, spot: float, strike: float,
                            days_to_expiry: float, iv: float, **kwargs) -> Dict:
        return self.research.run_derivatives_analysis(spot, strike, days_to_expiry, iv)

    def _macro_module(self, us_futures_chg: float = 0.0, crude_chg: float = 0.0,
                      dxy_chg: float = 0.0, vix: float = 15.0, **kwargs) -> Dict:
        return MarketDataToolkit.compute_intermarket_signals(
            us_futures_chg, crude_chg, dxy_chg, vix
        )

    def _quant_team_module(self, symbol: str, close: float, atr: float,
                           vix: float, capital: float = 100000.0, **kwargs) -> Dict:
        return self.quant_team.unified_trade_thesis(symbol, close, atr, vix, capital, **kwargs)


# ─────────────────────────────────────────────
#  Module-level singletons
# ─────────────────────────────────────────────

_platform: Optional[DeveloperPlatformCore] = None

def get_platform() -> DeveloperPlatformCore:
    global _platform
    if _platform is None:
        _platform = DeveloperPlatformCore()
    return _platform
