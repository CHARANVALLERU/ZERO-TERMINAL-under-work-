"""
ZERO AITE agent swarm — Notion-like realtime agent graph.

Roles: breeder_analyst, risk, researcher, execution.
Status machine: idle → thinking → working → done | error → idle.

Persists to ``db/aite/agents_state.json`` so the UI can visualize activity
even when Streamlit is closed (daemon / background jobs keep writing).
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from engine.aite import config as cfg
from engine.aite import store
from engine.aite.activity_log import log_activity
from engine.aite.models import AgentNode

# Requirement path (distinct from store's agents.json legacy helper) — lazy
def _agents_state_path():
    return cfg.AITE_DB_DIR / "agents_state.json"


def __getattr__(name: str):
    if name == "AGENTS_STATE_PATH":
        return _agents_state_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

ROLES = (
    "breeder_analyst",
    "risk",
    "researcher",
    "execution",
)

STATUSES = ("idle", "thinking", "working", "done", "error")

# Valid transitions (done/error may return to idle)
_TRANSITIONS: Dict[str, frozenset] = {
    "idle": frozenset({"thinking", "working", "idle"}),
    "thinking": frozenset({"working", "done", "error", "idle"}),
    "working": frozenset({"done", "error", "thinking", "working"}),
    "done": frozenset({"idle", "thinking", "working"}),
    "error": frozenset({"idle", "thinking"}),
}

_ROLE_LABELS = {
    "breeder_analyst": "Breeder Analyst",
    "risk": "Risk Officer",
    "researcher": "Market Researcher",
    "execution": "Execution Desk",
}

_lock = threading.RLock()


def _uid(prefix: str = "agt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _default_swarm() -> Dict[str, Any]:
    """Seed a four-role swarm with a root orchestrator edge layout."""
    root_id = "agt_orchestrator"
    nodes: List[Dict[str, Any]] = [
        AgentNode(
            agent_id=root_id,
            role="orchestrator",
            status="idle",
            message="AITE swarm ready",
            parent=None,
            children=[],
        ).to_dict()
    ]
    edges: List[Dict[str, str]] = []
    child_ids: List[str] = []
    for role in ROLES:
        aid = f"agt_{role}"
        child_ids.append(aid)
        nodes.append(
            AgentNode(
                agent_id=aid,
                role=role,
                status="idle",
                message=f"{_ROLE_LABELS[role]} standing by",
                parent=root_id,
                children=[],
            ).to_dict()
        )
        edges.append({"from": root_id, "to": aid, "kind": "delegates"})
    nodes[0]["children"] = child_ids
    return {
        "nodes": nodes,
        "edges": edges,
        "run_id": None,
        "updated_at": time.time(),
        "version": 1,
    }


def load_agents_state() -> Dict[str, Any]:
    """Load swarm state; seed defaults if missing/corrupt."""
    with _lock:
        data = store.read_json(_agents_state_path(), None)
        if not data or not isinstance(data, dict) or not data.get("nodes"):
            data = _default_swarm()
            store.write_json(_agents_state_path(), data)
            # Mirror into legacy store path for any older readers
            try:
                store.save_agents(data)
            except Exception:
                pass
        return data


def save_agents_state(state: Dict[str, Any]) -> bool:
    with _lock:
        state = dict(state)
        state["updated_at"] = time.time()
        ok = store.write_json(_agents_state_path(), state)
        try:
            store.save_agents(state)
        except Exception:
            pass
        return ok


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    state = load_agents_state()
    for n in state.get("nodes") or []:
        if n.get("agent_id") == agent_id:
            return n
    return None


def list_agents(role: Optional[str] = None) -> List[Dict[str, Any]]:
    state = load_agents_state()
    nodes = list(state.get("nodes") or [])
    if role:
        nodes = [n for n in nodes if n.get("role") == role]
    return nodes


def set_status(
    agent_id: str,
    status: str,
    message: str = "",
    *,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Advance an agent through the status machine and persist.
    Returns the updated node (or error stub).
    """
    status = (status or "idle").lower()
    if status not in STATUSES:
        status = "error"
        message = message or f"invalid status requested"

    with _lock:
        state = load_agents_state()
        node = None
        idx = -1
        for i, n in enumerate(state.get("nodes") or []):
            if n.get("agent_id") == agent_id:
                node = dict(n)
                idx = i
                break
        if node is None:
            return {"agent_id": agent_id, "status": "error", "message": "unknown agent"}

        prev = str(node.get("status") or "idle")
        if not force and status not in _TRANSITIONS.get(prev, frozenset({status})):
            # Soft-allow: record but mark transition note
            message = (message or "") + f" [soft-transition {prev}->{status}]"

        node["status"] = status
        if message:
            node["message"] = str(message)[:500]
        node["updated_at"] = time.time()
        state["nodes"][idx] = node
        save_agents_state(state)

    log_activity(
        node.get("message") or f"{agent_id} → {status}",
        level="AGENT",
        source="agents",
        agent_id=agent_id,
        role=node.get("role"),
        status=status,
    )
    return node


