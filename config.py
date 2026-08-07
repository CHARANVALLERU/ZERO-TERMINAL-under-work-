from __future__ import annotations
import os
import datetime as _dt_module
from datetime import time, datetime, timedelta, timezone
from typing import Optional, Union

# Project Name
PROJECT_NAME = "ZERO"

# ── ZERO ENGINE — Gemini AI Configuration ────────────────────────────────
# Free tier key from https://aistudio.google.com
# Override via environment variable GEMINI_API_KEY if preferred.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ZERO_ENGINE_MODEL = "gemini-2.0-flash"      # Latest available free-tier model
ZERO_ENGINE_MAX_HISTORY = 20                # Max message pairs to retain in context

# ── Hugging Face Hub (optional — public Kronos weights work without it) ─
# Prefer HF_TOKEN; HUGGING_FACE_HUB_TOKEN is the older alias huggingface_hub
# still reads.  Raises anonymous rate limits when set; never required.
HF_TOKEN = (
    os.getenv("HF_TOKEN", "") or os.getenv("HUGGING_FACE_HUB_TOKEN", "")
).strip()

# ── YouTube & Ingestion Proxy Configuration ──────────────────────────────
# Webshare or Generic Proxy credentials to bypass YouTube IP blocks (RequestBlocked/IpBlocked)
YOUTUBE_PROXY_USERNAME = os.getenv("YOUTUBE_PROXY_USERNAME", os.getenv("WEBSHARE_PROXY_USERNAME", ""))
YOUTUBE_PROXY_PASSWORD = os.getenv("YOUTUBE_PROXY_PASSWORD", os.getenv("WEBSHARE_PROXY_PASSWORD", ""))
YOUTUBE_PROXY_HTTP = os.getenv("YOUTUBE_PROXY_HTTP", os.getenv("HTTP_PROXY", ""))
YOUTUBE_PROXY_HTTPS = os.getenv("YOUTUBE_PROXY_HTTPS", os.getenv("HTTPS_PROXY", ""))

# ── Obsidian Vault Configuration ──────────────────────────────────────────
# Path to your Obsidian Vault directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", os.path.join(PROJECT_ROOT, "obsidian_vault"))
# Secondary vault: receives a delayed mirror of primary writes (≥24h).
# Override via SECOND_ZERO_VAULT_PATH. Sync is skipped (no crash) if unwritable.
SECOND_ZERO_VAULT_PATH = os.getenv(
    "SECOND_ZERO_VAULT_PATH",
    os.path.join(PROJECT_ROOT, "second_zero_vault"),
)
# Hours a primary write must age before it is copied to SECOND ZERO.
VAULT_BACKUP_DELAY_HOURS = float(os.getenv("VAULT_BACKUP_DELAY_HOURS", "24"))
# Persistent dual-vault sync queue (primary_synced_at → second_synced_at).
VAULT_SYNC_QUEUE_PATH = os.getenv(
    "VAULT_SYNC_QUEUE_PATH",
    os.path.join(PROJECT_ROOT, "db", "vault_sync_queue.json"),
)

# Timezone
TIMEZONE = 'Asia/Kolkata'

# Tickers
TICKERS = {
    'NIFTY': '^NSEI',
    'SENSEX': '^BSESN',
    'BANKNIFTY': '^NSEBANK',
    'VIX': '^VIX',
    'SP500': '^GSPC',
    'NASDAQ': '^NDX',
    'DOW': '^DJI',
    'INDIAVIX': '^INDIAVIX',
    'DXY': 'DX-Y.NYB',
    'BRENT': 'BZ=F',
    'USDINR': 'USDINR=X'
}

# ADR Mappings
ADR_TICKERS = {
    'HDFC': 'HDB',
    'ICICI': 'IBN',
    'INFOSYS': 'INFY',
    'TCS': 'TSN',
}

# US-futures overnight universe (used for us_fut_overnight_pct)
US_FUT_TICKERS = ('^GSPC', '^IXIC', '^DJI')

