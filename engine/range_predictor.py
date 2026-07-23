import numpy as np
from config import GAMMA

def calculate_envelopes(predicted_open, atr, iv=20.0):
    """
    B_Upper = Opening + (ATR * GAMMA * ln(IV))
    B_Lower = Opening - (ATR * GAMMA * ln(IV))
    """
    if atr is None or predicted_open is None:
        return None, None
        
    vol_scaling = GAMMA * np.log(max(iv, 1.1)) # ensure ln(iv) > 0
    upper_bound = predicted_open + (atr * vol_scaling)
    lower_bound = predicted_open - (atr * vol_scaling)
    
    return upper_bound, lower_bound

def predict_high_low(upper_bound, lower_bound, max_call_oi, max_put_oi):
    """
    H = min(B_Upper, OI_Call_Max)
    L = max(B_Lower, OI_Put_Max)
    """
    if upper_bound is None or lower_bound is None:
        return None, None
        
    # Integrating OI concentration zones
    high = min(upper_bound, max_call_oi) if max_call_oi else upper_bound
    low = max(lower_bound, max_put_oi) if max_put_oi else lower_bound
    
    return high, low

def sentiment_adjusted_levels(high, low, sentiment_data, atr):
    """
    Adjusts support (low) and resistance (high) zones based on news sentiment.
    
    Uses the rich sentiment data from analyze_sentiment() to dynamically
    shift support/resistance levels. The daily news insights directly
    influence where the engine calculates key price boundaries.
    
    Args:
        high: Raw predicted high (resistance zone)
        low: Raw predicted low (support zone)
        sentiment_data: dict with keys: score, intensity, bullish_count, bearish_count, dominant_factors
        atr: Average True Range for volatility scaling
    
    Returns:
        tuple: (adjusted_high, adjusted_low)
    
    Logic:
        - Bullish sentiment: Narrows support buffer (less downside risk), expands resistance ceiling
        - Bearish sentiment: Narrows resistance ceiling, expands support floor (more downside risk)
        - Extreme events: Additional ATR-based expansion in the sentiment direction
        - Neutral: No adjustment
    """
    if high is None or low is None or atr is None:
        return high, low
    
    # Handle both old-style float and new-style dict sentiment
    if isinstance(sentiment_data, (int, float)):
        score = float(sentiment_data)
        intensity = "neutral"
    elif isinstance(sentiment_data, dict):
        score = sentiment_data.get('score', 0)
        intensity = sentiment_data.get('intensity', 'neutral')
    else:
        return high, low
    
    adjusted_high = high
    adjusted_low = low
    
    if intensity in ('extreme_bullish',) or score > 0.6:
        # Extreme bullish: Strong ceiling expansion, significant support lift
        adjusted_high += atr * 0.40  # +40% ATR expansion above resistance
        adjusted_low += atr * 0.25   # Support lifts (market won't fall as much)
        
    elif intensity in ('strong_bullish',) or score > 0.3:
        # Strong bullish: Moderate ceiling expansion, mild support lift
        adjusted_high += atr * 0.25  # +25% ATR expansion above resistance
        adjusted_low += atr * 0.15   # Support lifts
        
    elif intensity in ('bullish',) or score > 0.05:
        # Mild bullish: Small adjustments
        adjusted_high += atr * 0.10
        adjusted_low += atr * 0.05
        
    elif intensity in ('extreme_bearish',) or score < -0.6:
        # Extreme bearish: Resistance pushes down, support drops significantly
        adjusted_high -= atr * 0.25  # Resistance drops (market capped)
        adjusted_low -= atr * 0.40   # Support collapses further
        
    elif intensity in ('strong_bearish',) or score < -0.3:
        # Strong bearish: Moderate resistance drop, support expansion
        adjusted_high -= atr * 0.15
        adjusted_low -= atr * 0.25
        
    elif intensity in ('bearish',) or score < -0.05:
        # Mild bearish: Small adjustments
        adjusted_high -= atr * 0.05
        adjusted_low -= atr * 0.10
    
    # else: neutral — no adjustment

    return round(adjusted_high, 2), round(adjusted_low, 2)


def _predict_high_low_pure(spot, atr, sentiment, news_overlay_pts, iv=20.0):
    """Single source of truth for the *live* high/low.

    Used by both the cached matrix builder and the partial-refresh path
    so the values stay byte-identical regardless of which call site produced
    them. Returns a tuple of (high, low) — both rounded to 2 dp, or
    (None, None) when the inputs aren't usable.

    `news_overlay_pts` is the absolute point shift estimated by the news
    impact engine for this index (positive = bullish, negative = bearish).
    It is applied symmetrically to high and low so the band width is
    preserved; a bearish shock pulls the whole band down, not just the
    lower edge.
    """
    if spot is None or atr is None:
        return None, None
    try:
        spot = float(spot)
        atr = float(atr)
    except (TypeError, ValueError):
        return None, None
    if atr <= 0:
        atr = max(abs(spot) * 0.005, 1.0)  # sane floor: 0.5 % of spot

    # Volatility envelope centered on spot.
    vol_scaling = GAMMA * max(0.05, float(np.log(max(iv, 1.1))))
    base_band = atr * vol_scaling

    # Sentiment scales the band width, not the center. Bullish sentiment
    # widens the upside a little; bearish widens the downside.
    score = float(sentiment or 0.0)
    score = max(-1.0, min(1.0, score))
    up_scale = 1.0 + max(score, 0.0) * 0.30
    down_scale = 1.0 + max(-score, 0.0) * 0.30

    high = spot + (base_band * up_scale)
    low = spot - (base_band * down_scale)

    # News overlay shifts the band symmetrically so a shock doesn't widen
    # the band artificially.
    try:
        shift = float(news_overlay_pts or 0.0)
    except (TypeError, ValueError):
        shift = 0.0
    high += shift
    low += shift

    # Preserve ordering even if inputs are pathological.
    if high < low:
        high, low = low, high

    return round(high, 2), round(low, 2)
