"""
ZERO Advanced Backtesting Engine
==================================
Inspired by NautilusTrader's deterministic backtesting architecture.
Implements walk-forward, multi-strategy, multi-venue backtesting
with Sharpe ratio, drawdown, and win-rate analytics.

Also carries ZERO's statistical-significance toolkit:
    * ``diebold_mariano_test``       — HAC (Newey–West) test of equal predictive accuracy
    * ``probabilistic_sharpe_ratio`` — PSR per Bailey & Lopez de Prado (2012)
    * ``deflated_sharpe_ratio``      — DSR with expected-max-SR multiple-testing correction

Pure numpy — no pandas required for core math (pandas used only for data loading).
scipy is optional: when absent, normal CDF/PPF fall back to math.erf / Acklam's
rational approximation. No network calls at import time.
"""

from __future__ import annotations

import datetime
import math
import os
from typing import Dict, List, Optional, Any
import numpy as np


# ─────────────────────────────────────────────
#  Performance Analytics
# ─────────────────────────────────────────────

class PerformanceAnalytics:
    """
    NautilusTrader-style performance statistics from equity curve.
    All calculations are pure numpy — no scipy needed.
    """

    @staticmethod
    def sharpe_ratio(returns: np.ndarray, risk_free: float = 0.065,
                     periods_per_year: int = 252) -> float:
        """Annualised Sharpe ratio (Indian risk-free: 6.5%)."""
        if len(returns) < 2:
            return 0.0
        mu  = float(np.mean(returns))
        sig = float(np.std(returns, ddof=1))
        if sig == 0:
            return 0.0
        daily_rf = (1 + risk_free) ** (1 / periods_per_year) - 1
        return round((mu - daily_rf) / sig * math.sqrt(periods_per_year), 4)

    @staticmethod
    def sortino_ratio(returns: np.ndarray, risk_free: float = 0.065,
                      periods_per_year: int = 252) -> float:
        """Sortino ratio (uses downside deviation)."""
        if len(returns) < 2:
            return 0.0
        mu       = float(np.mean(returns))
        daily_rf = (1 + risk_free) ** (1 / periods_per_year) - 1
        downside = returns[returns < daily_rf] - daily_rf
        dsig = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
        if dsig < 1e-12:
            return round((mu - daily_rf) * math.sqrt(periods_per_year) * 10, 4)  # infinite-ish Sortino
        return round((mu - daily_rf) / dsig * math.sqrt(periods_per_year), 4)

    @staticmethod
    def max_drawdown(equity_curve: np.ndarray) -> float:
        """Maximum drawdown as a fraction (0 to 1)."""
        if len(equity_curve) < 2:
            return 0.0
        peak = equity_curve[0]
        mdd  = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            if dd > mdd:
                mdd = dd
        return round(mdd, 6)

    @staticmethod
    def calmar_ratio(returns: np.ndarray, equity_curve: np.ndarray) -> float:
        """Calmar = annualised return / max drawdown."""
        mdd  = PerformanceAnalytics.max_drawdown(equity_curve)
        cagr = float(np.mean(returns)) * 252
        if mdd == 0:
            return 0.0
        return round(cagr / mdd, 4)

    @staticmethod
    def win_rate(pnl_list: List[float]) -> float:
        if not pnl_list:
            return 0.0
        wins = sum(1 for p in pnl_list if p > 0)
        return round(wins / len(pnl_list), 4)

    @staticmethod
    def profit_factor(pnl_list: List[float]) -> float:
        gross_win  = sum(p for p in pnl_list if p > 0)
        gross_loss = abs(sum(p for p in pnl_list if p < 0))
        if gross_loss == 0:
            return float("inf") if gross_win > 0 else 0.0
        return round(gross_win / gross_loss, 4)

    @staticmethod
    def expectancy(pnl_list: List[float]) -> float:
        """Average expected P&L per trade."""
        if not pnl_list:
            return 0.0
        return round(float(np.mean(pnl_list)), 4)

    @classmethod
    def full_report(cls, equity_curve: np.ndarray, pnl_list: List[float],
                    periods_per_year: int = 252) -> Dict:
        returns = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else np.array([0.0])
        psr = probabilistic_sharpe_ratio(returns)
        dsr = deflated_sharpe_ratio(returns, n_trials=DSR_DEFAULT_TRIALS)
        return {
            "total_trades":    len(pnl_list),
            "win_rate":        cls.win_rate(pnl_list),
            "profit_factor":   cls.profit_factor(pnl_list),
            "expectancy":      cls.expectancy(pnl_list),
            "sharpe_ratio":    cls.sharpe_ratio(returns, periods_per_year=periods_per_year),
            "sortino_ratio":   cls.sortino_ratio(returns, periods_per_year=periods_per_year),
            "max_drawdown_pct": round(cls.max_drawdown(equity_curve) * 100, 2),
            "calmar_ratio":    cls.calmar_ratio(returns, equity_curve),
            "final_equity":    round(float(equity_curve[-1]), 2) if len(equity_curve) else 0.0,
            "total_return_pct": round((equity_curve[-1] / equity_curve[0] - 1) * 100, 2)
                                if len(equity_curve) > 1 and equity_curve[0] != 0 else 0.0,
            # Statistical significance (None when the sample is too small)
            "psr":             _none_if_nan(psr["psr"]),
            "dsr":             _none_if_nan(dsr["dsr"]),
            "dsr_sr_threshold": _none_if_nan(dsr["sr_threshold"]),
        }


