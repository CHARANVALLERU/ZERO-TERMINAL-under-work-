"""
ZERO Genetic Strategy Mutator
==============================

StrategyQuant X-style evolutionary logic for dynamic strategy generation
and mutation.  Tracks which indicator-based rules work and auto-generates
technical criteria based on paper trading performance.

This module is self-contained — no coupling to the prediction pipeline or
UI.  It is called by the quant_orchestrator when Monte Carlo risk checks
reject a trade and the system needs to evolve its entry rules.

Design:
  - A "strategy" is a list of rules, each being a dict with
    {indicator, operator, threshold}.
  - Rules are scored against historical paper trading performance.
  - Underperforming strategies are mutated by replacing random rules with
    freshly generated ones from the indicator pool.
  - The best-performing strategy survives (elitism).
"""

from __future__ import annotations

import os
import json
import random
import datetime
from typing import List, Dict, Optional

from engine.quant_config import (
    GENETIC_INDICATOR_POOL,
    GENETIC_OPERATORS,
    GENETIC_THRESHOLD_MIN,
    GENETIC_THRESHOLD_MAX,
    GENETIC_MUTATION_RATE,
    GENETIC_MAX_RULES,
)

# Persistence
_STRATEGY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "db", "genetic_strategies.json"
)


class StrategyGeneticEngine:
    """Evolutionary engine for indicator-based trading rules."""

    def __init__(self, seed: int | None = None):
        self.indicator_pool = list(GENETIC_INDICATOR_POOL)
        self.operators = list(GENETIC_OPERATORS)
        self._rng = random.Random(seed)
        self._history: List[Dict] = []

    # ── Rule generation ──────────────────────────────────────────────────

    def generate_random_rule(self) -> Dict:
        """Generate a single random indicator rule."""
        return {
            "indicator": self._rng.choice(self.indicator_pool),
            "operator": self._rng.choice(self.operators),
            "threshold": round(
                self._rng.uniform(GENETIC_THRESHOLD_MIN, GENETIC_THRESHOLD_MAX), 2
            ),
        }

    def generate_strategy(self, n_rules: int | None = None) -> List[Dict]:
        """Generate a complete random strategy (list of rules)."""
        n = n_rules or self._rng.randint(1, GENETIC_MAX_RULES)
        return [self.generate_random_rule() for _ in range(n)]

    # ── Mutation ─────────────────────────────────────────────────────────

    def mutate_strategy(self, parent_strategy: List[Dict]) -> List[Dict]:
        """Evolve a strategy by mutating rules that fire below threshold.

        Each rule has a GENETIC_MUTATION_RATE probability of being replaced
        with a freshly generated one.  At least one mutation is guaranteed
        so the output always differs from the input.
        """
        if not parent_strategy:
            return self.generate_strategy()

        mutated = [dict(r) for r in parent_strategy]  # deep copy
        mutated_any = False

        for i in range(len(mutated)):
            if self._rng.random() < GENETIC_MUTATION_RATE:
                mutated[i] = self.generate_random_rule()
                mutated_any = True

        # Guarantee at least one mutation
        if not mutated_any:
            idx = self._rng.randint(0, len(mutated) - 1)
            mutated[idx] = self.generate_random_rule()

        return mutated

    def crossover(self, strategy_a: List[Dict],
                  strategy_b: List[Dict]) -> List[Dict]:
        """Single-point crossover between two strategies."""
        if not strategy_a or not strategy_b:
            return strategy_a or strategy_b or self.generate_strategy()

        # Pick a crossover point in each parent
        cut_a = self._rng.randint(0, len(strategy_a) - 1)
        cut_b = self._rng.randint(0, len(strategy_b) - 1)

        child = strategy_a[:cut_a + 1] + strategy_b[cut_b:]

        # Enforce max rules
        if len(child) > GENETIC_MAX_RULES:
            child = child[:GENETIC_MAX_RULES]

        return child

    # ── Scoring ──────────────────────────────────────────────────────────

    @staticmethod
    def score_strategy(strategy: List[Dict], trade_results: List[float]) -> float:
        """Score a strategy based on its paper trading results.

        A simple Sharpe-like metric: mean return / std of returns.
        `trade_results` is a list of per-trade P&L values.
        """
        if not trade_results or len(trade_results) < 2:
            return 0.0

        import numpy as np
        arr = np.array(trade_results, dtype=float)
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        if std <= 0:
            return mean  # all identical — degenerate case
        return round(mean / std, 4)

    # ── Evolution cycle ──────────────────────────────────────────────────

    def evolve(self, population: List[List[Dict]],
               scores: List[float],
               top_k: int = 2) -> List[List[Dict]]:
        """Run one generation of evolution.

        1. Rank by score.
        2. Keep top_k elites.
        3. Fill the rest with mutations and crossovers of elites.
        """
        if not population:
            return [self.generate_strategy() for _ in range(max(top_k, 4))]

        # Sort by score descending
        ranked = sorted(zip(scores, population), key=lambda x: x[0], reverse=True)
        elites = [s for _, s in ranked[:top_k]]

        new_pop = list(elites)  # elitism: carry over the best

        pop_size = max(len(population), top_k + 2)
        while len(new_pop) < pop_size:
            if self._rng.random() < 0.5 and len(elites) >= 2:
                # Crossover
                a = self._rng.choice(elites)
                b = self._rng.choice(elites)
                child = self.crossover(a, b)
                new_pop.append(self.mutate_strategy(child))
            else:
                # Mutate a random elite
                parent = self._rng.choice(elites)
                new_pop.append(self.mutate_strategy(parent))

        return new_pop

    # ── Persistence ──────────────────────────────────────────────────────

    def save_strategies(self, strategies: List[List[Dict]],
                        scores: Optional[List[float]] = None):
        """Save the current strategy population to disk."""
        os.makedirs(os.path.dirname(_STRATEGY_PATH), exist_ok=True)
        payload = {
            "strategies": strategies,
            "scores": scores or [],
            "saved_at": datetime.datetime.now().isoformat(),
        }
        with open(_STRATEGY_PATH, "w") as f:
            json.dump(payload, f, indent=2)

    def load_strategies(self) -> tuple:
        """Load strategies from disk. Returns (strategies, scores)."""
        if not os.path.exists(_STRATEGY_PATH):
            return [], []
        try:
            with open(_STRATEGY_PATH) as f:
                data = json.load(f)
            return data.get("strategies", []), data.get("scores", [])
        except (json.JSONDecodeError, IOError):
            return [], []


if __name__ == "__main__":
    engine = StrategyGeneticEngine(seed=42)

    print("=== Genetic Strategy Mutator ===\n")

    # Generate initial population
    pop = [engine.generate_strategy() for _ in range(4)]
    for i, strat in enumerate(pop):
        print(f"Strategy {i}: {strat}")

    # Simulate scores
    scores = [random.uniform(-1, 2) for _ in pop]
    print(f"\nScores: {[round(s, 2) for s in scores]}")

    # Evolve
    next_gen = engine.evolve(pop, scores, top_k=2)
    print(f"\nNext generation ({len(next_gen)} strategies):")
    for i, strat in enumerate(next_gen):
        print(f"  Strategy {i}: {strat}")
