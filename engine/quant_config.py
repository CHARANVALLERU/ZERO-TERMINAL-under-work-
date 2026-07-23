"""
ZERO Quant Architecture — Isolated Configuration
=================================================

All settings for the new multi-timeframe XGBoost predictor, genetic mutator,
Monte Carlo risk engine, and paper brokerage live here.  Kept separate from
the main config.py so the existing engine, calibrator, and UI are untouched.
"""

# ── XGBoost Multi-Timeframe Predictor ────────────────────────────────────

# Intraday model hyperparameters
INTRADAY_XGB = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
    "random_state": 42,
}

# Weekly model hyperparameters (slightly more conservative for sparse data)
WEEKLY_XGB = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.02,
    "subsample": 0.75,
    "colsample_bytree": 0.7,
    "tree_method": "hist",
    "random_state": 42,
}

# Minimum training rows before the XGBoost predictor activates
MTF_MIN_TRAIN_ROWS = 12

# Walk-forward folds for cross-validation
MTF_WALK_FORWARD_FOLDS = 5

# ── Monte Carlo Risk Engine ──────────────────────────────────────────────

MC_SIMULATIONS = 5000           # Number of stochastic paths per evaluation
MC_TRADE_SEQUENCE_LENGTH = 100  # Trades per simulated sequence
MC_RUIN_DRAWDOWN = 0.50         # 50% drawdown = structural ruin mark
MC_MAX_RUIN_PROBABILITY = 0.05  # Block execution above this probability

# ── Paper Brokerage ──────────────────────────────────────────────────────

PAPER_INITIAL_CAPITAL = 100000.0
PAPER_SLIPPAGE_PCT = 0.0005     # 5 bps slippage on each fill

# ── Genetic Strategy Mutator ─────────────────────────────────────────────

GENETIC_INDICATOR_POOL = [
    "RSI", "MACD", "GEX_Level", "TrendSpider_Breakout", "BBands",
    "ATR_Percentile", "PCR_Ratio", "VIX_Delta", "Sentiment_Score",
]

GENETIC_OPERATORS = [">", "<", "crosses_above", "crosses_below"]

# Default threshold range for random rule generation
GENETIC_THRESHOLD_MIN = 10.0
GENETIC_THRESHOLD_MAX = 90.0

# Mutation rate: probability of mutating each rule in a strategy
GENETIC_MUTATION_RATE = 0.3

# Maximum rules per strategy
GENETIC_MAX_RULES = 5

# ── Multi-Timeframe Feature Pipeline ─────────────────────────────────────

# GEX proxy: how many periods of OI delta to compute
GEX_DELTA_PERIODS = 5

# Weekly S/R proximity threshold (as fraction of ATR)
SR_PROXIMITY_ATR_FRACTION = 0.25

# Rolling VWAP lookback (bars)
VWAP_LOOKBACK_BARS = 20

# Rolling historical volatility window (trading days)
HIST_VOL_WINDOW = 20
