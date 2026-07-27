"""
Dynamic Prediction Range Management for ZERO Engine.

Defines prediction boundaries per index:
- SENSEX: ±5000 points
- NIFTY 50: ±2000 points
- BANKNIFTY: ±2000 points

Range center is auto-updated monthly from live market prices.
"""
import json
import os
import datetime

RANGE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'db', 'range_config.json')

# Maximum prediction deviation from center price (in points)
MAX_PREDICTION_RANGE = {
    "SENSEX": 5000,
    "NIFTY 50": 2000,
    "BANKNIFTY": 2000
}

# yfinance ticker symbols for each index
INDEX_TICKERS = {
    "NIFTY 50": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "SENSEX": "^BSESN"
}

def get_current_prices():
    """
    Fetches the latest closing prices for all 3 indices from yfinance.
    Returns dict: {"NIFTY 50": float, "BANKNIFTY": float, "SENSEX": float}
    """
    import yfinance as yf  # lazy import so offline callers can still load config
    prices = {}
    for idx_name, ticker_symbol in INDEX_TICKERS.items():
        try:
            data = yf.Ticker(ticker_symbol)
            df = data.history(period="5d")
            if not df.empty:
                prices[idx_name] = round(float(df['Close'].iloc[-1]), 2)
            else:
                prices[idx_name] = None
        except Exception as e:
            print(f"Error fetching price for {idx_name}: {e}")
            prices[idx_name] = None
    return prices


def _load_range_config():
    """Load stored range config from disk."""
    if os.path.exists(RANGE_CONFIG_FILE) and os.path.getsize(RANGE_CONFIG_FILE) > 0:
        try:
            with open(RANGE_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return None


def _save_range_config(config):
    """Save range config to disk."""
    os.makedirs(os.path.dirname(RANGE_CONFIG_FILE), exist_ok=True)
    with open(RANGE_CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def _is_config_stale(config):
    """Check if config is older than 30 days (monthly refresh)."""
    if not config or 'last_updated' not in config:
        return True
    try:
        last_updated = datetime.datetime.fromisoformat(config['last_updated'])
        age = datetime.datetime.now() - last_updated
        return age.days >= 30
    except (ValueError, TypeError):
        return True


def get_range_config(force_refresh=False):
    """
    Returns the current prediction range configuration.
    Auto-refreshes from live market prices if config is >30 days old.
    
    Returns:
        dict: {
            "NIFTY 50": {"center": 24000, "max_range": 2000, "max_high": 26000, "max_low": 22000},
            "BANKNIFTY": {"center": 58000, "max_range": 2000, "max_high": 60000, "max_low": 56000},
            "SENSEX": {"center": 77000, "max_range": 5000, "max_high": 82000, "max_low": 72000},
            "last_updated": "2026-07-01T00:00:00"
        }
    """
    config = _load_range_config()
    
    if force_refresh or _is_config_stale(config):
        # Refresh from live data
        prices = get_current_prices()
        config = {"last_updated": datetime.datetime.now().isoformat()}
        
        for idx_name, max_range in MAX_PREDICTION_RANGE.items():
            center = prices.get(idx_name)
            if center is None:
                # Fallback: use previous config if available, or hardcoded defaults
                old_config = _load_range_config()
                if old_config and idx_name in old_config:
                    center = old_config[idx_name]['center']
                else:
                    # Emergency defaults
                    center = {"NIFTY 50": 24000, "BANKNIFTY": 58000, "SENSEX": 78000}[idx_name]
            
            config[idx_name] = {
                "center": round(center, 2),
                "max_range": max_range,
                "max_high": round(center + max_range, 2),
                "max_low": round(center - max_range, 2)
            }
        
        _save_range_config(config)
    
    return config


def clamp_prediction(index_name, pred_open, pred_high, pred_low, center=None):
    """
    Clamps prediction values to stay within the allowed ±range for the index.
    
    Args:
        index_name: "NIFTY 50", "BANKNIFTY", or "SENSEX"
        pred_open, pred_high, pred_low: Raw prediction values
        center: Override center price (if None, uses stored config)
    
    Returns:
        tuple: (clamped_open, clamped_high, clamped_low)
    """
    config = get_range_config()
    idx_config = config.get(index_name)
    
    if not idx_config:
        return pred_open, pred_high, pred_low
    
    max_high = idx_config['max_high']
    max_low = idx_config['max_low']
    
    # If a center override is provided, recalculate bounds
    if center is not None:
        max_range = idx_config['max_range']
        max_high = center + max_range
        max_low = center - max_range
    
    clamped_open = max(min(pred_open, max_high), max_low)
    clamped_high = max(min(pred_high, max_high), max_low)
    clamped_low = max(min(pred_low, max_high), max_low)
    
    return round(clamped_open, 2), round(clamped_high, 2), round(clamped_low, 2)


if __name__ == "__main__":
    print("Fetching range config...")
    config = get_range_config(force_refresh=True)
    for key, val in config.items():
        print(f"  {key}: {val}")
