"""
ZERO AITE end-to-end pipeline — single orchestrator.

ALGORY-style flow (capabilities clone, not IP):
  idea → genome → breed population → OOS exam (≥252 bars) → survivors (10–40)
  → portfolio → deploy paper/MT5 → monitor edge → cut/replace → activity log

Every stage writes ``flow_progress.json`` + ``activity.jsonl``. Agent swarm
handoffs are driven by :mod:`engine.aite.orchestra` (real callables, no sleep-flips).
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.activity_log import log_activity

ProgressCb = Optional[Callable[[Dict[str, Any]], None]]

_LOCK = threading.RLock()
_FLOW: Dict[str, Any] = {
    "run_id": None,
    "stage": "idle",
    "pct": 0,
    "ok": True,
    "message": "Pipeline idle",
    "updated_at": None,
    "stages": [],
    "result_summary": {},
}

STAGES = (
    "idea",
    "genome",
    "load_bars",
    "breed",
    "exam",
    "survivors",
    "portfolio",
    "deploy",
    "monitor",
    "done",
)


def _flow_path():
    return cfg.AITE_DB_DIR / "flow_progress.json"


def get_flow_progress() -> Dict[str, Any]:
    """UI / service poller — disk + in-memory merge."""
    with _LOCK:
        mem = dict(_FLOW)
    disk = store.read_json(_flow_path(), None) or {}
    if isinstance(disk, dict) and disk.get("updated_at"):
        # Prefer fresher of the two
        if float(disk.get("updated_at") or 0) >= float(mem.get("updated_at") or 0):
            return disk
    return mem if mem.get("updated_at") else (disk or mem)


def _set_flow(
    stage: str,
    pct: int,
    message: str = "",
    *,
    run_id: Optional[str] = None,
    ok: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    with _LOCK:
        if run_id:
            _FLOW["run_id"] = run_id
        _FLOW["stage"] = stage
        _FLOW["pct"] = int(max(0, min(100, pct)))
        _FLOW["ok"] = bool(ok)
        _FLOW["message"] = message or stage
        _FLOW["updated_at"] = time.time()
        stages = list(_FLOW.get("stages") or [])
        entry = {
            "stage": stage,
            "pct": _FLOW["pct"],
            "message": _FLOW["message"],
            "ts": _FLOW["updated_at"],
            "ok": ok,
        }
        if extra:
            entry["extra"] = extra
            _FLOW["result_summary"] = {**(_FLOW.get("result_summary") or {}), **extra}
        stages.append(entry)
        # Cap history
        _FLOW["stages"] = stages[-80:]
        snap = dict(_FLOW)
    try:
        store.write_json(_flow_path(), snap)
    except Exception:
        pass
    log_activity(
        message or f"pipeline:{stage}",
        level="INFO",
        source="pipeline",
        stage=stage,
        pct=pct,
        run_id=snap.get("run_id"),
        **(extra or {}),
    )
    return snap


def _prog(cb: ProgressCb, payload: Dict[str, Any]) -> None:
    if cb:
        try:
            cb(payload)
        except Exception:
            pass


def ensure_enough_bars(
    symbol: str,
    bars: int | None = None,
    *,
    frames: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Load OHLC with ≥ TARGET_BARS (252). Retries with higher request if short.
    Never returns a frame below MIN_BARS when synthetic fallback is available.
    """
    from engine.aite.exam import load_market_frame, _synthetic_ohlcv

    need = int(bars or cfg.DEFAULT_BARS)
    need = max(need, cfg.TARGET_BARS, cfg.MIN_BARS)
    if frames and symbol in frames and len(frames[symbol]) >= cfg.MIN_BARS:
        return frames[symbol]

    df = load_market_frame(symbol, bars=need)
    if len(df) < cfg.MIN_BARS:
        # Force longer synthetic pad via second load request
        df = load_market_frame(symbol, bars=max(need, cfg.TARGET_BARS * 2))
    if len(df) < cfg.MIN_BARS:
        df = _synthetic_ohlcv(need, seed=abs(hash(symbol)) % 10_000)
        log_activity(
            f"ensure_enough_bars({symbol}): forced synthetic {len(df)} bars",
            level="WARN",
            source="pipeline",
            symbol=symbol,
        )
    if frames is not None:
        frames[symbol] = df
    return df


