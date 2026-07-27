from config import ALPHA, BETA

def predict_opening_gap(gift_premium, adr_delta, vix_factor=1.0):
    """
    Computes predicted opening gap vector.
    G = ALPHA * gift_premium + BETA * adr_delta
    Adjusted by VIX factor (higher VIX usually means compressed gap or deeper discount).
    """
    if gift_premium is None or adr_delta is None:
        return 0
    
    base_gap = (ALPHA * gift_premium) + (BETA * adr_delta)
    # Simple VIX adjustment: if factor > 1 (high volatility), we might expect some decay
    # but for now we keep it linear as per formula.
    return base_gap * vix_factor

def get_opening_price(spot_close, predicted_gap):
    """Returns absolute opening price."""
    return spot_close + predicted_gap