# ─────────────────────────────────────────────
#  Statistical Significance (Diebold–Mariano / Lopez de Prado)
# ─────────────────────────────────────────────

MIN_STAT_N: int = int(os.environ.get("ZERO_STATS_MIN_N", "8"))
"""Minimum sample size for any significance statistic (below → NaN + insufficient_data)."""

DSR_DEFAULT_TRIALS: int = int(os.environ.get("ZERO_DSR_TRIALS", "10"))
"""Default multiple-testing budget (number of configurations tried) for DSR."""

EULER_MASCHERONI: float = float(os.environ.get("ZERO_EULER_MASCHERONI", "0.5772156649015329"))
"""Euler–Mascheroni constant used in the expected-max-Sharpe approximation."""

_SCIPY_STATS = None
_SCIPY_CHECKED = False


def _get_scipy_stats():
    """Lazily import scipy.stats exactly once; None when scipy is unavailable."""
    global _SCIPY_STATS, _SCIPY_CHECKED
    if not _SCIPY_CHECKED:
        _SCIPY_CHECKED = True
        try:
            from scipy import stats as _s  # type: ignore
            _SCIPY_STATS = _s
        except Exception:
            _SCIPY_STATS = None
    return _SCIPY_STATS


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF — scipy when available, math.erf fallback otherwise."""
    s = _get_scipy_stats()
    if s is not None:
        try:
            return float(s.norm.cdf(x))
        except Exception:
            pass
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF — scipy when available, Acklam approximation otherwise."""
    s = _get_scipy_stats()
    if s is not None:
        try:
            return float(s.norm.ppf(p))
        except Exception:
            pass
    return _acklam_ppf(p)


# Acklam's rational-approximation coefficients (max |error| ≈ 1.15e-9)
_ACKLAM_A = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
             1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
_ACKLAM_B = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
             6.680131188771972e+01, -1.328068155288572e+01)
_ACKLAM_C = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
             -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
_ACKLAM_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
             3.754408661907416e+00)