# Coefficients (Initial calibration — kept for backward compatibility)
ALPHA = 0.5  # GIFT Nifty weight
BETA = 0.5   # ADR weight
GAMMA = 0.5  # Volatility multiplier

# Extended cross-asset weights (linear fallback used when ML model is absent)
US_FUT_WEIGHT = 0.30   # US-futures overnight Δ% contribution to gap
DXY_WEIGHT = -0.15     # DXY strength typically inverse to EM equities
BRENT_WEIGHT = -0.05   # Brent up → INR pressure / risk-off
VIX_DECAY = 0.20       # Sentiment gap adjustment per unit |sentiment_score|

# Threholds
VIX_THRESHOLD = 15.0
BRENT_THRESHOLD_HIGH = 85.0
DXY_THRESHOLD_HIGH = 104.0

# Database
DB_PATH = 'db/zero_market.db'
FEATURE_STORE_PATH = 'db/feature_store.parquet'
MODEL_REGISTRY_PATH = 'db/model_registry.json'

# Market Hours (IST)
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_MARKET_OPEN = time(9, 0)
ENGINE_REFRESH_TIME = time(9, 0)

# ML model
ML_MODEL_DIR = "db"
ML_MIN_TRAIN_ROWS = 12       # refuse to train below this
ML_WALK_FORWARD_FOLDS = 5    # expanding-window folds
ML_MAX_DEPTH = 4
ML_LEARNING_RATE = 0.05
ML_N_ESTIMATORS = 300
ML_BLEND_CAP = 0.6           # upper bound on ML weight in the linear+ML blend
ML_STALE_DAYS = 7            # after this, engine falls back to linear-only
QUANTILE_BAND_Z = 1.28       # ≈80% P10/P90 band; widen for risk-on
COMMIT_RELATIVE_IMPROVEMENT = 0.05   # require 5% relative CV-MAE gain before committing a learned correction

# Feature engineering
MAX_PREDICTION_RANGE = {
    "SENSEX": 5000,
    "NIFTY 50": 2000,
    "BANKNIFTY": 2000,
}

# Scraper Settings
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
NSE_HEADERS = {
    'User-Agent': USER_AGENT,
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
}

# ── Real-time News-Impact Engine ─────────────────────────────────────────
# Reference index levels used to convert an estimated % move into points when
# a live spot price is unavailable (refreshed opportunistically from history).
NEWS_REFERENCE_LEVELS = {
    "NIFTY 50": 24000.0,
    "BANKNIFTY": 57000.0,
    "SENSEX": 77000.0,
}
# The move (%) produced by a *maximal* headline (sentiment ±1, weight 1,
# severity 1). Real events scale down from here. ~1.4% is a realistic ceiling
# for a single pre-market shock on the Nifty.
NEWS_BASE_MOVE_PCT = 1.4
# Hard clamp so no single headline can imply an absurd move.
NEWS_MAX_MOVE_PCT = 2.8
# Impact score (0-100) at/above which a headline fires a device notification.
NEWS_ALERT_THRESHOLD = 45.0
# How often the live news feed polls for new items (seconds).
NEWS_REFRESH_SECONDS = 60
# Cache TTL for the prediction matrix when a fresh news overlay is present.
# The matrix re-runs end-to-end every 60 s while news is live so the high/low
# values track the live tape. Without news, the floor is 10 min to keep
# cold paths cheap.
NEWS_MATRIX_TTL_SECONDS = 60
NEWS_MATRIX_TTL_FLOOR_SECONDS = 600
# Minimum absolute move in the predicted high/low (in %) that warrants a
# "Quant Cores Calibrated" toast while the market is open. Prevents toasting
# on noise.
CALIBRATED_TOAST_MIN_SHIFT_PCT = 0.1
# Max number of news-overlay items included in the matrix cache key. We cap
# so a flood of news doesn't bloat the cache key.
NEWS_OVERLAY_CACHE_CAP = 20

