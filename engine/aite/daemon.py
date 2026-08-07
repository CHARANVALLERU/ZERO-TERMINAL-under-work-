"""
ZERO AITE 24/7 background daemon — thread-safe, UI-independent.

Survives Streamlit close: runs in a daemon thread (or can be started from a
standalone process). Heartbeat → ``db/aite/heartbeat.json``. Job queue →
SQLite ``db/aite/aite.db`` table ``jobs`` (+ optional ``db/aite/jobs/`` files).

Public API:
  start_daemon() / stop_daemon() / get_daemon_status()
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.RLock()
_THREAD: Optional[threading.Thread] = None
_STOP = threading.Event()
_RUNTIME: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "last_tick": None,
    "ticks": 0,
    "pid": None,
    "last_error": None,
    "last_job_id": None,
}


# ── Paths / SQLite (lazy; no I/O at import) ──────────────────────────────────

def _db_path() -> Path:
    from engine.aite import config as cfg

    return cfg.AITE_DB_DIR / "aite.db"


def _jobs_dir() -> Path:
    from engine.aite import config as cfg

    d = cfg.AITE_DB_DIR / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            payload TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            result TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at)"
    )
    conn.commit()
    return conn


# ── Job queue ────────────────────────────────────────────────────────────────

def enqueue_job(kind: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """Insert a pending job; also mirrors a JSON file under db/aite/jobs/."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = time.time()
    payload = payload or {}
    try:
        with _LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "INSERT INTO jobs (id, kind, payload, status, created_at, updated_at, result) "
                    "VALUES (?, ?, ?, 'pending', ?, ?, NULL)",
                    (job_id, kind, json.dumps(payload, default=str), now, now),
                )
                conn.commit()
            finally:
                conn.close()
        # File mirror (best-effort)
        try:
            from engine.aite import store

            store.write_json(
                _jobs_dir() / f"{job_id}.json",
                {
                    "id": job_id,
                    "kind": kind,
                    "payload": payload,
                    "status": "pending",
                    "created_at": now,
                },
            )
        except Exception:
            pass
    except Exception as exc:
        with _LOCK:
            _RUNTIME["last_error"] = f"enqueue failed: {exc}"
    return job_id


def _claim_next_job() -> Optional[Dict[str, Any]]:
    with _LOCK:
        try:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                now = time.time()
                conn.execute(
                    "UPDATE jobs SET status='running', updated_at=? WHERE id=? AND status='pending'",
                    (now, row["id"]),
                )
                conn.commit()
                return dict(row)
            finally:
                conn.close()
        except Exception as exc:
            _RUNTIME["last_error"] = f"claim failed: {exc}"
            return None


def _finish_job(job_id: str, ok: bool, result: Any) -> None:
    status = "done" if ok else "failed"
    now = time.time()
    try:
        with _LOCK:
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE jobs SET status=?, updated_at=?, result=? WHERE id=?",
                    (status, now, json.dumps(result, default=str), job_id),
                )
                conn.commit()
            finally:
                conn.close()
        try:
            from engine.aite import store

            p = _jobs_dir() / f"{job_id}.json"
            data = store.read_json(p, {})
            if isinstance(data, dict):
                data["status"] = status
                data["result"] = result
                data["updated_at"] = now
                store.write_json(p, data)
        except Exception:
            pass
    except Exception:
        pass


def _ingest_file_jobs() -> None:
    """Pick up externally dropped JSON jobs in db/aite/jobs/."""
    try:
        jdir = _jobs_dir()
        for path in sorted(jdir.glob("*.json")):
            try:
                from engine.aite import store

                data = store.read_json(path, {})
                if not isinstance(data, dict):
                    continue
                if data.get("status") not in (None, "pending"):
                    continue
                if data.get("id") and str(data["id"]).startswith("job_"):
                    # Already mirrored from SQLite — skip re-insert if present
                    continue
                kind = str(data.get("kind") or data.get("type") or "noop")
                payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
                new_id = enqueue_job(kind, payload)
                data["status"] = "claimed"
                data["claimed_as"] = new_id
                store.write_json(path, data)
            except Exception:
                continue
    except Exception:
        pass


