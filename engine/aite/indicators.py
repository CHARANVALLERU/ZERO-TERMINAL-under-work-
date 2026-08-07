"""
ZERO AITE indicator / feature matrix for genetic rule evaluation.
Pure numpy/pandas — no optional deps.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd


def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to lower-case open/high/low/close/volume."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    rename = {}
    for c in out.columns:
        cl = str(c).lower()
        if cl in ("open", "high", "low", "close", "volume", "vol"):
            rename[c] = "volume" if cl == "vol" else cl
    out = out.rename(columns=rename)
    for need in ("open", "high", "low", "close"):
        if need not in out.columns:
            return pd.DataFrame()
    if "volume" not in out.columns:
        out["volume"] = 1.0
    return out.reset_index(drop=True)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return feature frame aligned to input bars (NaNs forward-filled then 0)."""
    ohlcv = _ensure_ohlcv(df)
    if ohlcv.empty or len(ohlcv) < 30:
        return pd.DataFrame()

    c = ohlcv["close"].astype(float)
    h = ohlcv["high"].astype(float)
    l = ohlcv["low"].astype(float)
    v = ohlcv["volume"].astype(float)
    o = ohlcv["open"].astype(float)

    feats = pd.DataFrame(index=ohlcv.index)

    # RSI(14)
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    feats["rsi"] = 100 - (100 / (1 + rs))

    # MACD histogram
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    feats["macd_hist"] = macd - signal

    # Bollinger %B
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    feats["bb_pct_b"] = (c - lower) / (upper - lower).replace(0, np.nan) * 100

    # ATR %
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    feats["atr"] = atr
    feats["atr_pct"] = (atr / c.replace(0, np.nan)) * 100

    # EMA spread (fast vs slow) as % of price
    ema8 = c.ewm(span=8, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    feats["ema_spread"] = ((ema8 - ema21) / c.replace(0, np.nan)) * 100

    feats["mom_10"] = c.pct_change(10) * 100
    feats["mom_20"] = c.pct_change(20) * 100

    ret = c.pct_change()
    feats["ret_z"] = (ret - ret.rolling(20).mean()) / ret.rolling(20).std().replace(0, np.nan)
    feats["vol_z"] = (v - v.rolling(20).mean()) / v.rolling(20).std().replace(0, np.nan)

    # OBV slope
    direction = np.sign(c.diff()).fillna(0)
    obv = (direction * v).cumsum()
    feats["obv_slope"] = obv.diff(5) / (v.rolling(5).mean().replace(0, np.nan))

    # Stochastic
    lowest = l.rolling(14).min()
    highest = h.rolling(14).max()
    feats["stoch_k"] = (c - lowest) / (highest - lowest).replace(0, np.nan) * 100

    # ADX (simplified)
    up = h.diff()
    down = -l.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    atr14 = atr.replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=c.index).rolling(14).mean() / atr14
    minus_di = 100 * pd.Series(minus_dm, index=c.index).rolling(14).mean() / atr14
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
    feats["adx"] = dx.rolling(14).mean()

    # CCI
    tp = (h + l + c) / 3
    feats["cci"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std().replace(0, np.nan))

    # Williams %R
    feats["williams_r"] = (highest - c) / (highest - lowest).replace(0, np.nan) * -100

    # VWAP distance
    typical = (h + l + c) / 3
    cum_vp = (typical * v).cumsum()
    cum_v = v.cumsum().replace(0, np.nan)
    vwap = cum_vp / cum_v
    feats["vwap_dist"] = ((c - vwap) / c.replace(0, np.nan)) * 100

    feats["close"] = c
    feats["open"] = o
    feats["high"] = h
    feats["low"] = l

    return feats.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)


def evaluate_rule(feats: pd.DataFrame, indicator: str, operator: str, threshold: float) -> np.ndarray:
    """Boolean signal series for one rule."""
    if indicator not in feats.columns:
        return np.zeros(len(feats), dtype=bool)
    series = feats[indicator].values.astype(float)
    prev = np.roll(series, 1)
    prev[0] = series[0]
    thr = float(threshold)
    if operator == ">":
        return series > thr
    if operator == "<":
        return series < thr
    if operator == "crosses_above":
        return (prev <= thr) & (series > thr)
    if operator == "crosses_below":
        return (prev >= thr) & (series < thr)
    return series > thr


def combined_signal(feats: pd.DataFrame, rules, side_bias: str = "BOTH") -> np.ndarray:
    """
    Majority-weighted vote → +1 long, -1 short, 0 flat.
    """
    if feats.empty or not rules:
        return np.zeros(0, dtype=int)

    n = len(feats)
    score = np.zeros(n, dtype=float)
    total_w = 0.0
    for r in rules:
        ind = r.indicator if hasattr(r, "indicator") else r["indicator"]
        op = r.operator if hasattr(r, "operator") else r["operator"]
        thr = r.threshold if hasattr(r, "threshold") else r["threshold"]
        w = float(r.weight if hasattr(r, "weight") else r.get("weight", 1.0))
        hit = evaluate_rule(feats, ind, op, thr).astype(float)
        # Map rule polarity: ">" on RSI/macd tends long; "<" on overbought mean-reverts
        polarity = 1.0
        if ind in ("rsi", "stoch_k", "bb_pct_b", "cci") and op == ">":
            polarity = -1.0  # overbought → short bias for mean-rev style
        if ind in ("rsi", "stoch_k", "williams_r") and op == "<":
            polarity = 1.0
        score += w * polarity * (2 * hit - 1)
        total_w += w

    if total_w > 0:
        score /= total_w

    sig = np.zeros(n, dtype=int)
    sig[score > 0.25] = 1
    sig[score < -0.25] = -1

    if side_bias == "LONG":
        sig[sig < 0] = 0
    elif side_bias == "SHORT":
        sig[sig > 0] = 0
    return sig


def regime_label(feats: pd.DataFrame) -> str:
    """Coarse regime from ADX + momentum."""
    if feats.empty:
        return "UNKNOWN"
    adx = float(feats["adx"].iloc[-1]) if "adx" in feats else 15.0
    mom = float(feats["mom_20"].iloc[-1]) if "mom_20" in feats else 0.0
    atrp = float(feats["atr_pct"].iloc[-1]) if "atr_pct" in feats else 1.0
    if adx >= 25 and mom > 1.0:
        return "TREND_UP"
    if adx >= 25 and mom < -1.0:
        return "TREND_DOWN"
    if atrp > 2.0:
        return "HIGH_VOL"
    if adx < 18:
        return "RANGE"
    return "TRANSITIONAL"


def drawdown_from_peak(closes: np.ndarray) -> float:
    if closes is None or len(closes) == 0:
        return 0.0
    peak = np.maximum.accumulate(closes)
    dd = (closes - peak) / np.where(peak == 0, 1, peak)
    return float(abs(dd.min())) if len(dd) else 0.0