def run_pipeline(
    *,
    idea: Optional[str] = None,
    genome: Any = None,
    symbols: Optional[List[str]] = None,
    n_population: int = 48,
    n_survivors: int = 20,
    generations: int = 1,
    seed: Optional[int] = None,
    venue: str = "paper",
    deploy: bool = True,
    monitor: bool = True,
    persist: bool = True,
    progress_cb: ProgressCb = None,
    seed_genome: Any = None,
) -> Dict[str, Any]:
    """
    Full ALGORY-style cycle. Returns summary dict for UI / daemon / tests.

    When ``idea`` is set, researcher compiles a genome seed first.
    ``seed_genome`` / ``genome`` inject an existing BotGenome into the breed pool.
    """
    from engine.aite.models import BotGenome

    t0 = time.time()
    run_id = f"pipe_{uuid.uuid4().hex[:10]}"
    symbols = list(symbols or cfg.DEFAULT_SYMBOLS)
    n_survivors = max(cfg.MIN_BOTS, min(cfg.MAX_BOTS, int(n_survivors)))
    n_population = max(10, int(n_population))
    generations = max(1, int(generations))
    seed_bot: Optional[BotGenome] = seed_genome or genome

    # Honor persist=False — suppress ALL db/aite disk writes for this thread.
    store.set_persist_enabled(bool(persist))
    try:
        return _run_pipeline_body(
            idea=idea,
            seed_bot=seed_bot,
            symbols=symbols,
            n_population=n_population,
            n_survivors=n_survivors,
            generations=generations,
            seed=seed,
            venue=venue,
            deploy=deploy,
            monitor=monitor,
            persist=persist,
            progress_cb=progress_cb,
            run_id=run_id,
            t0=t0,
        )
    finally:
        store.set_persist_enabled(True)


