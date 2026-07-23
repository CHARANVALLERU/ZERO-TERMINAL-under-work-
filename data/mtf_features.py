"""
ZERO Multi-Timeframe Feature Pipeline
======================================

Extends the existing feature store (data/features.py) with multi-timeframe
features for the XGBoost predictor.  Does NOT modify the base feature store;
produces an augmented feature dict that layers on top.

Feature categories:
  1. GEX Proxy Features  — derived from options chain OI (MenthorQ logic)
  2. Structural Anchors  — weekly S/R binary flags (TrendSpider logic)
  3. Weekly Macro         — DXY/Brent/VIX momentum for the weekly model
  4. Rolling Volatility   — historical vol distribution for Monte Carlo bounds

All data is sourced from ZERO's existing scrapers — no new network I/O.
"""

from __future__ import annotations

import datetime
import math

import numpy as np
import pandas as pd

from engine.quant_config import (
    GEX_DELTA_PERIODS,
    SR_PROXIMITY_ATR_FRACTION,
    VWAP_LOOKBACK_BARS,
    HIST_VOL_WINDOW,
)

# Re-use ZERO's existing data layer
from data.historical import get_recent_ohlc_and_atr
from data.options_chain import fetch_and_process
from data.global_feeds import get_us_market_summary


# Mapping kept in sync with features.py / prediction_matrix.py
_INDEX_HIST_KEYS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
}
_INDEX_OPTIONS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": None,
}


# =========================================================================
#  GEX Proxy Features (MenthorQ-style)
# =========================================================================

def _gex_proxy_features(options_data: dict | None, spot: float) -> dict:
    """Derive gamma-exposure proxy features from the options chain.

    Real GEX requires dealer positioning data from MenthorQ.  We approximate
    with the OI distribution from the NSE chain:
      - gex_level        : absolute distance from spot to the max OI wall
                           (where market makers hedge hardest).
      - gex_net_delta     : (put OI wall − call OI wall) normalised by spot,
                           a proxy for net gamma direction.
      - gex_level_delta   : 5-period rolling delta (placeholder; set to 0
                           on a single snapshot, filled by the orchestrator
                           when a time-series is available).
    """
    if not options_data or not spot or spot <= 0:
        return {
            "gex_level": 0.0,
            "gex_net_delta": 0.0,
            "gex_level_delta": 0.0,
        }

    max_ce_strike = float(options_data.get("max_ce_oi_strike") or spot)
    max_pe_strike = float(options_data.get("max_pe_oi_strike") or spot)

    # GEX level: distance to the nearest dominant OI wall (normalised)
    ce_dist = abs(max_ce_strike - spot)
    pe_dist = abs(max_pe_strike - spot)
    gex_level = min(ce_dist, pe_dist) / spot  # fraction of spot

    # Net delta proxy: put floor minus call ceiling, normalised
    gex_net_delta = (max_pe_strike - max_ce_strike) / spot

    return {
        "gex_level": round(gex_level, 6),
        "gex_net_delta": round(gex_net_delta, 6),
        "gex_level_delta": 0.0,  # filled by time-series context
    }


# =========================================================================
#  Structural Anchor Features (TrendSpider-style)
# =========================================================================

def _structural_anchor_features(spot: float, atr: float,
                                 weekly_high: float | None,
                                 weekly_low: float | None,
                                 weekly_vwap: float | None) -> dict:
    """Binary features indicating if the current price is testing a
    weekly structural level.

    Mimics TrendSpider's multi-timeframe structural anchor concept:
      - at_weekly_resistance : 1 if spot is within ATR*fraction of weekly high
      - at_weekly_support    : 1 if spot is within ATR*fraction of weekly low
      - at_vwap_anchor       : 1 if spot is within ATR*fraction of weekly VWAP
    """
    threshold = atr * SR_PROXIMITY_ATR_FRACTION if atr and atr > 0 else float("inf")

    at_resistance = 0
    at_support = 0
    at_vwap = 0

    if weekly_high is not None and spot and threshold < float("inf"):
        at_resistance = 1 if abs(spot - weekly_high) <= threshold else 0
    if weekly_low is not None and spot and threshold < float("inf"):
        at_support = 1 if abs(spot - weekly_low) <= threshold else 0
    if weekly_vwap is not None and spot and threshold < float("inf"):
        at_vwap = 1 if abs(spot - weekly_vwap) <= threshold else 0

    return {
        "at_weekly_resistance": at_resistance,
        "at_weekly_support": at_support,
        "at_vwap_anchor": at_vwap,
    }


# =========================================================================
#  Weekly Macro Features
# =========================================================================

