"""
ZERO command-line interface
===========================

A dependency-light entry point for running the engine without the Streamlit
UI — useful for cron jobs, CI, debugging, and quickly checking model quality.

Usage
-----
    python cli.py predict            # run the full prediction matrix, print JSON
    python cli.py train              # retrain the adaptive calibration layer
    python cli.py backtest           # walk-forward evaluation on the feedback log
    python cli.py update             # run the full daily update cycle
    python cli.py accuracy           # baseline accuracy report from the log
"""
import sys
import json


def _predict():
    from engine.prediction_matrix import generate_prediction_matrix
    m = generate_prediction_matrix()
    for idx in ["NIFTY 50", "BANKNIFTY", "SENSEX"]:
        d = m.get(idx, {})
        print(f"\n=== {idx} ===")
        print(json.dumps(d, indent=2, default=str))


def _train():
    from engine.calibrator import retrain_and_save
    cal = retrain_and_save(verbose=True)
    committed = sum(1 for legs in cal.metrics.values()
                    for mm in legs.values() if mm.get("committed"))
    print(f"\nCommitted corrections: {committed}")


def _backtest():
    from engine.backtest import (evaluate_baseline, walk_forward,
                                  _print_report, _overall)
    _print_report("RAW BASELINE (logged predictions vs actuals)", evaluate_baseline())
    wf = walk_forward()
    _print_report("WALK-FORWARD (calibrated, no look-ahead)", wf)
    _overall(wf)


def _update():
    from engine.daily_updater import run_daily_update
    run_daily_update()


def _accuracy():
    from engine.backtest import evaluate_baseline, _print_report
    _print_report("BASELINE ACCURACY", evaluate_baseline())


_COMMANDS = {
    "predict": _predict,
    "train": _train,
    "backtest": _backtest,
    "update": _update,
    "accuracy": _accuracy,
}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] not in _COMMANDS:
        print(__doc__)
        print("Commands:", ", ".join(_COMMANDS))
        return 1
    _COMMANDS[argv[0]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