def _run_job(job: Dict[str, Any]) -> Any:
    kind = str(job.get("kind") or "")
    try:
        payload = json.loads(job.get("payload") or "{}")
    except Exception:
        payload = {}

    if kind in ("premarket", "run_premarket", "premarket_brief"):
        from engine.aite.premarket import run_premarket_brief

        return run_premarket_brief(persist=True, **{
            k: payload[k] for k in ("symbols", "date_str") if k in payload
        })

    if kind in ("breed_cycle", "breed", "run_cycle", "pipeline", "breed_seed"):
        from engine.aite.pipeline import run_breed_job
        from engine.aite.activity_log import log_activity

        log_activity(f"Daemon job {kind}", level="INFO", source="daemon", job_id=job.get("id"))
        # Flatten genome from breed_seed file drops
        if kind == "breed_seed" and "genome" in payload and "idea" not in payload:
            payload = dict(payload)
        return run_breed_job(payload)

    if kind in ("edge_monitor", "monitor", "rebalance"):
        from engine.aite.pipeline import run_edge_monitor_job

        return run_edge_monitor_job(payload)

    if kind in ("idea", "queue_idea"):
        from engine.aite.pipeline import run_pipeline

        return run_pipeline(
            idea=str(payload.get("idea") or ""),
            symbols=payload.get("symbols"),
            n_population=int(payload.get("n_population") or 32),
            generations=int(payload.get("generations") or 1),
            venue=str(payload.get("venue") or "paper"),
            deploy=bool(payload.get("deploy", True)),
            monitor=bool(payload.get("monitor", True)),
        )

    if kind in ("deploy",):
        from engine.aite.deploy import deploy_bots

        return deploy_bots(
            bot_ids=payload.get("bot_ids"),
            venue=str(payload.get("venue") or "paper"),
            note="daemon_job",
        )

    if kind in ("heartbeat", "ping"):
        return {"pong": True, "ts": time.time()}

    if kind == "noop":
        return {"ok": True}

    return {"error": f"unknown job kind: {kind}"}


# ── Tick loop ────────────────────────────────────────────────────────────────

def _tick_seconds() -> float:
    try:
        from engine.aite import config as cfg

        return float(cfg.DAEMON_TICK_SECONDS)
    except Exception:
        return 30.0


def _persist_daemon_state() -> None:
    try:
        from engine.aite import store

        with _LOCK:
            snap = {
                "running": _RUNTIME["running"],
                "started_at": _RUNTIME["started_at"],
                "last_tick": _RUNTIME["last_tick"],
                "ticks": _RUNTIME["ticks"],
                "pid": _RUNTIME["pid"],
                "last_error": _RUNTIME["last_error"],
                "last_job_id": _RUNTIME["last_job_id"],
            }
            # Preserve last_premarket from prior state
            prev = store.load_daemon_state()
            if prev.get("last_premarket") and "last_premarket" not in snap:
                snap["last_premarket"] = prev.get("last_premarket")
            # Prefer scheduler-owned key if present in prev
            if "last_premarket" in prev:
                snap.setdefault("last_premarket", prev["last_premarket"])
            store.save_daemon_state(snap)
    except Exception:
        pass


def _should_run_breed(ticks: int) -> bool:
    """True when breed interval elapsed since last_breed (or since daemon start)."""
    try:
        from engine.aite import config as cfg
        from engine.aite import store

        every = getattr(cfg, "BREED_EVERY_TICKS", None)
        if every is not None and int(every) > 0:
            return ticks > 0 and ticks % int(every) == 0
        st = store.load_daemon_state()
        last = float(st.get("last_breed") or 0)
        interval_h = float(getattr(cfg, "BREED_INTERVAL_HOURS", 6) or 6)
        interval_s = interval_h * 3600.0
        if last <= 0:
            started = float(_RUNTIME.get("started_at") or 0)
            if started <= 0:
                return False
            # First scheduled breed only after full interval from start
            # (avoids surprise heavy jobs on daemon boot / unit tests)
            return (time.time() - started) >= interval_s
        return (time.time() - last) >= interval_s
    except Exception:
        return False


def _should_run_edge(ticks: int) -> bool:
    try:
        from engine.aite import config as cfg

        every = int(getattr(cfg, "EDGE_MONITOR_EVERY_TICKS", 10) or 10)
        return ticks > 0 and ticks % max(1, every) == 0
    except Exception:
        return ticks % 10 == 0


