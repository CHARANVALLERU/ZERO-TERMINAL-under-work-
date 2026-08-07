"""
ZERO dual-vault sync — immediate primary (ZERO) writes, 24h delayed SECOND ZERO backup.

Design
------
1. Every meaningful change is written to ``OBSIDIAN_VAULT_PATH`` first.
2. The write is recorded in ``db/vault_sync_queue.json`` with ``primary_synced_at``
   and a content hash.
3. A background sweeper (or explicit ``process_backup_queue``) copies eligible
   items to ``SECOND_ZERO_VAULT_PATH`` only after ``VAULT_BACKUP_DELAY_HOURS``
   (default 24). Idempotent: same hash is not re-copied.

Public API (preferred for all writers)
--------------------------------------
* ``write_primary(rel_path, content, *, kind, append=False, changelog=None)``
* ``notify_primary_write(rel_path, *, kind, changelog=None)``
* ``append_changelog(summary, *, kind=None, rel_path=None)``
* ``process_backup_queue(force=False)``
* ``start_backup_sweeper()`` / ``stop_backup_sweeper()``
* ``get_queue_status()``

Import-safe: no network; paths resolved lazily; never raises to callers.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ZERO_VAULT_SYNC")

_LOCK = threading.RLock()
_SWEEPER_THREAD: Optional[threading.Thread] = None
_SWEEPER_STOP = threading.Event()
_SWEEPER_STARTED = False

# Significant AITE levels mirrored to the daily AITE vault note
_AITE_VAULT_LEVELS = frozenset({
    "BRIEF", "TRADE", "BREED", "EXAM", "ERROR", "IDEA", "AGENT", "WARN",
})

_CHANGELOG_HEADING = "## 🔄 Recent Engine Updates"
_MAX_CHANGELOG_LINES = 80
_DEFAULT_SWEEP_INTERVAL_SEC = 300.0  # 5 minutes


# ── Path helpers (lazy; no I/O at import beyond config read) ─────────────────

def _cfg():
    import config as cfg
    return cfg


def primary_vault_path() -> str:
    return str(getattr(_cfg(), "OBSIDIAN_VAULT_PATH", "obsidian_vault"))


def second_vault_path() -> str:
    return str(getattr(_cfg(), "SECOND_ZERO_VAULT_PATH", "second_zero_vault"))


def queue_path() -> str:
    return str(getattr(
        _cfg(),
        "VAULT_SYNC_QUEUE_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "db", "vault_sync_queue.json"),
    ))


def backup_delay_hours() -> float:
    try:
        return float(getattr(_cfg(), "VAULT_BACKUP_DELAY_HOURS", 24.0) or 24.0)
    except (TypeError, ValueError):
        return 24.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _now_ts() -> float:
    return time.time()


def _content_hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def _normalize_rel(rel_path: str) -> str:
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    # Refuse path escape
    parts = [p for p in rel.split("/") if p and p != "."]
    if ".." in parts:
        raise ValueError(f"unsafe vault relative path: {rel_path!r}")
    return "/".join(parts)


def primary_abs(rel_path: str) -> str:
    return os.path.join(primary_vault_path(), *_normalize_rel(rel_path).split("/"))


def second_abs(rel_path: str) -> str:
    return os.path.join(second_vault_path(), *_normalize_rel(rel_path).split("/"))


def ensure_primary_structure() -> None:
    """Create standard ZERO vault folders (idempotent)."""
    root = primary_vault_path()
    dirs = [
        "01_Daily_Logs",
        "02_Mental_Models",
        "03_Cognitive_Biases",
        "04_YouTube_Knowledge",
        "04_Quantitative_Strategies",
        "05_AI_Memory",
        "06_System_Architecture",
        "07_AITE_Logs",
        "Templates",
    ]
    try:
        os.makedirs(root, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(root, d), exist_ok=True)
    except OSError as exc:
        logger.warning("ensure_primary_structure failed: %s", exc)


# ── Queue persistence ───────────────────────────────────────────────────────

def _empty_queue() -> Dict[str, Any]:
    return {"version": 1, "items": {}, "sweeper": {"last_run": None, "last_result": None}}


def _load_queue() -> Dict[str, Any]:
    path = queue_path()
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return _empty_queue()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty_queue()
        data.setdefault("version", 1)
        data.setdefault("items", {})
        data.setdefault("sweeper", {"last_run": None, "last_result": None})
        if not isinstance(data["items"], dict):
            data["items"] = {}
        return data
    except Exception as exc:
        logger.warning("vault sync queue load failed: %s", exc)
        return _empty_queue()


def _save_queue(data: Dict[str, Any]) -> bool:
    path = queue_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning("vault sync queue save failed: %s", exc)
        try:
            if os.path.exists(path + ".tmp"):
                os.remove(path + ".tmp")
        except OSError:
            pass
        return False


def _record_primary(
    rel_path: str,
    content_hash: str,
    *,
    kind: str,
) -> Dict[str, Any]:
    rel = _normalize_rel(rel_path)
    with _LOCK:
        q = _load_queue()
        items = q["items"]
        prev = items.get(rel) or {}
        prev_hash = prev.get("content_hash")
        item = {
            "rel_path": rel,
            "kind": kind or prev.get("kind") or "note",
            "primary_synced_at": _now_iso(),
            "primary_synced_ts": _now_ts(),
            "content_hash": content_hash,
            "second_synced_at": prev.get("second_synced_at"),
            "second_sync_hash": prev.get("second_sync_hash"),
        }
        # New/changed content resets SECOND ZERO eligibility clock
        if prev_hash and prev_hash != content_hash:
            item["second_synced_at"] = None
            item["second_sync_hash"] = None
        elif prev.get("second_sync_hash") == content_hash and prev.get("second_synced_at"):
            # Unchanged content already backed up — keep stamps; refresh kind only
            item["primary_synced_at"] = prev.get("primary_synced_at") or item["primary_synced_at"]
            item["primary_synced_ts"] = prev.get("primary_synced_ts") or item["primary_synced_ts"]
            item["second_synced_at"] = prev.get("second_synced_at")
            item["second_sync_hash"] = prev.get("second_sync_hash")
        items[rel] = item
        _save_queue(q)
        return dict(item)


# ── ZERO.md changelog ───────────────────────────────────────────────────────

def append_changelog(
    summary: str,
    *,
    kind: Optional[str] = None,
    rel_path: Optional[str] = None,
) -> bool:
    """Append one bullet under Recent Engine Updates in ZERO.md (deduped)."""
    summary = (summary or "").strip()
    if not summary:
        return False
    try:
        ensure_primary_structure()
        zero_path = os.path.join(primary_vault_path(), "ZERO.md")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        kind_bit = f" `{kind}`" if kind else ""
        link_bit = f" → [[{rel_path.replace('.md', '')}]]" if rel_path else ""
        bullet = f"* `{ts}`{kind_bit}: {summary}{link_bit}"

        if os.path.exists(zero_path):
            with open(zero_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            content = (
                "---\ntitle: ZERO\naliases: [ZERO, Map of Content, Home, Index]\n"
                "tags: [moc, second-brain, zero-engine]\ntype: index\n---\n\n# ZERO\n\n"
            )

        # Dedupe: skip if same summary already present recently
        if summary in content and bullet.split(": ", 1)[-1].split(" →")[0] in content:
            # softer dedupe — exact bullet body without timestamp
            body = f"{kind_bit}: {summary}".strip()
            if body and body in content:
                return True

        if _CHANGELOG_HEADING in content:
            # Insert after heading
            parts = content.split(_CHANGELOG_HEADING, 1)
            head, rest = parts[0], parts[1]
            # rest begins with optional newlines then bullets / other sections
            lines = rest.splitlines()
            # Keep leading blank line
            insert_at = 0
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            new_lines = lines[:insert_at] + [bullet] + lines[insert_at:]
            # Cap changelog bullets
            bullet_idxs = [i for i, ln in enumerate(new_lines) if ln.startswith("* `")]
            if len(bullet_idxs) > _MAX_CHANGELOG_LINES:
                # drop oldest (last in list among consecutive bullets at top)
                drop = set(bullet_idxs[_MAX_CHANGELOG_LINES:])
                new_lines = [ln for i, ln in enumerate(new_lines) if i not in drop]
            content = head + _CHANGELOG_HEADING + "\n" + "\n".join(new_lines)
            if not content.endswith("\n"):
                content += "\n"
        else:
            content = content.rstrip() + f"\n\n{_CHANGELOG_HEADING}\n\n{bullet}\n"

        with open(zero_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Queue ZERO.md itself for delayed second-zero MOC backup
        try:
            with open(zero_path, "r", encoding="utf-8") as f:
                h = _content_hash(f.read())
            _record_primary("ZERO.md", h, kind="zero_moc")
        except Exception:
            pass
        return True
    except Exception as exc:
        logger.warning("append_changelog failed: %s", exc)
        return False


# ── Primary write API ───────────────────────────────────────────────────────

def write_primary(
    rel_path: str,
    content: str,
    *,
    kind: str = "note",
    append: bool = False,
    changelog: Optional[str] = None,
    update_zero_md: bool = True,
) -> Dict[str, Any]:
    """
    Write ``content`` to the ZERO (primary) vault immediately and enqueue for
    SECOND ZERO backup after the delay. Returns a status dict; never raises.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "rel_path": rel_path,
        "primary_path": None,
        "queued": False,
    }
    try:
        rel = _normalize_rel(rel_path)
        ensure_primary_structure()
        abs_path = primary_abs(rel)
        os.makedirs(os.path.dirname(abs_path) or ".", exist_ok=True)

        final = content if content is not None else ""
        if append and os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                existing = f.read()
            if final and final in existing:
                # Idempotent append — already present
                final = existing
            else:
                sep = "" if existing.endswith("\n") or not existing else "\n"
                final = existing + sep + final
                if final and not final.endswith("\n"):
                    final += "\n"

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(final)

        h = _content_hash(final)
        item = _record_primary(rel, h, kind=kind)
        out.update({
            "ok": True,
            "rel_path": rel,
            "primary_path": abs_path,
            "queued": True,
            "content_hash": h,
            "queue_item": item,
        })

        if update_zero_md:
            note = changelog or f"Updated `{rel}`"
            append_changelog(note, kind=kind, rel_path=rel)
        return out
    except Exception as exc:
        logger.warning("write_primary(%s) failed: %s", rel_path, exc)
        out["error"] = str(exc)
        return out