def _acklam_ppf(p: float) -> float:
    """Pure-python inverse normal CDF (Acklam, 2010). Valid for 0 < p < 1."""
    p = min(max(float(p), 1e-12), 1.0 - 1e-12)
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        num = (((((_ACKLAM_C[0] * q + _ACKLAM_C[1]) * q + _ACKLAM_C[2]) * q
                 + _ACKLAM_C[3]) * q + _ACKLAM_C[4]) * q + _ACKLAM_C[5])
        den = ((((_ACKLAM_D[0] * q + _ACKLAM_D[1]) * q + _ACKLAM_D[2]) * q
                + _ACKLAM_D[3]) * q + 1.0)
        return num / den
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        num = (((((_ACKLAM_C[0] * q + _ACKLAM_C[1]) * q + _ACKLAM_C[2]) * q
                 + _ACKLAM_C[3]) * q + _ACKLAM_C[4]) * q + _ACKLAM_C[5])
        den = ((((_ACKLAM_D[0] * q + _ACKLAM_D[1]) * q + _ACKLAM_D[2]) * q
                + _ACKLAM_D[3]) * q + 1.0)
        return -(num / den)
    q = p - 0.5
    r = q * q
    return ((((((_ACKLAM_A[0] * r + _ACKLAM_A[1]) * r + _ACKLAM_A[2]) * r
               + _ACKLAM_A[3]) * r + _ACKLAM_A[4]) * r + _ACKLAM_A[5]) * q
            / (((((_ACKLAM_B[0] * r + _ACKLAM_B[1]) * r + _ACKLAM_B[2]) * r
                 + _ACKLAM_B[3]) * r + _ACKLAM_B[4]) * r + 1.0))


def _none_if_nan(x: Optional[float]) -> Optional[float]:
    """Round to 4 dp, mapping NaN/None/unparseable values to None (JSON-safe)."""
    try:
        v = float(x)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 4)


def _skew_kurt(r: np.ndarray, mu: float) -> tuple:
    """Sample skewness and Pearson (non-excess) kurtosis of `r` (normal → (0, 3))."""
    dev = r - mu
    m2 = float(np.mean(dev ** 2))
    if m2 <= 0.0:
        return 0.0, 3.0
    m3 = float(np.mean(dev ** 3))
    m4 = float(np.mean(dev ** 4))
    return float(m3 / (m2 ** 1.5)), float(m4 / (m2 * m2))


def diebold_mariano_test(loss_model: np.ndarray, loss_baseline: np.ndarray,
                         h: int = 1, power: int = 2) -> Dict:
    """
    Diebold–Mariano test of equal predictive accuracy.

    H0: E[d_t] = 0 with d_t = |loss_model_t|^power − |loss_baseline_t|^power.
    A significantly NEGATIVE DM statistic means `loss_model` beats the baseline.

    Pass per-period forecast errors (power=2 → squared-error loss, the classic
    choice) or pre-computed non-negative losses (power=1). The long-run variance
    is Newey–West HAC with lag h−1 (Bartlett weights); the p-value uses the
    normal approximation (scipy.stats.norm when available, else math.erf).

    Samples smaller than MIN_STAT_N return NaNs plus 'insufficient_data': True.
    """
    res: Dict[str, Any] = {"dm_stat": float("nan"), "p_value": float("nan"),
                           "n": 0, "significant_5pct": False}
    lm = np.asarray(loss_model, dtype=float).ravel()
    lb = np.asarray(loss_baseline, dtype=float).ravel()
    n0 = int(min(lm.size, lb.size))
    lm, lb = lm[:n0], lb[:n0]
    ok = ~(np.isnan(lm) | np.isnan(lb))
    d = (np.abs(lm[ok]) ** power) - (np.abs(lb[ok]) ** power)
    n = int(d.size)
    res["n"] = n
    if n < MIN_STAT_N:
        res["insufficient_data"] = True
        return res
    mean_d = float(np.mean(d))
    dev = d - mean_d
    lrv = float(np.mean(dev * dev))                      # gamma_0
    lag = max(0, int(h) - 1)
    for k in range(1, lag + 1):                          # Newey–West, Bartlett weights
        cov_k = float(np.mean(dev[k:] * dev[:-k]))
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * cov_k
    if lrv <= 1e-16:                                     # degenerate loss differential
        if abs(mean_d) <= 1e-12:
            res.update(dm_stat=0.0, p_value=1.0)
        else:
            res.update(dm_stat=math.copysign(1e9, mean_d), p_value=0.0,
                       significant_5pct=True)
        return res
    dm = mean_d / math.sqrt(lrv / n)
    p = 2.0 * (1.0 - _norm_cdf(abs(dm)))
    p = min(max(p, 0.0), 1.0)
    res.update(dm_stat=round(dm, 4), p_value=round(p, 6),
               significant_5pct=bool(p < 0.05))
    return res


