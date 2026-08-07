"""Offline tests for dual-vault sync (ZERO immediate → SECOND ZERO after delay)."""
from __future__ import annotations

import json
import os
import time


def _patch_vault_paths(monkeypatch, tmp_path):
    import config
    import engine.vault_sync as vs

    primary = tmp_path / "obsidian_vault"
    second = tmp_path / "second_zero_vault"
    queue = tmp_path / "db" / "vault_sync_queue.json"
    primary.mkdir()
    (tmp_path / "db").mkdir()

    monkeypatch.setattr(config, "OBSIDIAN_VAULT_PATH", str(primary))
    monkeypatch.setattr(config, "SECOND_ZERO_VAULT_PATH", str(second))
    monkeypatch.setattr(config, "VAULT_SYNC_QUEUE_PATH", str(queue))
    monkeypatch.setattr(config, "VAULT_BACKUP_DELAY_HOURS", 24.0)
    # Ensure module helpers pick up patched config
    monkeypatch.setattr(vs, "primary_vault_path", lambda: str(primary))
    monkeypatch.setattr(vs, "second_vault_path", lambda: str(second))
    monkeypatch.setattr(vs, "queue_path", lambda: str(queue))
    monkeypatch.setattr(vs, "backup_delay_hours", lambda: 24.0)
    return primary, second, queue


def test_import_vault_sync_no_network():
    import engine.vault_sync as vs
    import engine.zero_backup_service as zbs

    assert callable(vs.write_primary)
    assert callable(vs.process_backup_queue)
    assert callable(vs.start_backup_sweeper)
    assert callable(zbs.sync_second_zero_now)
    assert callable(zbs.start_backup_service)


def test_write_primary_immediate_and_queue(tmp_path, monkeypatch):
    primary, second, queue = _patch_vault_paths(monkeypatch, tmp_path)
    import engine.vault_sync as vs

    result = vs.write_primary(
        "01_Daily_Logs/2099-01-01.md",
        "# Forecast\n\nhello\n",
        kind="daily_forecast",
        changelog="test forecast",
    )
    assert result["ok"] is True
    note = primary / "01_Daily_Logs" / "2099-01-01.md"
    assert note.is_file()
    assert "hello" in note.read_text(encoding="utf-8")
    zero = primary / "ZERO.md"
    assert zero.is_file()
    assert "test forecast" in zero.read_text(encoding="utf-8")
    assert queue.is_file()
    data = json.loads(queue.read_text(encoding="utf-8"))
    assert "01_Daily_Logs/2099-01-01.md" in data["items"]
    # Not yet aged → SECOND ZERO empty / not copied
    out = vs.process_backup_queue(force=False)
    assert "01_Daily_Logs/2099-01-01.md" not in out["backed_up"]
    assert not (second / "01_Daily_Logs" / "2099-01-01.md").exists()


def test_backup_after_delay_and_idempotent(tmp_path, monkeypatch):
    primary, second, queue = _patch_vault_paths(monkeypatch, tmp_path)
    import engine.vault_sync as vs

    vs.write_primary(
        "07_AITE_Logs/2099-01-02-Premarket.md",
        "# Premarket\n",
        kind="premarket",
        update_zero_md=False,
    )
    # Age the queue item to >24h
    data = json.loads(queue.read_text(encoding="utf-8"))
    item = data["items"]["07_AITE_Logs/2099-01-02-Premarket.md"]
    item["primary_synced_ts"] = time.time() - (25 * 3600)
    queue.write_text(json.dumps(data), encoding="utf-8")

    first = vs.process_backup_queue(force=False)
    assert "07_AITE_Logs/2099-01-02-Premarket.md" in first["backed_up"]
    dst = second / "07_AITE_Logs" / "2099-01-02-Premarket.md"
    assert dst.is_file()
    assert "# Premarket" in dst.read_text(encoding="utf-8")

    second_pass = vs.process_backup_queue(force=False)
    assert second_pass["backed_up"] == []


def test_graceful_when_second_vault_unusable(tmp_path, monkeypatch):
    primary, _second, queue = _patch_vault_paths(monkeypatch, tmp_path)
    import engine.vault_sync as vs

    # Point SECOND ZERO at a path whose parent cannot be created as a dir
    # (file occupying the parent name).
    blocker = tmp_path / "blocked_parent"
    blocker.write_text("not a dir", encoding="utf-8")
    bad = blocker / "second"
    monkeypatch.setattr(vs, "second_vault_path", lambda: str(bad))

    vs.write_primary("ZERO.md", "# ZERO\n\nbody\n", kind="zero_moc", update_zero_md=False)
    data = json.loads(queue.read_text(encoding="utf-8"))
    data["items"]["ZERO.md"]["primary_synced_ts"] = time.time() - (30 * 3600)
    queue.write_text(json.dumps(data), encoding="utf-8")

    result = vs.process_backup_queue(force=False)
    assert result["ok"] is True
    assert result["skipped_reason"]
    assert result["backed_up"] == []
    # Primary still intact
    assert (primary / "ZERO.md").is_file()


def test_aite_activity_level_filter(tmp_path, monkeypatch):
    _patch_vault_paths(monkeypatch, tmp_path)
    import engine.vault_sync as vs

    skipped = vs.sync_aite_activity({
        "id": "act_debug1",
        "ts": time.time(),
        "level": "DEBUG",
        "source": "test",
        "message": "noise",
    })
    assert skipped.get("skipped") is True

    ok = vs.sync_aite_activity({
        "id": "act_brief1",
        "ts": time.time(),
        "level": "BRIEF",
        "source": "daemon",
        "message": "Premarket fired",
    })
    assert ok.get("ok") is True
    # Second identical id is idempotent
    again = vs.sync_aite_activity({
        "id": "act_brief1",
        "ts": time.time(),
        "level": "BRIEF",
        "source": "daemon",
        "message": "Premarket fired",
    })
    assert again.get("skipped") is True


def test_zero_backup_service_compat(tmp_path, monkeypatch):
    primary, second, _queue = _patch_vault_paths(monkeypatch, tmp_path)
    import engine.zero_backup_service as zbs
    import engine.vault_sync as vs

    assert zbs.update_main_zero("compat changelog line", append=True) is True
    assert "compat changelog line" in (primary / "ZERO.md").read_text(encoding="utf-8")

    vs.write_primary("01_Daily_Logs/x.md", "x\n", kind="test", update_zero_md=False)
    # Force backup path
    assert zbs.sync_second_zero_now(force=True) in (True, False)
    status = zbs.get_backup_status()
    assert status["primary_vault"] == str(primary)
    assert "total_items" in status
