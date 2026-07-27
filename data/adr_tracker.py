"""
ADR premium tracking with caching and last-good persistence.
"""
from config import ADR_TICKERS, TICKERS
from data.cache import get_or_fetch
from data.last_good import save as lg_save, load as lg_load


CACHE_KEY = "adr_delta"
CACHE_TTL = 600
SOURCE_NAME = "adr_delta"

# Rebalanced for the 4-ADR universe (HDFC + ICICI + INFY + TCS).
# Kept as a static dict so the existing call sites stay unchanged.
WEIGHTS = {'HDFC': 0.30, 'ICICI': 0.25, 'INFOSYS': 0.25, 'TCS': 0.20}


def _live():
    import yfinance as yf  # lazy: offline callers use last-good cache
    deltas = {}
    total_weighted = 0.0
    usdinr = 83.0

    try:
        usdinr_df = yf.Ticker(TICKERS['USDINR']).history(period='5d')
        if not usdinr_df.empty:
            usdinr = float(usdinr_df['Close'].iloc[-1])
    except Exception:
        pass

    for key, symbol in ADR_TICKERS.items():
        try:
            t = yf.Ticker(symbol)
            df = t.history(period='5d')
            if df is None or len(df) < 2:
                continue
            last = float(df['Close'].iloc[-1])
            prev = float(df['Close'].iloc[-2])
            if prev <= 0:
                continue
            chg = (last - prev) / prev * 100.0
            deltas[key] = round(chg, 4)
            total_weighted += chg * WEIGHTS.get(key, 0.0)
        except Exception:
            continue

    return {
        'individual': deltas,
        'weighted_avg': round(total_weighted, 4),
        'usdinr': round(usdinr, 4),
    }


def get_adr_delta():
    """Cached ADR delta. Returns dict or None."""
    value, stale = get_or_fetch(CACHE_KEY, CACHE_TTL, _live)
    if value and not stale:
        lg_save(SOURCE_NAME, value)
    if value is None:
        last, age = lg_load(SOURCE_NAME)
        if last is not None:
            return last
        return None
    return value


if __name__ == "__main__":
    print("ADR Delta Summary:")
    print(get_adr_delta())
