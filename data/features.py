"""
Unified feature matrix builder for the ZERO engine.

`build_features(date_str, index_name)` is the single source of truth for
the per-day, per-index feature dict that drives both the linear baseline
and the XGBoost heads.

It composes the existing scrapers and the historical layer — no new
network I/O of its own, so the cache / last-good / retry plumbing is
already in place.

The returned dict is also persisted to db/feature_store.parquet (keyed by
date+index_name) so retraining reads from disk and doesn't re-hit the
network for every fold.
"""
import os
import datetime
import calendar
import numpy as np
import pandas as pd

from config import TICKERS, US_FUT_TICKERS
from data.historical import get_recent_ohlc_and_atr
from data.gift_nifty import get_gift_nifty_price
from data.adr_tracker import get_adr_delta
from data.global_feeds import get_us_market_summary
from data.options_chain import fetch_and_process
from data.market_news import get_global_news, analyze_sentiment


# Mapping from display name to historical key (kept in sync with prediction_matrix)
INDEX_HIST_KEYS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
}
INDEX_OPTIONS_SYMBOLS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": None,
}

FEATURE_COLUMNS = [
    "gift_premium",
    "gift_premium_pct",
    "adr_weighted",
    "us_fut_overnight_pct",
    "vix",
    "vix_chg_pct",
    "india_vix",
    "dxy_overnight_pct",
    "brent_overnight_pct",
    "usdinr_chg_pct",
    "pcr",
    "max_pain_distance",
    "atr_pct",
    "rvol_20",
    "dow_sin",
    "dow_cos",
    "is_weekly_expiry",
    "is_monthly_expiry",
    "sentiment_score",
    "prev_gap",
]


def _is_thursday_in_same_week(d):
    """Return True if `d`'s Thursday falls in the same ISO week as `d`."""
    thursday = d + datetime.timedelta(days=(3 - d.weekday()) % 7)
    return thursday.year == d.year and thursday.month == d.month


def _is_last_thursday_of_month(d):
    """Return True if `d`'s Thursday is the last one in `d`'s month."""
    thursday = d + datetime.timedelta(days=(3 - d.weekday()) % 7)
    last_day = calendar.monthrange(d.year, d.month)[1]
    # find last Thursday
    last_thursday = d
    for offset in range(1, 8):
        cand = d.replace(day=last_day) - datetime.timedelta(days=offset)
        if cand.weekday() == 3:
            last_thursday = cand
            break
    return thursday == last_thursday


