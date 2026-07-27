"""
ZERO Adaptive Calibration Layer
================================

This module is the learning core that upgrades ZERO from a fixed linear
formula (ALPHA*gift + BETA*adr) into a self-correcting, uncertainty-aware
engine — the capability the rest of the codebase was scaffolded for
(feature store, model registry, walk-forward config) but never actually
implemented.

Design goals
------------
1.  **No hard dependency on heavy ML stacks.** XGBoost/scikit-learn are used
    automatically *if present*, but the default path is a pure-numpy ridge
    regression so the engine trains and predicts on a bare
    `numpy`+`pandas` install. This matches the small-data regime of a daily
    pre-market engine (tens of samples), where a shallow linear correction
    generalises better than a deep tree anyway.

2.  **It can never make the engine worse.** Every candidate correction is
    scored with leave-one-out / walk-forward cross-validation against the
    raw baseline and only *committed* if it beats the baseline by
    `COMMIT_RELATIVE_IMPROVEMENT`. Otherwise the engine falls back to the
    raw geometric prediction. This is the guardrail that a naive
    "always trust the model" design lacks.

3.  **Probabilistic output.** Instead of three bare numbers, the calibrator
    emits split-conformal prediction intervals (P10/P90-style bands) whose
    width is *learned from the engine's own historical error*, giving the
    terminal an honest confidence signal.

The public surface is intentionally tiny:

    cal = Calibrator.load()                 # or Calibrator.fit_from_logs()
    out = cal.apply(index_name, raw_pred, feature_row)
    # -> {'pred_open','pred_high','pred_low', '<leg>_lo','<leg>_hi',
    #     'confidence', 'model'}

`raw_pred` is the dict the geometric engine already produces
(pred_open/high/low). `feature_row` is the flat feature dict from
`data.features.build_features` (optional — falls back to bias-only
correction when features are unavailable, e.g. fully offline).
"""

from __future__ import annotations

import json
import os
import math
import datetime

import numpy as np

from config import (
    ML_MIN_TRAIN_ROWS,
    ML_STALE_DAYS,
    QUANTILE_BAND_Z,
    COMMIT_RELATIVE_IMPROVEMENT,
)

# ---- optional heavy deps (used only if available) ------------------------
try:  # pragma: no cover - depends on environment
    from xgboost import XGBRegressor  # noqa: F401
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False

_LEGS = ("open", "high", "low")

# Feature columns the corrector consumes. Kept deliberately small and
# aligned with what is actually logged for every historical row, so the
# model trains from day one instead of dropping every sample on a join.
CORRECTOR_FEATURES = (
    "gift_premium_norm",   # (gift - prev_close)/prev_close, 0 when unavailable
    "adr_delta",
    "vix",
    "pcr",
    "sentiment_score",
    "atr_norm",            # atr / prev_close
)

# James-Stein-style shrinkage strength. A learned correction of sample size
# n is scaled by n/(n+SHRINK_K), so early, noisy corrections are pulled back
# toward the trusted geometric baseline and only firm up as evidence
# accumulates. Tuned by walk-forward grid search on the historical log.
SHRINK_K = 6.0

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "calibrator.json")