def probabilistic_sharpe_ratio(returns: np.ndarray, benchmark_sr: float = 0.0) -> Dict:
    """
    Probabilistic Sharpe Ratio (Bailey & Lopez de Prado, 2012).

    P(true SR > benchmark_sr) given the track record, adjusted for the skewness
    and Pearson kurtosis of `returns`. `returns` and `benchmark_sr` must share
    the same period (e.g. daily). Returns {'psr', 'sr_hat', 'n'}; NaN plus
    'insufficient_data': True below MIN_STAT_N observations.
    """
    res: Dict[str, Any] = {"psr": float("nan"), "sr_hat": float("nan"), "n": 0}
    r = np.asarray(returns, dtype=float).ravel()
    r = r[np.isfinite(r)]
    n = int(r.size)
    res["n"] = n
    if n < MIN_STAT_N:
        res["insufficient_data"] = True
        return res
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 1e-16:
        res["insufficient_data"] = True
        return res
    sr = mu / sd
    res["sr_hat"] = round(sr, 6)
    skew, kurt = _skew_kurt(r, mu)
    inner = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if inner <= 1e-12:
        res["insufficient_data"] = True
        return res
    z = (sr - float(benchmark_sr)) * math.sqrt(n - 1.0) / math.sqrt(inner)
    res["psr"] = round(_norm_cdf(z), 6)
    return res


