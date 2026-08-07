"""
ZERO AITE genetic breeding — QuantEvolve / StratEvo-inspired quality-diversity
evolution of trading bot genomes with style niches.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from engine.aite import config as cfg
from engine.aite.exam import load_market_frame, run_exam
from engine.aite.models import BotGenome, ExamResult, Rule, new_bot_name, _uid


STYLES = ("momentum", "mean_reversion", "breakout", "flow", "mixed")

_STYLE_BIAS = {
    "momentum": ("mom_10", "mom_20", "ema_spread", "macd_hist", "adx"),
    "mean_reversion": ("rsi", "bb_pct_b", "stoch_k", "cci", "williams_r"),
    "breakout": ("atr_pct", "vol_z", "adx", "ema_spread", "ret_z"),
    "flow": ("obv_slope", "vol_z", "vwap_dist", "macd_hist", "mom_10"),
    "mixed": tuple(cfg.INDICATOR_POOL),
}


class Breeder:
    """Population-based genetic algorithm for BotGenome."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed if seed is not None else cfg.SEED)
        self._seq = 0
        self.history: List[Dict] = []

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def random_rule(self, style: str = "mixed") -> Rule:
        pool = list(_STYLE_BIAS.get(style, cfg.INDICATOR_POOL))
        ind = self.rng.choice(pool)
        op = self.rng.choice(cfg.OPERATORS)
        # Sensible thresholds by indicator family
        if ind in ("rsi", "stoch_k", "bb_pct_b", "adx"):
            thr = self.rng.uniform(20, 80)
        elif ind in ("williams_r",):
            thr = self.rng.uniform(-80, -20)
        elif ind in ("cci",):
            thr = self.rng.uniform(-150, 150)
        elif ind in ("mom_10", "mom_20", "ema_spread", "vwap_dist", "atr_pct"):
            thr = self.rng.uniform(-3, 3)
        else:
            thr = self.rng.uniform(cfg.THRESHOLD_MIN, min(cfg.THRESHOLD_MAX, 5.0))
        return Rule(indicator=ind, operator=op, threshold=round(thr, 3),
                    weight=round(self.rng.uniform(0.5, 1.5), 2))

    def random_genome(
        self,
        symbol: str = "NIFTY 50",
        style: str | None = None,
        generation: int = 0,
    ) -> BotGenome:
        style = style or self.rng.choice(STYLES)
        n_rules = self.rng.randint(2, cfg.MAX_RULES)
        rules = [self.random_rule(style) for _ in range(n_rules)]
        side = self.rng.choice(["LONG", "SHORT", "BOTH", "BOTH"])
        seq = self._next_seq()
        return BotGenome(
            bot_id=_uid("bot"),
            name=new_bot_name(style, generation, seq),
            symbol=symbol,
            side_bias=side,
            rules=rules,
            stop_atr=round(self.rng.uniform(0.8, 2.5), 2),
            take_atr=round(self.rng.uniform(1.2, 4.0), 2),
            hold_bars=int(self.rng.randint(4, 30)),
            generation=generation,
            style=style,
            status="candidate",
        )

    def mutate(self, parent: BotGenome) -> BotGenome:
        child = BotGenome.from_dict(parent.to_dict())
        child.bot_id = _uid("bot")
        child.generation = parent.generation + 1
        child.parent_ids = [parent.bot_id]
        child.status = "candidate"
        child.name = new_bot_name(parent.style, child.generation, self._next_seq())

        rules = [Rule.from_dict(r.to_dict()) for r in child.rules]
        mutated_any = False
        for i in range(len(rules)):
            if self.rng.random() < cfg.MUTATION_RATE:
                rules[i] = self.random_rule(child.style)
                mutated_any = True
        if not mutated_any and rules:
            rules[self.rng.randint(0, len(rules) - 1)] = self.random_rule(child.style)

        # Structural mutations
        if self.rng.random() < 0.2 and len(rules) < cfg.MAX_RULES:
            rules.append(self.random_rule(child.style))
        if self.rng.random() < 0.15 and len(rules) > 2:
            rules.pop(self.rng.randint(0, len(rules) - 1))
        if self.rng.random() < 0.3:
            child.stop_atr = round(max(0.5, child.stop_atr * self.rng.uniform(0.8, 1.25)), 2)
        if self.rng.random() < 0.3:
            child.take_atr = round(max(0.8, child.take_atr * self.rng.uniform(0.8, 1.25)), 2)
        if self.rng.random() < 0.25:
            child.hold_bars = int(max(2, min(60, child.hold_bars + self.rng.randint(-5, 5))))
        if self.rng.random() < 0.1:
            child.side_bias = self.rng.choice(["LONG", "SHORT", "BOTH"])

        child.rules = rules
        return child

    def crossover(self, a: BotGenome, b: BotGenome) -> BotGenome:
        cut_a = self.rng.randint(0, max(0, len(a.rules) - 1)) if a.rules else 0
        cut_b = self.rng.randint(0, max(0, len(b.rules) - 1)) if b.rules else 0
        rules = list(a.rules[: cut_a + 1]) + list(b.rules[cut_b:])
        if len(rules) > cfg.MAX_RULES:
            rules = rules[: cfg.MAX_RULES]
        if not rules:
            rules = [self.random_rule()]
        style = a.style if self.rng.random() < 0.5 else b.style
        gen = max(a.generation, b.generation) + 1
        child = BotGenome(
            bot_id=_uid("bot"),
            name=new_bot_name(style, gen, self._next_seq()),
            symbol=a.symbol if self.rng.random() < 0.5 else b.symbol,
            side_bias=a.side_bias if self.rng.random() < 0.5 else b.side_bias,
            rules=[Rule.from_dict(r.to_dict() if hasattr(r, "to_dict") else r) for r in rules],
            stop_atr=round((a.stop_atr + b.stop_atr) / 2, 2),
            take_atr=round((a.take_atr + b.take_atr) / 2, 2),
            hold_bars=int((a.hold_bars + b.hold_bars) // 2),
            generation=gen,
            parent_ids=[a.bot_id, b.bot_id],
            style=style,
            status="candidate",
        )
        return child

    def initial_population(
        self,
        symbols: List[str] | None = None,
        size: int | None = None,
    ) -> List[BotGenome]:
        symbols = symbols or cfg.DEFAULT_SYMBOLS
        size = size or cfg.POPULATION_SIZE
        pop: List[BotGenome] = []
        for i in range(size):
            style = STYLES[i % len(STYLES)]
            sym = symbols[i % len(symbols)]
            pop.append(self.random_genome(symbol=sym, style=style, generation=0))
        return pop

    def breed_cycle(
        self,
        symbols: List[str] | None = None,
        generations: int | None = None,
        population_size: int | None = None,
        market_frames: Dict[str, object] | None = None,
        progress_cb=None,
    ) -> Tuple[List[BotGenome], List[ExamResult], List[str]]:
        """
        Full evolutionary cycle with OOS exam each generation.
        Returns (survivors_sorted, all_exam_results, log_lines).
        """
        generations = generations or cfg.GENERATIONS
        population_size = population_size or cfg.POPULATION_SIZE
        symbols = symbols or cfg.DEFAULT_SYMBOLS
        logs: List[str] = []
        frames = dict(market_frames or {})

        for sym in symbols:
            if sym not in frames:
                frames[sym] = load_market_frame(sym)

        pop = self.initial_population(symbols, population_size)
        all_exams: List[ExamResult] = []
        elite_by_niche: Dict[str, BotGenome] = {}

        for gen in range(generations):
            scored: List[Tuple[float, BotGenome, ExamResult]] = []
            for i, bot in enumerate(pop):
                df = frames.get(bot.symbol)
                exam = run_exam(bot, df)
                all_exams.append(exam)
                scored.append((exam.fitness, bot, exam))
                if progress_cb:
                    try:
                        progress_cb({
                            "generation": gen,
                            "bot_index": i,
                            "bot_name": bot.name,
                            "fitness": exam.fitness,
                            "passed": exam.passed,
                            "pct": int(100 * (gen * len(pop) + i + 1) / (generations * len(pop))),
                        })
                    except Exception:
                        pass

            scored.sort(key=lambda x: x[0], reverse=True)
            elites = [b for _, b, e in scored[: cfg.ELITE_K]]
            # Quality-diversity: keep best per (style, symbol) niche
            for fit, bot, exam in scored:
                niche = f"{bot.style}|{bot.symbol}"
                prev = elite_by_niche.get(niche)
                if prev is None or fit > getattr(prev, "_fit", -1e9):
                    bot._fit = fit  # type: ignore[attr-defined]
                    elite_by_niche[niche] = bot
                if exam.passed:
                    bot.status = "exam"

            logs.append(
                f"gen={gen} best_fit={scored[0][0]:.3f} "
                f"passed={sum(1 for _, _, e in scored if e.passed)}/{len(scored)}"
            )

            # Last generation: keep the full examined population for survivor
            # selection (do NOT shrink to ELITE_K — that starved MIN_BOTS=10
            # books when n_population was only slightly above 10).
            if gen == generations - 1:
                break

            new_pop: List[BotGenome] = list(elites)
            niche_elites = list(elite_by_niche.values())
            pool = elites + niche_elites if niche_elites else elites
            while len(new_pop) < population_size:
                if self.rng.random() < cfg.CROSSOVER_RATE and len(pool) >= 2:
                    a, b = self.rng.sample(pool, 2)
                    child = self.crossover(a, b)
                    child = self.mutate(child)
                else:
                    parent = self.rng.choice(pool)
                    child = self.mutate(parent)
                new_pop.append(child)
            pop = new_pop

        # Final survivors: passed exams first, then by fitness
        final: List[Tuple[float, BotGenome]] = []
        seen = set()
        for fit, bot, exam in sorted(
            [(e.fitness, next(b for f, b, e2 in scored if e2.bot_id == e.bot_id), e)
             for e in all_exams[-len(pop):]],
            key=lambda x: (x[2].passed, x[0]),
            reverse=True,
        ):
            if bot.bot_id in seen:
                continue
            seen.add(bot.bot_id)
            if exam.passed:
                bot.status = "alive"
            final.append((fit, bot))

        # Fallback ranking if list comprehension above is awkward — re-score last pop
        rescored: List[Tuple[float, BotGenome, ExamResult]] = []
        for bot in pop:
            if bot.bot_id in seen:
                # find exam
                ex = next((e for e in reversed(all_exams) if e.bot_id == bot.bot_id), None)
                if ex:
                    rescored.append((ex.fitness, bot, ex))
                continue
            df = frames.get(bot.symbol)
            ex = run_exam(bot, df)
            all_exams.append(ex)
            if ex.passed:
                bot.status = "alive"
            rescored.append((ex.fitness, bot, ex))
        rescored.sort(key=lambda x: (x[2].passed, x[0]), reverse=True)
        survivors = [b for _, b, _ in rescored]

        self.history.append({"generations": generations, "survivors": len(survivors), "logs": logs})
        return survivors, all_exams, logs


def breed_strategies(
    symbols: List[str] | None = None,
    generations: int | None = None,
    seed: int | None = None,
    progress_cb=None,
) -> Dict:
    """Public helper used by service / UI."""
    breeder = Breeder(seed=seed)
    survivors, exams, logs = breeder.breed_cycle(
        symbols=symbols,
        generations=generations,
        progress_cb=progress_cb,
    )
    return {
        "survivors": [b.to_dict() for b in survivors],
        "exams": [e.to_dict() for e in exams[-len(survivors):]],
        "logs": logs,
        "n_survivors": len(survivors),
        "n_passed": sum(1 for e in exams if e.passed),
    }