# Allowed direction values for the news impact feed. Anything outside this
# set is mapped to NEUTRAL before it reaches the UI; prevents both a UI
# crash on a typo in a feed source and accidental CSS-class injection.
ALLOWED_DIRECTIONS = ("BULLISH", "BEARISH", "NEUTRAL")
# Allowed link schemes in feed items. Anything else is dropped on render.
ALLOWED_LINK_SCHEMES = ("http", "https")

# Indian market session & holiday helpers -----------------------------------
IST = timezone(timedelta(hours=5, minutes=30))

# Official NSE National Trading Holidays (2024–2027)
NSE_HOLIDAYS = {
    # 2024
    "2024-01-22", "2024-01-26", "2024-03-08", "2024-03-25", "2024-03-29",
    "2024-04-11", "2024-04-17", "2024-05-01", "2024-05-20", "2024-06-17",
    "2024-07-17", "2024-08-15", "2024-10-02", "2024-11-01", "2024-11-15",
    "2024-11-20", "2024-12-25",
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-06-07", "2025-07-06",
    "2025-08-15", "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22",
    "2025-11-05", "2025-12-25",
    # 2026
    "2026-01-26", "2026-02-16", "2026-03-03", "2026-03-20", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-27", "2026-06-25", "2026-08-15",
    "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-08", "2026-11-24",
    "2026-12-25",
    # 2027
    "2027-01-26", "2027-03-08", "2027-03-22", "2027-03-26", "2027-04-14",
    "2027-05-01", "2027-08-15", "2027-10-02", "2027-12-25",
}


def now_ist() -> datetime:
    """Naive IST clock for comparisons against MARKET_OPEN / MARKET_CLOSE."""
    return datetime.now(IST).replace(tzinfo=None)


def is_trading_day(when: Optional[Union[datetime, _dt_module.date]] = None) -> bool:
    """True iff when is an official NSE trading day (Mon-Fri and not a national holiday)."""
    if when is None:
        when = now_ist()
    dt = when.date() if isinstance(when, datetime) else when
    if dt.weekday() >= 5:  # Saturday or Sunday
        return False
    if dt.strftime('%Y-%m-%d') in NSE_HOLIDAYS:
        return False
    return True


def get_next_trading_day(when: Optional[datetime] = None) -> _dt_module.date:
    """Returns the date of the next active trading session.

    If current time is past market close (>= 15:30) or today is a non-trading
    day (weekend/holiday), iterates forward to find the next open session date.
    """
    when = when or now_ist()
    dt = when.date()
    # If today's market is already closed or today is a non-trading day, start from tomorrow
    if when.time() >= MARKET_CLOSE or not is_trading_day(dt):
        dt = dt + timedelta(days=1)

    while not is_trading_day(dt):
        dt = dt + timedelta(days=1)
    return dt


def is_market_closed_post_4pm(when: datetime | None = None) -> bool:
    """True iff today is a valid trading day AND the current IST time is >= 4:00 PM (16:00 IST)."""
    when = when or now_ist()
    return is_trading_day(when) and when.time() >= time(16, 0)


def is_market_open(when: datetime | None = None) -> bool:
    """True iff the NSE cash session is currently open (Mon–Fri 09:15–15:30 IST,
    excluding national holidays).
    """
    when = when or now_ist()
    if not is_trading_day(when):
        return False
    return MARKET_OPEN <= when.time() <= MARKET_CLOSE


def market_state(when: datetime | None = None) -> str:
    """'open', 'closed_pre', 'closed_post', 'closed_holiday', or 'closed_weekend'."""
    when = when or now_ist()
    if when.weekday() >= 5:
        return "closed_weekend"
    if when.strftime("%Y-%m-%d") in NSE_HOLIDAYS:
        return "closed_holiday"
    if when.time() < MARKET_OPEN:
        return "closed_pre"
    if when.time() > MARKET_CLOSE:
        return "closed_post"
    return "open"

