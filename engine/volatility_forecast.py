"""
Volatility forecasting for the ZERO prediction engine.

Replaces the hardcoded ``iv = 15.0`` in ``engine/prediction_matrix.py`` with a
real, degradable volatility stack::

    EGARCH(1,1) -> GJR-GARCH(1,1) -> EWMA(lambda=0.94) -> ATR% fallback

Only numpy and pandas are hard dependencies. ``arch`` is lazily imported and
every model fit is wrapped in try/except, so the module always returns a
usable annualized IV and 1-day sigma — even fully offline with <30 rows of
history. Importable without Streamlit and without network access.

Entry point: ``get_session_iv(hist, india_vix)`` — runs the forecaster,
blends the model IV with India VIX, and clamps to sane bounds
(``IV_MIN``..``IV_MAX``).
"""
from __future__ import annotations

import math
import os
import warnings

import numpy as np
import pandas as pd

# ── Tunables (override via environment) ──────────────────────────────────────
TRADING_DAYS = int(os.environ.get("ZERO_VOL_TRADING_DAYS", "252"))
EWMA_LAMBDA = float(os.environ.get("ZERO_VOL_EWMA_LAMBDA", "0.94"))  # RiskMetrics
MIN_ROWS_MODEL = int(os.environ.get("ZERO_VOL_MIN_ROWS", "30"))
IV_MIN = float(os.environ.get("ZERO_IV_MIN", "5.0"))
IV_MAX = float(os.environ.get("ZERO_IV_MAX", "80.0"))
DEFAULT_IV = float(os.environ.get("ZERO_DEFAULT_IV", "15.0"))
VIX_WEIGHT = float(os.environ.get("ZERO_VIX_WEIGHT", "0.6"))
MAX_SANE_SIGMA_1D_PCT = float(os.environ.get("ZERO_VOL_MAX_SIGMA_1D", "25.0"))

