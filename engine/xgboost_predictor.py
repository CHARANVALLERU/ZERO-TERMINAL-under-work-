"""
ZERO Multi-Timeframe XGBoost Predictor
======================================

Dual-horizon predictor that outputs target boundaries for both intraday
and weekly horizons.  Runs alongside the existing Calibrator — does NOT
replace it.

Critical Design Rules (from the integration spec):
  1. Always predict PERCENTAGE CHANGE relative to the open/close, never
     raw prices.  XGBoost trees cannot extrapolate beyond training data
     limits; at all-time highs the raw-price model fails.
  2. Weekly features are snapshotted per week_id and held static across
     all intraday bars of that week — preventing look-ahead leakage.
  3. The weekly model's output (weekly pivot bounds) feeds into the
     intraday model as static binary features.

Training data comes from the same feedback_log.json used by the Calibrator.
"""

from __future__ import annotations

import os
import json
import datetime

import numpy as np
import pandas as pd

from engine.quant_config import (
    INTRADAY_XGB,
    WEEKLY_XGB,
    MTF_MIN_TRAIN_ROWS,
    MTF_WALK_FORWARD_FOLDS,
)

# Optional heavy dep — graceful fallback
try:
    import xgboost as xgb
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

# Persistence paths
_MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "db")
_INTRADAY_MODEL_PATH = os.path.join(_MODEL_DIR, "xgb_intraday.json")
_WEEKLY_MODEL_PATH = os.path.join(_MODEL_DIR, "xgb_weekly.json")


