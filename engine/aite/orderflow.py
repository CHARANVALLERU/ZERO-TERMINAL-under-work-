"""
ZERO AITE order-flow analytics — proxy CVD / imbalance from OHLCV +
options-chain OI / PCR overlays. No Level-2 required (graceful).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from engine.aite.config import INDEX_KEYS
from engine.aite.indicators import _ensure_ohlcv


def normalize_chart_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flatten MultiIndex / ticker-suffixed OHLCV so indicator helpers work.
    Safe no-op for already-normalized frames. Never raises.
    """
    try:
        if df is None or getattr(df, "empty", True):
            return pd.DataFrame()
        out = df.copy()
        if isinstance(out.columns, pd.MultiIndex):
            out.columns = [str(c[0]).lower().replace(" ", "_") for c in out.columns]
        else:
            out.columns = [str(c).lower().replace(" ", "_") for c in out.columns]
        rename = {
            "adj_close": "close",
            "adjclose": "close",
            "vol": "volume",
        }
        out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
        out = out.loc[:, ~out.columns.duplicated()]
        if "close" not in out.columns:
            for c in list(out.columns):
                if "close" in str(c):
                    out = out.rename(columns={c: "close"})
                    break
        # Keep only usable columns; drop index levels into optional timestamp
        if not isinstance(out.index, pd.RangeIndex):
            try:
                out = out.reset_index()
                for cand in ("date", "datetime", "timestamp", "index"):
                    if cand in out.columns and "timestamps" not in out.columns:
                        out = out.rename(columns={cand: "timestamps"})
                        break
            except Exception:
                out = out.reset_index(drop=True)
        else:
            out = out.reset_index(drop=True)
        return out
    except Exception:
        return pd.DataFrame()


def _options_overlay(symbol: str) -> Dict[str, Any]:
    """Fetch PCR / OI walls from data.options_chain when available."""
    out: Dict[str, Any] = {"available": False}
    try:
        from data.options_chain import fetch_nse_option_chain, process_option_chain
        opt_sym = INDEX_KEYS.get(symbol, symbol)
        if opt_sym in (None, "SENSEX"):
            out["note"] = "no_nse_options"
            return out
        chain = process_option_chain(fetch_nse_option_chain(opt_sym))
        if not chain:
            out["note"] = "chain_unavailable"
            return out
        out = {
            "available": True,
            "pcr": chain.get("pcr"),
            "max_pain": chain.get("max_pain"),
            "max_ce_oi_strike": chain.get("max_ce_oi_strike"),
            "max_pe_oi_strike": chain.get("max_pe_oi_strike"),
            "max_ce_oi_chg_strike": chain.get("max_ce_oi_chg_strike"),
            "max_pe_oi_chg_strike": chain.get("max_pe_oi_chg_strike"),
            "nearest_expiry": chain.get("nearest_expiry"),
        }
        pcr = out.get("pcr")
        if pcr is not None:
            if float(pcr) >= 1.2:
                out["oi_bias"] = "PUT_HEAVY"
            elif float(pcr) <= 0.8:
                out["oi_bias"] = "CALL_HEAVY"
            else:
                out["oi_bias"] = "BALANCED"
    except Exception as exc:
        out["note"] = f"options_error:{str(exc)[:80]}"
    return out


