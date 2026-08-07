"""
ZERO AITE configuration — isolated from config.py / quant_config.py.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[2]
AITE_DB_DIR = _ROOT / "db" / "aite"
AITE_DB_DIR.mkdir(parents=True, exist_ok=True)

BOTS_PATH = AITE_DB_DIR / "bots.json"
PORTFOLIO_PATH = AITE_DB_DIR / "portfolio.json"
TRADES_PATH = AITE_DB_DIR / "trades.jsonl"
LOGS_PATH = AITE_DB_DIR / "daemon.jsonl"
BRIEFS_PATH = AITE_DB_DIR / "briefs.jsonl"
PREMARKET_PATH = AITE_DB_DIR / "premarket.jsonl"
EXAM_CACHE_PATH = AITE_DB_DIR / "exam_cache.json"
FUND_PATH = AITE_DB_DIR / "fund.json"
AGENT_STATE_PATH = AITE_DB_DIR / "agents.json"
DAEMON_STATE_PATH = AITE_DB_DIR / "daemon_state.json"
IDEAS_PATH = AITE_DB_DIR / "ideas.jsonl"

# ── Paper fund ───────────────────────────────────────────────────────────────
DEFAULT_PAPER_FUND = float(os.environ.get("ZERO_AITE_PAPER_FUND", "1000000"))  # ₹10L
MIN_BOTS = 10
MAX_BOTS = 40
TARGET_BOTS = int(os.environ.get("ZERO_AITE_TARGET_BOTS", "20"))

# ── Genetic breeding ─────────────────────────────────────────────────────────
POPULATION_SIZE = 48
GENERATIONS = 12
ELITE_K = 6
MUTATION_RATE = 0.35
CROSSOVER_RATE = 0.55
MAX_RULES = 6
SEED = 42

INDICATOR_POOL = [
    "rsi", "macd_hist", "bb_pct_b", "atr_pct", "ema_spread",
    "mom_10", "mom_20", "vol_z", "obv_slope", "stoch_k",
    "adx", "cci", "williams_r", "vwap_dist", "ret_z",
]

OPERATORS = [">", "<", "crosses_above", "crosses_below"]
THRESHOLD_MIN = -3.0
THRESHOLD_MAX = 100.0

# Fitness: Sharpe × (1 + return) / (1 + max_dd) with OOS weight
IS_WEIGHT = 0.35
OOS_WEIGHT = 0.65
MIN_TRADES_OOS = 4
MIN_OOS_SHARPE = 0.15
MAX_OOS_DRAWDOWN = 0.35

# ── Portfolio / risk ─────────────────────────────────────────────────────────
MAX_PAIRWISE_CORR = 0.65          # bots that correlate higher get culled
FADE_LOOKBACK_TRADES = 12
FADE_PNL_THRESHOLD = -0.02        # cut if recent rolling return < -2%
MAX_BOT_ALLOC_PCT = 0.12
KILL_BLAST_MS = 1400              # UI death animation

# ── Exam / backtest ──────────────────────────────────────────────────────────
# Exam rejects when feature rows < MIN_BARS. ALGORY-style OOS needs ≥1 trading
# year of daily OHLC; DEFAULT_BARS is the load target for historical adapters.
MIN_BARS = 252                    # hard exam gate — ≥1 NSE trading year
TARGET_BARS = 252                 # ≥1 NSE trading year
DEFAULT_BARS = 400                # load target (calendar period derived from this)
EDGE_MONITOR_EVERY_TICKS = 10     # daemon: edge monitor cadence
BREED_EVERY_TICKS = None          # if set, override hour-based breed schedule
IS_FRAC = 0.60
OOS_FRAC = 0.40
COMMISSION_BPS = 2.0
SLIPPAGE_BPS = 3.0
BACKTEST_FLOW_LINES = 40          # UI synced progress lines

# ── Symbols ──────────────────────────────────────────────────────────────────
# UI / genome labels (left) → short internal keys used in logs & INDEX lookups.
# These are NOT MT5 Market Watch names — see MT5_SYMBOL_MAP below.
INDEX_KEYS = {
    "NIFTY 50": "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "SENSEX": "SENSEX",
}
DEFAULT_SYMBOLS = list(INDEX_KEYS.keys())

# ── Scheduler (IST) ──────────────────────────────────────────────────────────
PREMARKET_HHMM = (8, 45)          # 08:45 IST daily premarket
DAEMON_TICK_SECONDS = 30
BREED_INTERVAL_HOURS = 6

# ── MT5 ──────────────────────────────────────────────────────────────────────
# Opt-in paper path. Requires MetaTrader5 package + running terminal + AutoTrading.
MT5_ENABLED = os.environ.get("ZERO_AITE_MT5", "0") == "1"


def _mt5_env(*names: str, default: str) -> str:
    """First non-empty env among ``names``, else ``default``."""
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return default


# ZERO UI / BotGenome.symbol  →  exact MT5 Market Watch string for the broker.
# India CFD / index brokers differ: NIFTY may appear as NIFTY, NIFTY50, NSEI,
# .NIFTY50, etc. Copy the name from MT5 Market Watch into the env vars.
#   ZERO_AITE_MT5_NIFTY / ZERO_AITE_MT5_NIFTY50  → maps "NIFTY 50"
#   ZERO_AITE_MT5_BANKNIFTY                     → maps "BANKNIFTY"
#   ZERO_AITE_MT5_SENSEX                        → maps "SENSEX"
MT5_SYMBOL_MAP = {
    "NIFTY 50": _mt5_env("ZERO_AITE_MT5_NIFTY", "ZERO_AITE_MT5_NIFTY50", default="NIFTY"),
    "BANKNIFTY": _mt5_env("ZERO_AITE_MT5_BANKNIFTY", default="BANKNIFTY"),
    "SENSEX": _mt5_env("ZERO_AITE_MT5_SENSEX", default="SENSEX"),
}

# ── Brief / premarket ────────────────────────────────────────────────────────
BRIEF_DO_NOT_BUY_DD = 0.08        # drawdown threshold for do-not-buy
PREMARKET_SECTIONS = 8
