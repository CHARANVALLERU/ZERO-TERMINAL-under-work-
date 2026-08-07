"""
ZERO AITE one-shot / one-question market brief.

Produces price action, momentum, drawdown, regime, and a verdict
(including explicit DO_NOT_BUY). Uses free/local OHLCV via exam loader
and optionally overlays ``engine.prediction_matrix`` day predictions.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.activity_log import log_activity
from engine.aite.exam import load_market_frame
from engine.aite.indicators import compute_features, drawdown_from_peak, regime_label
from engine.aite.models import MarketBrief
from engine.aite.orderflow import analyze_orderflow, normalize_chart_frame

_SYMBOL_ALIASES = {
    "nifty": "NIFTY 50",
    "nifty50": "NIFTY 50",
    "nifty 50": "NIFTY 50",
    "^nsei": "NIFTY 50",
    "banknifty": "BANKNIFTY",
    "bank nifty": "BANKNIFTY",
    "bnf": "BANKNIFTY",
    "^nsebank": "BANKNIFTY",
    "sensex": "SENSEX",
    "^bsesn": "SENSEX",
}


def parse_brief_question(question: str) -> Tuple[str, str]:
    """
    Extract (symbol, intent) from a free-form question.
    intent ∈ {brief, buy, sell, regime, risk, general}
    """
    q = (question or "").strip()
    low = q.lower()
    symbol = "NIFTY 50"
    for key, sym in sorted(_SYMBOL_ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(key)}\b", low):
            symbol = sym
            break
    intent = "brief"
    if any(w in low for w in ("buy", "long", "accumulate", "should i enter")):
        intent = "buy"
    elif any(w in low for w in ("sell", "short", "exit", "reduce")):
        intent = "sell"
    elif any(w in low for w in ("regime", "trend", "range")):
        intent = "regime"
    elif any(w in low for w in ("risk", "drawdown", "dd", "danger")):
        intent = "risk"
    return symbol, intent


def _safe_prediction_slice(symbol: str) -> Dict[str, Any]:
    """Best-effort prediction_matrix overlay — never raises / never blocks long."""
    try:
        from engine.prediction_matrix import generate_prediction_matrix
        matrix = generate_prediction_matrix()
        if not isinstance(matrix, dict):
            return {}
        # Common shapes: { "NIFTY 50": {...}, ... } or nested under "indices"
        if symbol in matrix and isinstance(matrix[symbol], dict):
            return _thin_pred(matrix[symbol])
        indices = matrix.get("indices") or matrix.get("predictions") or matrix
        if isinstance(indices, dict) and symbol in indices:
            return _thin_pred(indices[symbol])
        # Fuzzy key match
        for k, v in (indices.items() if isinstance(indices, dict) else []):
            if str(k).upper().replace(" ", "") == symbol.upper().replace(" ", ""):
                return _thin_pred(v if isinstance(v, dict) else {})
    except Exception as exc:
        return {"available": False, "error": str(exc)[:120]}
    return {"available": False}


def _thin_pred(d: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only brief-relevant prediction fields."""
    if not d or d.get("error"):
        return {"available": False, "error": d.get("error") if d else "empty"}
    keys = (
        "spot_close", "predicted_open", "predicted_high", "predicted_low",
        "predicted_close", "bias", "confidence", "atr", "pcr",
        "gift_premium", "sentiment_score", "range_low", "range_high",
    )
    out = {"available": True}
    for k in keys:
        if k in d and d[k] is not None:
            out[k] = d[k]
    # nested common patterns
    for nest in ("levels", "prediction", "day"):
        sub = d.get(nest)
        if isinstance(sub, dict):
            for k in keys:
                if k in sub and k not in out:
                    out[k] = sub[k]
    return out


def _price_action_summary(feats) -> Dict[str, Any]:
    if feats is None or feats.empty:
        return {"bars": 0, "change_1d_pct": 0.0, "change_5d_pct": 0.0, "note": "no data"}
    c = feats["close"].astype(float)
    bars = len(c)
    ch1 = float((c.iloc[-1] / c.iloc[-2] - 1) * 100) if bars >= 2 else 0.0
    ch5 = float((c.iloc[-1] / c.iloc[-6] - 1) * 100) if bars >= 6 else 0.0
    hi = float(c.tail(20).max()) if bars >= 5 else float(c.iloc[-1])
    lo = float(c.tail(20).min()) if bars >= 5 else float(c.iloc[-1])
    return {
        "bars": bars,
        "change_1d_pct": round(ch1, 3),
        "change_5d_pct": round(ch5, 3),
        "range_20_high": round(hi, 2),
        "range_20_low": round(lo, 2),
        "last_close": round(float(c.iloc[-1]), 2),
    }


