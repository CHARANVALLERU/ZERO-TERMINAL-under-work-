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

Statistical rigor (BACKTEST-STATS layer):

* Naive baseline honesty check — open ≈ prev_close, high/low = prev_close ±
  prev-day ATR-proportion — scored side-by-side with the calibrated model.
* Diebold–Mariano test (HAC) of the model vs the naive baseline, plus a
  one-line verdict: "edge over naive: CONFIRMED / NOT CONFIRMED at 5%".
* PSR / DSR (Lopez de Prado) of the directional strategy returns.
* ``embargo`` parameter purges days at the walk-forward train/test boundary
  (purged K-fold style). Defaults keep every legacy behaviour intact.

Run:  ``python -m engine.backtest``
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

import numpy as np

from engine.learning_service import get_feedback_logs
from engine.calibrator import Calibrator, _LEGS
from engine.advanced_backtest import (
    MIN_STAT_N,
    deflated_sharpe_ratio,
    diebold_mariano_test,
    probabilistic_sharpe_ratio,
)

DSR_N_TRIALS: int = int(os.environ.get("ZERO_DSR_TRIALS", "10"))
"""Multiple-testing budget fed to the Deflated Sharpe Ratio."""

NAIVE_RANGE_MULT: float = float(os.environ.get("ZERO_NAIVE_RANGE_MULT", "1.0"))
"""Band multiplier applied to the naive baseline's ATR-proportion range."""

ATR_FIELD_CANDIDATES = (
    "atr", "ATR", "atr_14", "avg_true_range", "true_range",
    "avg_range", "day_range", "prev_atr",
)
"""raw_inputs keys probed for a usable ATR value (first positive hit wins)."""


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


# ─────────────────────────────────────────────
#  Naive baseline + significance helpers
# ─────────────────────────────────────────────

def _is_nan(x: Any) -> bool:
    try:
        return x is None or math.isnan(float(x))
    except (TypeError, ValueError):
        return True


def _fmt(x: Any, nd: int = 3) -> str:
    """Format a stat for the report; NaN/None render as 'NaN'."""
    if _is_nan(x):
        return "NaN"
    return f"{float(x):.{nd}f}"


