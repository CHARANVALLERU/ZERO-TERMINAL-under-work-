"""
ZERO News-Impact Engine
=======================

Turns a raw headline into a *quantified market call*: which bucket of news it
is, how severe it is, whether it is bullish or bearish, and — the part that
matters for a trader — an **estimated move for each Indian index** in both
percent and points.

Worked examples (mirroring the user's brief):

* "Trump says the Iran peace deal is off"  → geopolitical, high severity,
  strongly bearish → estimated Nifty ≈ -1.6% (~-380 pts).
* "Indian IT sector hits record export milestone" → sector_it, mild bullish →
  estimated Nifty ≈ +0.4% (~+95 pts), larger tilt on IT-heavy Nifty/Sensex than
  on Bank Nifty.

The model is intentionally interpretable (category × severity × sentiment ×
volatility), not a black box — a pre-market desk needs to *explain* an alert,
not just emit a number. It reuses ZERO's existing domain sentiment scorer.

Pure-python, no network, no heavy deps → fully unit-testable offline.
"""

from __future__ import annotations

import re

from config import (
    NEWS_REFERENCE_LEVELS,
    NEWS_BASE_MOVE_PCT,
    NEWS_MAX_MOVE_PCT,
    NEWS_ALERT_THRESHOLD,
)

# Reuse the tuned domain+VADER sentiment scorer already in the codebase.
try:
    from data.market_news import _score_text as _sentiment
except Exception:  # pragma: no cover - keep the engine importable in isolation
    def _sentiment(text):
        return 0.0


# ---------------------------------------------------------------------------
#  Category model
#  Each category carries:
#    weight        - how hard this class of news hits equities (0..1)
#    keywords      - trigger phrases
#    index_tilt    - per-index sensitivity multiplier (some news hits some
#                    indices harder, e.g. IT news → Nifty/Sensex > Bank Nifty,
#                    rate news → Bank Nifty > others)
# ---------------------------------------------------------------------------
_DEFAULT_TILT = {"NIFTY 50": 1.0, "BANKNIFTY": 1.0, "SENSEX": 1.0}