def _run_pipeline_body(
    *,
    idea: Optional[str],
    seed_bot: Any,
    symbols: List[str],
    n_population: int,
    n_survivors: int,
    generations: int,
    seed: Optional[int],
    venue: str,
    deploy: bool,
    monitor: bool,
    persist: bool,
    progress_cb: ProgressCb,
    run_id: str,
    t0: float,
) -> Dict[str, Any]:
    from engine.aite.models import BotGenome
    from engine.aite.orchestra import Orchestra

    with _LOCK:
        _FLOW.clear()
        _FLOW.update({
            "run_id": run_id,
            "stage": "idea",
            "pct": 0,
            "ok": True,
            "message": "Starting pipeline",
            "updated_at": time.time(),
            "stages": [],
            "result_summary": {},
        })

    orch = Orchestra()
    orch.begin(run_id, label="pipeline")

    result: Dict[str, Any] = {
        "ok": False,
        "run_id": run_id,
        "stages": {},
        "n_survivors": 0,
        "deployed": [],
        "elapsed_sec": 0.0,
    }

    try:
        # ── 1. IDEA → GENOME ─────────────────────────────────────────────
        _set_flow("idea", 5, "Ingesting idea / seed", run_id=run_id)
        _prog(progress_cb, {"stage": "idea", "pct": 5})
        idea_rec = None
        if idea and not seed_bot:
            idea_rec = orch.researcher_compile_idea(idea, symbol=symbols[0] if symbols else None)
            seed_bot = BotGenome.from_dict(idea_rec["genome"]) if idea_rec.get("genome") else None
            result["stages"]["idea"] = {
                "idea_id": idea_rec.get("idea_id"),
                "bot_id": seed_bot.bot_id if seed_bot else None,
            }
        elif seed_bot is not None:
            if isinstance(seed_bot, dict):
                seed_bot = BotGenome.from_dict(seed_bot)
            orch.researcher_register_genome(seed_bot)
            result["stages"]["idea"] = {"bot_id": seed_bot.bot_id, "seeded": True}
        else:
            orch.handoff("researcher", "breeder_analyst", "No idea — cold-start breed")
            result["stages"]["idea"] = {"cold_start": True}

        _set_flow("genome", 12, f"Seed genome ready: {getattr(seed_bot, 'name', 'cold')}",
                  extra={"seed_bot_id": getattr(seed_bot, "bot_id", None)})

        # ── 2. LOAD BARS (≥252) ──────────────────────────────────────────
        _set_flow("load_bars", 18, f"Loading ≥{cfg.TARGET_BARS} bars for {symbols}")
        _prog(progress_cb, {"stage": "load_bars", "pct": 18})
        frames: Dict[str, Any] = {}
        bar_counts: Dict[str, int] = {}
        for sym in symbols:
            df = ensure_enough_bars(sym, frames=frames)
            bar_counts[sym] = len(df)
            if bar_counts[sym] < cfg.MIN_BARS:
                raise RuntimeError(f"insufficient_bars for {sym}: {bar_counts[sym]} < {cfg.MIN_BARS}")
        orch.researcher_confirm_bars(bar_counts)
        result["stages"]["load_bars"] = bar_counts
        _set_flow("load_bars", 25, f"Bars loaded: {bar_counts}", extra={"bar_counts": bar_counts})

        # ── 3–4. BREED + EXAM ────────────────────────────────────────────
        _set_flow("breed", 30, f"Breeding pop={n_population} gens={generations}")
        _prog(progress_cb, {"stage": "breed", "pct": 30})

        def _breed_prog(p: Dict[str, Any]) -> None:
            pct = 30 + int(0.35 * float(p.get("pct") or 0))
            _set_flow("exam", pct, f"Exam gen={p.get('generation')} {p.get('bot_name', '')}")
            _prog(progress_cb, {**p, "stage": "exam", "pct": pct})

        breed_out = orch.breeder_run_cycle(
            symbols=symbols,
            n_population=n_population,
            generations=generations,
            seed=seed,
            frames=frames,
            seed_genome=seed_bot,
            progress_cb=_breed_prog,
            persist=persist,
        )
        result["stages"]["breed"] = {
            "n_population": breed_out.get("n_population"),
            "n_passed": breed_out.get("n_passed"),
            "n_examined": breed_out.get("n_examined"),
        }
        _set_flow(
            "exam",
            65,
            f"Exam done passed={breed_out.get('n_passed')}/{breed_out.get('n_examined')}",
            extra=result["stages"]["breed"],
        )

        # ── 5. SURVIVORS ─────────────────────────────────────────────────
        _set_flow("survivors", 72, "Selecting survivors 10–40")
        _prog(progress_cb, {"stage": "survivors", "pct": 72})
        surv_out = orch.risk_select_survivors(
            breed_out,
            n_survivors=n_survivors,
            frames=frames,
            persist=persist,
        )
        survivors = surv_out.get("survivors") or []
        result["stages"]["survivors"] = {
            "n_survivors": len(survivors),
            "n_killed": surv_out.get("n_killed", 0),
            "bot_ids": [s.get("bot_id") if isinstance(s, dict) else s.bot_id for s in survivors],
        }
        _set_flow("survivors", 78, f"Survivors={len(survivors)}", extra=result["stages"]["survivors"])

        # ── 6. PORTFOLIO ─────────────────────────────────────────────────
        _set_flow("portfolio", 82, "Building correlation-aware portfolio")
        _prog(progress_cb, {"stage": "portfolio", "pct": 82})
        port_out = orch.risk_build_portfolio(
            survivors,
            frames=frames,
            n_survivors=n_survivors,
            persist=persist,
            fitness=surv_out.get("fitness") or {},
        )
        result["stages"]["portfolio"] = {
            "bot_ids": port_out.get("bot_ids") or [],
            "n_bots": len(port_out.get("bot_ids") or []),
            "allocations": port_out.get("allocations") or {},
        }
        _set_flow("portfolio", 88, f"Portfolio n={result['stages']['portfolio']['n_bots']}",
                  extra=result["stages"]["portfolio"])

        # ── 7. DEPLOY ────────────────────────────────────────────────────
        deploy_out: Dict[str, Any] = {"ok": True, "deployed": [], "skipped": True}
        if deploy and persist:
            _set_flow("deploy", 92, f"Deploying → {venue}")
            _prog(progress_cb, {"stage": "deploy", "pct": 92})
            deploy_out = orch.execution_deploy(
                bot_ids=port_out.get("bot_ids"),
                venue=venue,
            )
            result["stages"]["deploy"] = {
                "ok": deploy_out.get("ok"),
                "venue": deploy_out.get("venue"),
                "deployed": deploy_out.get("deployed") or [],
            }
            result["deployed"] = list(deploy_out.get("deployed") or [])
            _set_flow("deploy", 95, f"Deployed {len(result['deployed'])} bots",
                      extra=result["stages"]["deploy"])
        else:
            result["stages"]["deploy"] = deploy_out
            orch.handoff("risk", "execution", "Deploy skipped (persist/deploy flag)")

        # ── 8. MONITOR EDGE ──────────────────────────────────────────────
        mon_out: Dict[str, Any] = {"ok": True, "skipped": True}
        if monitor and persist:
            _set_flow("monitor", 97, "Edge monitor / cut-replace")
            _prog(progress_cb, {"stage": "monitor", "pct": 97})
            mon_out = orch.execution_monitor_edge(persist=persist)
            result["stages"]["monitor"] = mon_out
            _set_flow("monitor", 99, f"Monitor kept={mon_out.get('kept')} killed={len(mon_out.get('killed') or [])}",
                      extra={"kept": mon_out.get("kept"), "n_killed": len(mon_out.get("killed") or [])})
        else:
            result["stages"]["monitor"] = mon_out

        elapsed = round(time.time() - t0, 2)
        # Canonical book = correlation portfolio selection (order + ids must match)
        selected = list(port_out.get("selected") or survivors)
        if not selected:
            selected = list(survivors)
        result["ok"] = True
        result["n_passed"] = breed_out.get("n_passed", 0)
        result["n_population"] = n_population
        result["bar_counts"] = bar_counts
        result["survivors"] = [
            s if isinstance(s, dict) else s.to_dict() for s in selected
        ]
        result["n_survivors"] = len(result["survivors"])
        result["stages"]["survivors"]["n_survivors"] = result["n_survivors"]
        result["stages"]["survivors"]["bot_ids"] = [
            s.get("bot_id") if isinstance(s, dict) else s.bot_id for s in selected
        ]
        portfolio = dict(port_out.get("portfolio") or {})
        portfolio["bot_ids"] = [
            s.get("bot_id") if isinstance(s, dict) else getattr(s, "bot_id", None)
            for s in selected
        ]
        portfolio["allocations"] = port_out.get("allocations") or portfolio.get("allocations") or {}
        result["portfolio"] = portfolio
        result["allocations"] = portfolio.get("allocations") or {}
        result["elapsed_sec"] = elapsed
        result["breed"] = breed_out
        result["monitor"] = mon_out

        orch.finish(ok=True, message=f"Pipeline ok survivors={result['n_survivors']}")
        _set_flow("done", 100, f"Pipeline complete in {elapsed}s", ok=True,
                  extra={"n_survivors": result["n_survivors"], "elapsed_sec": elapsed})
        _prog(progress_cb, {"stage": "done", "pct": 100})

        if persist:
            daemon = store.load_daemon_state()
            daemon["last_pipeline"] = time.time()
            daemon["last_pipeline_run_id"] = run_id
            daemon["last_breed"] = time.time()
            store.save_daemon_state(daemon)

        return result

    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)[:500]
        result["elapsed_sec"] = round(time.time() - t0, 2)
        orch.finish(ok=False, message=str(exc)[:200])
        _set_flow("done", int(_FLOW.get("pct") or 0), f"Pipeline failed: {exc}", ok=False)
        log_activity(f"Pipeline failed: {exc}", level="ERROR", source="pipeline", run_id=run_id)
        return result


