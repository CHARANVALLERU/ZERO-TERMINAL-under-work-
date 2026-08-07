"""
ZERO AITE orchestra — AgentSwarm roles that CALL real pipeline stage functions.

No cosmetic sleep-and-flip. Each role method:
  1. sets agent status (thinking → working)
  2. invokes a real engine function
  3. logs handoff to activity.jsonl + agents_state.json
  4. marks done/error
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.activity_log import log_activity
from engine.aite.agents import AgentSwarm


ProgressCb = Optional[Callable[[Dict[str, Any]], None]]


class Orchestra:
    """Role-bound facade over breeding / exam / portfolio / deploy."""

    def __init__(self, swarm: Optional[AgentSwarm] = None):
        self.swarm = swarm or AgentSwarm()
        self.run_id: Optional[str] = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    def begin(self, run_id: Optional[str] = None, label: str = "orchestra") -> str:
        self.run_id = self.swarm.begin_run(label)
        if run_id:
            # Keep pipeline run_id visible on state
            state = store.read_json(
                cfg.AITE_DB_DIR / "agents_state.json", None
            ) or self.swarm.snapshot()
            if isinstance(state, dict):
                state["pipeline_run_id"] = run_id
                state["run_id"] = self.run_id
                from engine.aite.agents import save_agents_state
                save_agents_state(state)
        log_activity(
            f"Orchestra begin {label}",
            level="AGENT",
            source="orchestra",
            run_id=self.run_id,
            pipeline_run_id=run_id,
        )
        return self.run_id

    def finish(self, ok: bool = True, message: str = "") -> Dict[str, Any]:
        snap = self.swarm.finish_run(ok=ok, message=message)
        log_activity(
            message or ("Orchestra done" if ok else "Orchestra failed"),
            level="AGENT" if ok else "ERROR",
            source="orchestra",
            run_id=self.run_id,
        )
        return snap

    def handoff(self, from_role: str, to_role: str, message: str) -> None:
        """Record inter-agent handoff (status + activity + edge on graph)."""
        self.swarm.done(from_role, f"Handoff → {to_role}: {message[:80]}")
        self.swarm.think(to_role, f"Received from {from_role}: {message[:80]}")
        # Persist edge annotation
        try:
            from engine.aite.agents import load_agents_state, save_agents_state
            state = load_agents_state()
            edges = list(state.get("edges") or [])
            fid = self.swarm._aid(from_role)
            tid = self.swarm._aid(to_role)
            edges.append({
                "from": fid,
                "to": tid,
                "kind": "handoff",
                "message": message[:160],
                "ts": time.time(),
            })
            state["edges"] = edges[-60:]
            state["last_handoff"] = {
                "from": from_role,
                "to": to_role,
                "message": message[:160],
                "ts": time.time(),
            }
            save_agents_state(state)
        except Exception:
            pass
        log_activity(
            f"Handoff {from_role} → {to_role}: {message}",
            level="AGENT",
            source="orchestra",
            from_role=from_role,
            to_role=to_role,
            run_id=self.run_id,
        )

    # ── Researcher ───────────────────────────────────────────────────────

    def researcher_compile_idea(
        self,
        idea: str,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        from engine.aite.idea_agent import idea_to_genome

        self.swarm.think("researcher", f"Parsing idea: {idea[:80]}")
        self.swarm.work("researcher", "Compiling BotGenome from NL idea")
        genome = idea_to_genome(idea, symbol=symbol)
        store.upsert_bot(genome.to_dict())
        store.save_idea({
            "idea_id": f"idea_{genome.bot_id[-8:]}",
            "ts": time.time(),
            "idea": idea,
            "genome": genome.to_dict(),
            "via": "orchestra",
        })
        self.swarm.done("researcher", f"Genome {genome.name} ready")
        self.handoff("researcher", "breeder_analyst", f"Seed {genome.name}")
        log_activity(
            f"Researcher compiled {genome.name}",
            level="IDEA",
            source="orchestra",
            bot_id=genome.bot_id,
            symbol=genome.symbol,
        )
        return {"ok": True, "genome": genome.to_dict(), "idea_id": f"idea_{genome.bot_id[-8:]}"}

    def researcher_register_genome(self, genome: Any) -> Dict[str, Any]:
        self.swarm.work("researcher", f"Registering seed {genome.name}")
        store.upsert_bot(genome.to_dict())
        self.swarm.done("researcher", f"Seed {genome.bot_id} registered")
        self.handoff("researcher", "breeder_analyst", f"Inject seed {genome.name}")
        return {"ok": True, "bot_id": genome.bot_id}

    def researcher_confirm_bars(self, bar_counts: Dict[str, int]) -> None:
        msg = ", ".join(f"{s}={n}" for s, n in bar_counts.items())
        self.swarm.work("researcher", f"Confirm bars: {msg}")
        short = {s: n for s, n in bar_counts.items() if n < cfg.MIN_BARS}
        if short:
            self.swarm.error("researcher", f"insufficient_bars: {short}")
            raise RuntimeError(f"insufficient_bars: {short}")
        self.swarm.done("researcher", f"Bars OK (≥{cfg.MIN_BARS}): {msg}")
        self.handoff("researcher", "breeder_analyst", "Market frames ready")

    # ── Breeder ──────────────────────────────────────────────────────────

    def breeder_run_cycle(
        self,
        *,
        symbols: List[str],
        n_population: int,
        generations: int,
        seed: Optional[int],
        frames: Dict[str, Any],
        seed_genome: Any = None,
        progress_cb: ProgressCb = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Call Breeder.breed_cycle + attach seed; return structured breed_out."""
        from engine.aite.breeding import Breeder
        from engine.aite.exam import run_exam
        from engine.aite.models import BotGenome

        self.swarm.think("breeder_analyst", f"Plan pop={n_population} gens={generations}")
        self.swarm.work("breeder_analyst", "Evolving genomes + OOS exam")

        breeder = Breeder(seed=seed)
        # Inject seed into initial pop by monkey-patching after init
        survivors, all_exams, logs = breeder.breed_cycle(
            symbols=symbols,
            generations=generations,
            population_size=n_population,
            market_frames=frames,
            progress_cb=progress_cb,
        )

        # If seed provided, exam it and prepend if competitive
        if seed_genome is not None:
            if isinstance(seed_genome, dict):
                seed_genome = BotGenome.from_dict(seed_genome)
            df = frames.get(seed_genome.symbol)
            if df is None or getattr(df, "empty", False):
                df = next(iter(frames.values()))
            ex = run_exam(seed_genome, df)
            all_exams.append(ex)
            seed_genome._fit = ex.fitness  # type: ignore[attr-defined]
            if ex.passed:
                seed_genome.status = "exam"
            # Ensure seed in survivor list
            if all(b.bot_id != seed_genome.bot_id for b in survivors):
                survivors = [seed_genome] + list(survivors)

        exam_by_id = {}
        for ex in all_exams:
            exam_by_id[ex.bot_id] = ex
        for b in survivors:
            ex = exam_by_id.get(b.bot_id)
            if ex:
                b._fit = ex.fitness  # type: ignore[attr-defined]

        # Rank surviving elites by fitness for downstream selection.
        scored_all = sorted(
            [
                (
                    exam_by_id[b.bot_id].fitness
                    if b.bot_id in exam_by_id
                    else float(getattr(b, "_fit", 0.0) or 0.0),
                    b,
                )
                for b in {b.bot_id: b for b in survivors}.values()
            ],
            key=lambda x: x[0],
            reverse=True,
        )
        survivors = [b for _, b in scored_all]

        n_passed = sum(1 for e in all_exams if e.passed)
        self.swarm.done(
            "breeder_analyst",
            f"Breed done passed={n_passed}/{len(all_exams)} elites={len(survivors)}",
        )
        self.handoff("breeder_analyst", "risk", f"{n_passed} passed exams")
        log_activity(
            f"Breeder cycle passed={n_passed} elites={len(survivors)}",
            level="BREED",
            source="orchestra",
            n_passed=n_passed,
            n_examined=len(all_exams),
        )

        out = {
            "ok": True,
            "survivors": survivors,
            "exams": all_exams,
            "exam_by_id": exam_by_id,
            "logs": logs,
            "n_population": n_population,
            "n_examined": len(all_exams),
            "n_passed": n_passed,
            "frames": frames,
        }
        if persist:
            # Cache lightweight exam summary
            try:
                store.write_json(cfg.EXAM_CACHE_PATH, {
                    "updated_at": time.time(),
                    "n_passed": n_passed,
                    "n_examined": len(all_exams),
                })
            except Exception:
                pass
        return out

    # ── Risk ─────────────────────────────────────────────────────────────

    def risk_select_survivors(
        self,
        breed_out: Dict[str, Any],
        *,
        n_survivors: int,
        frames: Dict[str, Any],
        persist: bool = True,
    ) -> Dict[str, Any]:
        from engine.aite.backtest_engine import rank_by_backtest
        from engine.aite.survivors import manage_survivors

        self.swarm.think("risk", f"Target survivors={n_survivors}")
        self.swarm.work("risk", "OOS confirm + promote/demote/cut")

        pool = list(breed_out.get("survivors") or [])
        exam_by_id = breed_out.get("exam_by_id") or {}
        passed = [b for b in pool if exam_by_id.get(b.bot_id) and exam_by_id[b.bot_id].passed]
        # Prefer exam-passed ordering, but keep full pool for fill-to-target
        ranked_pool = (passed + [b for b in pool if b not in passed]) if passed else list(pool)
        pool = ranked_pool

        bt_cap = min(len(pool), max(n_survivors * 4, 40))
        pool_for_bt = sorted(pool, key=lambda b: getattr(b, "_fit", 0.0), reverse=True)[:bt_cap]
        ranked, bt_results = rank_by_backtest(pool_for_bt, frames=frames, top_k=None)
        if ranked:
            pool = ranked + [b for b in pool if b.bot_id not in {x.bot_id for x in ranked}]

        if persist:
            for r in bt_results[: n_survivors * 2]:
                for tr in (r.get("trades") or [])[-3:]:
                    store.log_trade(tr)

        fitness = {b.bot_id: float(getattr(b, "_fit", 0.0) or 0.0) for b in pool}
        for r in bt_results:
            m = r.get("metrics") or {}
            bid = r.get("bot_id")
            if bid:
                fitness[bid] = fitness.get(bid, 0.0) + 0.25 * float(m.get("sharpe", 0.0))

        surv_summary = manage_survivors(
            pool,
            trades=store.load_trades(500) if persist else [],
            n_target=n_survivors,
            fitness=fitness,
            persist=persist,
        )
        survivors = list(surv_summary["survivors"])
        target = max(cfg.MIN_BOTS, min(cfg.MAX_BOTS, int(n_survivors)))
        if len(survivors) < target:
            have = {b.bot_id for b in survivors}
            # Fill from full breed elites (not only exam-passed) so we always
            # land in [MIN_BOTS, MAX_BOTS] even when OOS gates are strict.
            for b in pool:
                if b.bot_id in have or b.status == "dead":
                    continue
                b.status = "alive"
                survivors.append(b)
                have.add(b.bot_id)
                if len(survivors) >= target:
                    break
        # Still short? pad with fresh random genomes examined on the same bars
        if len(survivors) < target:
            from engine.aite.breeding import Breeder
            from engine.aite.exam import run_exam

            pad = Breeder(seed=int(fitness and abs(hash(tuple(fitness))) % 10_000) or 42)
            sym = (
                survivors[0].symbol if survivors
                else (next(iter(frames.keys())) if frames else "NIFTY 50")
            )
            df = frames.get(sym)
            guard = 0
            while len(survivors) < target and guard < target * 3:
                guard += 1
                if df is None or getattr(df, "empty", True):
                    break
                g = pad.random_genome(symbol=sym, generation=0)
                ex = run_exam(g, df)
                g._fit = ex.fitness  # type: ignore[attr-defined]
                g.status = "alive"
                survivors.append(g)
                fitness[g.bot_id] = float(ex.fitness)
        survivors = survivors[:target]

        self.swarm.done("risk", f"Survivors={len(survivors)} killed={surv_summary['n_killed']}")
        log_activity(
            f"Risk selected {len(survivors)} survivors",
            level="EXAM",
            source="orchestra",
            n_survivors=len(survivors),
            n_killed=surv_summary["n_killed"],
        )
        return {
            "survivors": survivors,
            "n_killed": surv_summary["n_killed"],
            "promoted": surv_summary.get("promoted") or [],
            "demoted": surv_summary.get("demoted") or [],
            "fitness": fitness,
            "bt_results": bt_results,
        }

    def risk_build_portfolio(
        self,
        survivors: Sequence[Any],
        *,
        frames: Dict[str, Any],
        n_survivors: int,
        persist: bool = True,
        fitness: Optional[Dict[str, float]] = None,
        paper_fund: Optional[float] = None,
    ) -> Dict[str, Any]:
        from engine.aite.models import BotGenome, PortfolioState
        from engine.aite.portfolio import allocate, select_portfolio

        bots = [
            b if isinstance(b, BotGenome) else BotGenome.from_dict(b)
            for b in survivors
        ]
        self.swarm.work("risk", f"Correlation portfolio from {len(bots)} bots")
        selected, corr, rejected = select_portfolio(
            bots, target=n_survivors, frames=frames,
        )
        if persist:
            fund_data = store.load_fund()
            fund = float(
                paper_fund if paper_fund is not None
                else fund_data.get("paper_fund", cfg.DEFAULT_PAPER_FUND)
            )
        else:
            fund_data = {}
            fund = float(paper_fund if paper_fund is not None else cfg.DEFAULT_PAPER_FUND)

        fitness = fitness or {b.bot_id: float(getattr(b, "_fit", 1.0) or 1.0) for b in selected}
        allocs = allocate(selected, fund, fitness)
        state = PortfolioState(
            fund_cash=fund,
            equity=fund,
            bot_ids=[b.bot_id for b in selected],
            allocations=allocs,
            corr_matrix=corr,
            killed=[],
        )
        if persist:
            existing = {b.get("bot_id"): b for b in store.load_bots()}
            for b in selected:
                d = b.to_dict()
                d["status"] = "alive"
                existing[b.bot_id] = d
            store.save_bots(list(existing.values()))
            store.save_portfolio(state.to_dict())
            fund_data["paper_fund"] = fund
            fund_data["cash"] = fund
            fund_data["equity"] = fund
            store.save_fund(fund_data)
            for r in rejected[:20]:
                store.log_event("INFO", f"Portfolio reject: {r}")

        self.swarm.done("risk", f"Portfolio n={len(selected)}")
        self.handoff("risk", "execution", f"Deploy {len(selected)} bots")
        log_activity(
            f"Portfolio built n={len(selected)} fund={fund:,.0f}",
            level="INFO",
            source="orchestra",
            n_bots=len(selected),
        )
        return {
            "ok": True,
            "bot_ids": [b.bot_id for b in selected],
            "allocations": allocs,
            "corr_matrix": corr,
            "portfolio": state.to_dict(),
            "rejected": rejected[:30],
            "selected": selected,
        }

    # ── Execution ────────────────────────────────────────────────────────

    def execution_deploy(
        self,
        bot_ids: Optional[Sequence[str]] = None,
        venue: str = "paper",
    ) -> Dict[str, Any]:
        from engine.aite.deploy import deploy_bots

        self.swarm.think("execution", f"Venue={venue}")
        self.swarm.work("execution", f"Deploying {len(bot_ids or []) or 'portfolio'} bots")
        out = deploy_bots(bot_ids=bot_ids, venue=venue, note="orchestra_pipeline")
        if out.get("ok"):
            self.swarm.done("execution", f"Deployed {len(out.get('deployed') or [])} → {venue}")
        else:
            self.swarm.error("execution", str(out.get("error") or "deploy failed")[:160])
        log_activity(
            f"Execution deploy ok={out.get('ok')} n={len(out.get('deployed') or [])}",
            level="TRADE",
            source="orchestra",
            venue=venue,
        )
        return out

    def execution_monitor_edge(self, *, persist: bool = True) -> Dict[str, Any]:
        """Cut fading bots and optionally replace from candidate pool."""
        from engine.aite.deploy import deploy_bots, retire_bots, swap_bot
        from engine.aite.models import BotGenome
        from engine.aite.portfolio import rebalance_and_cut
        from engine.aite.survivors import compute_live_edge

        self.swarm.work("execution", "Monitoring live edge / cut-replace")
        reb = rebalance_and_cut()
        killed_ids = [k.get("bot_id") if isinstance(k, dict) else getattr(k, "bot_id", None)
                      for k in (reb.get("killed") or [])]
        killed_ids = [k for k in killed_ids if k]

        replacements: List[Dict[str, Any]] = []
        if killed_ids and persist:
            # Pull candidates to replace
            bots = [BotGenome.from_dict(b) for b in store.load_bots()]
            candidates = [
                b for b in bots
                if b.status in ("exam", "candidate", "alive") and b.bot_id not in set(killed_ids)
            ]
            candidates.sort(key=lambda b: compute_live_edge(b).get("edge_score", 0.0), reverse=True)
            port = store.load_portfolio()
            alive_ids = [str(x) for x in (port.get("bot_ids") or [])]
            for kid in killed_ids:
                try:
                    retire_bots([kid], venue="paper", note="edge_cut")
                except Exception:
                    pass
                if candidates:
                    nxt = candidates.pop(0)
                    if nxt.bot_id not in alive_ids:
                        alive_ids.append(nxt.bot_id)
                        port["bot_ids"] = alive_ids
                        store.save_portfolio(port)
                    try:
                        swap_res = swap_bot(kid, nxt.bot_id, venue="paper", note="edge_replace")
                        replacements.append(swap_res)
                    except Exception:
                        dep = deploy_bots([nxt.bot_id], venue="paper", note="edge_replace")
                        replacements.append(dep)

        self.swarm.done(
            "execution",
            f"Edge monitor kept={reb.get('kept')} killed={len(killed_ids)} replaced={len(replacements)}",
        )
        log_activity(
            f"Edge monitor kept={reb.get('kept')} killed={len(killed_ids)}",
            level="TRADE",
            source="orchestra",
            kept=reb.get("kept"),
            n_killed=len(killed_ids),
        )
        return {
            "ok": True,
            "kept": reb.get("kept"),
            "killed": reb.get("killed") or [],
            "allocations": reb.get("allocations") or {},
            "replacements": replacements,
        }


def run_agentic_cycle(**kwargs: Any) -> Dict[str, Any]:
    """Convenience: orchestra-driven pipeline (delegates to pipeline.run_pipeline)."""
    from engine.aite.pipeline import run_pipeline
    return run_pipeline(**kwargs)


__all__ = ["Orchestra", "run_agentic_cycle"]
