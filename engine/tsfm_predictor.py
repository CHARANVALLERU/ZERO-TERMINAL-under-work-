"""
ZERO Time-Series Foundation Model (TSFM) Predictor
==================================================

OPTIONAL third ensemble leg for ZERO's daily OHLC envelope stack
(geometric ATR-envelope + adaptive calibrator + XGBoost).  Provides a
probabilistic close forecast (P10/P50/P90) plus a high/low envelope from a
time-series foundation model:

    1. chronos2  — Amazon Chronos-2 (covariate-informed; preferred)
    2. kronos    — Kronos finance K-line foundation model (HF + local repo)
    3. timesfm   — Google TimesFM 2.5 (close quantiles only)
    4. none      — hard no-op

No-op safety contract
---------------------
* Core deps are only numpy / pandas.  chronos-forecasting / torch / Kronos /
  timesfm are OPTIONAL and are imported lazily inside try/except.
* This module always imports cleanly — even with none of the optional deps
  installed, without Streamlit, and with no network access.  Model weights
  are downloaded lazily on the FIRST forecast call (never at import time),
  fully wrapped so any failure degrades to status 'unavailable' / 'error'.
* No public method ever raises.

Environment overrides (all optional)
------------------------------------
TSFM_BACKEND        default backend: auto|chronos2|kronos|timesfm|none (auto)
TSFM_DEVICE         torch device string (cpu)
TSFM_MAX_CONTEXT    max context bars for chronos/timesfm (1024)
TSFM_MIN_CONTEXT    minimum bars required to attempt a forecast (16)
TSFM_OFFSET_WINDOW  window for the high/low offset heuristic (20)
TSFM_FLAT_EPS_PCT   |drift| below this fraction => direction 'flat' (0.001)
CHRONOS2_MODEL_ID   HuggingFace model id (amazon/chronos-2)
KRONOS_REPO_PATH    local clone of https://github.com/shiyu-coder/Kronos
KRONOS_MODEL_ID     (NeoQuasar/Kronos-small)
KRONOS_TOKENIZER_ID (NeoQuasar/Kronos-Tokenizer-base)
KRONOS_MAX_CONTEXT  (512)
KRONOS_SAMPLE_COUNT sampled paths for empirical quantiles, >=4 (8)

Output schema of forecast_ohlc()
--------------------------------
{
    'status':   'forecasted' | 'unavailable' | 'error',
    'backend':  'chronos2' | 'kronos' | 'timesfm' | None,
    'close':    {'p10': float|None, 'p50': float|None, 'p90': float|None},
    'high_p90': float | None,          # 90th-pct high envelope
    'low_p10':  float | None,          # 10th-pct low envelope
    'horizon':  int,
    'n_context': int,
    # extras (informational, safe to ignore):
    'error':     str,                  # only when status == 'error'
    'direction': 'up' | 'down' | 'flat',
    'last_close': float,
}

Integration (engine/orchestrator — prediction_matrix)
-----------------------------------------------------
    from engine.tsfm_predictor import get_forecaster
    tsfm_fc = get_forecaster().forecast_ohlc(
        hist_df, horizon=1,
        covariates={'gift_premium': gift_premium, 'vix': vix,
                    'pcr': pcr, 'sentiment': sentiment_score},
    )
    blend_signals = get_forecaster().compare_vs_point(tsfm_fc, point_pred)

Optional pip packages (comment into requirements.txt when enabling):
    # chronos-forecasting>=2.0   # Chronos-2 leg (pulls torch)
    # torch>=2.2                 # backend for Chronos-2 / Kronos
    # timesfm[torch]>=2.0        # TimesFM leg (optional)
    # Kronos: git clone shiyu-coder/Kronos + its requirements; set KRONOS_REPO_PATH
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np
import pandas as pd


# ── Env-overridable constants ────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


TSFM_BACKEND = os.environ.get("TSFM_BACKEND", "auto").strip().lower()
TSFM_DEVICE = os.environ.get("TSFM_DEVICE", "cpu").strip() or "cpu"
TSFM_MAX_CONTEXT = _env_int("TSFM_MAX_CONTEXT", 1024)
TSFM_MIN_CONTEXT = _env_int("TSFM_MIN_CONTEXT", 16)
TSFM_OFFSET_WINDOW = _env_int("TSFM_OFFSET_WINDOW", 20)
TSFM_FLAT_EPS_PCT = _env_float("TSFM_FLAT_EPS_PCT", 0.001)

CHRONOS2_MODEL_ID = os.environ.get("CHRONOS2_MODEL_ID", "amazon/chronos-2")

KRONOS_REPO_PATH = os.environ.get("KRONOS_REPO_PATH", "").strip()
KRONOS_MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base")
KRONOS_MAX_CONTEXT = _env_int("KRONOS_MAX_CONTEXT", 512)
KRONOS_SAMPLE_COUNT = max(4, _env_int("KRONOS_SAMPLE_COUNT", 8))

QUANTILE_LEVELS = (0.1, 0.5, 0.9)
VALID_BACKENDS = ("auto", "chronos2", "kronos", "timesfm", "none")
AUTO_BACKEND_PRIORITY = ("chronos2", "kronos", "timesfm")

# ── Module-level singleton caches ────────────────────────────────────────────
# Loaded weights are shared across every TSFMForecaster instance so repeated
# instantiation is cheap.  _LOAD_FAILED avoids retrying a broken backend for
# the rest of the process (e.g. no network for the HF download).
_MODEL_CACHE: dict = {}
_LOAD_FAILED: set = set()
_FORECASTER_CACHE: dict = {}


def _r(value, nd: int = 2):
    """None-safe float rounding for report fields."""
    try:
        if value is None:
            return None
        return round(float(value), nd)
    except (TypeError, ValueError):
        return None


class TSFMForecaster:
    """Optional TSFM ensemble leg with lazy backend loading.

    backend: 'auto' (chronos2 → kronos → timesfm → none), or pin one of
    'chronos2' | 'kronos' | 'timesfm' | 'none'.  An unknown value coerces to
    'none' (hard no-op).  When backend == 'auto', the TSFM_BACKEND env var
    overrides the default chain.

    Model weights are NOT loaded here — loading happens on the first
    forecast_ohlc() call and is cached module-wide.
    """

    def __init__(self, backend: str = "auto", device: str | None = None):
        backend = (backend or "auto").strip().lower()
        if backend == "auto" and TSFM_BACKEND in VALID_BACKENDS:
            backend = TSFM_BACKEND  # env override of the default chain
        if backend not in VALID_BACKENDS:
            backend = "none"
        self.backend = backend
        self.device = (device or TSFM_DEVICE or "cpu").strip()
        self._resolved: str | None = None  # actual backend after first lazy load
        self._last_error: str | None = None

    # ── Availability / lazy loading ──────────────────────────────────────

    @staticmethod
    def _probe(backend: str) -> bool:
        """Cheap dependency probe — find_spec only, never executes heavy
        imports, never touches the network, never downloads weights."""
        try:
            if backend == "chronos2":
                return importlib.util.find_spec("chronos") is not None
            if backend == "timesfm":
                return importlib.util.find_spec("timesfm") is not None
            if backend == "kronos":
                # Vendored engine.kronos package first (no env var needed).
                try:
                    if importlib.util.find_spec("engine.kronos") is not None:
                        return True
                except Exception:
                    pass
                # Fallback: Kronos runs from a local repo clone on sys.path.
                return bool(KRONOS_REPO_PATH) and os.path.isdir(KRONOS_REPO_PATH)
        except Exception:
            return False
        return False

    def _load(self, backend: str):
        """Lazy-load and cache model weights.  May hit HuggingFace on first
        call — callers wrap this in try/except; never invoked at import time."""
        if backend in _MODEL_CACHE:
            return _MODEL_CACHE[backend]
        if backend == "chronos2":
            obj = self._load_chronos2()
        elif backend == "kronos":
            obj = self._load_kronos()
        elif backend == "timesfm":
            obj = self._load_timesfm()
        else:
            raise ValueError(f"no loader for backend {backend!r}")
        _MODEL_CACHE[backend] = obj
        return obj

    def _load_chronos2(self):
        from chronos import Chronos2Pipeline  # lazy heavy import
        return Chronos2Pipeline.from_pretrained(CHRONOS2_MODEL_ID, device_map=self.device)

    def _load_kronos(self):
        try:
            # Vendored package (engine/kronos/) first — no env var needed.
            from engine.kronos import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
        except ImportError:
            # Fallback: external repo clone on sys.path via KRONOS_REPO_PATH.
            if KRONOS_REPO_PATH and KRONOS_REPO_PATH not in sys.path:
                sys.path.insert(0, KRONOS_REPO_PATH)
            from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
        tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_ID)
        model = Kronos.from_pretrained(KRONOS_MODEL_ID)
        return KronosPredictor(model, tokenizer, device=self.device,
                               max_context=KRONOS_MAX_CONTEXT)

    def _load_timesfm(self):
        import timesfm  # lazy heavy import
        model = timesfm.TimesFM_2p5_200M_torch()
        try:
            model.compile(timesfm.ForecastConfig(max_context=TSFM_MAX_CONTEXT))
        except Exception:
            try:
                model.compile()  # older API: no ForecastConfig
            except Exception:
                pass  # some versions self-compile on first forecast
        return model

    def _ensure_backend(self) -> str | None:
        """Resolve + lazy-load the first working candidate backend."""
        if self._resolved is not None:
            return None if self._resolved == "none" else self._resolved
        if self.backend == "none":
            self._resolved = "none"
            return None
        candidates = AUTO_BACKEND_PRIORITY if self.backend == "auto" else (self.backend,)
        for cand in candidates:
            if cand in _LOAD_FAILED:
                continue
            if not self._probe(cand):
                continue
            try:
                self._load(cand)
                self._resolved = cand
                return cand
            except Exception as exc:  # download/init failure → try next leg
                _LOAD_FAILED.add(cand)
                self._last_error = f"{cand}: {exc}"
        self._resolved = "none"
        return None

    def is_available(self) -> bool:
        """True when at least one candidate backend's deps are present.
        Cheap probe only — never downloads or loads model weights."""
        if self._resolved is not None:
            return self._resolved != "none"
        if self.backend == "none":
            return False
        candidates = AUTO_BACKEND_PRIORITY if self.backend == "auto" else (self.backend,)
        return any(self._probe(c) for c in candidates)

    # ── Public forecast API ──────────────────────────────────────────────

    def forecast_ohlc(self, hist_df: pd.DataFrame, horizon: int = 1,
                      covariates: dict | None = None) -> dict:
        """Probabilistic OHLC envelope from the first available TSFM backend.

        hist_df: columns open/high/low/close (+optional volume), most-recent
        LAST.  Capitalized yfinance columns and MultiIndex columns are also
        accepted.  covariates: optional dict of scalars or per-bar series
        (e.g. {'gift_premium': …, 'vix': …, 'pcr': …, 'sentiment': …}) used
        by the Chronos-2 covariate path.

        Returns the schema documented in the module docstring; NEVER raises.
        """
        try:
            horizon = max(1, int(horizon))
        except Exception:
            horizon = 1
        try:
            df = self._normalize_hist(hist_df)
            if df is None or len(df) < TSFM_MIN_CONTEXT:
                n = 0 if df is None else len(df)
                return self._result("error", None, horizon, n,
                                    error=f"insufficient context ({n} < {TSFM_MIN_CONTEXT})")

            backend = self._ensure_backend()
            if backend is None:
                if self._last_error:
                    return self._result("error", None, horizon, len(df), error=self._last_error)
                return self._result("unavailable", None, horizon, len(df))

            ctx = self._context_slice(df, backend)
            if backend == "chronos2":
                q = self._forecast_chronos2(ctx, horizon, covariates)
            elif backend == "kronos":
                q = self._forecast_kronos(ctx, horizon)
            else:
                q = self._forecast_timesfm(ctx, horizon)

            close_q = q.get("close") or {}
            p10, p50, p90 = close_q.get("p10"), close_q.get("p50"), close_q.get("p90")
            high_p90, low_p10 = q.get("high_p90"), q.get("low_p10")
            if high_p90 is None or low_p10 is None:
                # HEURISTIC fallback for close-only backends (see _offset_band).
                est_high, est_low = self._offset_band(ctx, p90, p10)
                if high_p90 is None:
                    high_p90 = est_high
                if low_p10 is None:
                    low_p10 = est_low

            last_close = float(ctx["close"].iloc[-1])
            return self._result(
                "forecasted", backend, horizon, len(ctx),
                close={"p10": _r(p10), "p50": _r(p50), "p90": _r(p90)},
                high_p90=_r(high_p90), low_p10=_r(low_p10),
                direction=self._direction(p50, last_close),
                last_close=_r(last_close),
            )
        except Exception as exc:  # absolute no-raise guarantee
            backend = self._resolved if self._resolved not in (None, "none") else None
            return self._result("error", backend, horizon, 0, error=str(exc))

    def compare_vs_point(self, forecast: dict, point_pred: dict) -> dict:
        """Compare a TSFM interval forecast with ZERO's point prediction
        {'pred_open','pred_high','pred_low','pred_close'}.

        Returns ensemble-blending signals:
            close_disagreement_pct : |tsfm_p50 − pred_close| / pred_close × 100
            band_overlap           : do [pred_low,pred_high] and the TSFM
                                     [low_p10,high_p90] envelope intersect?
            tsfm_direction         : 'up' | 'down' | 'flat'
        Unavailable/error forecasts return the neutral default
        {0.0, True, 'flat'} so the ensemble is never penalized by a no-op leg.
        """
        out = {"close_disagreement_pct": 0.0, "band_overlap": True, "tsfm_direction": "flat"}
        if not isinstance(forecast, dict) or forecast.get("status") != "forecasted":
            return out

        close_q = forecast.get("close") or {}
        p50 = close_q.get("p50")
        pred = point_pred or {}
        pred_close = pred.get("pred_close")

        if p50 is not None and isinstance(pred_close, (int, float)) and pred_close > 0:
            out["close_disagreement_pct"] = round(
                abs(float(p50) - float(pred_close)) / float(pred_close) * 100.0, 4)

        t_low = forecast.get("low_p10")
        if t_low is None:
            t_low = close_q.get("p10")
        t_high = forecast.get("high_p90")
        if t_high is None:
            t_high = close_q.get("p90")
        pred_low, pred_high = pred.get("pred_low"), pred.get("pred_high")
        if None not in (pred_low, pred_high, t_low, t_high):
            try:
                out["band_overlap"] = bool(
                    max(float(pred_low), float(t_low)) <= min(float(pred_high), float(t_high)))
            except (TypeError, ValueError):
                pass

        direction = forecast.get("direction")
        if direction in ("up", "down", "flat"):
            out["tsfm_direction"] = direction
        elif p50 is not None and isinstance(pred_close, (int, float)) and pred_close > 0:
            out["tsfm_direction"] = self._direction(p50, pred_close)
        return out

    # ── Input normalization ──────────────────────────────────────────────

    @staticmethod
    def _normalize_hist(hist_df) -> pd.DataFrame | None:
        """Coerce to a clean lowercase-OHLC DataFrame (most-recent-last),
        accepting yfinance-style 'Open/High/Low/Close' and MultiIndex columns."""
        if hist_df is None or not isinstance(hist_df, pd.DataFrame) or hist_df.empty:
            return None
        df = hist_df.copy()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).strip().lower() for c in df.columns]
        needed = ["open", "high", "low", "close"]
        if any(c not in df.columns for c in needed):
            return None
        for c in needed + ["volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=needed)
        df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
        return df if not df.empty else None

    @staticmethod
    def _context_slice(df: pd.DataFrame, backend: str) -> pd.DataFrame:
        limit = KRONOS_MAX_CONTEXT if backend == "kronos" else TSFM_MAX_CONTEXT
        return df.tail(limit)

    @staticmethod
    def _timestamps(df: pd.DataFrame) -> pd.DatetimeIndex:
        """Real timestamps when the index provides them, else synthesized
        business days ending today (foundation models only need spacing)."""
        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) == len(df) \
                and not df.index.hasnans:
            return pd.DatetimeIndex(df.index)
        return pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=len(df))

    @staticmethod
    def _future_timestamps(last_ts: pd.Timestamp, horizon: int) -> pd.DatetimeIndex:
        return pd.bdate_range(start=pd.Timestamp(last_ts) + pd.Timedelta(days=1),
                              periods=horizon)

    # ── Backend: Amazon Chronos-2 (covariate-informed) ───────────────────

    def _forecast_chronos2(self, ctx: pd.DataFrame, horizon: int,
                           covariates: dict | None) -> dict:
        pipe = self._load("chronos2")  # cached by _ensure_backend
        ts = self._timestamps(ctx)
        future_ts = self._future_timestamps(ts[-1], horizon)

        context_df = pd.DataFrame({
            "id": "zero",
            "timestamp": ts,
            "target": ctx["close"].to_numpy(dtype=float),
        })
        future_df = pd.DataFrame({"id": "zero", "timestamp": future_ts})

        # Covariates (gift_premium / vix / pcr / sentiment …): scalars or
        # per-bar series.  Future values repeat the last known observation
        # unless a horizon-length series was supplied.
        for name, value in (covariates or {}).items():
            try:
                col, fut = self._covariate_columns(value, len(ctx), horizon)
            except Exception:
                continue  # unparseable covariate → skip, never fail the leg
            if col is None:
                continue
            context_df[str(name)] = col
            future_df[str(name)] = fut

        kwargs = dict(prediction_length=horizon, quantile_levels=list(QUANTILE_LEVELS),
                      id_column="id", timestamp_column="timestamp", target="target")
        try:
            preds = pipe.predict_df(context_df, future_df=future_df, **kwargs)
        except Exception:
            # API without covariate support → univariate retry.
            preds = pipe.predict_df(context_df[["id", "timestamp", "target"]],
                                    future_df=future_df[["id", "timestamp"]], **kwargs)

        return {"close": self._quantiles_from_prediction(preds),
                "high_p90": None, "low_p10": None}

    @staticmethod
    def _covariate_columns(value, n_ctx: int, horizon: int):
        """Return (context_column, future_column) lists, or (None, None)."""
        if value is None:
            return None, None
        if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
            arr = [float(v) for v in list(value)]
            if len(arr) == n_ctx:
                return arr, [arr[-1]] * horizon
            if len(arr) == horizon:
                return [arr[0]] * n_ctx, arr
            return None, None
        scalar = float(value)
        return [scalar] * n_ctx, [scalar] * horizon

    # ── Backend: Kronos (finance K-line foundation model) ────────────────

    def _forecast_kronos(self, ctx: pd.DataFrame, horizon: int) -> dict:
        predictor = self._load("kronos")  # cached by _ensure_backend
        ts = self._timestamps(ctx)
        future_ts = self._future_timestamps(ts[-1], horizon)
        cols = [c for c in ("open", "high", "low", "close", "volume") if c in ctx.columns]
        kdf = ctx[cols].reset_index(drop=True)

        preds = predictor.predict(
            df=kdf,
            x_timestamp=pd.Series(ts),
            y_timestamp=pd.Series(future_ts),
            pred_len=horizon,
            T=1.0,
            top_p=0.9,
            sample_count=KRONOS_SAMPLE_COUNT,  # >=4 sampled paths → empirical quantiles
            verbose=False,
        )
        arr = self._to_numpy(preds)
        if arr is None:
            raise RuntimeError("kronos predictor returned no array")
        arr = np.asarray(arr, dtype=float)
        if arr.ndim == 2:  # (horizon, features) — single path
            arr = arr[None, :, :]
        if arr.ndim != 3 or arr.shape[0] == 0:
            raise RuntimeError(f"unexpected kronos output shape {arr.shape}")

        step = arr[:, -1, :]  # final horizon step → (sample_count, features)
        feat = {name: step[:, i] for i, name in enumerate(cols) if i < step.shape[1]}
        close_paths = feat.get("close")
        if close_paths is None:  # unknown layout → last feature column is close
            close_paths = step[:, -1]

        close_q = {
            "p10": float(np.percentile(close_paths, 10)),
            "p50": float(np.percentile(close_paths, 50)),
            "p90": float(np.percentile(close_paths, 90)),
        }
        # Envelope from sampled paths: 90th-pct high / 10th-pct low.
        high_p90 = float(np.percentile(feat["high"], 90)) if "high" in feat else None
        low_p10 = float(np.percentile(feat["low"], 10)) if "low" in feat else None
        return {"close": close_q, "high_p90": high_p90, "low_p10": low_p10}

    # ── Backend: Google TimesFM 2.5 ──────────────────────────────────────

    def _forecast_timesfm(self, ctx: pd.DataFrame, horizon: int) -> dict:
        model = self._load("timesfm")  # cached by _ensure_backend
        inputs = [ctx["close"].to_numpy(dtype=float)]
        try:
            point_fc, quantile_fc = model.forecast(horizon=horizon, inputs=inputs)
        except Exception:
            point_fc, quantile_fc = model.forecast(inputs, horizon=horizon)  # alt signature

        q = None
        a = self._to_numpy(quantile_fc)
        if a is not None:
            a = np.asarray(a, dtype=float)
            while a.ndim > 2:
                a = a[0]  # drop batch dim
            step = a[-1] if a.ndim >= 2 else a
            q = self._pick_quantiles(step)
        if q is None or q.get("p50") is None:
            p = self._to_numpy(point_fc)
            val = None
            if p is not None:
                p = np.asarray(p, dtype=float).ravel()
                if p.size:
                    val = float(p[-1])
            q = {"p10": val, "p50": val, "p90": val}
        return {"close": q, "high_p90": None, "low_p10": None}

    # ── Quantile extraction helpers (best-effort across API versions) ────

    def _quantiles_from_prediction(self, preds) -> dict:
        """Extract p10/p50/p90 of the FINAL horizon step from a Chronos-style
        predict() return: DataFrame, tuple/list of tensors, or raw array."""
        if isinstance(preds, pd.DataFrame):
            return self._quantiles_from_frame(preds)
        arr = preds[0] if isinstance(preds, (tuple, list)) and len(preds) else preds
        a = self._to_numpy(arr)
        if a is None:
            return {"p10": None, "p50": None, "p90": None}
        a = np.asarray(a, dtype=float)
        while a.ndim > 2:
            a = a[0]
        step = a[-1] if a.ndim == 2 else a.ravel()
        return self._pick_quantiles(step)

    @staticmethod
    def _quantiles_from_frame(preds: pd.DataFrame) -> dict:
        q = {"p10": None, "p50": None, "p90": None}
        cols = {str(c).lower(): c for c in preds.columns}
        row = preds.iloc[-1]
        names = {
            "p10": ("0.1", "0.10", "q10", "p10", "quantile_0.1"),
            "p50": ("0.5", "0.50", "q50", "p50", "median", "predictions", "mean"),
            "p90": ("0.9", "0.90", "q90", "p90", "quantile_0.9"),
        }
        for key, candidates in names.items():
            for name in candidates:
                if name in cols:
                    try:
                        q[key] = float(row[cols[name]])
                    except (TypeError, ValueError):
                        pass
                    break
        return q

    @staticmethod
    def _pick_quantiles(step) -> dict:
        """Map a 1-D ascending quantile grid to p10/p50/p90.

        Common grids: 3 = [0.1,0.5,0.9]; 9 = deciles 0.1–0.9;
        10/11 = mean + deciles (index 0 skipped).  Unknown grids are assumed
        ascending over [0,1].  Output is sorted to enforce p10 ≤ p50 ≤ p90.
        """
        a = np.asarray(step, dtype=float).ravel()
        a = a[~np.isnan(a)]
        if a.size == 0:
            return {"p10": None, "p50": None, "p90": None}
        if a.size == 1:
            v = float(a[0])
            return {"p10": v, "p50": v, "p90": v}
        grid = {3: (0, 1, 2), 9: (0, 4, 8), 10: (1, 5, 9), 11: (1, 5, 9)}
        if a.size in grid:
            i10, i50, i90 = grid[a.size]
        else:
            n = a.size - 1
            i10, i50, i90 = int(round(0.1 * n)), int(round(0.5 * n)), int(round(0.9 * n))
        vals = sorted(float(a[i]) for i in (i10, i50, i90))
        return {"p10": vals[0], "p50": vals[1], "p90": vals[2]}

    @staticmethod
    def _to_numpy(x):
        """Convert torch tensors / arrays / lists to ndarray; None on failure."""
        if x is None:
            return None
        if hasattr(x, "detach"):  # torch tensor
            try:
                return x.detach().cpu().numpy()
            except Exception:
                return None
        try:
            return np.asarray(x, dtype=float)
        except Exception:
            return None

    # ── Heuristics ───────────────────────────────────────────────────────

    @staticmethod
    def _offset_band(ctx: pd.DataFrame, close_p90, close_p10):
        """HEURISTIC for close-only backends: build the envelope from recent
        bar asymmetry over the last TSFM_OFFSET_WINDOW (20) bars —
            high_p90 = close_p90 + mean(high − close)
            low_p10  = close_p10 − mean(close − low)
        Mirrors the additive offset structure of ZERO's ATR envelope."""
        tail = ctx.tail(TSFM_OFFSET_WINDOW)
        up = float((tail["high"] - tail["close"]).clip(lower=0.0).mean())
        dn = float((tail["close"] - tail["low"]).clip(lower=0.0).mean())
        high_p90 = close_p90 + up if close_p90 is not None else None
        low_p10 = close_p10 - dn if close_p10 is not None else None
        return high_p90, low_p10

    @staticmethod
    def _direction(p50, ref) -> str:
        """'up'/'down' when p50 drifts from ref by more than TSFM_FLAT_EPS_PCT
        (default 0.1%), else 'flat'."""
        try:
            if p50 is None or ref is None or float(ref) <= 0:
                return "flat"
            drift = (float(p50) - float(ref)) / float(ref)
        except (TypeError, ValueError, ZeroDivisionError):
            return "flat"
        if drift > TSFM_FLAT_EPS_PCT:
            return "up"
        if drift < -TSFM_FLAT_EPS_PCT:
            return "down"
        return "flat"

    # ── Result helper ────────────────────────────────────────────────────

    @staticmethod
    def _result(status: str, backend: str | None, horizon: int, n_context: int,
                error: str | None = None, **extra) -> dict:
        out = {
            "status": status,
            "backend": backend,
            "close": {"p10": None, "p50": None, "p90": None},
            "high_p90": None,
            "low_p10": None,
            "horizon": horizon,
            "n_context": n_context,
        }
        if error:
            out["error"] = str(error)
        out.update(extra)
        return out