def notify_primary_write(
    rel_path: str,
    *,
    kind: str = "note",
    changelog: Optional[str] = None,
    update_zero_md: bool = True,
) -> Dict[str, Any]:
    """
    Register a file already written into the primary vault (by another module)
    for changelog + 24h SECOND ZERO backup. Never raises.
    """
    out: Dict[str, Any] = {"ok": False, "rel_path": rel_path, "queued": False}
    try:
        rel = _normalize_rel(rel_path)
        abs_path = primary_abs(rel)
        if not os.path.exists(abs_path):
            out["error"] = "primary file missing"
            return out
        with open(abs_path, "rb") as f:
            h = _content_hash(f.read())
        item = _record_primary(rel, h, kind=kind)
        out.update({
            "ok": True,
            "rel_path": rel,
            "primary_path": abs_path,
            "queued": True,
            "content_hash": h,
            "queue_item": item,
        })
        if update_zero_md:
            append_changelog(changelog or f"Updated `{rel}`", kind=kind, rel_path=rel)
        return out
    except Exception as exc:
        logger.warning("notify_primary_write(%s) failed: %s", rel_path, exc)
        out["error"] = str(exc)
        return out


# ── SECOND ZERO backup ──────────────────────────────────────────────────────

def _second_vault_ready() -> bool:
    """True if SECOND ZERO path is usable (exists or can be created)."""
    path = second_vault_path()
    if not path:
        return False
    try:
        if os.path.isdir(path):
            return True
        # Create on first use when parent is writable
        parent = os.path.dirname(path) or "."
        if not os.path.isdir(parent):
            return False
        os.makedirs(path, exist_ok=True)
        return os.path.isdir(path)
    except OSError:
        return False