def _one_tick() -> None:
    from engine.aite import heartbeat as hb

    with _LOCK:
        _RUNTIME["ticks"] = int(_RUNTIME.get("ticks") or 0) + 1
        _RUNTIME["last_tick"] = time.time()
        ticks = _RUNTIME["ticks"]
        pid = _RUNTIME.get("pid") or os.getpid()

    hb.write_heartbeat(
        status="alive",
        pid=pid,
        ticks=ticks,
        extra={"component": "aite_daemon"},
    )
    _persist_daemon_state()

    # Keep agent graph / heartbeat visible on disk when UI is closed
    try:
        from engine.aite.agents import ensure_swarm, set_status

        ensure_swarm()
        pending = 0
        try:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE status='pending'"
                ).fetchone()
                pending = int(row["n"] if row else 0)
            finally:
                conn.close()
        except Exception:
            pass
        set_status(
            "agt_orchestrator",
            "working" if pending else "idle",
            f"Daemon tick #{ticks} pending_jobs={pending}",
            force=True,
        )
    except Exception:
        pass

    # Scheduled 08:45 IST premarket
    try:
        from engine.aite import scheduler as sched

        pm = sched.run_scheduled_premarket(force=False)
        if pm is not None:
            try:
                from engine.aite.activity_log import log_activity

                log_activity("Premarket brief fired (08:45 IST)", level="BRIEF", source="daemon")
            except Exception:
                pass
    except Exception as exc:
        with _LOCK:
            _RUNTIME["last_error"] = f"scheduler: {exc}"

    # Scheduled breed cycle (ALGORY-style continuous evolution)
    try:
        if _should_run_breed(ticks):
            enqueue_job("breed_cycle", {
                "n_population": 32,
                "n_survivors": 20,
                "generations": 1,
                "deploy": True,
                "monitor": True,
                "scheduled": True,
            })
            try:
                from engine.aite.activity_log import log_activity

                log_activity("Scheduled breed_cycle enqueued", level="BREED", source="daemon")
            except Exception:
                pass
    except Exception as exc:
        with _LOCK:
            _RUNTIME["last_error"] = f"breed_sched: {exc}"

    # Edge monitor cadence
    try:
        if _should_run_edge(ticks):
            enqueue_job("edge_monitor", {"scheduled": True})
    except Exception as exc:
        with _LOCK:
            _RUNTIME["last_error"] = f"edge_sched: {exc}"

    # Dual-vault: flush aged PRIMARY → SECOND ZERO queue (~every 10 ticks)
    try:
        if ticks % 10 == 0:
            from engine.vault_sync import process_backup_queue
            process_backup_queue(force=False)
    except Exception as exc:
        with _LOCK:
            _RUNTIME["last_error"] = f"vault_backup: {exc}"

    # File-drop + SQLite jobs
    _ingest_file_jobs()
    job = _claim_next_job()
    if job:
        jid = job["id"]
        with _LOCK:
            _RUNTIME["last_job_id"] = jid
        try:
            result = _run_job(job)
            ok = not (
                isinstance(result, dict)
                and (result.get("error") or result.get("ok") is False)
            )
            _finish_job(jid, ok, result)
        except Exception as exc:
            _finish_job(jid, False, {"error": str(exc)})
            with _LOCK:
                _RUNTIME["last_error"] = f"job {jid}: {exc}"


def _loop() -> None:
    try:
        from engine.aite import store

        store.log_event("INFO", "AITE daemon loop started", pid=os.getpid())
    except Exception:
        pass

    while not _STOP.is_set():
        try:
            _one_tick()
        except Exception as exc:
            with _LOCK:
                _RUNTIME["last_error"] = f"tick: {exc}"
        # Interruptible sleep
        _STOP.wait(timeout=_tick_seconds())

    # Final heartbeat
    try:
        from engine.aite import heartbeat as hb

        hb.write_heartbeat(
            status="stopped",
            pid=os.getpid(),
            ticks=int(_RUNTIME.get("ticks") or 0),
            extra={"component": "aite_daemon"},
        )
    except Exception:
        pass
    with _LOCK:
        _RUNTIME["running"] = False
    _persist_daemon_state()
    try:
        from engine.aite import store

        store.log_event("INFO", "AITE daemon loop stopped")
    except Exception:
        pass


# ── Public API ───────────────────────────────────────────────────────────────