__all__ = ["VolatilityForecaster", "blend_india_vix", "get_session_iv"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_number(x) -> float | None:
    """Coerce to a finite float, else None (robust to None/NaN/inf/junk)."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _extract_column(hist: pd.DataFrame | None, name: str) -> np.ndarray:
    """Pull a column out of an OHLC frame as a finite float array.

    Tolerates yfinance MultiIndex columns (('Close', '^NSEI')), duplicate
    columns returning a DataFrame, and case variants (Close/close).
    """
    if hist is None or not hasattr(hist, "columns"):
        return np.empty(0)
    lookup: dict[str, object] = {}
    for c in hist.columns:
        key = c[0] if isinstance(c, tuple) else c
        lookup.setdefault(str(key).strip().lower(), c)
    actual = lookup.get(name.lower())
    if actual is None:
        return np.empty(0)
    series = hist[actual]
    if isinstance(series, pd.DataFrame):  # duplicate column labels
        series = series.iloc[:, 0]
    try:
        vals = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    except (TypeError, ValueError):
        return np.empty(0)
    return vals[np.isfinite(vals)]


def _log_returns(closes: np.ndarray) -> np.ndarray:
    closes = closes[np.isfinite(closes) & (closes > 0)]
    if closes.size < 2:
        return np.empty(0)
    rets = np.diff(np.log(closes))
    return rets[np.isfinite(rets)]


def _mean_true_range_pct(hist: pd.DataFrame | None) -> float | None:
    """Mean True Range as a percentage of close — a daily-sigma proxy."""
    if hist is None or len(hist) == 0:
        return None
    high = _extract_column(hist, "High")
    low = _extract_column(hist, "Low")
    close = _extract_column(hist, "Close")
    n = min(high.size, low.size, close.size)
    if n == 0:
        return None
    high, low, close = high[-n:], low[-n:], close[-n:]
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]  # first row: TR reduces to high - low
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        tr_pct = np.where(close > 0, tr / close * 100.0, np.nan)
    tr_pct = tr_pct[np.isfinite(tr_pct)]
    if tr_pct.size == 0:
        return None
    val = float(np.mean(tr_pct))
    return val if val > 0 else None


# ── Forecaster ───────────────────────────────────────────────────────────────

class VolatilityForecaster:
    """
    Fits the best available volatility model to a daily OHLC history.

    ``forecast(hist)`` returns::

        {'iv_annualized': float,   # annualized vol, percent (e.g. 14.2)
         'sigma_1d_pct': float,    # 1-day sigma, percent of price
         'method': 'egarch' | 'gjr_garch' | 'ewma' | 'atr_fallback',
         'n_obs': int}             # number of log returns used
    """

    def __init__(
        self,
        ewma_lambda: float = EWMA_LAMBDA,
        min_rows: int = MIN_ROWS_MODEL,
    ) -> None:
        self.ewma_lambda = float(ewma_lambda)
        self.min_rows = int(min_rows)

    # ---- public ------------------------------------------------------

    def forecast(self, hist: pd.DataFrame) -> dict:
        closes = _extract_column(hist, "Close")
        rets = _log_returns(closes)
        n_obs = int(rets.size)

        if hist is None or len(hist) < self.min_rows or n_obs < self.min_rows - 1:
            return self._atr_result(hist, n_obs)

        result = self._try_arch(rets, n_obs)
        if result is not None:
            return result

        try:
            return self._ewma_result(rets, n_obs)
        except Exception:
            return self._atr_result(hist, n_obs)

    # ---- model chain ---------------------------------------------------

    def _try_arch(self, rets: np.ndarray, n_obs: int) -> dict | None:
        """EGARCH(1,1), then GJR-GARCH(1,1). None if arch missing/fits fail."""
        try:
            from arch import arch_model  # lazy import: optional dependency
        except Exception:
            return None

        rets_pct = rets * 100.0  # arch convention: work in percent units
        specs = (
            # EGARCH with the asymmetry term (o=1) — the leverage effect is
            # the whole point of EGARCH; still colloquially EGARCH(1,1).
            ("egarch", {"vol": "EGARCH", "p": 1, "o": 1, "q": 1}),
            ("gjr_garch", {"vol": "GARCH", "p": 1, "o": 1, "q": 1}),
        )
        for method, vol_kwargs in specs:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    model = arch_model(
                        rets_pct,
                        mean="Constant",
                        dist="normal",
                        rescale=False,
                        **vol_kwargs,
                    )
                    res = model.fit(disp="off", show_warning=False)
                    fcast = res.forecast(horizon=1, reindex=False)
                var_col = fcast.variance.iloc[:, 0].dropna()
                var1 = float(var_col.iloc[-1])  # 1-step-ahead variance, pct^2
            except Exception:
                continue
            if not (math.isfinite(var1) and var1 > 0):
                continue
            sigma_1d_pct = math.sqrt(var1)
            if not (0.01 <= sigma_1d_pct <= MAX_SANE_SIGMA_1D_PCT):
                continue  # implausible fit — degrade one level down
            iv_ann = sigma_1d_pct * math.sqrt(TRADING_DAYS)
            return {
                "iv_annualized": iv_ann,
                "sigma_1d_pct": sigma_1d_pct,
                "method": method,
                "n_obs": n_obs,
            }
        return None

    def _ewma_result(self, rets: np.ndarray, n_obs: int) -> dict:
        """RiskMetrics EWMA recursion: var_t = lam*var_{t-1} + (1-lam)*r^2."""
        lam = min(max(self.ewma_lambda, 0.5), 0.999)
        var = float(np.mean(rets ** 2)) if rets.size else 0.0
        for r in rets:
            var = lam * var + (1.0 - lam) * float(r * r)
        if not (math.isfinite(var) and var > 0):
            raise ValueError("degenerate EWMA variance")
        sigma_1d_pct = math.sqrt(var) * 100.0  # returns are decimals here
        iv_ann = sigma_1d_pct * math.sqrt(TRADING_DAYS)
        return {
            "iv_annualized": iv_ann,
            "sigma_1d_pct": sigma_1d_pct,
            "method": "ewma",
            "n_obs": n_obs,
        }

    def _atr_result(self, hist: pd.DataFrame | None, n_obs: int) -> dict:
        """Mean True Range % as the daily-sigma proxy (<min_rows rows, or
        every model above failed)."""
        sigma_1d_pct = _mean_true_range_pct(hist)
        if sigma_1d_pct is None:
            sigma_1d_pct = DEFAULT_IV / math.sqrt(TRADING_DAYS)
        iv_ann = sigma_1d_pct * math.sqrt(TRADING_DAYS)
        return {
            "iv_annualized": iv_ann,
            "sigma_1d_pct": sigma_1d_pct,
            "method": "atr_fallback",
            "n_obs": n_obs,
        }


# ── Blending + session entry point ───────────────────────────────────────────

def blend_india_vix(
    india_vix: float | None,
    model_iv: float,
    vix_weight: float = 0.6,
) -> float:
    """
    Weighted blend of the implied-vol proxy (India VIX) and the model
    forecast. Both inputs are annualized percents. Robust to None/NaN on
    either side; returns DEFAULT_IV if both are unusable.
    """
    w = _clean_number(vix_weight)
    w = 0.6 if w is None else min(max(w, 0.0), 1.0)
    vix = _clean_number(india_vix)
    mdl = _clean_number(model_iv)
    if vix is None and mdl is None:
        return DEFAULT_IV
    if vix is None:
        return mdl
    if mdl is None:
        return vix
    return w * vix + (1.0 - w) * mdl


def get_session_iv(
    hist: pd.DataFrame,
    india_vix: float | None = None,
) -> dict:
    """
    Single entry point for the orchestrator.

    Runs ``VolatilityForecaster`` on the OHLC history, blends the model IV
    with India VIX (weight ``VIX_WEIGHT``), and clamps the result to
    [``IV_MIN``, ``IV_MAX``]. ``sigma_1d_pct`` is derived from the final
    blended IV so the two fields are always mutually consistent.

    Returns::

        {'iv': float,             # blended, clamped annualized IV (percent)
         'sigma_1d_pct': float,   # implied 1-day sigma, percent of price
         'method': str,           # which model produced the forecast
         'vix_used': float|None}  # the VIX value blended in, or None
    """
    fc = VolatilityForecaster().forecast(hist)
    vix_clean = _clean_number(india_vix)
    blended = blend_india_vix(vix_clean, fc.get("iv_annualized"), VIX_WEIGHT)
    iv = min(max(blended, IV_MIN), IV_MAX)
    sigma_1d = iv / math.sqrt(TRADING_DAYS)
    return {
        "iv": round(iv, 2),
        "sigma_1d_pct": round(sigma_1d, 4),
        "method": str(fc.get("method", "atr_fallback")),
        "vix_used": vix_clean,
    }


if __name__ == "__main__":
    # Offline smoke test on synthetic OHLC (no network, no arch required).
    rng = np.random.default_rng(7)
    n = 120
    rets = rng.normal(0.0, 0.01, n)
    close = 24000.0 * np.exp(np.cumsum(rets))
    span = np.abs(rng.normal(0.008, 0.003, n)) * close
    demo = pd.DataFrame(
        {
            "Open": close * (1.0 - rets / 2.0),
            "High": close + span / 2.0,
            "Low": close - span / 2.0,
            "Close": close,
        }
    )
    print(VolatilityForecaster().forecast(demo))
    print(get_session_iv(demo, india_vix=13.5))
    print(get_session_iv(demo.iloc[:10], india_vix=None))  # ATR fallback path