def pulse(agent_id: str, message: str, status: str = "working") -> Dict[str, Any]:
    """Convenience heartbeat update while an agent is mid-task."""
    return set_status(agent_id, status, message)


def reset_swarm(message: str = "Swarm reset") -> Dict[str, Any]:
    with _lock:
        state = _default_swarm()
        for n in state["nodes"]:
            n["message"] = message if n.get("role") == "orchestrator" else n["message"]
        save_agents_state(state)
    log_activity(message, level="AGENT", source="agents")
    return state


class AgentSwarm:
    """
    High-level orchestrator for the four-role swarm.

    Typical cycle:
        swarm = AgentSwarm()
        swarm.begin_run("breed_cycle")
        swarm.think("researcher", "Scanning NIFTY regime…")
        swarm.work("breeder_analyst", "Evolving genomes…")
        …
        swarm.finish_run()
    """

    ROLE_IDS = {r: f"agt_{r}" for r in ROLES}
    ORCH_ID = "agt_orchestrator"

    def __init__(self):
        self.state = load_agents_state()

    def begin_run(self, label: str = "run") -> str:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        with _lock:
            self.state = load_agents_state()
            self.state["run_id"] = run_id
            self.state["run_label"] = label
            save_agents_state(self.state)
        set_status(self.ORCH_ID, "working", f"Run {label} ({run_id})", force=True)
        log_activity(f"Swarm run started: {label}", level="AGENT", source="agents", run_id=run_id)
        return run_id

    def finish_run(self, ok: bool = True, message: str = "") -> Dict[str, Any]:
        msg = message or ("Run complete" if ok else "Run failed")
        set_status(self.ORCH_ID, "done" if ok else "error", msg, force=True)
        # Park workers
        for role in ROLES:
            aid = self.ROLE_IDS[role]
            cur = get_agent(aid) or {}
            if cur.get("status") in ("thinking", "working"):
                set_status(aid, "done" if ok else "error", msg[:120], force=True)
            elif cur.get("status") == "done":
                set_status(aid, "idle", "Standing by", force=True)
        with _lock:
            self.state = load_agents_state()
            self.state["last_run_id"] = self.state.get("run_id")
            self.state["run_id"] = None
            save_agents_state(self.state)
        log_activity(msg, level="AGENT" if ok else "ERROR", source="agents")
        return self.snapshot()

    def think(self, role: str, message: str) -> Dict[str, Any]:
        return set_status(self._aid(role), "thinking", message, force=True)

    def work(self, role: str, message: str) -> Dict[str, Any]:
        return set_status(self._aid(role), "working", message, force=True)

    def done(self, role: str, message: str = "Done") -> Dict[str, Any]:
        return set_status(self._aid(role), "done", message, force=True)

    def error(self, role: str, message: str) -> Dict[str, Any]:
        return set_status(self._aid(role), "error", message, force=True)

    def idle(self, role: str, message: str = "Standing by") -> Dict[str, Any]:
        return set_status(self._aid(role), "idle", message, force=True)

    def _aid(self, role: str) -> str:
        role = role.replace(" ", "_").lower()
        if role in self.ROLE_IDS:
            return self.ROLE_IDS[role]
        # Allow passing agent_id directly
        if role.startswith("agt_"):
            return role
        # Aliases
        aliases = {
            "breeder": "breeder_analyst",
            "analyst": "breeder_analyst",
            "research": "researcher",
            "exec": "execution",
            "trader": "execution",
        }
        mapped = aliases.get(role, role)
        return self.ROLE_IDS.get(mapped, f"agt_{mapped}")

    def snapshot(self) -> Dict[str, Any]:
        """UI-friendly graph payload (nodes + edges + timestamps)."""
        self.state = load_agents_state()
        return {
            "nodes": self.state.get("nodes") or [],
            "edges": self.state.get("edges") or [],
            "run_id": self.state.get("run_id"),
            "run_label": self.state.get("run_label"),
            "updated_at": self.state.get("updated_at"),
            "roles": list(ROLES),
            "statuses": list(STATUSES),
        }

    def run_pipeline(
        self,
        label: str,
        steps: List[Dict[str, Any]],
        *,
        on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a declared pipeline of {role, message, fn?} steps.
        ``fn`` if present is called while status=working; exceptions → error.
        """
        run_id = self.begin_run(label)
        results: List[Dict[str, Any]] = []
        ok = True
        try:
            for step in steps:
                role = str(step.get("role") or "researcher")
                msg = str(step.get("message") or f"{role} step")
                self.think(role, f"Planning: {msg}")
                self.work(role, msg)
                step_result: Dict[str, Any] = {"role": role, "message": msg, "ok": True}
                fn = step.get("fn")
                if callable(fn):
                    try:
                        step_result["result"] = fn()
                    except Exception as exc:
                        ok = False
                        step_result["ok"] = False
                        step_result["error"] = str(exc)[:300]
                        self.error(role, str(exc)[:200])
                        results.append(step_result)
                        if on_step:
                            on_step(step_result)
                        break
                if step_result["ok"]:
                    self.done(role, f"Completed: {msg[:80]}")
                results.append(step_result)
                if on_step:
                    on_step(step_result)
        finally:
            snap = self.finish_run(ok=ok, message=f"{label} {'ok' if ok else 'failed'}")
        snap["run_id"] = run_id
        snap["results"] = results
        snap["ok"] = ok
        return snap


def get_swarm_snapshot() -> Dict[str, Any]:
    """Module-level helper for UI polling."""
    return AgentSwarm().snapshot()


def ensure_swarm() -> Dict[str, Any]:
    """Idempotent bootstrap — call at daemon / service start."""
    return load_agents_state()


def invoke_role(role: str, action: str, **kwargs: Any) -> Dict[str, Any]:
    """
    Dispatch a real orchestra action for ``role`` (no cosmetic status-only path).

    Actions:
      researcher: compile_idea | confirm_bars
      breeder_analyst: breed_cycle
      risk: select_survivors | build_portfolio
      execution: deploy | monitor_edge
    """
    from engine.aite.orchestra import Orchestra

    orch = Orchestra()
    orch.begin(label=f"invoke:{role}:{action}")
    try:
        role_l = role.replace(" ", "_").lower()
        if role_l in ("researcher", "research") and action in ("compile_idea", "idea"):
            out = orch.researcher_compile_idea(str(kwargs.get("idea") or ""), symbol=kwargs.get("symbol"))
        elif role_l in ("breeder_analyst", "breeder", "analyst") and action in ("breed_cycle", "breed"):
            from engine.aite.pipeline import ensure_enough_bars

            symbols = list(kwargs.get("symbols") or cfg.DEFAULT_SYMBOLS)
            frames = {s: ensure_enough_bars(s) for s in symbols}
            out = orch.breeder_run_cycle(
                symbols=symbols,
                n_population=int(kwargs.get("n_population") or 32),
                generations=int(kwargs.get("generations") or 1),
                seed=kwargs.get("seed"),
                frames=frames,
                seed_genome=kwargs.get("genome"),
                persist=bool(kwargs.get("persist", True)),
            )
            # Serialize genomes for JSON-friendly return
            out = {
                **{k: v for k, v in out.items() if k not in ("survivors", "exams", "exam_by_id", "frames")},
                "survivors": [b.to_dict() for b in (out.get("survivors") or [])],
                "n_survivors": len(out.get("survivors") or []),
            }
        elif role_l in ("execution", "exec", "trader") and action in ("deploy",):
            out = orch.execution_deploy(
                bot_ids=kwargs.get("bot_ids"),
                venue=str(kwargs.get("venue") or "paper"),
            )
        elif role_l in ("execution", "exec", "trader", "risk") and action in ("monitor_edge", "monitor"):
            out = orch.execution_monitor_edge(persist=bool(kwargs.get("persist", True)))
        else:
            # Full pipeline fallback
            from engine.aite.pipeline import run_pipeline

            out = run_pipeline(**{k: v for k, v in kwargs.items() if k != "action"})
        orch.finish(ok=bool(out.get("ok", True)), message=f"{role}:{action} done")
        return out if isinstance(out, dict) else {"ok": True, "result": out}
    except Exception as exc:
        orch.finish(ok=False, message=str(exc)[:200])
        return {"ok": False, "error": str(exc)}