def _naive_range(entry: Dict, train: List[Dict]) -> Optional[float]:
    """
    ATR-proportion range for the naive baseline, in index points.

    1. Probe the entry's own raw_inputs for an ATR-like field.
    2. Fall back to the median actual (high − low) of *training* days for the
       same index (strictly past data — no look-ahead).
    3. Return None when neither exists (caller skips high/low gracefully).
    """
    ri = entry.get("raw_inputs") or {}
    for key in ATR_FIELD_CANDIDATES:
        try:
            v = float(ri.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v * NAIVE_RANGE_MULT
    ranges = []
    for te in train:
        if te.get("index") != entry.get("index"):
            continue
        a = te.get("actual") or {}
        try:
            hi, lo = float(a.get("high")), float(a.get("low"))
        except (TypeError, ValueError):
            continue
        if hi > lo > 0:
            ranges.append(hi - lo)
    if ranges:
        return float(np.median(ranges)) * NAIVE_RANGE_MULT
    return None


def _naive_update(entry: Dict, idx: str, calibrated: Dict, train: List[Dict],
                  model_loss: Dict, naive_loss: Dict, strat_ret: Dict,
                  naive_cov: Dict) -> None:
    """
    Score one test entry against the naive baseline and append to the per-index
    series used by DM / PSR / DSR. Naive prediction: open = prev_close,
    high/low = prev_close ± ATR-proportion (skipped gracefully when no range
    estimate exists). Missing fields are skipped, never fatal.
    """
    a = entry.get("actual") or {}
    ri = entry.get("raw_inputs") or {}
    try:
        pc = float(ri.get("prev_close") or 0)
    except (TypeError, ValueError):
        return
    if pc <= 0:
        return

    naive = {"open": pc}
    rng = _naive_range(entry, train)
    if rng is not None:
        naive["high"] = pc + rng
        naive["low"] = pc - rng

    cov = naive_cov.setdefault(idx, {"full": 0, "partial": 0})
    cov["full" if rng is not None else "partial"] += 1

    m_errs: List[float] = []
    n_errs: List[float] = []
    for leg, nv in naive.items():
        try:
            act = float(a.get(leg))
            mp = float(calibrated.get("pred_" + leg))
        except (TypeError, ValueError):
            continue
        m_errs.append(abs(mp - act))
        n_errs.append(abs(nv - act))
    if m_errs:
        model_loss.setdefault(idx, []).append(float(np.mean(m_errs)))
        naive_loss.setdefault(idx, []).append(float(np.mean(n_errs)))

    # Directional strategy return: trade the predicted gap direction.
    try:
        act_c = float(a.get("close"))
        pred_c = float(calibrated.get("pred_close", calibrated.get("pred_open")))
        direction = 1.0 if pred_c > pc else (-1.0 if pred_c < pc else 0.0)
        strat_ret.setdefault(idx, []).append(direction * (act_c - pc) / pc)
    except (TypeError, ValueError):
        pass


def _significance_block(idx: str, model_loss: Dict, naive_loss: Dict,
                        strat_ret: Dict, n_trials: int) -> Dict:
    """DM + PSR + DSR + verdict for one index. Never raises on small samples."""
    ml = np.asarray(model_loss.get(idx, []), dtype=float)
    nl = np.asarray(naive_loss.get(idx, []), dtype=float)
    dm = diebold_mariano_test(ml, nl, h=1, power=2)
    rets = np.asarray(strat_ret.get(idx, []), dtype=float)
    psr = probabilistic_sharpe_ratio(rets)
    dsr = deflated_sharpe_ratio(rets, n_trials=n_trials)

    confirmed: Optional[bool]
    if dm.get("insufficient_data"):
        confirmed = None
        verdict = "edge over naive: INSUFFICIENT DATA"
    else:
        # d = model_loss − naive_loss → significantly negative ⇒ model wins
        confirmed = bool(dm["significant_5pct"] and dm["dm_stat"] < 0)
        verdict = ("edge over naive: CONFIRMED at 5%" if confirmed
                   else "edge over naive: NOT CONFIRMED at 5%")
    return {
        "dm": dm, "psr": psr, "dsr": dsr,
        "verdict": verdict, "confirmed": confirmed,
        "n_days": int(min(ml.size, nl.size)),
    }


def walk_forward(logs=None, min_train=3, embargo: int = 0,
                 n_trials: int = DSR_N_TRIALS):
    """Chronological walk-forward: train on the past, score the next day.

    Returns baseline vs calibrated MAE per index/leg plus the overall
    improvement, with zero look-ahead. `min_train` days are needed before
    the calibrator is allowed to act (below that it passes through baseline).

    `embargo` > 0 drops that many most-recent training dates before each test
    day (purged K-fold style leakage guard); the default 0 reproduces the
    legacy behaviour exactly. Each index also gains a "_stats" block with the
    Diebold–Mariano test vs the naive baseline, PSR/DSR of the directional
    strategy returns, and a one-line edge verdict.
    """
    logs = logs if logs is not None else get_feedback_logs()
    valid = [e for e in logs if _valid(e)]
    valid.sort(key=lambda e: (e.get("date", ""), e.get("index", "")))

    # group by date, keep chronological order of unique dates
    dates = sorted({e["date"] for e in valid})

    base_err = {}   # idx -> leg -> list
    cal_err = {}
    model_loss: Dict[str, List[float]] = {}
    naive_loss: Dict[str, List[float]] = {}
    strat_ret: Dict[str, List[float]] = {}
    naive_cov: Dict[str, Dict[str, int]] = {}

    for i, day in enumerate(dates):
        train = [e for e in valid if e["date"] < day]
        if embargo > 0 and train:
            tdates = sorted({e["date"] for e in train})
            purged = set(tdates[-embargo:]) if embargo < len(tdates) else set(tdates)
            train = [e for e in train if e["date"] not in purged]
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

            # Naive-baseline honesty series (DM / PSR / DSR inputs)
            _naive_update(e, idx, calibrated, train,
                          model_loss, naive_loss, strat_ret, naive_cov)

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
        report[idx]["_stats"] = _significance_block(
            idx, model_loss, naive_loss, strat_ret, n_trials)
        report[idx]["_stats"]["naive_coverage"] = naive_cov.get(
            idx, {"full": 0, "partial": 0})
    return report


def _print_stats(st: Dict) -> None:
    """One significance block under an index in the walk-forward report."""
    pad = " " * 9
    dm, psr, dsr = st["dm"], st["psr"], st["dsr"]
    cov = st.get("naive_coverage") or {}
    print(f"{pad}── significance (n={st.get('n_days', 0)} days"
          f", min_n={MIN_STAT_N}) ──")
    print(f"{pad}DM vs naive = {_fmt(dm.get('dm_stat'))}"
          f"  (p={_fmt(dm.get('p_value'), 4)}, n={dm.get('n', 0)})"
          f"  |  PSR = {_fmt(psr.get('psr'))}"
          f"  |  DSR = {_fmt(dsr.get('dsr'))}"
          f" (SR*={_fmt(dsr.get('sr_threshold'))}, trials={dsr.get('n_trials', 0)})")
    if cov:
        print(f"{pad}naive coverage: full={cov.get('full', 0)}"
              f"  partial(open-only)={cov.get('partial', 0)}")
    print(f"{pad}{st.get('verdict', '')}")


def _print_report(title, report):
    print(f"\n{'='*72}\n  {title}\n{'='*72}")
    for idx, legs in report.items():
        print(f"\n  {idx}")
        for leg, m in legs.items():
            if leg.startswith("_"):
                continue
            if "calibrated_mae" in m:
                imp = m["improvement_pct"]
                arrow = "->"
                tag = f"  ({imp:+.1f}%)" if imp is not None else ""
                print(f"    {leg:5s} n={m['n']:2d}  baseline MAE {str(m['baseline_mae']):>9s} "
                      f"{arrow} calibrated {str(m['calibrated_mae']):>9s}{tag}")
            else:
                print(f"    {leg:5s} n={m['n']:2d}  MAE={m['mae']}  MAPE={m['mape']}%")
        stats = legs.get("_stats")
        if isinstance(stats, dict):
            _print_stats(stats)


def _overall(report):
    imps = [m["improvement_pct"] for legs in report.values() for m in legs.values()
            if isinstance(m, dict) and m.get("improvement_pct") is not None]
    if imps:
        print(f"\n  >>> Mean walk-forward MAE improvement across all legs: "
              f"{np.mean(imps):+.1f}%\n")
    blocks = [legs["_stats"] for legs in report.values()
              if isinstance(legs.get("_stats"), dict)]
    if blocks:
        n_conf = sum(1 for b in blocks if b.get("confirmed"))
        psrs = [b["psr"]["psr"] for b in blocks if not _is_nan(b["psr"].get("psr"))]
        dsrs = [b["dsr"]["dsr"] for b in blocks if not _is_nan(b["dsr"].get("dsr"))]
        line = (f"  >>> Significance: {n_conf}/{len(blocks)} indices show a "
                f"confirmed edge over naive at 5%")
        if psrs:
            line += f"  |  mean PSR {np.mean(psrs):.3f}"
        if dsrs:
            line += f"  |  mean DSR {np.mean(dsrs):.3f}"
        print(line + "\n")


if __name__ == "__main__":
    base = evaluate_baseline()
    _print_report("RAW BASELINE (logged predictions vs actuals)", base)
    wf = walk_forward()
    _print_report("WALK-FORWARD (calibrated, no look-ahead)", wf)
    _overall(wf)
