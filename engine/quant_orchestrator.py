"""
ZERO Quant Orchestrator
========================

Standalone event loop that chains the multi-timeframe quant architecture:

  1. Multi-Timeframe Feature Generation
  2. XGBoost Prediction (intraday + weekly)
  3. Monte Carlo Risk Validation
  4. Genetic Rule Evaluation
  5. Paper Brokerage Execution (if risk passes)
     — or Genetic Mutation (if risk fails)

This is a standalone module — does NOT modify or replace the existing
prediction_matrix, daily_updater, or calibrator pipelines.

Run:  python -m engine.quant_orchestrator
"""

from __future__ import annotations

import sys
import os
import datetime

# Ensure project root is on path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import numpy as np
import pandas as pd

from engine.quant_config import MC_MAX_RUIN_PROBABILITY
from engine.xgboost_predictor import MultiTimeframePredictor
from engine.monte_carlo import MonteCarloRiskEngine
from engine.genetic_mutator import StrategyGeneticEngine
from engine.paper_brokerage import PaperBrokerage
from data.mtf_features import build_mtf_features


_INDICES = ["NIFTY 50", "BANKNIFTY", "SENSEX"]


def _log(tag: str, msg: str):
    """Simple timestamped console logger."""
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}")


def run_quant_cycle(indices: list | None = None, verbose: bool = True):
    """Execute one full quant cycle across all indices.

    Returns a dict of per-index results.
    """
    indices = indices or _INDICES
    results = {}

    if verbose:
        _log("INIT", "Initializing Multi-Timeframe Quant Architecture...")

    # ── 1. Initialize Components ─────────────────────────────────────────

    brokerage = PaperBrokerage.load()
    intraday_predictor = MultiTimeframePredictor(timeframe="intraday")
    weekly_predictor = MultiTimeframePredictor(timeframe="weekly")
    risk_engine = MonteCarloRiskEngine()
    genetic_engine = StrategyGeneticEngine()

    # Try loading pre-trained models
    intraday_loaded = intraday_predictor.load()
    weekly_loaded = weekly_predictor.load()

    if verbose:
        _log("INIT", f"Paper Brokerage: balance={brokerage.balance:.2f}, "
                      f"positions={len(brokerage.positions)}")
        _log("INIT", f"Intraday model loaded: {intraday_loaded}")
        _log("INIT", f"Weekly model loaded: {weekly_loaded}")

    # ── 2. Train Models (if not loaded) ──────────────────────────────────

    if not intraday_loaded:
        if verbose:
            _log("TRAIN", "Assembling intraday training data...")
        df_intra = MultiTimeframePredictor.assemble_training_data("intraday")
        if not df_intra.empty:
            result = intraday_predictor.train(df_intra)
            if verbose:
                _log("TRAIN", f"Intraday: {result}")
            if result.get("status") == "trained":
                intraday_predictor.save()
        elif verbose:
            _log("TRAIN", "No intraday training data available.")

    if not weekly_loaded:
        if verbose:
            _log("TRAIN", "Assembling weekly training data...")
        df_weekly = MultiTimeframePredictor.assemble_training_data("weekly")
        if not df_weekly.empty:
            result = weekly_predictor.train(df_weekly)
            if verbose:
                _log("TRAIN", f"Weekly: {result}")
            if result.get("status") == "trained":
                weekly_predictor.save()
        elif verbose:
            _log("TRAIN", "No weekly training data available.")

    # ── 3. Per-Index Processing Loop ─────────────────────────────────────

    if verbose:
        _log("CYCLE", "Starting per-index processing...")

    for index_name in indices:
        if verbose:
            _log("CYCLE", f"{'='*50}")
            _log("CYCLE", f"  Processing: {index_name}")

        idx_result = _process_index(
            index_name=index_name,
            intraday_predictor=intraday_predictor,
            weekly_predictor=weekly_predictor,
            risk_engine=risk_engine,
            genetic_engine=genetic_engine,
            brokerage=brokerage,
            verbose=verbose,
        )
        results[index_name] = idx_result

    # ── 4. Save State ────────────────────────────────────────────────────

    brokerage.save_log()

    if verbose:
        _log("DONE", "Quant cycle complete.")
        summary = brokerage.portfolio_summary()
        _log("PORTFOLIO", f"Balance: {summary['cash_balance']:.2f}, "
                          f"Equity: {summary['equity']:.2f}, "
                          f"Total P&L: {summary['total_pnl']:.2f}")

    return results