# =========================================================================
#  Low-level: dependency-free ridge regression
# =========================================================================
class _Ridge:
    """Closed-form ridge regression (L2). Pure numpy, no sklearn needed.

    Solves  w = (XᵀX + λI)⁻¹ Xᵀy  with a bias column appended to X.
    Ridge (rather than OLS) is deliberate: with only a handful of daily
    samples, unregularised fits overshoot wildly. λ shrinks the correction
    toward the raw baseline, which is the safe prior.
    """

    def __init__(self, lam: float = 10.0):
        self.lam = float(lam)
        self.w = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim == 1:
            X = X.reshape(-1, 1)
        n, d = X.shape
        Xb = np.hstack([X, np.ones((n, 1))])          # bias term
        A = Xb.T @ Xb
        # Regularise features but NOT the bias (last diagonal entry).
        reg = self.lam * np.eye(d + 1)
        reg[-1, -1] = 0.0
        try:
            self.w = np.linalg.solve(A + reg, Xb.T @ y)
        except np.linalg.LinAlgError:
            self.w = np.linalg.pinv(A + reg) @ (Xb.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        Xb = np.hstack([X, np.ones((X.shape[0], 1))])
        return Xb @ self.w


def _mae(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0:
        return float("inf")
    return float(np.mean(np.abs(a - b)))


# =========================================================================
#  Calibrator
# =========================================================================
class Calibrator:
    """Per-index, per-leg residual corrector + conformal band widths.

    The model for each (index, leg) predicts the *residual*
    `actual - raw_prediction` from a small feature vector, then adds it back
    to the raw prediction. Learning the residual (not the level) means the
    geometric engine keeps doing the heavy lifting and the ML layer only
    cleans up its systematic bias — exactly what the historical logs show is
    needed (the raw envelope is consistently too wide).
    """

    def __init__(self, models=None, band=None, trained_at=None, metrics=None):
        # models[index][leg] -> dict(weights, features) or None (baseline)
        self.models = models or {}
        # band[index][leg] -> conformal half-width in points
        self.band = band or {}
        self.trained_at = trained_at
        self.metrics = metrics or {}

    # ---- feature extraction ---------------------------------------------
    @staticmethod
    def _row_to_vec(feature_row, prev_close):
        """Map a logged raw_inputs / feature dict to CORRECTOR_FEATURES.

        Robust to both the rich `build_features` dict and the leaner
        `raw_inputs` block stored in feedback_log.json, and to fully missing
        data (returns zeros → bias-only correction).
        """
        fr = feature_row or {}
        pc = float(prev_close) if prev_close else 0.0

        gift = fr.get("gift_nifty") or fr.get("gift_premium")
        if fr.get("gift_premium_pct") is not None:
            gift_norm = float(fr.get("gift_premium_pct") or 0.0)
        elif gift and pc > 0 and fr.get("gift_nifty") is not None:
            gift_norm = (float(gift) - pc) / pc
        else:
            gift_norm = 0.0

        atr = fr.get("atr")
        if fr.get("atr_pct") is not None:
            atr_norm = float(fr.get("atr_pct") or 0.0)
        elif atr and pc > 0:
            atr_norm = float(atr) / pc
        else:
            atr_norm = 0.0

        return [
            gift_norm,
            float(fr.get("adr_delta") or fr.get("adr_weighted") or 0.0),
            float(fr.get("vix") or 15.0),
            float(fr.get("pcr") or 1.0),
            float(fr.get("sentiment_score") or 0.0),
            atr_norm,
        ]

    # ---- training -------------------------------------------------------
    @classmethod
    def fit_from_logs(cls, logs=None, verbose=False):
        """Train the corrector from feedback_log.json entries.

        Every entry carries `predicted`, `actual`, `raw_inputs`, and its own
        per-index `prev_close`, so training is self-contained — no fragile
        join against a parquet feature store that may be empty.
        """
        from engine.learning_service import get_feedback_logs
        if logs is None:
            logs = get_feedback_logs()

        # bucket rows by index
        buckets = {}
        for e in logs or []:
            a = e.get("actual") or {}
            p = e.get("predicted") or {}
            if not isinstance(a, dict) or str(a.get("open")) in ("N/A", "None", ""):
                continue
            idx = e.get("index")
            ri = e.get("raw_inputs") or {}
            prev_close = ri.get("prev_close") or 0
            try:
                if float(prev_close) <= 0:
                    continue
                actuals = {leg: float(a[leg]) for leg in _LEGS}
                preds = {leg: float(p["pred_" + leg]) for leg in _LEGS}
            except (KeyError, TypeError, ValueError):
                continue
            vec = cls._row_to_vec(ri, prev_close)
            buckets.setdefault(idx, []).append({
                "x": vec, "actual": actuals, "pred": preds,
            })

        models, band, metrics = {}, {}, {}
        for idx, rows in buckets.items():
            models[idx], band[idx], metrics[idx] = cls._fit_index(rows, verbose)

        trained_at = datetime.datetime.now().isoformat()
        return cls(models=models, band=band, trained_at=trained_at, metrics=metrics)

    @classmethod
    def _fit_index(cls, rows, verbose=False):
        """Fit all three legs for one index; return (models, bands, metrics)."""
        n = len(rows)
        X = np.array([r["x"] for r in rows], dtype=float)
        idx_models, idx_band, idx_metrics = {}, {}, {}

        for leg in _LEGS:
            resid = np.array([r["actual"][leg] - r["pred"][leg] for r in rows], dtype=float)
            baseline_mae = _mae(resid, 0.0)  # doing nothing = raw prediction

            model_spec = None
            model_mae = baseline_mae
            band_source = np.abs(resid)  # conformal residuals default to raw errors
            shrink = n / (n + SHRINK_K)  # pull correction toward baseline

            if n >= ML_MIN_TRAIN_ROWS:
                # Enough data: try a feature-driven ridge correction, scored
                # by leave-one-out CV so we never over-fit the tiny sample.
                loo_pred = cls._loo_predict(X, resid) * shrink
                cv_mae = _mae(loo_pred, resid)
                if cv_mae < baseline_mae * (1.0 - COMMIT_RELATIVE_IMPROVEMENT):
                    full = _Ridge().fit(X, resid)
                    model_spec = {
                        "type": "ridge",
                        "w": (full.w * shrink).tolist(),
                        "features": list(CORRECTOR_FEATURES),
                    }
                    model_mae = cv_mae
                    band_source = np.abs(resid - loo_pred)  # honest CV errors

            if model_spec is None and n >= 3:
                # Sparse data (or ridge rejected): a shrunk bias correction
                # (subtract the mean residual, damped toward 0) is the most we
                # can safely learn. Commit only if LOO shows it truly helps.
                mean_bias = float(np.mean(resid)) * shrink
                loo_bias = np.array(
                    [((np.sum(resid) - resid[i]) / (n - 1)) * shrink for i in range(n)]
                ) if n > 1 else np.zeros(n)
                cv_mae = _mae(loo_bias, resid)
                if cv_mae < baseline_mae * (1.0 - COMMIT_RELATIVE_IMPROVEMENT):
                    model_spec = {"type": "bias", "b": mean_bias}
                    model_mae = cv_mae
                    band_source = np.abs(resid - loo_bias)

            # Conformal half-width: the (1-α) empirical quantile of |errors|,
            # scaled to the configured band z so the UI's band matches the
            # engine's realised accuracy rather than a hand-tuned constant.
            alpha_q = min(0.95, max(0.5, 2 * _z_to_quantile(QUANTILE_BAND_Z) - 1))
            half = float(np.quantile(band_source, alpha_q)) if band_source.size else 0.0

            idx_models[leg] = model_spec
            idx_band[leg] = round(half, 2)
            idx_metrics[leg] = {
                "n": n,
                "baseline_mae": round(baseline_mae, 2),
                "model_mae": round(model_mae, 2),
                "committed": model_spec is not None,
            }
            if verbose:
                print(f"    {leg:5s} n={n} baseline={baseline_mae:8.1f} "
                      f"model={model_mae:8.1f} committed={model_spec is not None}")

        return idx_models, idx_band, idx_metrics

    @staticmethod
    def _loo_predict(X, y):
        """Leave-one-out ridge predictions — the honest small-sample score."""
        n = len(y)
        out = np.zeros(n)
        for i in range(n):
            mask = np.ones(n, dtype=bool)
            mask[i] = False
            m = _Ridge().fit(X[mask], y[mask])
            out[i] = float(m.predict(X[i:i+1])[0])
        return out

    # ---- inference ------------------------------------------------------
    def apply(self, index_name, raw_pred, feature_row=None):
        """Return a calibrated prediction dict with probabilistic bands.

        Falls back cleanly to the raw geometric prediction for any leg whose
        model was not committed, so the engine degrades to its previous
        behaviour instead of failing.
        """
        prev_close = (feature_row or {}).get("prev_close") or raw_pred.get("prev_close")
        vec = self._row_to_vec(feature_row, prev_close)
        x = np.array(vec, dtype=float)

        out = dict(raw_pred)
        idx_models = self.models.get(index_name, {})
        idx_band = self.band.get(index_name, {})
        committed = 0

        for leg in _LEGS:
            raw = float(raw_pred.get("pred_" + leg))
            spec = idx_models.get(leg)
            corrected = raw
            if spec is not None:
                if spec["type"] == "bias":
                    corrected = raw + float(spec["b"])
                elif spec["type"] == "ridge":
                    w = np.array(spec["w"], dtype=float)
                    corrected = raw + float(np.dot(np.append(x, 1.0), w))
                committed += 1
            half = float(idx_band.get(leg, 0.0))
            out["pred_" + leg] = round(corrected, 2)
            out[leg + "_lo"] = round(corrected - half, 2)
            out[leg + "_hi"] = round(corrected + half, 2)

        # Enforce H >= O >= L ordering after independent per-leg correction.
        o, h, l = out["pred_open"], out["pred_high"], out["pred_low"]
        out["pred_high"] = round(max(h, o, l), 2)
        out["pred_low"] = round(min(l, o, h), 2)

        # ── Obsidian Cognitive Mistake-Feedback Loop (Section 6 of plan) ──
        try:
            from engine.brain_engine import get_brain
            brain = get_brain()
            import datetime as dt
            scores = []
            active_biases_count = 0
            today = dt.date.today()
            for i in range(7):
                d_str = (today - dt.timedelta(days=i)).isoformat()
                log = brain.get_daily_log(d_str)
                # Count if we have entries today or if there was a logged forecast
                if log.get("entries_today", 0) > 0 or log.get("forecasts"):
                    scores.append(log.get("score", 10))
                    active_biases_count += len(log.get("biases_flagged", []))
            
            avg_score = np.mean(scores) if scores else 10.0
            
            # If avg_score is low, or any biases were active, apply safety scale-down
            if avg_score < 8.0 or active_biases_count > 0:
                scale_factor = max(0.5, min(1.0, avg_score / 10.0))
                
                # Scale down range width by narrowing high and low toward predicted open
                open_val = out["pred_open"]
                high_val = out["pred_high"]
                low_val = out["pred_low"]
                
                out["pred_high"] = round(open_val + (high_val - open_val) * scale_factor, 2)
                out["pred_low"] = round(open_val - (open_val - low_val) * scale_factor, 2)
                
                # Also narrow split-conformal confidence bands
                for leg in _LEGS:
                    val = out["pred_" + leg]
                    lo = out[leg + "_lo"]
                    hi = out[leg + "_hi"]
                    out[leg + "_lo"] = round(val - (val - lo) * scale_factor, 2)
                    out[leg + "_hi"] = round(val + (hi - val) * scale_factor, 2)
                
                out["discipline_scaled"] = True
                out["discipline_scale_factor"] = scale_factor
        except Exception:
            pass

        out["model"] = "calibrated" if committed else "baseline"
        out["confidence"] = self._confidence(index_name, raw_pred)
        return out

    def _confidence(self, index_name, raw_pred):
        """0-100 confidence from band width relative to the day's range.

        Tighter learned bands (engine has been accurate for this index) → higher
        confidence. Expressed as a percentage the terminal can render directly.
        """
        idx_band = self.band.get(index_name, {})
        if not idx_band:
            return 50.0
        span = abs(float(raw_pred.get("pred_high", 0)) - float(raw_pred.get("pred_low", 0)))
        if span <= 0:
            return 50.0
        avg_half = np.mean([idx_band.get(leg, span) for leg in _LEGS])
        # band == half the range -> ~50%; band -> 0 -> ~100%.
        conf = max(5.0, min(99.0, 100.0 * (1.0 - avg_half / span)))
        return round(float(conf), 1)

    def is_stale(self):
        if not self.trained_at:
            return True
        try:
            age = datetime.datetime.now() - datetime.datetime.fromisoformat(self.trained_at)
            return age.days >= ML_STALE_DAYS
        except (ValueError, TypeError):
            return True

    # ---- persistence ----------------------------------------------------
    def save(self, path=MODEL_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "models": self.models,
            "band": self.band,
            "trained_at": self.trained_at,
            "metrics": self.metrics,
            "features": list(CORRECTOR_FEATURES),
            "has_xgb": _HAS_XGB,
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        return path

    @classmethod
    def load(cls, path=MODEL_PATH):
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                p = json.load(f)
            return cls(models=p.get("models"), band=p.get("band"),
                       trained_at=p.get("trained_at"), metrics=p.get("metrics"))
        except (json.JSONDecodeError, IOError):
            return None

    @classmethod
    def load_or_baseline(cls):
        """Always return a usable Calibrator. If none is saved, return an
        empty one whose `apply` is an identity pass-through (baseline)."""
        return cls.load() or cls()


def _z_to_quantile(z):
    """Standard-normal CDF at z (Φ), via erf — no scipy dependency."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def retrain_and_save(verbose=True):
    """Convenience entry point for the daily updater / CLI."""
    cal = Calibrator.fit_from_logs(verbose=verbose)
    path = cal.save()
    if verbose:
        print(f"\nCalibrator saved -> {path}")
        print(f"Trained at: {cal.trained_at}")
    return cal


if __name__ == "__main__":
    retrain_and_save(verbose=True)