def volume_profile_proxy(df: pd.DataFrame, bins: int = 12) -> Dict[str, Any]:
    """
    Coarse volume-by-price proxy from OHLCV (no tick data).
    Returns POC / VAH / VAL style levels from the window.
    """
    ohlcv = _ensure_ohlcv(normalize_chart_frame(df))
    if ohlcv.empty or len(ohlcv) < 10:
        return {"available": False, "note": "insufficient bars"}

    c = ohlcv["close"].astype(float).values
    v = ohlcv["volume"].astype(float).values
    lo, hi = float(np.min(c)), float(np.max(c))
    if hi <= lo:
        return {"available": False, "note": "flat_range"}

    edges = np.linspace(lo, hi, bins + 1)
    # Assign each bar's volume to the bin of its close
    idx = np.clip(np.digitize(c, edges) - 1, 0, bins - 1)
    vol_bins = np.zeros(bins, dtype=float)
    for i, b in enumerate(idx):
        vol_bins[b] += v[i]

    poc_i = int(np.argmax(vol_bins))
    poc = float((edges[poc_i] + edges[poc_i + 1]) / 2)

    # Value area ≈ 70% of volume around POC
    order = list(np.argsort(vol_bins)[::-1])
    target = float(vol_bins.sum()) * 0.70
    acc = 0.0
    selected = set()
    for i in order:
        selected.add(int(i))
        acc += float(vol_bins[i])
        if acc >= target:
            break
    if selected:
        vah = float(edges[max(selected) + 1])
        val = float(edges[min(selected)])
    else:
        vah, val = hi, lo

    return {
        "available": True,
        "poc": round(poc, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "bins": bins,
        "last": round(float(c[-1]), 2),
        "position": (
            "above_value" if c[-1] > vah else
            "below_value" if c[-1] < val else
            "inside_value"
        ),
    }


def oi_volume_proxy(df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
    """
    Combine historical volume z-score with options OI overlay.
    Useful when true open-interest time series is unavailable.
    """
    ohlcv = _ensure_ohlcv(normalize_chart_frame(df))
    vol_z = 0.0
    vol_trend = "FLAT"
    if not ohlcv.empty and len(ohlcv) >= 20:
        v = ohlcv["volume"].astype(float)
        mu = float(v.tail(20).mean())
        sd = float(v.tail(20).std()) or 1.0
        vol_z = (float(v.iloc[-1]) - mu) / sd
        slope = float(v.tail(10).mean() - v.tail(20).head(10).mean())
        vol_trend = "RISING" if slope > 0 else "FALLING" if slope < 0 else "FLAT"

    opt = _options_overlay(symbol) if symbol else {"available": False}
    return {
        "symbol": symbol,
        "volume_z": round(vol_z, 3),
        "volume_trend": vol_trend,
        "options": opt,
        "pcr": opt.get("pcr"),
        "oi_bias": opt.get("oi_bias"),
        "max_pain": opt.get("max_pain"),
    }


def analyze_orderflow(df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
    """
    Returns imbalance, CVD slope, aggression proxy, OI/volume overlays,
    and a qualitative read for the current chart window.
    """
    ohlcv = _ensure_ohlcv(normalize_chart_frame(df))
    if ohlcv.empty or len(ohlcv) < 20:
        return {
            "symbol": symbol,
            "imbalance": 0.0,
            "cvd_slope": 0.0,
            "aggression": "NEUTRAL",
            "buy_pressure": 0.5,
            "sell_pressure": 0.5,
            "pcr": None,
            "volume_profile": {"available": False},
            "oi_volume": {"available": False},
            "note": "insufficient data",
        }

    c = ohlcv["close"].astype(float).values
    o = ohlcv["open"].astype(float).values
    h = ohlcv["high"].astype(float).values
    l = ohlcv["low"].astype(float).values
    v = ohlcv["volume"].astype(float).values

    # Candle body aggression
    body = c - o
    range_ = np.maximum(h - l, 1e-9)
    body_frac = body / range_
    buy_vol = np.where(body >= 0, v * (0.5 + 0.5 * np.clip(body_frac, 0, 1)), v * 0.35)
    sell_vol = np.where(body < 0, v * (0.5 + 0.5 * np.clip(-body_frac, 0, 1)), v * 0.35)

    window = min(20, len(v))
    bp = float(buy_vol[-window:].sum())
    sp = float(sell_vol[-window:].sum())
    tot = bp + sp + 1e-9
    imbalance = (bp - sp) / tot

    cvd = np.cumsum(buy_vol - sell_vol)
    cvd_slope = float(cvd[-1] - cvd[-window]) / (abs(cvd[-window]) + 1e-9)

    if imbalance > 0.15 and cvd_slope > 0:
        aggression = "BUY_AGGRESSIVE"
    elif imbalance < -0.15 and cvd_slope < 0:
        aggression = "SELL_AGGRESSIVE"
    elif abs(imbalance) < 0.05:
        aggression = "BALANCED"
    else:
        aggression = "MIXED"

    opt = _options_overlay(symbol) if symbol else {"available": False}
    pcr = opt.get("pcr")
    vp = volume_profile_proxy(ohlcv)
    oi_vol = oi_volume_proxy(ohlcv, symbol)

    # Soft-adjust aggression with PCR if extreme
    if pcr is not None:
        try:
            pcr_f = float(pcr)
            if pcr_f >= 1.35 and aggression == "BUY_AGGRESSIVE":
                aggression = "MIXED"
            elif pcr_f <= 0.7 and aggression == "SELL_AGGRESSIVE":
                aggression = "MIXED"
        except (TypeError, ValueError):
            pass

    note = "ohlcv_proxy"
    if opt.get("available"):
        note += f"+pcr={pcr:.2f}" if pcr is not None else "+oi"
    elif opt.get("note"):
        note += f"({opt['note']})"

    return {
        "symbol": symbol,
        "imbalance": round(imbalance, 4),
        "cvd_slope": round(cvd_slope, 4),
        "aggression": aggression,
        "buy_pressure": round(bp / tot, 4),
        "sell_pressure": round(sp / tot, 4),
        "pcr": pcr,
        "oi_bias": opt.get("oi_bias"),
        "max_pain": opt.get("max_pain"),
        "options": opt,
        "volume_profile": vp,
        "oi_volume": oi_vol,
        "cvd_tail": [round(float(x), 2) for x in cvd[-min(40, len(cvd)):].tolist()],
        "note": note,
    }


def analyze_symbol_orderflow(symbol: str, bars: int = 120) -> Dict[str, Any]:
    """Convenience: load market frame for symbol then analyze."""
    try:
        from engine.aite.exam import load_market_frame
        df = load_market_frame(symbol, bars=bars)
    except Exception:
        df = pd.DataFrame()
    return analyze_orderflow(df, symbol)