def _copy_to_second(rel_path: str) -> bool:
    src = primary_abs(rel_path)
    if not os.path.isfile(src):
        return False
    dst = second_abs(rel_path)
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _sync_legacy_second_zero_note() -> bool:
    """Keep in-vault ``second zero.md`` MOC as a delayed mirror of ZERO.md."""
    try:
        main = os.path.join(primary_vault_path(), "ZERO.md")
        backup = os.path.join(primary_vault_path(), "second zero.md")
        if not os.path.isfile(main):
            return False
        with open(main, "r", encoding="utf-8") as f:
            body = f.read()
        # Strip original frontmatter/title for backup header
        lines = body.splitlines(keepends=True)
        out_body: List[str] = []
        skip = True
        for line in lines:
            if line.startswith("# ZERO"):
                skip = False
                continue
            if not skip:
                out_body.append(line)
        header = (
            "---\ntitle: second zero\naliases: [second zero, Backup Index, MOC Backup]\n"
            "tags: [moc, backup, second-brain, zero-engine]\ntype: index_backup\n"
            f"last_backup_sync: '{datetime.now().date().isoformat()}'\n---\n\n"
            "# second zero (Vault Backup)\n\n"
        )
        with open(backup, "w", encoding="utf-8") as f:
            f.write(header)
            f.write("".join(out_body))
        return True
    except Exception as exc:
        logger.warning("legacy second zero.md sync failed: %s", exc)
        return False


