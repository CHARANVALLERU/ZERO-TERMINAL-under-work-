"""
ZERO dual-vault backup service (compat layer).

Prefer ``engine.vault_sync`` for new callers. This module keeps the historical
``update_main_zero`` / ``sync_second_zero_now`` API and delegates to the
central queue-backed pipeline:

* Immediate writes → ``OBSIDIAN_VAULT_PATH`` (ZERO vault)
* After ≥24h → ``SECOND_ZERO_VAULT_PATH`` (+ legacy in-vault ``second zero.md``)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger("ZERO_BACKUP_SERVICE")

MAIN_ZERO_NOTE = os.path.join(OBSIDIAN_VAULT_PATH, "ZERO.md")
BACKUP_ZERO_NOTE = os.path.join(OBSIDIAN_VAULT_PATH, "second zero.md")
# Legacy meta path kept for discovery; authoritative queue is db/vault_sync_queue.json
BACKUP_META_FILE = os.path.join(OBSIDIAN_VAULT_PATH, ".second_zero_sync.json")


def update_main_zero(content_or_append: str = "", append: bool = False) -> bool:
    """
    All project updates are added to ZERO.md first (primary vault).
    When ``append`` is True, content is treated as a changelog bullet summary.
    """
    try:
        from engine import vault_sync as vs

        if append:
            return bool(vs.append_changelog(content_or_append or "", kind="manual"))
        if content_or_append:
            result = vs.write_primary(
                "ZERO.md",
                content_or_append,
                kind="zero_moc",
                append=False,
                update_zero_md=False,
            )
            return bool(result.get("ok"))
        # Touch / ensure structure + queue entry for existing ZERO.md
        vs.ensure_primary_structure()
        if os.path.exists(MAIN_ZERO_NOTE):
            vs.notify_primary_write("ZERO.md", kind="zero_moc", update_zero_md=False)
        logger.info("ZERO.md updated successfully.")
        return True
    except Exception as e:
        logger.error("Failed to update ZERO.md: %s", e)
        return False


def sync_second_zero_now(force: bool = False) -> bool:
    """
    Process the dual-vault backup queue.

    Copies aged primary writes to SECOND ZERO (≥24h, or immediately if
    ``force=True``). Also refreshes in-vault ``second zero.md`` when ZERO.md
    is backed up. Graceful when SECOND ZERO path is missing.
    """
    try:
        from engine import vault_sync as vs

        result = vs.process_backup_queue(force=force)
        backed = result.get("backed_up") or []
        if backed:
            logger.info("SECOND ZERO backup synced %d item(s): %s", len(backed), backed)
            return True
        if result.get("skipped_reason"):
            logger.info("Backup sync skipped: %s", result["skipped_reason"])
            # Legacy MOC still refreshable on force
            if force:
                return True
            return False
        pending = result.get("pending") or []
        if pending:
            hrs = pending[0].get("hours_remaining")
            logger.info("Backup sync pending: ~%.1f hours remaining (sample).", float(hrs or 0))
        return False
    except Exception as e:
        logger.error("Error syncing second zero backup: %s", e)
        return False


def start_backup_service() -> bool:
    """Start the non-blocking 24h backup sweeper (idempotent)."""
    try:
        from engine import vault_sync as vs

        return bool(vs.start_backup_sweeper())
    except Exception as e:
        logger.error("Failed to start backup sweeper: %s", e)
        return False


def get_backup_status() -> Dict[str, Any]:
    try:
        from engine import vault_sync as vs

        return vs.get_queue_status()
    except Exception as e:
        return {"ok": False, "error": str(e)}