def run_cycle(**kwargs: Any) -> Dict[str, Any]:
    """Alias used by service / daemon — full pipeline with defaults."""
    return run_pipeline(**kwargs)


def run_breed_job(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Daemon job entry: breed (+ optional deploy/monitor)."""
    payload = payload or {}
    return run_pipeline(
        idea=payload.get("idea"),
        symbols=payload.get("symbols"),
        n_population=int(payload.get("n_population") or 48),
        n_survivors=int(payload.get("n_survivors") or cfg.TARGET_BOTS),
        generations=int(payload.get("generations") or 1),
        seed=payload.get("seed"),
        venue=str(payload.get("venue") or "paper"),
        deploy=bool(payload.get("deploy", True)),
        monitor=bool(payload.get("monitor", True)),
        persist=bool(payload.get("persist", True)),
        seed_genome=payload.get("genome"),
    )


def run_edge_monitor_job(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Daemon job: cut/replace fading bots without a full breed."""
    from engine.aite.orchestra import Orchestra

    payload = payload or {}
    orch = Orchestra()
    orch.begin(label="edge_monitor")
    try:
        out = orch.execution_monitor_edge(persist=True)
        orch.finish(ok=True, message=f"Edge monitor kept={out.get('kept')}")
        _set_flow("monitor", 100, "Edge monitor tick", ok=True, extra=out)
        return {"ok": True, **out}
    except Exception as exc:
        orch.finish(ok=False, message=str(exc)[:200])
        return {"ok": False, "error": str(exc)}


__all__ = [
    "STAGES",
    "run_pipeline",
    "run_cycle",
    "run_breed_job",
    "run_edge_monitor_job",
    "get_flow_progress",
    "ensure_enough_bars",
]