CATEGORIES = {
    "geopolitical": {
        "weight": 1.00,
        "label": "GEOPOLITICAL & ELECTIONS",
        "keywords": [
            "war", "ceasefire", "peace deal", "peace talks", "invasion", "invade",
            "missile", "nuclear", "airstrike", "air strike", "strike", "attack",
            "sanction", "sanctions", "conflict", "escalation", "escalate", "troops",
            "border", "coup", "terror", "terrorist", "hostage", "iran", "israel",
            "russia", "ukraine", "gaza", "middle east", "opec", "blockade", "drone",
            "election", "elections", "poll", "polls", "exit poll", "ballot", "vote",
            "voting", "parliamentary", "presidential", "general election", "campaign",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "monetary_policy": {
        "weight": 0.95,
        "label": "CENTRAL BANK & PRESS CONF",
        "keywords": [
            "rate cut", "rate hike", "rate decision", "fed", "fomc", "powell", "jerome powell",
            "rbi", "shaktikanta das", "das", "repo rate", "reverse repo", "interest rate",
            "central bank", "press conference", "policy statement", "monetary policy",
            "hawkish", "dovish", "tapering", "liquidity", "bond yield", "yields",
            "quantitative", "basis points", "bps", "ecb", "lagarde", "boe", "boj",
        ],
        # Banks are the most rate-sensitive.
        "index_tilt": {"NIFTY 50": 1.0, "BANKNIFTY": 1.35, "SENSEX": 1.0},
    },
    "budget": {
        "weight": 0.88,
        "label": "BUDGET ANNOUNCEMENTS",
        "keywords": [
            "budget", "union budget", "fiscal budget", "budget speech", "finance minister",
            "fm speech", "nirmala sitharaman", "tax cut", "tax rate", "customs duty",
            "income tax", "capital expenditure", "capex", "fiscal deficit", "gst",
            "spending", "disinvestment", "subsidy", "stimulus package", "fiscal policy",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "corporate": {
        "weight": 0.65,
        "label": "CORPORATE EARNINGS",
        "keywords": [
            "earnings", "results", "quarterly results", "q1", "q2", "q3", "q4",
            "profit", "revenue", "guidance", "merger", "acquisition", "ipo",
            "buyback", "dividend", "layoffs", "fundraise", "eps", "net profit",
            "operating margin", "topline", "bottomline", "beat estimates", "missed estimates",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "economic_data": {
        "weight": 0.82,
        "label": "ECONOMIC DATA RELEASES",
        "keywords": [
            "cpi", "inflation", "gdp", "gdp growth", "recession", "unemployment",
            "payrolls", "non-farm payrolls", "jobs data", "jobs report", "pmi",
            "manufacturing pmi", "services pmi", "industrial output", "iip",
            "wpi", "wholesale price", "trade balance", "trade deficit",
            "current account deficit", "retail sales", "economic data", "data release",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "macro": {
        "weight": 0.72,
        "label": "MACRO / GROWTH",
        "keywords": [
            "growth", "jobs", "industrial output", "slowdown", "stimulus", "downgrade",
            "credit rating", "sovereign", "world bank", "imf",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "commodity": {
        "weight": 0.62,
        "label": "COMMODITY / ENERGY",
        "keywords": [
            "crude", "oil", "brent", "wti", "opec", "gold", "natural gas",
            "commodity", "barrel", "energy prices", "fuel",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "currency": {
        "weight": 0.55,
        "label": "CURRENCY / FX",
        "keywords": [
            "rupee", "usdinr", "dollar", "dxy", "forex", "currency", "devaluation",
            "depreciation", "appreciation", "yuan", "yen",
        ],
        "index_tilt": _DEFAULT_TILT,
    },
    "sector_it": {
        "weight": 0.55,
        "label": "IT / TECH SECTOR",
        "keywords": [
            "it sector", "it exports", "infosys", "tcs", "wipro", "hcl", "tech mahindra",
            "nasdaq", "software", "semiconductor", "chip", "ai deal", "h-1b", "h1b",
            "outsourcing", "tech", "it services", "it firm", "it field",
        ],
        # IT weighs on Nifty/Sensex, barely touches Bank Nifty.
        "index_tilt": {"NIFTY 50": 1.15, "BANKNIFTY": 0.35, "SENSEX": 1.10},
    },
}

# Words that amplify the raw move (a "peace deal is OFF" is a violent repricing).
_SEVERITY_TERMS = {
    "breaking": 0.5, "urgent": 0.5, "collapse": 0.8, "crash": 0.9, "plunge": 0.8,
    "soar": 0.7, "surge": 0.6, "record": 0.5, "emergency": 0.8, "default": 0.9,
    "war": 0.8, "ceasefire": 0.7, "invasion": 0.9, "nuclear": 1.0, "sanction": 0.6,
    "shutdown": 0.6, "ban": 0.5, "tariff": 0.5, "halt": 0.5, "freeze": 0.5,
    "is off": 0.7, "called off": 0.7, "breaks down": 0.7, "off the table": 0.7,
    "escalat": 0.6, "unexpected": 0.5, "shock": 0.7,
}

_INDICES = ("NIFTY 50", "BANKNIFTY", "SENSEX")


def classify(text: str):
    """Return (category_key, match_count). Picks the highest-weight category
    that has the most keyword hits — geopolitical/monetary win ties because
    they move markets hardest."""
    t = (text or "").lower()
    best_key, best_score = "general", 0.0
    for key, spec in CATEGORIES.items():
        hits = sum(1 for kw in spec["keywords"] if kw in t)
        if hits == 0:
            continue
        # score = hits, tie-broken by category weight
        score = hits + spec["weight"] * 0.01
        if score > best_score:
            best_score, best_key = score, key
    return best_key, int(best_score)


def _severity(text: str) -> float:
    """1.0 baseline, amplified up to ~2.5x by high-impact terms."""
    t = (text or "").lower()
    bonus = sum(w for term, w in _SEVERITY_TERMS.items() if term in t)
    return round(min(1.0 + bonus, 2.5), 3)


# ---------------------------------------------------------------------------
#  Directional sentiment for *news* — more robust than a generic bag-of-words
#  scorer for the constructions that dominate market-moving headlines:
#  negated positives ("peace deal is OFF") and explicit risk-off language.
# ---------------------------------------------------------------------------
_POSITIVE_EVENTS = ("peace deal", "peace talks", "ceasefire", "truce", "trade deal",
                    "deal", "agreement", "resolution", "de-escalation", "accord")
_CANCELLERS = ("is off", "called off", "off the table", "collapse", "collapses",
               "breaks down", "break down", "breaking down", "falls through",
               "fails", "failed", "over", "ends", "ended", "scrapped", "cancelled",
               "canceled", "abandoned", "rejected", "no deal", "dead")
_RISK_OFF = ("war", "invasion", "invade", "missile", "airstrike", "air strike",
             "nuclear", "attack", "escalate", "escalates", "escalation", "tensions",
             "sanction", "sanctions", "conflict", "terror", "shutdown", "default",
             "crash", "plunge", "recession", "crisis", "selloff", "sell-off", "slump")
_RISK_ON = ("rate cut", "stimulus", "recovery", "record high", "surge", "rally",
            "growth", "breakthrough", "resolved", "boom", "upgrade", "milestone",
            "beats", "record", "cooling inflation", "dovish")


def _news_direction(text: str, base_score: float) -> float:
    """Refine the raw sentiment for market news. Returns a score in [-1, 1].

    The generic scorer is kept as a prior, then corrected for:
      * negated positives  -> force bearish (the 'peace deal is OFF' case)
      * explicit risk-off terms with no positive frame -> push bearish
      * explicit risk-on terms -> push bullish
    """
    t = (text or "").lower()
    score = base_score

    has_positive = any(p in t for p in _POSITIVE_EVENTS)
    has_canceller = any(c in t for c in _CANCELLERS)
    risk_off = sum(1 for w in _RISK_OFF if w in t)
    risk_on = sum(1 for w in _RISK_ON if w in t)

    # A positive peace/deal framing that is explicitly cancelled is a classic
    # violent risk-off repricing — override any spurious bullish read.
    if has_positive and has_canceller:
        score = -abs(max(0.55, abs(base_score), 0.15 * risk_off + 0.4))
    elif risk_off and not has_positive:
        # Net risk-off headline: bias bearish proportional to how many fired.
        score = min(score, 0.0) - min(0.9, 0.25 * risk_off)
    elif risk_on and risk_on > risk_off:
        score = max(score, 0.0) + min(0.6, 0.2 * risk_on)

    return round(max(-1.0, min(1.0, score)), 3)


def assess(text: str, index_levels: dict | None = None) -> dict:
    """Assess one headline. Returns a rich, explainable impact dict.

    index_levels: optional {index_name: spot_level}. Falls back to config
    reference levels so the engine still returns points estimates offline.
    """
    text = (text or "").strip()
    base = float(_sentiment(text))                # generic prior
    score = _news_direction(text, base)           # news-robust direction [-1,1]
    cat_key, hits = classify(text)
    spec = CATEGORIES.get(cat_key)
    weight = spec["weight"] if spec else 0.25
    tilt = spec["index_tilt"] if spec else _DEFAULT_TILT
    label = spec["label"] if spec else "GENERAL"
    sev = _severity(text)

    levels = dict(NEWS_REFERENCE_LEVELS)
    if index_levels:
        for k, v in index_levels.items():
            if v:
                levels[k] = float(v)

    per_index = {}
    move_pcts = []
    for idx in _INDICES:
        # core reaction model: sentiment × category weight × severity × base,
        # scaled by this index's sensitivity to the category.
        pct = score * weight * sev * NEWS_BASE_MOVE_PCT * tilt.get(idx, 1.0)
        pct = max(-NEWS_MAX_MOVE_PCT, min(NEWS_MAX_MOVE_PCT, pct))
        spot = levels.get(idx, 0.0)
        pts = pct / 100.0 * spot
        per_index[idx] = {
            "move_pct": round(pct, 3),
            "move_points": round(pts, 1),
            "target": round(spot + pts, 1) if spot else None,
        }
        move_pcts.append(abs(pct))

    magnitude = max(move_pcts) if move_pcts else 0.0
    if score > 0.05:
        direction = "BULLISH"
    elif score < -0.05:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # 0-100 impact score: how alert-worthy is this? Drives notifications.
    impact_score = round(min(100.0, magnitude / NEWS_MAX_MOVE_PCT * 100.0), 1)
    # confidence in the call: firmer when sentiment is decisive and category clear.
    confidence = round(min(99.0, 40.0 + 55.0 * min(1.0, abs(score) * sev)), 1)

    return {
        "headline": text,
        "category": cat_key,
        "category_label": label,
        "sentiment": round(score, 3),
        "direction": direction,
        "severity": sev,
        "magnitude_pct": round(magnitude, 3),
        "impact_score": impact_score,
        "confidence": confidence,
        "is_high_impact": impact_score >= NEWS_ALERT_THRESHOLD,
        "per_index": per_index,
    }


def summarize_alert(assessment: dict) -> str:
    """One-line, notification-ready summary of the estimated market reaction."""
    nifty = assessment["per_index"].get("NIFTY 50", {})
    pct = nifty.get("move_pct", 0.0)
    pts = nifty.get("move_points", 0.0)
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "•")
    return (f"{assessment['direction']} {assessment['category_label']} — "
            f"est. Nifty {arrow} {pct:+.2f}% (~{pts:+.0f} pts), "
            f"impact {assessment['impact_score']:.0f}/100")


def aggregate_impact(assessments, index_levels=None):
    """Blend several fresh high-impact headlines into a single net overlay per
    index — used to nudge the live prediction when news breaks pre-open."""
    net = {idx: 0.0 for idx in _INDICES}
    if not assessments:
        return {idx: {"move_pct": 0.0, "move_points": 0.0} for idx in _INDICES}
    # weight each item by its own impact score so a 90/100 shock dominates noise.
    total_w = sum(max(a["impact_score"], 1.0) for a in assessments)
    for a in assessments:
        w = max(a["impact_score"], 1.0) / total_w
        for idx in _INDICES:
            net[idx] += a["per_index"][idx]["move_pct"] * w
    levels = dict(NEWS_REFERENCE_LEVELS)
    if index_levels:
        levels.update({k: v for k, v in index_levels.items() if v})
    out = {}
    for idx in _INDICES:
        pct = max(-NEWS_MAX_MOVE_PCT, min(NEWS_MAX_MOVE_PCT, net[idx]))
        out[idx] = {"move_pct": round(pct, 3),
                    "move_points": round(pct / 100.0 * levels.get(idx, 0.0), 1)}
    return out


if __name__ == "__main__":
    demos = [
        "Breaking: Trump says the Iran peace deal is off, tensions escalate",
        "Indian IT sector hits record export milestone, Infosys TCS rally",
        "RBI unexpectedly cuts repo rate by 50 bps to support growth",
        "Crude oil surges 8% after OPEC output cut",
        "Company reports quarterly earnings in line with estimates",
    ]
    for d in demos:
        a = assess(d)
        print(f"\n[{a['category_label']}] {d}")
        print("   ", summarize_alert(a))
        for idx, v in a["per_index"].items():
            print(f"     {idx:10s} {v['move_pct']:+.2f}%  (~{v['move_points']:+.0f} pts)")