def _verdict(
    momentum: float,
    drawdown: float,
    regime: str,
    oflow: Dict[str, Any],
    pred: Dict[str, Any],
    intent: str = "brief",
) -> Tuple[str, str]:
    """Return (verdict, rationale). Includes DO_NOT_BUY path."""
    aggr = oflow.get("aggression", "NEUTRAL")
    imb = float(oflow.get("imbalance") or 0)
    pcr = oflow.get("pcr")
    pred_bias = str(pred.get("bias") or "").lower() if pred.get("available") else ""

    # Hard do-not-buy gates
    if drawdown >= cfg.BRIEF_DO_NOT_BUY_DD and momentum < 0:
        return (
            "DO_NOT_BUY",
            f"Peak-to-trough drawdown {drawdown:.1%} with negative momentum; "
            f"regime={regime}. Fresh capital deployment discouraged.",
        )
    if regime == "TREND_DOWN" and aggr == "SELL_AGGRESSIVE":
        return (
            "DO_NOT_BUY",
            "Downtrend + sell-side aggression in order-flow proxy. Stand aside on longs.",
        )
    if regime == "HIGH_VOL" and drawdown >= cfg.BRIEF_DO_NOT_BUY_DD * 0.75:
        return (
            "DO_NOT_BUY",
            f"Elevated volatility with {drawdown:.1%} drawdown — wait for regime settle.",
        )
    if intent == "buy" and regime == "TREND_DOWN":
        return (
            "DO_NOT_BUY",
            "Question asked about buying into a confirmed downtrend — deny.",
        )
    if pcr is not None and float(pcr) > 1.4 and momentum < 0:
        return (
            "DO_NOT_BUY",
            f"Elevated put/call ratio (PCR={float(pcr):.2f}) with negative momentum.",
        )
    if pred_bias in ("bearish", "down", "sell") and regime in ("TREND_DOWN", "HIGH_VOL"):
        return (
            "DO_NOT_BUY",
            f"Prediction-matrix bias={pred_bias} aligned with {regime}.",
        )

    if regime == "TREND_UP" and momentum > 1.0 and imb > 0.1:
        return (
            "ACCUMULATE",
            f"Uptrend intact (mom={momentum:.2f}%), buy-side flow supportive.",
        )
    if regime == "TREND_DOWN" and momentum < -1.0:
        return (
            "REDUCE",
            "Downtrend / negative momentum — trim risk exposure.",
        )
    if regime == "RANGE":
        return (
            "HOLD",
            "Range-bound tape; no edge for aggressive directional deployment.",
        )
    return (
        "HOLD",
        f"Regime={regime}, mom={momentum:.2f}%, dd={drawdown:.1%}; maintain posture.",
    )


def build_brief(
    symbol: str = "NIFTY 50",
    persist: bool = True,
    *,
    include_prediction: bool = True,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """One-shot institutional brief for a symbol (optionally from a question)."""
    intent = "brief"
    if question:
        symbol, intent = parse_brief_question(question)

    # Normalize alias
    symbol = _SYMBOL_ALIASES.get(symbol.lower(), symbol) if isinstance(symbol, str) else "NIFTY 50"

    df = normalize_chart_frame(load_market_frame(symbol, bars=120))
    feats = compute_features(df)
    oflow = analyze_orderflow(df, symbol)
    pred = _safe_prediction_slice(symbol) if include_prediction else {"available": False}
    pa = _price_action_summary(feats)

    if feats.empty:
        brief = MarketBrief(
            symbol=symbol, price=0.0, momentum=0.0, drawdown=0.0,
            regime="UNKNOWN", verdict="HOLD",
            rationale="No market data available.",
            orderflow=oflow,
        )
        d = brief.to_dict()
        d["price_action"] = pa
        d["prediction"] = pred
        d["question"] = question
        d["intent"] = intent
        if persist:
            store.save_brief(d)
        return d

    price = float(feats["close"].iloc[-1])
    momentum = float(feats["mom_20"].iloc[-1]) if "mom_20" in feats else 0.0
    closes = feats["close"].values.astype(float)
    drawdown = drawdown_from_peak(closes[-60:])
    regime = regime_label(feats)
    verdict, rationale = _verdict(momentum, drawdown, regime, oflow, pred, intent=intent)

    brief = MarketBrief(
        symbol=symbol,
        price=round(price, 2),
        momentum=round(momentum, 3),
        drawdown=round(drawdown, 4),
        regime=regime,
        verdict=verdict,
        rationale=rationale,
        orderflow=oflow,
    )
    d = brief.to_dict()
    d["price_action"] = pa
    d["prediction"] = pred
    d["question"] = question
    d["intent"] = intent
    if persist:
        store.save_brief(d)
        store.log_event("INFO", f"Brief {symbol}: {verdict}", symbol=symbol)
        log_activity(
            f"Brief {symbol}: {verdict} — {rationale[:120]}",
            level="BRIEF",
            source="brief",
            symbol=symbol,
            verdict=verdict,
        )
    return d


def ask_brief(question: str, persist: bool = True) -> Dict[str, Any]:
    """
    One-question entrypoint for UI / agents.
    Example: ``ask_brief("Should I buy NIFTY today?")``
    """
    symbol, _ = parse_brief_question(question)
    return build_brief(symbol=symbol, persist=persist, question=question)


def build_multi_brief(symbols: List[str] | None = None) -> List[Dict[str, Any]]:
    symbols = symbols or cfg.DEFAULT_SYMBOLS
    return [build_brief(s) for s in symbols]