def process_backup_queue(force: bool = False) -> Dict[str, Any]:
    """
    Copy primary vault items older than the delay window to SECOND ZERO.
    If SECOND ZERO path is missing/unwritable, returns ``skipped`` gracefully.
    """
    result: Dict[str, Any] = {
        "ok": True,
        "backed_up": [],
        "pending": [],
        "skipped_reason": None,
        "force": bool(force),
    }
    delay_h = backup_delay_hours()
    delay_s = max(0.0, delay_h) * 3600.0
    now = _now_ts()

    second_ok = _second_vault_ready()
    if not second_ok:
        result["skipped_reason"] = f"SECOND ZERO path unavailable: {second_vault_path()!r}"
        # Still allow legacy in-vault second zero.md MOC refresh when force
        if force:
            _sync_legacy_second_zero_note()
        with _LOCK:
            q = _load_queue()
            q["sweeper"]["last_run"] = _now_iso()
            q["sweeper"]["last_result"] = result
            _save_queue(q)
        return result

    with _LOCK:
        q = _load_queue()
        items = q.get("items") or {}
        for rel, item in list(items.items()):
            try:
                h = item.get("content_hash")
                already = item.get("second_sync_hash") == h and item.get("second_synced_at")
                if already and not force:
                    continue
                age = now - float(item.get("primary_synced_ts") or 0)
                if not force and age < delay_s:
                    result["pending"].append({
                        "rel_path": rel,
                        "hours_remaining": round((delay_s - age) / 3600.0, 2),
                    })
                    continue
                src = primary_abs(rel)
                if not os.path.isfile(src):
                    continue
                # Refresh hash from disk
                with open(src, "rb") as f:
                    disk_h = _content_hash(f.read())
                if not _copy_to_second(rel):
                    continue
                item["content_hash"] = disk_h
                item["second_synced_at"] = _now_iso()
                item["second_sync_hash"] = disk_h
                items[rel] = item
                result["backed_up"].append(rel)
                if rel == "ZERO.md":
                    _sync_legacy_second_zero_note()
            except Exception as exc:
                logger.warning("backup item %s failed: %s", rel, exc)
        q["items"] = items
        q["sweeper"]["last_run"] = _now_iso()
        q["sweeper"]["last_result"] = {
            "backed_up": list(result["backed_up"]),
            "pending_count": len(result["pending"]),
            "force": bool(force),
        }
        _save_queue(q)
    return result


def get_queue_status() -> Dict[str, Any]:
    with _LOCK:
        q = _load_queue()
    items = q.get("items") or {}
    pending = 0
    ready = 0
    backed = 0
    delay_s = backup_delay_hours() * 3600.0
    now = _now_ts()
    for item in items.values():
        h = item.get("content_hash")
        if item.get("second_sync_hash") == h and item.get("second_synced_at"):
            backed += 1
        elif now - float(item.get("primary_synced_ts") or 0) >= delay_s:
            ready += 1
        else:
            pending += 1
    return {
        "queue_path": queue_path(),
        "primary_vault": primary_vault_path(),
        "second_vault": second_vault_path(),
        "second_vault_ready": _second_vault_ready(),
        "delay_hours": backup_delay_hours(),
        "total_items": len(items),
        "pending_lt_24h": pending,
        "ready_for_backup": ready,
        "backed_up": backed,
        "sweeper": q.get("sweeper") or {},
    }


# ── Domain helpers (writers call these) ─────────────────────────────────────

def sync_daily_note(rel_or_date: str, *, kind: str = "daily_forecast") -> Dict[str, Any]:
    """Notify after ``obsidian_sync`` wrote ``01_Daily_Logs/YYYY-MM-DD.md``."""
    rel = rel_or_date
    if "/" not in rel.replace("\\", "/") and not rel.endswith(".md"):
        rel = f"01_Daily_Logs/{rel}.md"
    return notify_primary_write(rel, kind=kind, changelog=f"Daily log / forecast sync `{rel}`")


