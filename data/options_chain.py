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


# ---------------------------------------------------------------------------
# OPTIONS-INTEL extension (append-only): intraday option-chain snapshots.
# Nothing above is modified; the live prediction engine is unaffected.
# ---------------------------------------------------------------------------
import json as _json
import os as _os

# Env-overridable default snapshot root.
SNAPSHOT_DIR_DEFAULT = _os.environ.get('ZERO_OPTIONS_SNAPSHOT_DIR', 'db/options_snapshots')


def _pyarrow_available() -> bool:
    """Lazy pyarrow probe. No import cost at module load; never raises."""
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
        return True
    except Exception:
        return False


def _snapshot_rows(data):
    """Build per-strike snapshot rows from raw NSE JSON (nearest expiry).

    Returns (spot, expiry, rows) where rows is a list of
    {'strike', 'ce_oi', 'pe_oi', 'ce_iv', 'pe_iv', 'ce_ltp', 'pe_ltp'};
    (None, None, []) on any problem. Never raises.
    """
    try:
        if not data:
            return None, None, []
        records = data.get('records', {}) or {}
        rows = data.get('filtered', {}).get('data', []) or records.get('data', []) or []
        if not rows:
            return None, None, []
        expiry_dates = records.get('expiryDates') or []
        nearest_expiry = expiry_dates[0] if expiry_dates else None
        if nearest_expiry:
            rows = [r for r in rows if r.get('expiry') == nearest_expiry] or rows
        spot = records.get('underlyingValue')
        if spot is None:
            spot = (data.get('filtered', {}) or {}).get('underlyingValue')
        out = []
        for r in rows:
            ce = r.get('CE', {}) or {}
            pe = r.get('PE', {}) or {}
            try:
                strike = float(r.get('strikePrice', 0) or 0)
            except Exception:
                continue
            out.append({
                'strike': strike,
                'ce_oi': float(ce.get('openInterest', 0) or 0),
                'pe_oi': float(pe.get('openInterest', 0) or 0),
                'ce_iv': ce.get('impliedVolatility'),
                'pe_iv': pe.get('impliedVolatility'),
                'ce_ltp': ce.get('lastPrice'),
                'pe_ltp': pe.get('lastPrice'),
            })
        return spot, nearest_expiry, out
    except Exception:
        return None, None, []


def _append_parquet(path: str, record: dict) -> str | None:
    """Append one snapshot record to a parquet file (read-concat-rewrite).

    Nested per-strike data is stored as a JSON string column ('strikes_json')
    so the parquet schema stays flat and stable across appends.
    Returns the path written. Raises on failure (caller handles fallback).
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    flat = {
        'ts': record.get('ts'),
        'symbol': record.get('symbol'),
        'spot': record.get('spot'),
        'pcr': record.get('pcr'),
        'max_pain': record.get('max_pain'),
        'expiry': record.get('expiry'),
        'strikes_json': _json.dumps(record.get('strikes') or [], default=str),
    }
    rows = []
    if _os.path.exists(path):
        try:
            rows = pq.read_table(path).to_pylist()
        except Exception:
            rows = []
    rows.append(flat)
    pq.write_table(pa.Table.from_pylist(rows), path)
    return path


def snapshot_option_chain(symbol: str, snapshot_dir: str = SNAPSHOT_DIR_DEFAULT) -> str | None:
    """Fetch + process the live chain and append a timestamped snapshot.

    Record shape: {'ts', 'symbol', 'spot', 'pcr', 'max_pain', 'expiry',
    'strikes': [{'strike', 'ce_oi', 'pe_oi', 'ce_iv', 'pe_iv', 'ce_ltp',
    'pe_ltp'}, ...]}.

    Storage: <snapshot_dir>/<SYMBOL>/<YYYY-MM-DD>.parquet when pyarrow is
    importable, else <YYYY-MM-DD>.jsonl (one JSON record per line).
    Returns the file path written, or None on failure. Never raises.
    """
    try:
        raw = fetch_nse_option_chain(symbol)
        processed = process_option_chain(raw)
        spot, expiry, strikes = _snapshot_rows(raw)
        if processed is None or not strikes:
            return None
        now = datetime.datetime.now()
        record = {
            'ts': now.isoformat(),
            'symbol': str(symbol).upper(),
            'spot': spot,
            'pcr': processed.get('pcr'),
            'max_pain': processed.get('max_pain'),
            'expiry': expiry or processed.get('nearest_expiry'),
            'strikes': strikes,
        }
        day = now.strftime('%Y-%m-%d')
        folder = _os.path.join(snapshot_dir, str(symbol).upper())
        _os.makedirs(folder, exist_ok=True)
        if _pyarrow_available():
            try:
                return _append_parquet(_os.path.join(folder, day + '.parquet'), record)
            except Exception:
                pass  # fall through to JSONL on any parquet failure
        jsonl_path = _os.path.join(folder, day + '.jsonl')
        with open(jsonl_path, 'a', encoding='utf-8') as fh:
            fh.write(_json.dumps(record, default=str) + '\n')
        return jsonl_path
    except Exception:
        return None


def _read_parquet_snapshots(path: str) -> list[dict]:
    """Read snapshot rows from a parquet file; 'strikes_json' is decoded
    back into the 'strikes' list. [] on any problem."""
    out = []
    try:
        import pyarrow.parquet as pq
        for row in pq.read_table(path).to_pylist():
            row = dict(row)
            strikes_json = row.pop('strikes_json', None)
            if strikes_json is not None:
                try:
                    row['strikes'] = _json.loads(strikes_json)
                except Exception:
                    row['strikes'] = []
            out.append(row)
    except Exception:
        pass
    return out


def _read_jsonl_snapshots(path: str) -> list[dict]:
    """Read snapshot records from a JSONL file; skips bad lines."""
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(_json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def load_snapshots(symbol: str, date_str: str | None = None,
                   snapshot_dir: str = SNAPSHOT_DIR_DEFAULT) -> list[dict]:
    """Load snapshot records for a symbol, newest-last.

    date_str ('YYYY-MM-DD') restricts to a single day; None loads every
    stored day. Reads both .parquet and .jsonl files and merges them.
    Empty list when nothing is stored. Never raises.
    """
    try:
        folder = _os.path.join(snapshot_dir, str(symbol).upper())
        if not _os.path.isdir(folder):
            return []
        if date_str:
            names = [date_str + '.parquet', date_str + '.jsonl']
        else:
            names = sorted(
                n for n in _os.listdir(folder)
                if n.endswith('.parquet') or n.endswith('.jsonl')
            )
        records: list[dict] = []
        for name in names:
            path = _os.path.join(folder, name)
            if not _os.path.exists(path):
                continue
            if name.endswith('.parquet'):
                records.extend(_read_parquet_snapshots(path))
            else:
                records.extend(_read_jsonl_snapshots(path))
        records.sort(key=lambda r: str(r.get('ts') or ''))
        return records
    except Exception:
        return []
