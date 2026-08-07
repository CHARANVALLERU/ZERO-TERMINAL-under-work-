"""
ZERO AITE generation-cycle runner.

Thin compatibility wrapper — delegates to :mod:`engine.aite.pipeline`
(the single ALGORY-style orchestrator). Prefer ``pipeline.run_cycle``.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from engine.aite import config as cfg

ProgressCb = Optional[Callable[[Dict[str, Any]], None]]


def _clamp_survivors(n: int) -> int:
    return max(cfg.MIN_BOTS, min(cfg.MAX_BOTS, int(n)))


def run_generation_cycle(
    n_population: int = 1000,
    n_survivors: int = 20,
    generations: int | None = 1,
    symbols: List[str] | None = None,
    seed: int | None = None,
    paper_fund: float | None = None,
    progress_cb: ProgressCb = None,
    persist: bool = True,
    deploy: bool = False,
    monitor: bool = False,
    idea: str | None = None,
    venue: str = "paper",
) -> Dict[str, Any]:
    """
    One end-to-end AITE generation cycle via ``pipeline.run_pipeline``.

    Defaults keep deploy/monitor off for backward-compatible smoke tests;
    service.run_cycle enables the full ALGORY path.
    """
    from engine.aite.pipeline import run_pipeline

    n_population = max(10, int(n_population))
    n_survivors = _clamp_survivors(n_survivors)
    generations = cfg.GENERATIONS if generations is None else max(1, int(generations))

    result = run_pipeline(
        idea=idea,
        symbols=symbols,
        n_population=n_population,
        n_survivors=n_survivors,
        generations=generations,
        seed=seed,
        venue=venue,
        deploy=deploy and persist,
        monitor=monitor and persist,
        persist=persist,
        progress_cb=progress_cb,
    )
    # Preserve legacy keys expected by older UI / tests
    result.setdefault("n_generations", generations)
    result.setdefault("n_examined", (result.get("breed") or {}).get("n_examined", 0))
    result.setdefault("n_killed", (result.get("stages") or {}).get("survivors", {}).get("n_killed", 0))
    result.setdefault("promoted", [])
    result.setdefault("demoted", [])
    result.setdefault("allocations", (result.get("stages") or {}).get("portfolio", {}).get("allocations") or {})
    result.setdefault("corr_matrix", {})
    result.setdefault("rejected", [])
    result.setdefault("backtests", [])
    result.setdefault("exams", [])
    result.setdefault("logs", [])
    result.setdefault("db_dir", str(cfg.AITE_DB_DIR))
    if paper_fund is not None and persist:
        try:
            from engine.aite import store

            fund = store.load_fund()
            fund["paper_fund"] = float(paper_fund)
            store.save_fund(fund)
        except Exception:
            pass
    return result


def run_quick_cycle(
    n_population: int = 48,
    n_survivors: int = 10,
    seed: int = 42,
) -> Dict[str, Any]:
    """Small offline-friendly cycle for smoke tests / CLI demos."""
    return run_generation_cycle(
        n_population=n_population,
        n_survivors=n_survivors,
        generations=1,
        seed=seed,
        persist=True,
    )


if __name__ == "__main__":
    import json
    import sys

    pop = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    surv = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    result = run_generation_cycle(
        n_population=pop,
        n_survivors=surv,
        generations=1,
        seed=42,
    )
    print(json.dumps({
        "ok": result["ok"],
        "n_population": result["n_population"],
        "n_passed": result["n_passed"],
        "n_survivors": result["n_survivors"],
        "elapsed_sec": result["elapsed_sec"],
        "db_dir": result["db_dir"],
        "survivor_names": [s["name"] for s in result["survivors"]],
    }, indent=2))