def sync_ic_memo(abs_or_rel_path: str, trade_date: Optional[str] = None) -> Dict[str, Any]:
    """Register an IC memo file under Daily Logs for dual-vault tracking."""
    path = abs_or_rel_path.replace("\\", "/")
    vault = primary_vault_path().replace("\\", "/").rstrip("/")
    if path.startswith(vault + "/"):
        rel = path[len(vault) + 1:]
    elif path.startswith("obsidian_vault/"):
        rel = path[len("obsidian_vault/"):]
    else:
        base = os.path.basename(path)
        rel = f"01_Daily_Logs/{base}"
    date_bit = trade_date or ""
    return notify_primary_write(
        rel,
        kind="ic_memo",
        changelog=f"IC memo written {date_bit}".strip(),
    )


def sync_youtube_note(rel_or_title: str) -> Dict[str, Any]:
    rel = rel_or_title.replace("\\", "/")
    if not rel.startswith("04_YouTube_Knowledge/"):
        name = os.path.basename(rel)
        if not name.endswith(".md"):
            name = f"{name}.md"
        rel = f"04_YouTube_Knowledge/{name}"
    return notify_primary_write(
        rel,
        kind="youtube",
        changelog=f"YouTube knowledge ingested `{os.path.basename(rel)}`",
    )


