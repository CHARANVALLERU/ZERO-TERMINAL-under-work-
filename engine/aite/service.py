"""
ZERO AITE service facade — thin singleton wrapping pipeline / daemon / agents.

Never raises on construction. Public methods degrade to error dicts when
underlying modules fail. Used by ``ui.aite.panel`` via ``get_aite_service()``.

APIs:
  start / stop / start_daemon / stop_daemon
  run_cycle / breed / run_generation / run_quick_cycle
  ask_brief / queue_idea / deploy
  get_graph_state / get_flow_progress / status / get_daemon_status
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Sequence

_LOCK = threading.Lock()
_INSTANCE: Optional["AiteService"] = None


class AiteService:
    """Process-local facade over engine.aite pipeline / daemon / orchestra."""

    # ── Daemon ───────────────────────────────────────────────────────────

    def start(self, *, force: bool = False) -> Dict[str, Any]:
        """Start 24/7 daemon (alias of start_daemon)."""
        return self.start_daemon(force=force)

    def stop(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Stop daemon (alias of stop_daemon)."""
        return self.stop_daemon(timeout=timeout)

    def start_daemon(self, *, force: bool = False) -> Dict[str, Any]:
        try:
            from engine.aite.daemon import start_daemon
            from engine.aite.agents import ensure_swarm

            ensure_swarm()
            return start_daemon(force=force)
        except Exception as exc:
            return {"ok": False, "running": False, "error": str(exc)}

    def stop_daemon(self, timeout: float = 5.0) -> Dict[str, Any]:
        try:
            from engine.aite.daemon import stop_daemon

            return stop_daemon(timeout=timeout)
        except Exception as exc:
            return {"ok": False, "running": False, "error": str(exc)}

    def get_daemon_status(self) -> Dict[str, Any]:
        try:
            from engine.aite.daemon import get_daemon_status

            return get_daemon_status()
        except Exception as exc:
            return {"ok": False, "running": False, "error": str(exc)}

    def enqueue_job(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> str:
        from engine.aite.daemon import enqueue_job

        return enqueue_job(kind, payload)

    # ── Pipeline cycle ───────────────────────────────────────────────────

    def run_cycle(
        self,
        *,
        idea: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        n_population: int = 48,
        n_survivors: int = 20,
        generations: int = 1,
        seed: Optional[int] = None,
        venue: str = "paper",
        deploy: bool = True,
        monitor: bool = True,
        persist: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """End-to-end idea→breed→exam→survivors→portfolio→deploy→monitor."""
        try:
            from engine.aite.pipeline import run_pipeline

            return run_pipeline(
                idea=idea,
                symbols=symbols,
                n_population=n_population,
                n_survivors=n_survivors,
                generations=generations,
                seed=seed,
                venue=venue,
                deploy=deploy,
                monitor=monitor,
                persist=persist,
                **kwargs,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc), "n_survivors": 0}

    def breed(
        self,
        symbols: Optional[List[str]] = None,
        generations: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Run genetic breed cycle (UI control). Prefer full pipeline when needed."""
        try:
            from engine.aite.breeding import breed_strategies

            return breed_strategies(
                symbols=symbols,
                generations=generations,
                seed=seed,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc), "n_survivors": 0, "n_passed": 0}

    def run_generation(
        self,
        n_population: int = 48,
        n_survivors: int = 20,
        generations: int = 1,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            from engine.aite.runner import run_generation_cycle

            return run_generation_cycle(
                n_population=n_population,
                n_survivors=n_survivors,
                generations=generations,
                seed=seed,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc), "n_survivors": 0}

    def run_quick_cycle(self, **kwargs: Any) -> Dict[str, Any]:
        try:
            from engine.aite.runner import run_quick_cycle

            return run_quick_cycle(**kwargs)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Idea / brief / deploy ────────────────────────────────────────────

    def ask_brief(self, question: str, persist: bool = True) -> Dict[str, Any]:
        try:
            from engine.aite.brief import ask_brief

            return ask_brief(question, persist=persist)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def queue_idea(
        self,
        idea: str,
        *,
        symbol: Optional[str] = None,
        run_exam_now: bool = False,
        enqueue_breed: bool = True,
        run_pipeline_now: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Queue NL idea → genome. Optionally kick full pipeline immediately."""
        try:
            if run_pipeline_now:
                return self.run_cycle(
                    idea=idea,
                    symbols=[symbol] if symbol else None,
                    **{k: v for k, v in kwargs.items() if k in (
                        "n_population", "n_survivors", "generations", "seed",
                        "venue", "deploy", "monitor", "persist",
                    )},
                )
            from engine.aite.idea_agent import queue_idea

            rec = queue_idea(
                idea,
                symbol=symbol,
                run_exam_now=run_exam_now,
                enqueue_breed=enqueue_breed,
            )
            # Also enqueue real daemon job (not just file drop)
            if enqueue_breed:
                try:
                    self.enqueue_job("breed_cycle", {
                        "idea": idea,
                        "genome": (rec.get("genome") or {}),
                        "symbols": [symbol] if symbol else None,
                        "n_population": 48,
                        "generations": 1,
                    })
                except Exception:
                    pass
            return rec
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def deploy(
        self,
        bot_ids: Optional[Sequence[str]] = None,
        venue: str = "paper",
        *,
        note: str = "",
    ) -> Dict[str, Any]:
        try:
            from engine.aite.deploy import deploy_bots
            from engine.aite.activity_log import log_activity

            out = deploy_bots(bot_ids=bot_ids, venue=venue, note=note or "service.deploy")
            log_activity(
                f"Service deploy ok={out.get('ok')} venue={venue}",
                level="TRADE",
                source="service",
                venue=venue,
                n=len(out.get("deployed") or []),
            )
            return out
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Graph / flow / status ────────────────────────────────────────────

    def get_graph_state(self) -> Dict[str, Any]:
        """Agent swarm nodes/edges for Notion-like UI graph."""
        try:
            from engine.aite.agents import get_swarm_snapshot

            return get_swarm_snapshot()
        except Exception as exc:
            return {"nodes": [], "edges": [], "error": str(exc)}

    def get_flow_progress(self) -> Dict[str, Any]:
        """Pipeline stage progress (pct / stage / message)."""
        try:
            from engine.aite.pipeline import get_flow_progress

            return get_flow_progress()
        except Exception as exc:
            return {"stage": "error", "pct": 0, "error": str(exc)}

    def status(self) -> Dict[str, Any]:
        """Lightweight snapshot for UI status strip."""
        out: Dict[str, Any] = {"service": "aite", "ok": True}
        try:
            out["daemon"] = self.get_daemon_status()
        except Exception as exc:
            out["daemon"] = {"error": str(exc)}
        try:
            out["flow"] = self.get_flow_progress()
        except Exception as exc:
            out["flow"] = {"error": str(exc)}
        try:
            out["graph"] = {
                "run_id": (self.get_graph_state() or {}).get("run_id"),
                "n_nodes": len((self.get_graph_state() or {}).get("nodes") or []),
            }
        except Exception:
            pass
        try:
            from engine.aite import store

            bots = store.load_bots() or []
            fund = store.load_fund() or {}
            out["n_bots"] = len(bots)
            out["fund"] = fund
        except Exception as exc:
            out["store_error"] = str(exc)
        return out


def get_aite_service() -> AiteService:
    """Lazy singleton — cheap; no I/O / MT5 at construct time."""
    global _INSTANCE
    with _LOCK:
        if _INSTANCE is None:
            _INSTANCE = AiteService()
        return _INSTANCE
