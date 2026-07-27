"""
NSE options chain with Max Pain, OI walls, change-in-OI, and a
last-good cache. Returns a dict the engine can consume directly.
"""
import datetime

from config import NSE_HEADERS
from data.cache import get_or_fetch
from data.retry import fetch as retry_fetch
from data.last_good import save as lg_save, load as lg_load


CACHE_KEY_TPL = "option_chain:{symbol}"
CACHE_TTL = 600  # 10 min
SOURCE_NAME_TPL = "option_chain:{symbol}"


def fetch_nse_option_chain(symbol='NIFTY'):
    """Returns the raw NSE JSON, or None on failure."""
    session_headers = dict(NSE_HEADERS)
    session_headers['Referer'] = 'https://www.nseindia.com/option-chain'
    url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"

    # Warm session with a home-page hit
    try:
        warm = retry_fetch("https://www.nseindia.com/",
                           headers=session_headers, timeout=8)
        # We don't care about the result; we just need cookies set.
        _ = warm
    except Exception:
        pass

    r = retry_fetch(url, headers=session_headers, timeout=10)
    if r and r.status_code == 200:
        try:
            return r.json()
        except ValueError:
            return None
    return None


def _max_pain(rows, expiry):
    """
    Standard max-pain calculation: pick the strike where total option-holder
    pain (sum of intrinsic value across all OI at every strike) is minimized.
    """
    if not rows:
        return None
    strikes = sorted({r['strikePrice'] for r in rows})
    if not strikes:
        return None

    best_strike = None
    best_pain = float('inf')
    for candidate in strikes:
        pain = 0
        for r in rows:
            ce_oi = r.get('CE', {}).get('openInterest', 0) or 0
            pe_oi = r.get('PE', {}).get('openInterest', 0) or 0
            ce_oi = float(ce_oi)
            pe_oi = float(pe_oi)
            # If candidate above this strike, calls expire ITM for holders
            pain += max(0, candidate - r['strikePrice']) * ce_oi
            pain += max(0, r['strikePrice'] - candidate) * pe_oi
        if pain < best_pain:
            best_pain = pain
            best_strike = candidate
    return best_strike


def process_option_chain(data):
    """Extract OI walls, PCR, max pain, and OI change from NSE JSON."""
    if not data:
        return None

    records = data.get('records', {})
    rows = data.get('filtered', {}).get('data', []) or records.get('data', [])
    if not rows:
        return None

    # Filter to nearest expiry (the NSE payload already does this with `filtered`,
    # but if a custom payload is passed in we still want a single expiry for max-pain).
    nearest_expiry = records.get('expiryDates', [None])[0] if records.get('expiryDates') else None
    if nearest_expiry:
        rows = [r for r in rows if r.get('expiry') == nearest_expiry] or rows

    ce_oi = [(r.get('CE', {}) or {}).get('openInterest', 0) or 0 for r in rows]
    pe_oi = [(r.get('PE', {}) or {}).get('openInterest', 0) or 0 for r in rows]
    strikes = [r['strikePrice'] for r in rows]

    if not strikes or not any(ce_oi) and not any(pe_oi):
        return None

    max_ce_oi_idx = ce_oi.index(max(ce_oi)) if any(ce_oi) else 0
    max_pe_oi_idx = pe_oi.index(max(pe_oi)) if any(pe_oi) else 0

    sum_ce = sum(float(x) for x in ce_oi)
    sum_pe = sum(float(x) for x in pe_oi)
    pcr = (sum_pe / sum_ce) if sum_ce > 0 else 0

    # OI change: net change in OI today vs prior session
    ce_oi_chg = [(r.get('CE', {}) or {}).get('changeinOpenInterest', 0) or 0 for r in rows]
    pe_oi_chg = [(r.get('PE', {}) or {}).get('changeinOpenInterest', 0) or 0 for r in rows]
    if any(ce_oi_chg) or any(pe_oi_chg):
        idx_max_ce_chg = ce_oi_chg.index(max(ce_oi_chg)) if any(ce_oi_chg) else 0
        idx_max_pe_chg = pe_oi_chg.index(min(pe_oi_chg)) if any(pe_oi_chg) else 0
    else:
        idx_max_ce_chg = max_ce_oi_idx
        idx_max_pe_chg = max_pe_oi_idx

    return {
        'max_ce_oi_strike': strikes[max_ce_oi_idx],
        'max_pe_oi_strike': strikes[max_pe_oi_idx],
        'max_ce_oi_chg_strike': strikes[idx_max_ce_chg],
        'max_pe_oi_chg_strike': strikes[idx_max_pe_chg],
        'pcr': round(pcr, 4),
        'max_pain': _max_pain(rows, nearest_expiry),
        'nearest_expiry': nearest_expiry,
        'timestamp': datetime.datetime.now().isoformat(),
    }


def fetch_and_process(symbol='NIFTY'):
    """Cached fetch+process. Returns dict or None."""
    cache_key = CACHE_KEY_TPL.format(symbol=symbol)
    src = SOURCE_NAME_TPL.format(symbol=symbol)

    def _live():
        return process_option_chain(fetch_nse_option_chain(symbol))

    value, stale = get_or_fetch(cache_key, CACHE_TTL, _live)
    if value and not stale:
        lg_save(src, value)
    if value is None:
        last, age = lg_load(src)
        if last is not None:
            return last
        return None
    return value


if __name__ == "__main__":
    stats = fetch_and_process('NIFTY')
    if stats:
        for k, v in stats.items():
            print(f"  {k}: {v}")
    else:
        print("Failed to fetch NIFTY option chain. (NSE may be blocking or market closed.)")