# ── Module singleton accessor ────────────────────────────────────────────────

def get_forecaster(backend: str = "auto", device: str | None = None) -> TSFMForecaster:
    """Cached singleton — repeated calls with the same (backend, device) are
    free, and all instances share the module-level model-weight cache."""
    key = ((backend or "auto").strip().lower(), (device or TSFM_DEVICE))
    if key not in _FORECASTER_CACHE:
        _FORECASTER_CACHE[key] = TSFMForecaster(backend=key[0], device=key[1])
    return _FORECASTER_CACHE[key]


if __name__ == "__main__":
    # Self-test: safe to run with zero optional deps installed.
    print("ZERO TSFM Predictor")
    print(f"  default backend: {TSFM_BACKEND}   device: {TSFM_DEVICE}")
    for _b in ("chronos2", "kronos", "timesfm"):
        print(f"  probe[{_b}]: {TSFMForecaster._probe(_b)}")

    _fc = get_forecaster()
    print(f"  forecaster backend: {_fc.backend}   available: {_fc.is_available()}")

    _rng = np.random.default_rng(42)
    _n = 60
    _close = 25000.0 * np.cumprod(1.0 + _rng.normal(0.0, 0.01, _n))
    _demo = pd.DataFrame({
        "open": _close * (1.0 + _rng.normal(0.0, 0.002, _n)),
        "high": _close * (1.0 + abs(_rng.normal(0.0, 0.004, _n))),
        "low": _close * (1.0 - abs(_rng.normal(0.0, 0.004, _n))),
        "close": _close,
    })
    _out = _fc.forecast_ohlc(_demo, horizon=1,
                             covariates={"gift_premium": 0.2, "vix": 14.5,
                                         "pcr": 1.05, "sentiment": 0.1})
    print(f"  forecast: {_out}")
    _point = {"pred_open": float(_close[-1]), "pred_high": float(_close[-1]) * 1.01,
              "pred_low": float(_close[-1]) * 0.99, "pred_close": float(_close[-1]) * 1.002}
    print(f"  compare:  {_fc.compare_vs_point(_out, _point)}")