def _safe_get(d, keys, default=0.0):
    """Walk a nested dict, returning `default` if any key is missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def _us_fut_overnight_pct(us_summary):
    """Average overnight Δ% of US-futures proxies (S&P 500, NASDAQ, DOW)."""
    vals = []
    for key in ("SP500", "NASDAQ", "DOW"):
        chg = _safe_get(us_summary, [key, "change_pct"], None)
        if chg is not None and chg != 0:
            vals.append(float(chg))
    if not vals:
        return 0.0
    return float(np.mean(vals))


def _overnight_chg(us_summary, key):
    """Overnight Δ% for a single ticker key from us_summary."""
    chg = _safe_get(us_summary, [key, "change_pct"], None)
    return float(chg) if chg is not None else 0.0


def build_features(date_str, index_name):
    """
    Returns a flat dict of features for (date_str, index_name).
    The dict is also persisted to the parquet feature store.
    """
    hist_key = INDEX_HIST_KEYS.get(index_name, "NIFTY")
    hist = get_recent_ohlc_and_atr(hist_key) or {}

    spot_close = float(hist.get("close") or 0.0)
    atr = float(hist.get("atr") or 0.0)
    prev_open = float(hist.get("open") or 0.0)
    prev_gap = ((prev_open - spot_close) / spot_close) if spot_close > 0 else 0.0
    atr_pct = (atr / spot_close) if spot_close > 0 else 0.0
    rvol = float(hist.get("rvol_20") or 0.0)
    if np.isnan(rvol):
        rvol = 1.0

    gift_price, _ = get_gift_nifty_price()
    if gift_price and spot_close:
        gift_premium = float(gift_price) - spot_close
        gift_premium_pct = gift_premium / spot_close
    else:
        gift_premium = 0.0
        gift_premium_pct = 0.0

    adr = get_adr_delta() or {}
    adr_weighted = float(adr.get("weighted_avg") or 0.0)

    us_summary = get_us_market_summary() or {}
    us_fut_overnight_pct = _us_fut_overnight_pct(us_summary)
    vix = float(_safe_get(us_summary, ["VIX", "price"], 15.0))
    vix_chg = _overnight_chg(us_summary, "VIX")
    india_vix = float(_safe_get(us_summary, ["INDIAVIX", "price"], 0.0))
    dxy_chg = _overnight_chg(us_summary, "DXY")
    brent_chg = _overnight_chg(us_summary, "BRENT")
    usdinr_chg = _overnight_chg(us_summary, "USDINR")

    pcr = 1.0
    max_pain_distance = 0.0
    opt_symbol = INDEX_OPTIONS_SYMBOLS.get(index_name)
    if opt_symbol:
        opt = fetch_and_process(opt_symbol)
        if opt:
            pcr = float(opt.get("pcr") or 1.0)
            mp = opt.get("max_pain")
            if mp and spot_close and atr:
                max_pain_distance = (float(mp) - spot_close) / atr

    # Sentiment
    news = get_global_news()
    sent = analyze_sentiment(news) or {}
    sent_score = float(sent.get("score") or 0.0) if isinstance(sent, dict) else float(sent or 0.0)

    # Calendar features
    try:
        d = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        d = datetime.datetime.now()
    dow_sin = float(np.sin(2 * np.pi * d.weekday() / 5))
    dow_cos = float(np.cos(2 * np.pi * d.weekday() / 5))
    is_weekly = 1.0 if _is_thursday_in_same_week(d) else 0.0
    is_monthly = 1.0 if _is_last_thursday_of_month(d) else 0.0

    feats = {
        "gift_premium": gift_premium,
        "gift_premium_pct": gift_premium_pct,
        "adr_weighted": adr_weighted,
        "us_fut_overnight_pct": us_fut_overnight_pct,
        "vix": vix,
        "vix_chg_pct": vix_chg,
        "india_vix": india_vix,
        "dxy_overnight_pct": dxy_chg,
        "brent_overnight_pct": brent_chg,
        "usdinr_chg_pct": usdinr_chg,
        "pcr": pcr,
        "max_pain_distance": max_pain_distance,
        "atr_pct": atr_pct,
        "rvol_20": rvol,
        "dow_sin": dow_sin,
        "dow_cos": dow_cos,
        "is_weekly_expiry": is_weekly,
        "is_monthly_expiry": is_monthly,
        "sentiment_score": sent_score,
        "prev_gap": prev_gap,
    }
    # clean NaN
    feats = {k: (0.0 if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v))
             for k, v in feats.items()}

    _persist(date_str, index_name, feats)
    return feats


def _persist(date_str, index_name, feats):
    """Append the row to db/feature_store.parquet, creating it on first call."""
    from config import FEATURE_STORE_PATH
    row = {"date": date_str, "index": index_name, **feats}
    df = pd.DataFrame([row])
    os.makedirs(os.path.dirname(FEATURE_STORE_PATH), exist_ok=True)
    if os.path.exists(FEATURE_STORE_PATH):
        try:
            existing = pd.read_parquet(FEATURE_STORE_PATH)
            df = pd.concat([existing, df], ignore_index=True)
            df = df.drop_duplicates(subset=["date", "index"], keep="last")
        except Exception:
            pass
    try:
        df.to_parquet(FEATURE_STORE_PATH, index=False)
    except Exception:
        # If pyarrow is missing or the store is unreadable we silently degrade —
        # the feature store is a cache, not a source of truth.
        pass


def load_feature_store():
    """Return the parquet feature store as a DataFrame, or an empty one."""
    from config import FEATURE_STORE_PATH
    if not os.path.exists(FEATURE_STORE_PATH):
        return pd.DataFrame(columns=["date", "index"] + FEATURE_COLUMNS)
    try:
        return pd.read_parquet(FEATURE_STORE_PATH)
    except Exception:
        return pd.DataFrame(columns=["date", "index"] + FEATURE_COLUMNS)


def assemble_training_matrix(target="pred_open"):
    """
    Join the feature store with feedback_log.json so the XGB head can train
    on (features → actual_{target}_deviation).

    Returns:
        X: np.ndarray of shape (n_samples, n_features)
        y: np.ndarray of shape (n_samples,) — target deviation in points
        meta: list of dicts with date/index/prev_close keys (for re-anchoring)
    """
    from engine.learning_service import get_feedback_logs

    store = load_feature_store()
    if store.empty:
        return np.empty((0, len(FEATURE_COLUMNS))), np.empty((0,)), []

    logs = get_feedback_logs()
    rows = []
    for log in logs:
        idx_name = log.get("index")
        date = log.get("date")
        actual = log.get("actual") or {}
        if not isinstance(actual, dict):
            continue
        # target is e.g. "pred_open"; the actual dict is keyed by the bare
        # leg name ("open"). The previous key transform produced
        # "actual_open", which never matched and silently dropped every
        # training row. Map straight to the leg instead.
        leg = target.replace("pred_", "")
        try:
            actual_val = float(actual.get(leg))
        except (TypeError, ValueError):
            continue
        if not actual_val or actual_val <= 0:
            continue
        match = store[(store["date"] == date) & (store["index"] == idx_name)]
        if match.empty:
            continue
        row = match.iloc[0].to_dict()
        prev_close = float(row.get("prev_close") or 0)
        if prev_close <= 0:
            # pull from historical layer if needed
            from data.historical import get_recent_ohlc_and_atr
            hk = INDEX_HIST_KEYS.get(idx_name, "NIFTY")
            hist = get_recent_ohlc_and_atr(hk) or {}
            prev_close = float(hist.get("close") or 0)
        if prev_close <= 0:
            continue
        feat_vec = [float(row.get(c, 0.0) or 0.0) for c in FEATURE_COLUMNS]
        rows.append({
            "X": feat_vec,
            "y": actual_val - prev_close,  # deviation in points
            "meta": {
                "date": date,
                "index": idx_name,
                "prev_close": prev_close,
            }
        })

    if not rows:
        return np.empty((0, len(FEATURE_COLUMNS))), np.empty((0,)), []
    X = np.array([r["X"] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    meta = [r["meta"] for r in rows]
    return X, y, meta


if __name__ == "__main__":
    import json
    today = datetime.date.today().strftime("%Y-%m-%d")
    for idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
        feats = build_features(today, idx)
        print(f"\n{idx} features @ {today}:")
        for k, v in feats.items():
            print(f"  {k:25s} {v}")