def sync_brain_entry(entry: Dict[str, Any], *, changelog: bool = False) -> Dict[str, Any]:
    """Append a brain ingest snippet into AI Memory (idempotent by entry id)."""
    if not entry or not entry.get("content"):
        return {"ok": False, "error": "empty entry"}
    eid = str(entry.get("id") or "")[:16]
    date = str(entry.get("date") or datetime.now().date().isoformat())
    content = str(entry.get("content") or "").strip()
    source = str(entry.get("source") or "user")
    etype = str(entry.get("type") or "note")
    block = (
        f"\n### `{date}` · {etype} · `{eid}` · source:{source}\n\n"
        f"{content[:1200]}\n\n---\n"
    )
    rel = "05_AI_Memory/Brain_Ingest_Log.md"
    abs_path = primary_abs(rel)
    try:
        ensure_primary_structure()
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                existing = f.read()
            if eid and eid in existing:
                return notify_primary_write(rel, kind="brain", update_zero_md=False)
        else:
            existing = (
                "---\ntitle: Brain Ingest Log\ntags: [brain, memory, zero-engine]\n"
                "type: brain_log\n---\n\n# Brain Ingest Log\n\n"
                "Append-only mirror of ZERO Brain Engine ingest entries.\n"
            )
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(existing)
        return write_primary(
            rel,
            block,
            kind="brain",
            append=True,
            update_zero_md=bool(changelog),
            changelog=f"Brain note ingested `{eid or etype}`" if changelog else None,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def sync_premarket_brief(report: Dict[str, Any]) -> Dict[str, Any]:
    """Render AITE premarket JSON report to a vault markdown note."""
    if not isinstance(report, dict) or not report:
        return {"ok": False, "error": "empty report"}
    date_str = str(report.get("date") or datetime.now().date().isoformat())
    sections = report.get("sections") or {}
    symbols = report.get("symbols") or []
    lines = [
        "---",
        f"date: {date_str}",
        "type: premarket_brief",
        "tags: [aite, premarket, research]",
        "---",
        "",
        f"# ZERO AITE Premarket Brief — {date_str}",
        "",
        f"**Symbols:** {', '.join(str(s) for s in symbols)}",
        "",
        f"*Linked:* [[ZERO]] · [[01_Daily_Logs/{date_str}]] · [[ZERO Brain Engine]]",
        "",
    ]
    for key, body in sections.items():
        title = str(key).replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        lines.append(str(body or "_n/a_").strip())
        lines.append("")
    if report.get("disclaimer"):
        lines.append("## Disclaimer")
        lines.append("")
        lines.append(str(report["disclaimer"]))
        lines.append("")
    rel = f"07_AITE_Logs/{date_str}-Premarket.md"
    return write_primary(
        rel,
        "\n".join(lines) + "\n",
        kind="premarket",
        changelog=f"Premarket brief `{date_str}`",
    )


def sync_aite_activity(row: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror significant AITE activity rows to the daily AITE log note."""
    if not isinstance(row, dict):
        return {"ok": False}
    level = str(row.get("level") or "INFO").upper()
    if level not in _AITE_VAULT_LEVELS:
        return {"ok": True, "skipped": True, "reason": "level_filtered"}
    try:
        ts = float(row.get("ts") or _now_ts())
        day = datetime.fromtimestamp(ts).date().isoformat()
    except Exception:
        day = datetime.now().date().isoformat()
    eid = str(row.get("id") or "")
    msg = str(row.get("message") or "").strip()
    source = str(row.get("source") or "aite")
    stamp = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if row.get("ts") else ""
    line = f"* `{stamp}` **{level}** ({source}): {msg}"
    if row.get("agent_id"):
        line += f" · agent=`{row['agent_id']}`"
    if row.get("symbol"):
        line += f" · `{row['symbol']}`"
    line += "\n"
    rel = f"07_AITE_Logs/{day}.md"
    abs_path = primary_abs(rel)
    try:
        ensure_primary_structure()
        if os.path.exists(abs_path):
            with open(abs_path, "r", encoding="utf-8") as f:
                existing = f.read()
            if eid and eid in existing:
                return {"ok": True, "skipped": True, "reason": "duplicate"}
            if line.strip() in existing:
                return {"ok": True, "skipped": True, "reason": "duplicate_line"}
        else:
            header = (
                f"---\ndate: {day}\ntype: aite_activity\n"
                f"tags: [aite, activity, zero-engine]\n---\n\n"
                f"# ZERO AITE Activity — {day}\n\n"
                f"*Linked:* [[ZERO]] · [[ZERO Brain Engine]]\n\n"
                f"<!-- activity_ids -->\n"
            )
            write_primary(rel, header, kind="aite_activity", changelog=f"AITE log opened `{day}`")
        # Tag id for dedupe without cluttering the readable line
        payload = (f"<!-- {eid} -->\n" if eid else "") + line
        return write_primary(
            rel,
            payload,
            kind="aite_activity",
            append=True,
            update_zero_md=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── Background sweeper ──────────────────────────────────────────────────────

def _sweeper_loop(interval_sec: float) -> None:
    while not _SWEEPER_STOP.wait(timeout=max(30.0, float(interval_sec))):
        try:
            process_backup_queue(force=False)
        except Exception as exc:
            logger.warning("vault backup sweeper tick failed: %s", exc)


def start_backup_sweeper(interval_sec: float = _DEFAULT_SWEEP_INTERVAL_SEC) -> bool:
    """
    Start a non-blocking daemon thread that runs ``process_backup_queue``
    periodically. Idempotent. Never raises.
    """
    global _SWEEPER_THREAD, _SWEEPER_STARTED
    try:
        with _LOCK:
            if _SWEEPER_THREAD is not None and _SWEEPER_THREAD.is_alive():
                return True
            _SWEEPER_STOP.clear()
            _SWEEPER_THREAD = threading.Thread(
                target=_sweeper_loop,
                args=(float(interval_sec),),
                name="zero-vault-backup-sweeper",
                daemon=True,
            )
            _SWEEPER_THREAD.start()
            _SWEEPER_STARTED = True
        # Opportunistic immediate pass (non-blocking work; usually no-ops)
        try:
            process_backup_queue(force=False)
        except Exception:
            pass
        logger.info("Vault backup sweeper started (interval=%ss)", interval_sec)
        return True
    except Exception as exc:
        logger.warning("start_backup_sweeper failed: %s", exc)
        return False


def stop_backup_sweeper(timeout: float = 2.0) -> bool:
    global _SWEEPER_THREAD, _SWEEPER_STARTED
    try:
        _SWEEPER_STOP.set()
        thr = _SWEEPER_THREAD
        if thr is not None and thr.is_alive():
            thr.join(timeout=timeout)
        with _LOCK:
            if thr is not None and not thr.is_alive():
                _SWEEPER_THREAD = None
            _SWEEPER_STARTED = False
        return True
    except Exception:
        return False


__all__ = [
    "append_changelog",
    "ensure_primary_structure",
    "get_queue_status",
    "notify_primary_write",
    "primary_vault_path",
    "process_backup_queue",
    "second_vault_path",
    "start_backup_sweeper",
    "stop_backup_sweeper",
    "sync_aite_activity",
    "sync_brain_entry",
    "sync_daily_note",
    "sync_ic_memo",
    "sync_premarket_brief",
    "sync_youtube_note",
    "write_primary",
]