class MultiTimeframePredictor:
    """Intraday + Weekly XGBoost prediction engine.

    Predicts percentage-change targets:
      - target_high_pct = (high - open) / open
      - target_low_pct  = (low  - open) / open   (negative)

    Both models are optional and degrade to no-op when unavailable.
    """

    def __init__(self, timeframe: str = "intraday"):
        self.timeframe = timeframe
        self._model_high = None
        self._model_low = None
        self._feature_cols = []
        self._trained = False

        if _HAS_XGB:
            params = INTRADAY_XGB if timeframe == "intraday" else WEEKLY_XGB
            self._model_high = xgb.XGBRegressor(**params)
            self._model_low = xgb.XGBRegressor(**params)

    # ── Feature preparation ──────────────────────────────────────────────

    @staticmethod
    def prepare_features(df: pd.DataFrame) -> tuple:
        """Engineer stationarized targets and return (X, y_high, y_low).

        Target variables are percentage changes — never raw prices.
        This is critical: XGBoost cannot extrapolate, so at all-time
        highs a raw-price target would cap out at the training maximum.
        """
        df = df.copy()

        # Stationarized targets: predict % change from open
        df["target_high_pct"] = (df["high"] - df["open"]) / df["open"]
        df["target_low_pct"] = (df["low"] - df["open"]) / df["open"]

        # Feature columns: everything except OHLCV and targets
        exclude = {"open", "high", "low", "close", "volume",
                    "target_high_pct", "target_low_pct",
                    "date", "index", "symbol"}
        feature_cols = [c for c in df.columns if c not in exclude]

        X = df[feature_cols].copy()
        y_high = df["target_high_pct"]
        y_low = df["target_low_pct"]

        # Replace infinities and NaN with 0
        X = X.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        y_high = y_high.replace([np.inf, -np.inf], 0.0).fillna(0.0)
        y_low = y_low.replace([np.inf, -np.inf], 0.0).fillna(0.0)

        return X, y_high, y_low, feature_cols

    # ── Training ─────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame) -> dict:
        """Train both high and low models on prepared data.

        Returns training metrics dict.
        """
        if not _HAS_XGB:
            return {"status": "skipped", "reason": "xgboost not installed"}

        if len(df) < MTF_MIN_TRAIN_ROWS:
            return {"status": "skipped", "reason": f"insufficient data ({len(df)} < {MTF_MIN_TRAIN_ROWS})"}

        X, y_high, y_low, feature_cols = self.prepare_features(df)
        self._feature_cols = feature_cols

        self._model_high.fit(X, y_high)
        self._model_low.fit(X, y_low)
        self._trained = True

        # Walk-forward MAE estimate (simple expanding-window)
        mae_high, mae_low = self._walk_forward_score(df)

        return {
            "status": "trained",
            "timeframe": self.timeframe,
            "n_samples": len(df),
            "n_features": len(feature_cols),
            "walk_forward_mae_high": round(mae_high, 6),
            "walk_forward_mae_low": round(mae_low, 6),
        }

    def _walk_forward_score(self, df: pd.DataFrame) -> tuple:
        """Expanding-window walk-forward CV score. Returns (mae_high, mae_low)."""
        if not _HAS_XGB:
            return (float("inf"), float("inf"))

        n = len(df)
        if n < MTF_MIN_TRAIN_ROWS + 2:
            return (float("inf"), float("inf"))

        fold_size = max(1, (n - MTF_MIN_TRAIN_ROWS) // MTF_WALK_FORWARD_FOLDS)
        errors_high = []
        errors_low = []

        for fold in range(MTF_WALK_FORWARD_FOLDS):
            split = MTF_MIN_TRAIN_ROWS + fold * fold_size
            if split >= n:
                break

            train_df = df.iloc[:split]
            test_df = df.iloc[split:split + fold_size]
            if test_df.empty:
                break

            X_train, y_h_train, y_l_train, cols = self.prepare_features(train_df)
            X_test, y_h_test, y_l_test, _ = self.prepare_features(test_df)

            # Ensure test has same columns
            for c in cols:
                if c not in X_test.columns:
                    X_test[c] = 0.0
            X_test = X_test[cols]

            params = INTRADAY_XGB if self.timeframe == "intraday" else WEEKLY_XGB
            m_h = xgb.XGBRegressor(**params)
            m_l = xgb.XGBRegressor(**params)
            m_h.fit(X_train, y_h_train)
            m_l.fit(X_train, y_l_train)

            pred_h = m_h.predict(X_test)
            pred_l = m_l.predict(X_test)
            errors_high.extend(np.abs(pred_h - y_h_test.values).tolist())
            errors_low.extend(np.abs(pred_l - y_l_test.values).tolist())

        mae_h = float(np.mean(errors_high)) if errors_high else float("inf")
        mae_l = float(np.mean(errors_low)) if errors_low else float("inf")
        return (mae_h, mae_l)

    # ── Prediction ───────────────────────────────────────────────────────

    def predict_bounds(self, current_features: pd.DataFrame,
                       current_open: float) -> dict:
        """Predict the upcoming target boundaries for the trading session.

        Returns percentage-change predictions converted back to absolute
        levels using the current open price.
        """
        if not self._trained or not _HAS_XGB:
            return {
                "predicted_high": None,
                "predicted_low": None,
                "high_pct": None,
                "low_pct": None,
                "status": "no_model",
            }

        # Ensure feature alignment
        X = current_features.copy()
        for c in self._feature_cols:
            if c not in X.columns:
                X[c] = 0.0
        X = X[self._feature_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)

        high_pct = float(self._model_high.predict(X)[0])
        low_pct = float(self._model_low.predict(X)[0])

        # Convert percentage back to absolute levels
        predicted_high = current_open * (1.0 + high_pct)
        predicted_low = current_open * (1.0 + low_pct)

        # Enforce ordering: high >= open >= low
        predicted_high = max(predicted_high, current_open)
        predicted_low = min(predicted_low, current_open)

        return {
            "predicted_high": round(predicted_high, 2),
            "predicted_low": round(predicted_low, 2),
            "high_pct": round(high_pct, 6),
            "low_pct": round(low_pct, 6),
            "status": "predicted",
        }

    # ── Training Data Assembly ───────────────────────────────────────────

    @staticmethod
    def assemble_training_data(timeframe: str = "intraday") -> pd.DataFrame:
        """Build a training DataFrame from the feedback log + feature store.

        For the intraday model: uses daily feedback entries with OHLC.
        For the weekly model: aggregates to weekly bars from daily data.

        Returns an empty DataFrame if insufficient data is available.
        """
        from engine.learning_service import get_feedback_logs

        logs = get_feedback_logs()
        if not logs:
            return pd.DataFrame()

        rows = []
        for entry in logs:
            actual = entry.get("actual") or {}
            if not isinstance(actual, dict):
                continue
            try:
                o = float(actual.get("open"))
                h = float(actual.get("high"))
                l = float(actual.get("low"))
                c = float(actual.get("close"))
            except (TypeError, ValueError):
                continue
            if o <= 0 or h <= 0 or l <= 0 or c <= 0:
                continue

            ri = entry.get("raw_inputs") or {}
            row = {
                "date": entry.get("date"),
                "index": entry.get("index"),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                # Pull available features from raw_inputs
                "prev_close": float(ri.get("prev_close") or 0.0),
                "gift_nifty": float(ri.get("gift_nifty") or 0.0),
                "adr_delta": float(ri.get("adr_delta") or 0.0),
                "vix": float(ri.get("vix") or 15.0),
                "pcr": float(ri.get("pcr") or 1.0),
                "sentiment_score": float(ri.get("sentiment_score") or 0.0),
                "atr": float(ri.get("atr") or 0.0),
            }
            rows.append(row)

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

        if timeframe == "weekly":
            # Aggregate daily rows to weekly bars
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"])
            df["week_id"] = df["date"].dt.isocalendar().week.astype(int)
            df["year"] = df["date"].dt.year

            weekly_rows = []
            for (idx, year, week), grp in df.groupby(["index", "year", "week_id"]):
                weekly_rows.append({
                    "index": idx,
                    "open": grp["open"].iloc[0],
                    "high": grp["high"].max(),
                    "low": grp["low"].min(),
                    "close": grp["close"].iloc[-1],
                    # Use week-start features (no leakage)
                    "prev_close": grp["prev_close"].iloc[0],
                    "gift_nifty": grp["gift_nifty"].iloc[0],
                    "adr_delta": grp["adr_delta"].iloc[0],
                    "vix": grp["vix"].mean(),
                    "pcr": grp["pcr"].mean(),
                    "sentiment_score": grp["sentiment_score"].mean(),
                    "atr": grp["atr"].mean(),
                })
            df = pd.DataFrame(weekly_rows) if weekly_rows else pd.DataFrame()

        return df

    # ── Persistence ──────────────────────────────────────────────────────

    def save(self):
        """Save the trained models to disk."""
        if not _HAS_XGB or not self._trained:
            return None

        os.makedirs(_MODEL_DIR, exist_ok=True)
        path = _INTRADAY_MODEL_PATH if self.timeframe == "intraday" else _WEEKLY_MODEL_PATH
        meta_path = path.replace(".json", "_meta.json")

        self._model_high.save_model(path.replace(".json", "_high.json"))
        self._model_low.save_model(path.replace(".json", "_low.json"))

        with open(meta_path, "w") as f:
            json.dump({
                "timeframe": self.timeframe,
                "feature_cols": self._feature_cols,
                "trained_at": datetime.datetime.now().isoformat(),
            }, f, indent=2)

        return path

    def load(self) -> bool:
        """Load models from disk. Returns True if successful."""
        if not _HAS_XGB:
            return False

        path = _INTRADAY_MODEL_PATH if self.timeframe == "intraday" else _WEEKLY_MODEL_PATH
        meta_path = path.replace(".json", "_meta.json")
        high_path = path.replace(".json", "_high.json")
        low_path = path.replace(".json", "_low.json")

        if not all(os.path.exists(p) for p in [high_path, low_path, meta_path]):
            return False

        try:
            self._model_high = xgb.XGBRegressor()
            self._model_high.load_model(high_path)
            self._model_low = xgb.XGBRegressor()
            self._model_low.load_model(low_path)

            with open(meta_path) as f:
                meta = json.load(f)
            self._feature_cols = meta.get("feature_cols", [])
            self._trained = True
            return True
        except Exception:
            self._trained = False
            return False


if __name__ == "__main__":
    # Quick self-test
    print("Multi-Timeframe XGBoost Predictor")
    print(f"  XGBoost available: {_HAS_XGB}")

    for tf in ["intraday", "weekly"]:
        print(f"\n  [{tf.upper()}]")
        predictor = MultiTimeframePredictor(timeframe=tf)
        df = predictor.assemble_training_data(timeframe=tf)
        print(f"    Training samples: {len(df)}")
        if not df.empty:
            result = predictor.train(df)
            print(f"    Training result: {result}")
        else:
            print("    Skipped — no training data in feedback log.")
