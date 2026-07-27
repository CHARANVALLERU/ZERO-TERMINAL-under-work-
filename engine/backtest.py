"""
ZERO Backtest & Evaluation Harness
==================================

Measures the engine's real predictive accuracy from the feedback log and
quantifies how much the adaptive calibration layer (engine.calibrator)
improves on the raw geometric prediction.

Two modes:

* ``evaluate_baseline()`` — MAE / MAPE / directional-hit of the raw logged
  predictions vs actuals, per index and leg. This is "where the engine was".

* ``walk_forward()`` — the honest test: sort every logged day chronologically,
  and for each day *t* train the calibrator on days < *t* only, then score its
  prediction for day *t*. No look-ahead. This is the number to trust.

Run:  ``python -m engine.backtest``
"""

from __future__ import annotations

import numpy as np

from engine.learning_service import get_feedback_logs
from engine.calibrator import Calibrator, _LEGS


def _valid(e):
    a = e.get("actual") or {}
    if not isinstance(a, dict) or str(a.get("open")) in ("N/A", "None", ""):
        return False
    ri = e.get("raw_inputs") or {}
    try:
        return float(ri.get("prev_close") or 0) > 0 and float(a.get("open")) > 0
    except (TypeError, ValueError):
        return False


def _metrics(errors):
    if not errors:
        return {"n": 0, "mae": None, "mape": None}
    abs_err = [abs(e[0]) for e in errors]
    pct = [abs(e[0]) / e[1] * 100 for e in errors if e[1]]
    return {
        "n": len(errors),
        "mae": round(float(np.mean(abs_err)), 2),
        "mape": round(float(np.mean(pct)), 4) if pct else None,
    }


def evaluate_baseline(logs=None):
    """Per-index/leg accuracy of the raw predictions already in the log."""
    logs = logs if logs is not None else get_feedback_logs()
    out = {}
    for e in logs:
        if not _valid(e):
            continue
        idx = e["index"]
        a, p = e["actual"], e["predicted"]
        d = out.setdefault(idx, {leg: [] for leg in _LEGS})
        for leg in _LEGS:
            d[leg].append((float(a[leg]) - float(p["pred_" + leg]), float(a[leg])))
    return {idx: {leg: _metrics(errs) for leg, errs in legs.items()}
            for idx, legs in out.items()}


def walk_forward(logs=None, min_train=3):
    """Chronological walk-forward: train on the past, score the next day.

    Returns baseline vs calibrated MAE per index/leg plus the overall
    improvement, with zero look-ahead. `min_train` days are needed before
    the calibrator is allowed to act (below that it passes through baseline).
    """
    logs = logs if logs is not None else get_feedback_logs()
    valid = [e for e in logs if _valid(e)]
    valid.sort(key=lambda e: (e.get("date", ""), e.get("index", "")))

    # group by date, keep chronological order of unique dates
    dates = sorted({e["date"] for e in valid})

    base_err = {}   # idx -> leg -> list
    cal_err = {}

    for i, day in enumerate(dates):
        train = [e for e in valid if e["date"] < day]
        test = [e for e in valid if e["date"] == day]
        cal = None
        if len({e["date"] for e in train}) >= min_train:
            cal = Calibrator.fit_from_logs(logs=train, verbose=False)

        for e in test:
            idx = e["index"]
            a = e["actual"]
            raw_pred = {("pred_" + leg): float(e["predicted"]["pred_" + leg]) for leg in _LEGS}
            raw_pred["prev_close"] = float((e.get("raw_inputs") or {}).get("prev_close"))
            if cal is not None:
                calibrated = cal.apply(idx, raw_pred, e.get("raw_inputs"))
            else:
                calibrated = raw_pred

            bd = base_err.setdefault(idx, {leg: [] for leg in _LEGS})
            cd = cal_err.setdefault(idx, {leg: [] for leg in _LEGS})
            for leg in _LEGS:
                act = float(a[leg])
                bd[leg].append((act - raw_pred["pred_" + leg], act))
                cd[leg].append((act - float(calibrated["pred_" + leg]), act))

    report = {}
    for idx in base_err:
        report[idx] = {}
        for leg in _LEGS:
            b = _metrics(base_err[idx][leg])
            c = _metrics(cal_err[idx][leg])
            imp = None
            if b["mae"] and c["mae"] is not None and b["mae"] > 0:
                imp = round(100 * (b["mae"] - c["mae"]) / b["mae"], 1)
            report[idx][leg] = {"baseline_mae": b["mae"], "calibrated_mae": c["mae"],
                                "improvement_pct": imp, "n": b["n"]}
    return report


def _print_report(title, report):
    print(f"\n{'='*72}\n  {title}\n{'='*72}")
    for idx, legs in report.items():
        print(f"\n  {idx}")
        for leg, m in legs.items():
            if "calibrated_mae" in m:
                imp = m["improvement_pct"]
                arrow = "->" 
                tag = f"  ({imp:+.1f}%)" if imp is not None else ""
                print(f"    {leg:5s} n={m['n']:2d}  baseline MAE {str(m['baseline_mae']):>9s} "
                      f"{arrow} calibrated {str(m['calibrated_mae']):>9s}{tag}")
            else:
                print(f"    {leg:5s} n={m['n']:2d}  MAE={m['mae']}  MAPE={m['mape']}%")


def _overall(report):
    imps = [m["improvement_pct"] for legs in report.values() for m in legs.values()
            if m.get("improvement_pct") is not None]
    if imps:
        print(f"\n  >>> Mean walk-forward MAE improvement across all legs: "
              f"{np.mean(imps):+.1f}%\n")


if __name__ == "__main__":
    base = evaluate_baseline()
    _print_report("RAW BASELINE (logged predictions vs actuals)", base)
    wf = walk_forward()
    _print_report("WALK-FORWARD (calibrated, no look-ahead)", wf)
    _overall(wf)
