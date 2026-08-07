"""
ZERO AITE — Automated Intelligent Trading Environment
=====================================================

Hedge-fund-grade autonomous strategy breeding, OOS examination, correlation-aware
portfolio construction (10–40 bots), MT5 paper execution, idea→live agents,
one-shot market briefs, order-flow analytics, and 08:45 IST premarket research.

Public facade: ``engine.aite.service.get_aite_service()``.
All optional deps (MetaTrader5, plotly extras) are lazy-imported.
"""
from __future__ import annotations

from typing import Any

__version__ = "1.1.0"

__all__ = [
    "get_aite_service",
    "__version__",
    # paper fund / MT5 / deploy (lazy via __getattr__)
    "PaperFund",
    "get_paper_fund",
    "MT5Adapter",
    "get_mt5_adapter",
    "mt5_package_available",
    "deploy_bots",
    "swap_bot",
    "retire_bots",
    "list_deploys",
    "active_deployments",
    # agents / brief / orderflow / idea / activity (lazy via __getattr__)
    "AgentSwarm",
    "get_swarm_snapshot",
    "ensure_swarm",
    "set_status",
    "build_brief",
    "ask_brief",
    "build_multi_brief",
    "analyze_orderflow",
    "analyze_symbol_orderflow",
    "idea_to_genome",
    "queue_idea",
    "submit_idea_and_exam",
    "log_activity",
    "read_activity",
    "tail_activity",
    # daemon / scheduler / premarket / heartbeat (lazy via __getattr__)
    "start_daemon",
    "stop_daemon",
    "get_daemon_status",
    "run_premarket_brief",
    "enqueue_job",
    # generation cycle / backtest / survivors (lazy via __getattr__)
    "run_generation_cycle",
    "run_quick_cycle",
    "run_pipeline",
    "run_cycle",
    "get_flow_progress",
    "Orchestra",
    "backtest",
    "backtest_batch",
    "manage_survivors",
    "compute_live_edge",
]


def get_aite_service():
    """Lazy accessor — never raises on import of this package."""
    from engine.aite.service import get_aite_service as _get
    return _get()


_LAZY_EXPORTS = {
    "PaperFund": ("engine.aite.paper_fund", "PaperFund"),
    "get_paper_fund": ("engine.aite.paper_fund", "get_paper_fund"),
    "MT5Adapter": ("engine.aite.mt5_adapter", "MT5Adapter"),
    "get_mt5_adapter": ("engine.aite.mt5_adapter", "get_mt5_adapter"),
    "mt5_package_available": ("engine.aite.mt5_adapter", "mt5_package_available"),
    "deploy_bots": ("engine.aite.deploy", "deploy_bots"),
    "swap_bot": ("engine.aite.deploy", "swap_bot"),
    "retire_bots": ("engine.aite.deploy", "retire_bots"),
    "list_deploys": ("engine.aite.deploy", "list_deploys"),
    "active_deployments": ("engine.aite.deploy", "active_deployments"),
    # agents / brief / orderflow / idea / activity
    "AgentSwarm": ("engine.aite.agents", "AgentSwarm"),
    "get_swarm_snapshot": ("engine.aite.agents", "get_swarm_snapshot"),
    "ensure_swarm": ("engine.aite.agents", "ensure_swarm"),
    "set_status": ("engine.aite.agents", "set_status"),
    "build_brief": ("engine.aite.brief", "build_brief"),
    "ask_brief": ("engine.aite.brief", "ask_brief"),
    "build_multi_brief": ("engine.aite.brief", "build_multi_brief"),
    "analyze_orderflow": ("engine.aite.orderflow", "analyze_orderflow"),
    "analyze_symbol_orderflow": ("engine.aite.orderflow", "analyze_symbol_orderflow"),
    "idea_to_genome": ("engine.aite.idea_agent", "idea_to_genome"),
    "queue_idea": ("engine.aite.idea_agent", "queue_idea"),
    "submit_idea_and_exam": ("engine.aite.idea_agent", "submit_idea_and_exam"),
    "log_activity": ("engine.aite.activity_log", "log_activity"),
    "read_activity": ("engine.aite.activity_log", "read_activity"),
    "tail_activity": ("engine.aite.activity_log", "tail_activity"),
    # daemon stack
    "start_daemon": ("engine.aite.daemon", "start_daemon"),
    "stop_daemon": ("engine.aite.daemon", "stop_daemon"),
    "get_daemon_status": ("engine.aite.daemon", "get_daemon_status"),
    "run_premarket_brief": ("engine.aite.premarket", "run_premarket_brief"),
    "enqueue_job": ("engine.aite.daemon", "enqueue_job"),
    # generation cycle / backtest / survivors
    "run_generation_cycle": ("engine.aite.runner", "run_generation_cycle"),
    "run_quick_cycle": ("engine.aite.runner", "run_quick_cycle"),
    "run_pipeline": ("engine.aite.pipeline", "run_pipeline"),
    "run_cycle": ("engine.aite.pipeline", "run_cycle"),
    "get_flow_progress": ("engine.aite.pipeline", "get_flow_progress"),
    "Orchestra": ("engine.aite.orchestra", "Orchestra"),
    "backtest": ("engine.aite.backtest_engine", "backtest"),
    "backtest_batch": ("engine.aite.backtest_engine", "backtest_batch"),
    "manage_survivors": ("engine.aite.survivors", "manage_survivors"),
    "compute_live_edge": ("engine.aite.survivors", "compute_live_edge"),
}


def __getattr__(name: str) -> Any:
    """PEP 562 lazy exports — keep package import free of MetaTrader5 / I/O."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    mod_path, attr = target
    import importlib
    mod = importlib.import_module(mod_path)
    val = getattr(mod, attr)
    globals()[name] = val
    return val
