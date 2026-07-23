"""
ZERO Monte Carlo Risk Engine
==============================

Pre-trade risk validation via stochastic simulation.  Before the paper
brokerage executes any trade idea, this engine intercepts it and checks
whether the risk profile complies with institutional limits.

Core output:
  - probability_of_ruin    : fraction of simulated paths that hit the
                              structural drawdown threshold (default 50%).
  - expected_max_drawdown  : average peak-to-trough drawdown across all
                              simulated paths.

The orchestrator gates execution on `probability_of_ruin < MC_MAX_RUIN_PROBABILITY`.
If risk is too high, the genetic mutator is invoked to evolve the strategy.
"""

from __future__ import annotations

import numpy as np

from engine.quant_config import (
    MC_SIMULATIONS,
    MC_TRADE_SEQUENCE_LENGTH,
    MC_RUIN_DRAWDOWN,
    MC_MAX_RUIN_PROBABILITY,
)


class MonteCarloRiskEngine:
    """Stochastic risk evaluator for strategy validation."""

    def __init__(self, simulations: int | None = None):
        self.simulations = simulations or MC_SIMULATIONS

    def evaluate_strategy_risk(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        balance: float,
        n_trades: int | None = None,
    ) -> dict:
        """Simulate alternative market paths using stochastic processing.

        Parameters
        ----------
        win_rate : float
            Probability of a winning trade (0.0 – 1.0).
        avg_win : float
            Average profit per winning trade (positive).
        avg_loss : float
            Average loss per losing trade (positive — will be subtracted).
        balance : float
            Starting account balance.
        n_trades : int | None
            Number of trades per simulated sequence.  Defaults to
            MC_TRADE_SEQUENCE_LENGTH.

        Returns
        -------
        dict
            probability_of_ruin, expected_max_drawdown, median_final_balance,
            percentile_5_balance, percentile_95_balance, passed.
        """
        n_trades = n_trades or MC_TRADE_SEQUENCE_LENGTH

        # Input validation
        win_rate = max(0.0, min(1.0, float(win_rate)))
        avg_win = abs(float(avg_win))
        avg_loss = abs(float(avg_loss))
        balance = float(balance)
        if balance <= 0:
            return self._fail_result("balance must be positive")

        ruin_threshold = balance * MC_RUIN_DRAWDOWN
        ruin_count = 0
        max_drawdowns = []
        final_balances = []

        for _ in range(self.simulations):
            equity_curve = [balance]

            # Draw the entire trade sequence at once (vectorised)
            outcomes = np.random.choice(
                [avg_win, -avg_loss],
                size=n_trades,
                p=[win_rate, 1.0 - win_rate],
            )

            hit_ruin = False
            for trade in outcomes:
                new_balance = equity_curve[-1] + trade
                if new_balance <= ruin_threshold:
                    hit_ruin = True
                equity_curve.append(max(0.0, new_balance))

            if hit_ruin:
                ruin_count += 1

            # Peak-to-trough drawdown
            peak = np.maximum.accumulate(equity_curve)
            drawdown = np.where(peak > 0, (peak - equity_curve) / peak, 0.0)
            max_drawdowns.append(float(np.max(drawdown)))
            final_balances.append(equity_curve[-1])

        prob_ruin = ruin_count / self.simulations
        exp_max_dd = float(np.mean(max_drawdowns))
        median_final = float(np.median(final_balances))
        p5 = float(np.percentile(final_balances, 5))
        p95 = float(np.percentile(final_balances, 95))

        return {
            "probability_of_ruin": round(prob_ruin, 4),
            "expected_max_drawdown": round(exp_max_dd, 4),
            "median_final_balance": round(median_final, 2),
            "percentile_5_balance": round(p5, 2),
            "percentile_95_balance": round(p95, 2),
            "simulations": self.simulations,
            "n_trades": n_trades,
            "ruin_threshold_pct": MC_RUIN_DRAWDOWN,
            "passed": prob_ruin < MC_MAX_RUIN_PROBABILITY,
        }

    def evaluate_prediction_risk(
        self,
        predicted_high_pct: float,
        predicted_low_pct: float,
        hist_vol_pct: float,
    ) -> dict:
        """Check if XGBoost's predicted bounds are within Monte Carlo's
        historical volatility distribution.

        If the predicted range exceeds 2× the rolling historical volatility,
        the prediction is flagged as potentially unreliable (XGBoost
        extrapolation into unseen territory).
        """
        if hist_vol_pct <= 0:
            return {"bounded": True, "reason": "no volatility data"}

        pred_range = abs(predicted_high_pct) + abs(predicted_low_pct)
        vol_range = hist_vol_pct * 2.0  # ±1σ band

        bounded = pred_range <= vol_range * 2.0  # allow up to 2× historical vol

        return {
            "bounded": bounded,
            "predicted_range_pct": round(pred_range, 6),
            "hist_vol_range_pct": round(vol_range, 6),
            "ratio": round(pred_range / vol_range, 4) if vol_range > 0 else 0.0,
            "reason": "within bounds" if bounded else "predicted range exceeds 2x historical vol",
        }

    @staticmethod
    def _fail_result(reason: str) -> dict:
        return {
            "probability_of_ruin": 1.0,
            "expected_max_drawdown": 1.0,
            "median_final_balance": 0.0,
            "percentile_5_balance": 0.0,
            "percentile_95_balance": 0.0,
            "simulations": 0,
            "n_trades": 0,
            "ruin_threshold_pct": MC_RUIN_DRAWDOWN,
            "passed": False,
            "error": reason,
        }


if __name__ == "__main__":
    engine = MonteCarloRiskEngine(simulations=5000)

    print("=== Monte Carlo Risk Engine ===\n")

    # Simulate a moderately profitable strategy
    result = engine.evaluate_strategy_risk(
        win_rate=0.55, avg_win=200, avg_loss=150, balance=50000
    )
    print("Strategy Risk Assessment:")
    for k, v in result.items():
        print(f"  {k:30s} {v}")

    print()

    # Prediction bounds check
    pred_check = engine.evaluate_prediction_risk(
        predicted_high_pct=0.015,
        predicted_low_pct=-0.012,
        hist_vol_pct=0.01,
    )
    print("Prediction Bounds Check:")
    for k, v in pred_check.items():
        print(f"  {k:30s} {v}")