def _process_index(
    index_name: str,
    intraday_predictor: MultiTimeframePredictor,
    weekly_predictor: MultiTimeframePredictor,
    risk_engine: MonteCarloRiskEngine,
    genetic_engine: StrategyGeneticEngine,
    brokerage: PaperBrokerage,
    verbose: bool = True,
) -> dict:
    """Process one index through the full quant pipeline."""

    result = {"index": index_name, "timestamp": datetime.datetime.now().isoformat()}

    # ── Step 1: Multi-Timeframe Features ─────────────────────────────────

    try:
        mtf_feats = build_mtf_features(index_name)
        if verbose:
            _log("FEATURES", f"  Built {len(mtf_feats)} MTF features for {index_name}")
        result["features"] = mtf_feats
    except Exception as e:
        if verbose:
            _log("FEATURES", f"  Feature build failed: {e}")
        result["features"] = {}
        result["error"] = f"feature_build_failed: {e}"
        return result

    # Get spot price from historical data
    try:
        from data.historical import get_recent_ohlc_and_atr
        _HIST_KEYS = {"NIFTY 50": "NIFTY", "BANKNIFTY": "BANKNIFTY", "SENSEX": "SENSEX"}
        hist = get_recent_ohlc_and_atr(_HIST_KEYS.get(index_name, "NIFTY")) or {}
        spot = float(hist.get("close") or 0.0)
        atr = float(hist.get("atr") or 0.0)
    except Exception:
        spot = 0.0
        atr = 0.0

    if spot <= 0:
        if verbose:
            _log("PREDICT", f"  No spot price for {index_name} — skipping.")
        result["error"] = "no_spot_price"
        return result

    result["spot"] = spot

    # ── Step 2: XGBoost Predictions ──────────────────────────────────────

    # Build feature row for prediction
    feat_df = pd.DataFrame([mtf_feats])

    # Intraday prediction
    intraday_pred = intraday_predictor.predict_bounds(feat_df, spot)
    result["intraday_prediction"] = intraday_pred
    if verbose:
        if intraday_pred.get("status") == "predicted":
            _log("PREDICT", f"  Intraday → High: {intraday_pred['predicted_high']}, "
                            f"Low: {intraday_pred['predicted_low']}")
        else:
            _log("PREDICT", f"  Intraday → {intraday_pred.get('status', 'no_model')}")

    # Weekly prediction
    weekly_pred = weekly_predictor.predict_bounds(feat_df, spot)
    result["weekly_prediction"] = weekly_pred
    if verbose:
        if weekly_pred.get("status") == "predicted":
            _log("PREDICT", f"  Weekly   → High: {weekly_pred['predicted_high']}, "
                            f"Low: {weekly_pred['predicted_low']}")
        else:
            _log("PREDICT", f"  Weekly   → {weekly_pred.get('status', 'no_model')}")

    # ── Step 3: Monte Carlo Prediction Bounds Check ──────────────────────

    hist_vol = mtf_feats.get("hist_vol_pct", 0.0)

    if intraday_pred.get("high_pct") is not None and intraday_pred.get("low_pct") is not None:
        bounds_check = risk_engine.evaluate_prediction_risk(
            predicted_high_pct=intraday_pred["high_pct"],
            predicted_low_pct=intraday_pred["low_pct"],
            hist_vol_pct=hist_vol,
        )
        result["prediction_bounds_check"] = bounds_check
        if verbose:
            _log("BOUNDS", f"  Prediction bounds: {bounds_check['reason']} "
                          f"(ratio={bounds_check['ratio']})")

    # ── Step 4: Monte Carlo Strategy Risk ────────────────────────────────

    trade_stats = brokerage.trade_statistics()
    win_rate = trade_stats["win_rate"] or 0.5
    avg_win = trade_stats["avg_win"] or 200.0
    avg_loss = trade_stats["avg_loss"] or 150.0

    risk_metrics = risk_engine.evaluate_strategy_risk(
        win_rate=win_rate,
        avg_win=avg_win,
        avg_loss=avg_loss,
        balance=brokerage.balance,
    )
    result["risk_metrics"] = risk_metrics

    if verbose:
        _log("RISK", f"  P(ruin)={risk_metrics['probability_of_ruin']:.4f}, "
                     f"E[maxDD]={risk_metrics['expected_max_drawdown']:.4f}, "
                     f"passed={risk_metrics['passed']}")

    # ── Step 5: Execute or Evolve ────────────────────────────────────────

    if risk_metrics["passed"]:
        if verbose:
            _log("EXEC", "  Risk PASSED — executing paper trade.")

        # Simple directional logic: if intraday predicts upside > downside, buy
        high_pct = intraday_pred.get("high_pct") or 0.0
        low_pct = intraday_pred.get("low_pct") or 0.0

        if abs(high_pct) > abs(low_pct) and high_pct > 0:
            trade = brokerage.execute_order(
                symbol=index_name, side="BUY",
                quantity=1, current_price=spot,
            )
        elif abs(low_pct) > abs(high_pct) and low_pct < 0:
            # If we have a position, sell
            if brokerage.positions.get(index_name, 0) > 0:
                trade = brokerage.execute_order(
                    symbol=index_name, side="SELL",
                    quantity=1, current_price=spot,
                )
            else:
                trade = {"status": "skipped", "reason": "no position to sell, bearish bias"}
        else:
            trade = {"status": "skipped", "reason": "neutral — no clear directional bias"}

        result["trade"] = trade
        if verbose:
            _log("EXEC", f"  Trade: {trade.get('status')} — "
                        f"{trade.get('side', 'N/A')} @ {trade.get('fill_price', 'N/A')}")

    else:
        if verbose:
            _log("EVOLVE", "  Risk REJECTED — activating Genetic Mutation Engine.")

        # Load existing strategies or create initial population
        strategies, scores = genetic_engine.load_strategies()
        if not strategies:
            strategies = [genetic_engine.generate_strategy() for _ in range(4)]
            scores = [0.0] * len(strategies)

        # Evolve
        new_gen = genetic_engine.evolve(strategies, scores)
        genetic_engine.save_strategies(new_gen, [0.0] * len(new_gen))

        result["trade"] = {"status": "blocked", "reason": "risk_too_high"}
        result["mutation"] = {
            "strategies_evolved": len(new_gen),
            "sample_rule": new_gen[0][0] if new_gen and new_gen[0] else None,
        }

        if verbose:
            _log("EVOLVE", f"  Evolved {len(new_gen)} strategies. "
                          f"Sample: {new_gen[0][0] if new_gen and new_gen[0] else 'N/A'}")

    return result


if __name__ == "__main__":
    print("=" * 60)
    print("  ZERO Multi-Timeframe Quant Orchestrator")
    print("=" * 60)
    print()

    results = run_quant_cycle(verbose=True)

    print("\n" + "=" * 60)
    print("  CYCLE SUMMARY")
    print("=" * 60)
    for idx, data in results.items():
        status = "PREDICTED" if data.get("intraday_prediction", {}).get("status") == "predicted" else "BASELINE"
        trade = data.get("trade", {}).get("status", "none")
        print(f"  {idx:15s} model={status:10s} trade={trade}")
