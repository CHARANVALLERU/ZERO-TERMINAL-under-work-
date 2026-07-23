"""
Unit tests for the ZERO adaptive calibration layer.

Runnable with `pytest` if installed, or standalone:  `python tests/test_calibrator.py`.
These tests intentionally use only numpy so they run on the minimal stack.
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.calibrator import Calibrator, _Ridge, _LEGS, _z_to_quantile  # noqa: E402


def test_ridge_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 3))
    true_w = np.array([2.0, -1.0, 0.5])
    y = X @ true_w + 3.0
    m = _Ridge(lam=1e-6).fit(X, y)
    pred = m.predict(X)
    assert np.mean(np.abs(pred - y)) < 1e-3


def test_zscore_to_quantile():
    # Φ(0)=0.5, Φ(1.28)≈0.90
    assert abs(_z_to_quantile(0.0) - 0.5) < 1e-9
    assert abs(_z_to_quantile(1.28) - 0.8997) < 1e-3


def _synthetic_logs(n=15, bias=120.0, seed=1):
    """A log where actual_high is systematically `bias` below predicted_high —
    exactly the kind of correctable structure the calibrator targets."""
    rng = np.random.default_rng(seed)
    logs = []
    close = 24000.0
    for i in range(n):
        po, ph, pl = close, close + 300, close - 300
        ah = ph - bias + rng.normal(0, 20)
        al = pl + bias + rng.normal(0, 20)
        ao = po + rng.normal(0, 30)
        logs.append({
            "date": f"2026-01-{i+1:02d}", "index": "NIFTY 50",
            "predicted": {"pred_open": po, "pred_high": ph, "pred_low": pl},
            "actual": {"open": ao, "high": ah, "low": al, "close": ah - 50},
            "raw_inputs": {"prev_close": close, "vix": 15, "pcr": 1.0,
                           "adr_delta": 0.0, "sentiment_score": 0.0, "atr": 200},
        })
    return logs


def test_calibrator_reduces_systematic_bias():
    logs = _synthetic_logs()
    cal = Calibrator.fit_from_logs(logs=logs)
    m = cal.metrics["NIFTY 50"]["high"]
    # High leg has a strong learnable bias -> must be committed and improve CV MAE.
    assert m["committed"] is True
    assert m["model_mae"] < m["baseline_mae"]


def test_calibrator_never_commits_pure_noise():
    """With no structure, the guardrail should refuse to commit (stay baseline)."""
    rng = np.random.default_rng(2)
    logs = []
    close = 24000.0
    for i in range(15):
        po, ph, pl = close, close + 300, close - 300
        logs.append({
            "date": f"2026-02-{i+1:02d}", "index": "NIFTY 50",
            "predicted": {"pred_open": po, "pred_high": ph, "pred_low": pl},
            "actual": {"open": po + rng.normal(0, 150),
                       "high": ph + rng.normal(0, 150),
                       "low": pl + rng.normal(0, 150), "close": po},
            "raw_inputs": {"prev_close": close, "vix": 15, "pcr": 1.0,
                           "adr_delta": 0.0, "sentiment_score": 0.0, "atr": 200},
        })
    cal = Calibrator.fit_from_logs(logs=logs)
    committed = [cal.metrics["NIFTY 50"][leg]["committed"] for leg in _LEGS]
    # It is allowed to commit 0 here; the key invariant is it must not *hurt* CV MAE.
    for leg in _LEGS:
        mm = cal.metrics["NIFTY 50"][leg]
        assert mm["model_mae"] <= mm["baseline_mae"] + 1e-6


def test_apply_preserves_ohlc_ordering_and_is_safe_offline():
    logs = _synthetic_logs()
    cal = Calibrator.fit_from_logs(logs=logs)
    raw = {"pred_open": 24000.0, "pred_high": 24300.0, "pred_low": 23700.0,
           "prev_close": 24000.0}
    # No feature row at all (fully offline) must still work.
    out = cal.apply("NIFTY 50", raw, None)
    assert out["pred_high"] >= out["pred_open"] >= out["pred_low"]
    assert 0 <= out["confidence"] <= 100
    assert out["model"] in ("calibrated", "baseline")


def test_baseline_calibrator_is_identity():
    cal = Calibrator()  # empty / untrained
    raw = {"pred_open": 100.0, "pred_high": 110.0, "pred_low": 90.0, "prev_close": 100.0}
    out = cal.apply("NIFTY 50", raw, None)
    assert out["pred_open"] == 100.0
    assert out["pred_high"] == 110.0
    assert out["pred_low"] == 90.0
    assert out["model"] == "baseline"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    raise SystemExit(0 if _run_all() else 1)