def deflated_sharpe_ratio(returns: np.ndarray, n_trials: int,
                          benchmark_sr: float = 0.0) -> Dict:
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    PSR computed against the expected MAXIMUM Sharpe producible by luck alone
    after `n_trials` configuration attempts (Euler–Mascheroni approximation):

        SR* = benchmark_sr + sqrt(Var[SR]) * [(1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e))]

    Var[SR] is estimated from this series' own skew/kurtosis (single-series
    approximation). Returns {'dsr', 'sr_threshold', 'n_trials'}; NaN plus
    'insufficient_data': True below MIN_STAT_N observations.
    """
    N = max(1, int(n_trials))
    res: Dict[str, Any] = {"dsr": float("nan"), "sr_threshold": float("nan"),
                           "n_trials": N}
    r = np.asarray(returns, dtype=float).ravel()
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n < MIN_STAT_N:
        res["insufficient_data"] = True
        return res
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 1e-16:
        res["insufficient_data"] = True
        return res
    sr = mu / sd
    skew, kurt = _skew_kurt(r, mu)
    inner = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr
    if inner <= 1e-12:
        res["insufficient_data"] = True
        return res
    var_sr = inner / (n - 1.0)
    if N <= 1:
        sr_star = float(benchmark_sr)
    else:
        t1 = _norm_ppf(1.0 - 1.0 / N)
        t2 = _norm_ppf(1.0 - 1.0 / (N * math.e))
        sr_star = float(benchmark_sr) + math.sqrt(var_sr) * (
            (1.0 - EULER_MASCHERONI) * t1 + EULER_MASCHERONI * t2)
    z = (sr - sr_star) * math.sqrt(n - 1.0) / math.sqrt(inner)
    res.update(sr_threshold=round(sr_star, 6), dsr=round(_norm_cdf(z), 6))
    return res


# ─────────────────────────────────────────────
#  Signal Generator (technical indicators)
# ─────────────────────────────────────────────

class TechnicalSignals:
    """
    Pure-numpy technical indicator library for backtesting.
    All functions accept np.ndarrays and return np.ndarrays.
    """

    @staticmethod
    def ema(data: np.ndarray, period: int) -> np.ndarray:
        alpha = 2.0 / (period + 1)
        out   = np.full(len(data), float("nan"))
        if len(data) < period:
            return out
        out[period - 1] = np.mean(data[:period])
        for i in range(period, len(data)):
            out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]
        return out

    @staticmethod
    def sma(data: np.ndarray, period: int) -> np.ndarray:
        out = np.full(len(data), float("nan"))
        for i in range(period - 1, len(data)):
            out[i] = np.mean(data[i - period + 1 : i + 1])
        return out

    @staticmethod
    def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        n   = len(close)
        tr  = np.full(n, float("nan"))
        atr = np.full(n, float("nan"))
        for i in range(1, n):
            tr[i] = max(high[i] - low[i],
                        abs(high[i] - close[i - 1]),
                        abs(low[i]  - close[i - 1]))
        if n > period:
            atr[period] = np.nanmean(tr[1:period + 1])
            for i in range(period + 1, n):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr

    @staticmethod
    def rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
        n   = len(close)
        out = np.full(n, float("nan"))
        if n < period + 1:
            return out
        deltas = np.diff(close)
        gains  = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)
        avg_g  = np.mean(gains[:period])
        avg_l  = np.mean(losses[:period])
        for i in range(period, n - 1):
            avg_g = (avg_g * (period - 1) + gains[i]) / period
            avg_l = (avg_l * (period - 1) + losses[i]) / period
            rs    = avg_g / avg_l if avg_l > 0 else 1e9
            out[i + 1] = 100.0 - 100.0 / (1 + rs)
        return out

    @staticmethod
    def macd(close: np.ndarray, fast: int = 12, slow: int = 26,
             signal: int = 9) -> tuple:
        ema_f  = TechnicalSignals.ema(close, fast)
        ema_s  = TechnicalSignals.ema(close, slow)
        macd_l = ema_f - ema_s
        sig_l  = TechnicalSignals.ema(macd_l, signal)
        hist   = macd_l - sig_l
        return macd_l, sig_l, hist

    @staticmethod
    def bollinger_bands(close: np.ndarray, period: int = 20,
                        num_std: float = 2.0) -> tuple:
        mid = TechnicalSignals.sma(close, period)
        std = np.full(len(close), float("nan"))
        for i in range(period - 1, len(close)):
            std[i] = np.std(close[i - period + 1 : i + 1], ddof=0)
        upper = mid + num_std * std
        lower = mid - num_std * std
        return upper, mid, lower

    @staticmethod
    def vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             volume: np.ndarray) -> np.ndarray:
        tp  = (high + low + close) / 3.0
        cum_tp_vol  = np.cumsum(tp * volume)
        cum_vol     = np.cumsum(volume)
        return np.where(cum_vol > 0, cum_tp_vol / cum_vol, tp)

    @staticmethod
    def supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                   period: int = 10, multiplier: float = 3.0) -> tuple:
        """Returns (supertrend_line, trend_direction +1/-1)."""
        n   = len(close)
        atr = TechnicalSignals.atr(high, low, close, period)
        mid = (high + low) / 2.0
        bu  = mid + multiplier * atr   # basic upper
        bl  = mid - multiplier * atr   # basic lower
        fu  = bu.copy()
        fl  = bl.copy()
        trend = np.ones(n)
        for i in range(1, n):
            fu[i] = bu[i] if (bu[i] < fu[i-1] or close[i-1] > fu[i-1]) else fu[i-1]
            fl[i] = bl[i] if (bl[i] > fl[i-1] or close[i-1] < fl[i-1]) else fl[i-1]
            if trend[i-1] == 1:
                trend[i] =  1 if close[i] >= fl[i] else -1
            else:
                trend[i] = -1 if close[i] <= fu[i] else  1
        st = np.where(trend == 1, fl, fu)
        return st, trend


# ─────────────────────────────────────────────
#  Backtest Engine
# ─────────────────────────────────────────────

def _load_costs_net_pnl():
    """
    Lazily resolve the optional ``engine.india_costs.net_pnl`` transaction-cost
    hook (owned by a separate workstream). Returns None when the module is
    absent, unimportable, or exposes no callable ``net_pnl``.
    """
    try:
        from engine import india_costs  # type: ignore  # optional module
    except Exception:
        return None
    fn = getattr(india_costs, "net_pnl", None)
    return fn if callable(fn) else None


def _apply_cost_hook(costs_fn, fallback_pnl: float, **ctx) -> tuple:
    """
    Call the india_costs hook for a net-of-costs PnL. Any failure (bad
    signature, exception inside the hook) silently falls back to the gross
    value, preserving pre-hook behaviour exactly. Returns (pnl, hook_applied).
    """
    if costs_fn is None:
        return fallback_pnl, False
    try:
        return float(costs_fn(fallback_pnl, **ctx)), True
    except TypeError:
        try:
            return float(costs_fn(fallback_pnl)), True
        except Exception:
            return fallback_pnl, False
    except Exception:
        return fallback_pnl, False


class ZeroBacktestEngine:
    """
    ZERO's own walk-forward backtesting engine.
    Accepts OHLCV bars and a signal function, runs simulated paper trades,
    and returns comprehensive performance analytics.

    Design principles (Nautilus-inspired):
    - Same signal logic used in live → zero research-to-live divergence.
    - Walk-forward validation: in-sample train → out-of-sample test.
    - Commission + slippage modelling.
    - No lookahead bias: signals computed from strictly past bars.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_pct:  float = 0.0003,   # 0.03% per side (NSE standard)
        slippage_bps:    float = 0.5,
        lot_size:        float = 1.0,
        max_position:    int   = 1,
    ):
        self.initial_capital = initial_capital
        self.commission_pct  = commission_pct
        self.slippage_bps    = slippage_bps
        self.lot_size        = lot_size
        self.max_position    = max_position

    def run(
        self,
        bars: List[Dict],   # [{date, open, high, low, close, volume}, ...]
        signal_fn,          # fn(index, bars) → "BUY" | "SELL" | "EXIT" | None
        walk_forward: bool = True,
        train_frac:   float = 0.7,
        embargo:      int   = 0,
    ) -> Dict:
        """
        Run a backtest over the provided bars.
        signal_fn receives (bar_index: int, bars: List[Dict]) and returns a signal string.
        Returns performance report dict.

        `embargo` > 0 purges that many bars from the END of the training
        partition (purged K-fold style leakage guard). The test partition is
        unchanged; with embargo=0 (default) behaviour is identical to before.
        """
        if not bars or len(bars) < 10:
            return {"error": "Insufficient bars for backtesting (min 10)"}

        # Optional India transaction-cost hook (engine.india_costs, separate
        # workstream). None when the module is absent or exposes no net_pnl.
        costs_fn = _load_costs_net_pnl()
        cost_hit = False

        # Partition into train / test
        n_total = len(bars)
        if walk_forward:
            n_train = max(5, int(n_total * train_frac))
            n_purge = min(max(0, int(embargo)), max(0, n_train - 5))
            test_bars  = bars[n_train:]
            train_bars = bars[:n_train - n_purge]
        else:
            test_bars  = bars
            train_bars = bars

        equity  = [self.initial_capital]
        pnl_lst = []
        trades  = []
        position = 0.0
        entry_px = 0.0

        slip_mult = 1.0 + self.slippage_bps / 10_000

        all_bars = test_bars
        for i in range(1, len(all_bars)):
            bar     = all_bars[i]
            prev    = all_bars[i - 1]
            close   = float(bar.get("close", 0))
            open_   = float(bar.get("open", 0))

            # Signal (look-back only — no future data)
            sig = signal_fn(i, all_bars)

            current_equity = equity[-1]

            if sig == "BUY" and position == 0:
                fill_px = round(close * slip_mult, 2)
                comm    = fill_px * self.lot_size * self.commission_pct
                position = self.lot_size
                entry_px = fill_px
                current_equity -= comm
                trades.append({"type": "BUY", "price": fill_px, "date": bar.get("date", ""), "comm": comm})

            elif sig in ("SELL", "EXIT") and position > 0:
                fill_px = round(close / slip_mult, 2)
                comm    = fill_px * position * self.commission_pct
                raw_pnl = (fill_px - entry_px) * position
                net_pnl = raw_pnl - comm
                net_pnl, hit = _apply_cost_hook(costs_fn, net_pnl,
                                                entry_price=entry_px, exit_price=fill_px,
                                                qty=abs(position), side="LONG_EXIT",
                                                date=bar.get("date", ""))
                cost_hit = cost_hit or hit
                pnl_lst.append(net_pnl)
                current_equity += net_pnl - comm
                trades.append({"type": "SELL", "price": fill_px, "date": bar.get("date", ""),
                               "pnl": round(net_pnl, 2), "gross_pnl": round(raw_pnl, 2), "comm": comm})
                position = 0.0

            elif sig == "SHORT" and position == 0:
                fill_px = round(close / slip_mult, 2)
                comm    = fill_px * self.lot_size * self.commission_pct
                position = -self.lot_size
                entry_px = fill_px
                current_equity -= comm
                trades.append({"type": "SHORT", "price": fill_px, "date": bar.get("date", ""), "comm": comm})

            elif sig in ("COVER", "EXIT") and position < 0:
                fill_px = round(close * slip_mult, 2)
                comm    = fill_px * abs(position) * self.commission_pct
                raw_pnl = (entry_px - fill_px) * abs(position)
                net_pnl = raw_pnl - comm
                net_pnl, hit = _apply_cost_hook(costs_fn, net_pnl,
                                                entry_price=entry_px, exit_price=fill_px,
                                                qty=abs(position), side="SHORT_EXIT",
                                                date=bar.get("date", ""))
                cost_hit = cost_hit or hit
                pnl_lst.append(net_pnl)
                current_equity += net_pnl - comm
                trades.append({"type": "COVER", "price": fill_px, "date": bar.get("date", ""),
                               "pnl": round(net_pnl, 2), "gross_pnl": round(raw_pnl, 2), "comm": comm})
                position = 0.0

            # Mark-to-market open position
            if position > 0:
                current_equity += (close - prev.get("close", close)) * position
            elif position < 0:
                current_equity += (prev.get("close", close) - close) * abs(position)

            equity.append(current_equity)

        eq_arr = np.array(equity, dtype=float)
        report = PerformanceAnalytics.full_report(eq_arr, pnl_lst)
        report.update({
            "bars_tested":    len(all_bars),
            "train_bars":     len(train_bars) if walk_forward else 0,
            "initial_capital": self.initial_capital,
            "trades":         trades[-20:],  # last 20 for display
            "walk_forward":   walk_forward,
            "embargo":        int(embargo),
            "cost_hook":      "india_costs" if cost_hit else None,
        })
        return report

    def run_strategy_suite(self, bars: List[Dict]) -> Dict[str, Dict]:
        """
        Run all built-in signal generators and return ranked results.
        """
        if not bars:
            return {}

        closes  = np.array([float(b.get("close", 0)) for b in bars])
        highs   = np.array([float(b.get("high", 0)) for b in bars])
        lows    = np.array([float(b.get("low", 0)) for b in bars])
        volumes = np.array([float(b.get("volume", 1)) for b in bars])
        atr_arr = TechnicalSignals.atr(highs, lows, closes, 14)
        rsi_arr = TechnicalSignals.rsi(closes, 14)
        ema20   = TechnicalSignals.ema(closes, 20)
        ema50   = TechnicalSignals.ema(closes, 50)
        _, _, hist = TechnicalSignals.macd(closes)

        results = {}

        # ── Strategy 1: EMA Crossover ──────────────────────────────
        def ema_signal(i, bs):
            if i < 50 or math.isnan(ema20[i]) or math.isnan(ema50[i]):
                return None
            if ema20[i] > ema50[i] and ema20[i-1] <= ema50[i-1]:
                return "BUY"
            if ema20[i] < ema50[i] and ema20[i-1] >= ema50[i-1]:
                return "SELL"
            return None

        results["EMA Crossover (20/50)"] = self.run(bars, ema_signal)

        # ── Strategy 2: RSI Mean Reversion ────────────────────────
        def rsi_signal(i, bs):
            if i < 15 or math.isnan(rsi_arr[i]):
                return None
            if rsi_arr[i] < 30:
                return "BUY"
            if rsi_arr[i] > 70:
                return "SELL"
            return None

        results["RSI Mean Reversion (30/70)"] = self.run(bars, rsi_signal)

        # ── Strategy 3: MACD Histogram ────────────────────────────
        def macd_signal(i, bs):
            if i < 27 or math.isnan(hist[i]) or math.isnan(hist[i-1]):
                return None
            if hist[i] > 0 and hist[i-1] <= 0:
                return "BUY"
            if hist[i] < 0 and hist[i-1] >= 0:
                return "SELL"
            return None

        results["MACD Histogram Crossover"] = self.run(bars, macd_signal)

        # ── Strategy 4: Breakout above prev High ──────────────────
        def breakout_signal(i, bs):
            if i < 2:
                return None
            prev_high = float(bs[i-1].get("high", 0))
            c = float(bs[i].get("close", 0))
            prev_c = float(bs[i-1].get("close", 0))
            if c > prev_high and prev_c <= prev_high:
                return "BUY"
            if math.isnan(atr_arr[i]):
                return None
            if c < float(bs[i-1].get("low", 0)):
                return "SELL"
            return None

        results["Breakout (Above Prev High)"] = self.run(bars, breakout_signal)

        # Rank by Sharpe
        ranked = dict(sorted(results.items(),
                              key=lambda x: x[1].get("sharpe_ratio", -999),
                              reverse=True))
        return ranked