def _weekly_macro_features(us_summary: dict | None) -> dict:
    """Macro features for the weekly XGBoost model.

    Derived from existing global_feeds data:
      - dxy_momentum       : DXY overnight change (proxy for dollar strength)
      - brent_momentum     : Brent overnight change
      - vix_term_spread    : VIX level relative to its 20-day norm (proxy)
      - us_futures_momentum: average US futures overnight delta
    """
    us = us_summary or {}

    def _chg(key):
        try:
            return float((us.get(key) or {}).get("change_pct") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _price(key, default=0.0):
        try:
            return float((us.get(key) or {}).get("price") or default)
        except (TypeError, ValueError):
            return default

    vix = _price("VIX", 15.0)
    # Normalised VIX: how far from the "calm" baseline of 15
    vix_term_spread = (vix - 15.0) / 15.0

    us_fut_vals = [_chg(k) for k in ("SP500", "NASDAQ", "DOW") if _chg(k) != 0.0]
    us_fut_momentum = float(np.mean(us_fut_vals)) if us_fut_vals else 0.0

    return {
        "dxy_momentum": round(_chg("DXY"), 6),
        "brent_momentum": round(_chg("BRENT"), 6),
        "vix_term_spread": round(vix_term_spread, 6),
        "us_futures_momentum": round(us_fut_momentum, 6),
    }


# =========================================================================
#  Rolling Historical Volatility
# =========================================================================

def _rolling_volatility(hist_data: dict | None, spot: float) -> dict:
    """Rolling historical volatility for Monte Carlo boundary checks.

    Uses ATR as a proxy for realised volatility (the full intraday bar
    history isn't available from a single OHLC snapshot).
    """
    if not hist_data or not spot or spot <= 0:
        return {"hist_vol_pct": 0.0, "hist_vol_zscore": 0.0}

    atr = float(hist_data.get("atr") or 0.0)
    atr_pct = atr / spot if atr > 0 else 0.0

    # Z-score relative to a "normal" 1% daily range
    normal_vol = 0.01
    z = (atr_pct - normal_vol) / normal_vol if normal_vol > 0 else 0.0

    return {
        "hist_vol_pct": round(atr_pct, 6),
        "hist_vol_zscore": round(z, 4),
    }


# =========================================================================
#  Week-ID for Data Leakage Prevention
# =========================================================================

def _week_id(dt: datetime.datetime | None = None) -> str:
    """ISO week identifier.  Weekly features are keyed by this so they
    remain static across all intraday bars of the same week — preventing
    data leakage from later-in-week values into early-week predictions."""
    dt = dt or datetime.datetime.now()
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# =========================================================================
#  Public API
# =========================================================================

# Columns produced by this module (for training matrix assembly)
MTF_FEATURE_COLUMNS = [
    # GEX proxy
    "gex_level", "gex_net_delta", "gex_level_delta",
    # Structural anchors
    "at_weekly_resistance", "at_weekly_support", "at_vwap_anchor",
    # Weekly macro
    "dxy_momentum", "brent_momentum", "vix_term_spread", "us_futures_momentum",
    # Rolling volatility
    "hist_vol_pct", "hist_vol_zscore",
    # Meta
    "week_id_hash",
]


def build_mtf_features(index_name: str,
                        weekly_high: float | None = None,
                        weekly_low: float | None = None,
                        weekly_vwap: float | None = None,
                        dt: datetime.datetime | None = None) -> dict:
    """Build the full multi-timeframe feature dict for one index.

    This layers on top of the base features from data/features.py.
    All data comes from ZERO's existing scrapers.

    Parameters
    ----------
    index_name : str
        One of "NIFTY 50", "BANKNIFTY", "SENSEX".
    weekly_high, weekly_low, weekly_vwap : float | None
        Weekly structural levels.  When None, the structural anchor
        features default to 0 (no anchor test fires).
    dt : datetime | None
        Timestamp for week-ID computation.  Defaults to now().

    Returns
    -------
    dict
        Flat feature dict with all MTF columns.
    """
    hist_key = _INDEX_HIST_KEYS.get(index_name, "NIFTY")
    hist = get_recent_ohlc_and_atr(hist_key) or {}
    spot = float(hist.get("close") or 0.0)
    atr = float(hist.get("atr") or 0.0)

    # Options chain (GEX proxy)
    opt_symbol = _INDEX_OPTIONS.get(index_name)
    options_data = fetch_and_process(opt_symbol) if opt_symbol else None

    # US / global summary (weekly macro)
    us_summary = get_us_market_summary()

    # Assemble all feature groups
    feats = {}
    feats.update(_gex_proxy_features(options_data, spot))
    feats.update(_structural_anchor_features(spot, atr, weekly_high, weekly_low, weekly_vwap))
    feats.update(_weekly_macro_features(us_summary))
    feats.update(_rolling_volatility(hist, spot))

    # Week-ID hash: integer hash of the ISO week string so XGBoost can use
    # it as a categorical split if needed, while remaining static all week.
    wid = _week_id(dt)
    feats["week_id_hash"] = hash(wid) % (2**31)

    # Clean NaN
    feats = {
        k: (0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v))
        for k, v in feats.items()
    }

    return feats


if __name__ == "__main__":
    for idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
        f = build_mtf_features(idx)
        print(f"\n{idx} MTF features:")
        for k, v in f.items():
            print(f"  {k:30s} {v}")
