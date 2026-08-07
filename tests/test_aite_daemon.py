"""Smoke tests for ZERO AITE daemon / scheduler / premarket / heartbeat."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def test_import_aite_daemon_no_network():
    """Importing daemon stack must not raise and must stay lazy."""
    import engine.aite.daemon as d
    import engine.aite.heartbeat as hb
    import engine.aite.premarket as pm
    import engine.aite.scheduler as sch

    assert callable(d.start_daemon)
    assert callable(d.stop_daemon)
    assert callable(d.get_daemon_status)
    assert callable(pm.run_premarket_brief)
    assert callable(sch.run_scheduled_premarket)
    assert callable(hb.write_heartbeat)


def test_heartbeat_roundtrip(tmp_path, monkeypatch):
    from engine.aite import config as cfg
    from engine.aite import heartbeat as hb

    monkeypatch.setattr(cfg, "AITE_DB_DIR", tmp_path)
    assert hb.write_heartbeat(status="alive", pid=1, ticks=2)
    data = hb.read_heartbeat()
    assert data.get("status") == "alive"
    assert data.get("pid") == 1
    assert data.get("ticks") == 2
    assert hb.is_heartbeat_fresh(max_age_seconds=60)


def test_premarket_offline_sections(tmp_path, monkeypatch):
    """Premarket must return 8 sections and never emit buy/sell verbs."""
    from engine.aite import config as cfg
    import engine.aite.premarket as pm

    monkeypatch.setattr(cfg, "AITE_DB_DIR", tmp_path)
    (tmp_path / "premarket").mkdir(parents=True, exist_ok=True)

    # Force prediction matrix miss + daily synthetic via exam
    monkeypatch.setattr(pm, "_safe_prediction_matrix", lambda: {})

    report = pm.run_premarket_brief(
        symbols=["NIFTY 50"],
        persist=True,
        date_str="2099-01-01",
    )
    assert report["date"] == "2099-01-01"
    assert set(report["sections"].keys()) == set(pm.SECTION_KEYS)
    assert len(report["sections"]) == 8
    blob = json.dumps(report["sections"]).lower()
    for banned in (" buy ", " sell ", "\nbuy", "\nsell"):
        assert banned.strip() not in blob or "buy/sell" in blob
    # Explicit: no naked "buy" / "sell" tokens as recommendations
    import re

    assert not re.search(r"\bbuy\b", blob)
    assert not re.search(r"\bsell\b", blob)

    out = tmp_path / "premarket" / "2099-01-01.json"
    assert out.exists()


def test_daemon_start_stop_heartbeat(tmp_path, monkeypatch):
    from engine.aite import config as cfg
    from engine.aite import daemon as d

    monkeypatch.setattr(cfg, "AITE_DB_DIR", tmp_path)
    monkeypatch.setattr(cfg, "DAEMON_TICK_SECONDS", 1)

    # Avoid real premarket network during tick
    monkeypatch.setattr(
        "engine.aite.scheduler.run_scheduled_premarket",
        lambda force=False: None,
    )

    status = d.start_daemon()
    assert status.get("running") is True
    # Wait for at least one tick
    deadline = time.time() + 5
    while time.time() < deadline:
        st = d.get_daemon_status()
        if (st.get("ticks") or 0) >= 1 and (tmp_path / "heartbeat.json").exists():
            break
        time.sleep(0.2)
    assert (tmp_path / "heartbeat.json").exists()
    hb = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb.get("status") in ("alive", "stopped")

    stopped = d.stop_daemon(timeout=3)
    assert stopped.get("running") is False


def test_enqueue_job_sqlite(tmp_path, monkeypatch):
    from engine.aite import config as cfg
    from engine.aite import daemon as d

    monkeypatch.setattr(cfg, "AITE_DB_DIR", tmp_path)
    jid = d.enqueue_job("noop", {"x": 1})
    assert jid.startswith("job_")
    jobs = d.list_jobs(limit=5)
    assert any(j["id"] == jid for j in jobs)


def test_package_exports():
    import engine.aite as aite

    assert callable(aite.start_daemon)
    assert callable(aite.stop_daemon)
    assert callable(aite.get_daemon_status)