def start_daemon(*, force: bool = False) -> Dict[str, Any]:
    """
    Start the background daemon thread if not already running.
    Thread is ``daemon=True`` so it won't block process exit, but while the
    parent process lives (e.g. a dedicated runner), it keeps ticking after
    Streamlit UI teardown of other threads.
    """
    global _THREAD
    with _LOCK:
        if _RUNTIME.get("running") and _THREAD is not None and _THREAD.is_alive():
            if not force:
                return get_daemon_status()
            # force restart
            _STOP.set()
        _STOP.clear()
        _RUNTIME.update(
            {
                "running": True,
                "started_at": time.time(),
                "last_tick": None,
                "ticks": 0,
                "pid": os.getpid(),
                "last_error": None,
            }
        )
        _THREAD = threading.Thread(
            target=_loop,
            name="zero-aite-daemon",
            daemon=True,
        )
        _THREAD.start()
    _persist_daemon_state()
    # Dual-vault backup sweeper (non-blocking; idempotent)
    try:
        from engine.vault_sync import start_backup_sweeper
        start_backup_sweeper()
    except Exception:
        pass
    # Immediate heartbeat so status is fresh before first tick sleep
    try:
        from engine.aite import heartbeat as hb

        hb.write_heartbeat(
            status="alive",
            pid=os.getpid(),
            ticks=0,
            extra={"component": "aite_daemon", "phase": "start"},
        )
    except Exception:
        pass
    return get_daemon_status()


def stop_daemon(timeout: float = 5.0) -> Dict[str, Any]:
    """Signal the daemon to stop and join briefly."""
    global _THREAD
    with _LOCK:
        _STOP.set()
        thr = _THREAD
    if thr is not None and thr.is_alive():
        thr.join(timeout=timeout)
    with _LOCK:
        _RUNTIME["running"] = False
        if thr is not None and not thr.is_alive():
            _THREAD = None
    _persist_daemon_state()
    try:
        from engine.aite import heartbeat as hb

        hb.write_heartbeat(
            status="stopped",
            pid=os.getpid(),
            ticks=int(_RUNTIME.get("ticks") or 0),
            extra={"component": "aite_daemon"},
        )
    except Exception:
        pass
    return get_daemon_status()


def get_daemon_status() -> Dict[str, Any]:
    """Thread-safe status snapshot including file heartbeat age."""
    with _LOCK:
        snap = dict(_RUNTIME)
        alive = bool(
            snap.get("running")
            and _THREAD is not None
            and _THREAD.is_alive()
            and not _STOP.is_set()
        )
        snap["thread_alive"] = bool(_THREAD is not None and _THREAD.is_alive())
        snap["running"] = alive

    try:
        from engine.aite import heartbeat as hb

        snap["heartbeat"] = hb.read_heartbeat()
        snap["heartbeat_age_s"] = hb.heartbeat_age_seconds()
        snap["heartbeat_fresh"] = hb.is_heartbeat_fresh()
    except Exception:
        snap["heartbeat"] = {}
        snap["heartbeat_age_s"] = None
        snap["heartbeat_fresh"] = False

    try:
        from engine.aite import scheduler as sched

        snap["scheduler"] = sched.get_scheduler_status()
    except Exception as exc:
        snap["scheduler"] = {"error": str(exc)}

    # Pending job count (best-effort)
    try:
        with _LOCK:
            conn = _connect()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM jobs WHERE status='pending'"
                ).fetchone()
                snap["pending_jobs"] = int(row["n"] if row else 0)
            finally:
                conn.close()
    except Exception:
        snap["pending_jobs"] = None

    return snap


def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        with _LOCK:
            conn = _connect()
            try:
                rows = conn.execute(
                    "SELECT id, kind, status, created_at, updated_at FROM jobs "
                    "ORDER BY created_at DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
    except Exception:
        return []


# Module-level re-exports expected by package facade
__all__ = [
    "start_daemon",
    "stop_daemon",
    "get_daemon_status",
    "enqueue_job",
    "list_jobs",
]


if __name__ == "__main__":
    # Standalone 24/7 runner — keeps process alive after UI close:
    #   python -m engine.aite.daemon
    import signal
    import sys

    print("ZERO AITE daemon starting…", flush=True)
    print(json.dumps(start_daemon(), default=str, indent=2), flush=True)

    def _shutdown(signum, frame):  # noqa: ARG001
        print("\nStopping…", flush=True)
        print(json.dumps(stop_daemon(), default=str, indent=2), flush=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    try:
        signal.signal(signal.SIGTERM, _shutdown)
    except (AttributeError, ValueError):
        pass

    while True:
        time.sleep(60)
        st = get_daemon_status()
        print(
            f"[aite] ticks={st.get('ticks')} hb_age={st.get('heartbeat_age_s')} "
            f"pending={st.get('pending_jobs')}",
            flush=True,
        )