# ─────────────────────────────────────────────
#  Multi-Venue Backtest Router (Nautilus multi-venue pattern)
# ─────────────────────────────────────────────

class MultiVenueBacktestRouter:
    """
    Simulates order routing across multiple venues (NSE, BSE, MCX).
    Each venue has its own fill probability, latency, and liquidity model.
    """

    VENUES = {
        "NSE":   {"fill_prob": 0.97, "latency_ms": 5,  "liquidity_mult": 1.0},
        "BSE":   {"fill_prob": 0.94, "latency_ms": 8,  "liquidity_mult": 0.85},
        "MCX":   {"fill_prob": 0.90, "latency_ms": 12, "liquidity_mult": 0.70},
        "GIFT":  {"fill_prob": 0.85, "latency_ms": 15, "liquidity_mult": 0.60},
    }

    @classmethod
    def best_venue(cls, symbol: str, qty: float, order_type: str = "MARKET") -> Dict:
        """Return the venue with the best execution probability for this order."""
        # Simple model: NSE always best for equities, MCX for commodities
        if any(x in symbol.upper() for x in ["GOLD", "SILVER", "CRUDE", "COPPER"]):
            return {"venue": "MCX", **cls.VENUES["MCX"]}
        if "GIFT" in symbol.upper():
            return {"venue": "GIFT", **cls.VENUES["GIFT"]}
        return {"venue": "NSE", **cls.VENUES["NSE"]}

    @classmethod
    def route_order(cls, symbol: str, qty: float, price: float,
                    venue_override: Optional[str] = None) -> Dict:
        """Simulate multi-venue order routing and return fill result."""
        venue_name = venue_override or cls.best_venue(symbol, qty)["venue"]
        v = cls.VENUES.get(venue_name, cls.VENUES["NSE"])
        import random
        filled = random.random() < v["fill_prob"]
        return {
            "venue":       venue_name,
            "filled":      filled,
            "latency_ms":  v["latency_ms"],
            "fill_price":  round(price * (1 + 0.0001), 2) if filled else None,
            "reason":      "FILLED" if filled else "NO_LIQUIDITY",
        }
