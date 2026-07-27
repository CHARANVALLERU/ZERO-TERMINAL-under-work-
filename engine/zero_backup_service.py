import os
import shutil
import time
import datetime
import logging
from config import OBSIDIAN_VAULT_PATH

logger = logging.getLogger('ZERO_BACKUP_SERVICE')

MAIN_ZERO_NOTE = os.path.join(OBSIDIAN_VAULT_PATH, "ZERO.md")
BACKUP_ZERO_NOTE = os.path.join(OBSIDIAN_VAULT_PATH, "second zero.md")
BACKUP_META_FILE = os.path.join(OBSIDIAN_VAULT_PATH, ".second_zero_sync.json")


def update_main_zero(content_or_append: str = "", append: bool = False):
    """
    All project updates are added to ZERO.md first.
    """
    try:
        os.makedirs(OBSIDIAN_VAULT_PATH, exist_ok=True)
        if append and os.path.exists(MAIN_ZERO_NOTE):
            with open(MAIN_ZERO_NOTE, "a", encoding="utf-8") as f:
                f.write(f"\n{content_or_append}\n")
        elif content_or_append:
            with open(MAIN_ZERO_NOTE, "w", encoding="utf-8") as f:
                f.write(content_or_append)
        
        logger.info("ZERO.md updated successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to update ZERO.md: {e}")
        return False


def sync_second_zero_now(force: bool = False) -> bool:
    """
    Syncs ZERO.md to 'second zero.md' after 24 hours of stable execution,
    or immediately if force=True (e.g. after verified fix).
    """
    try:
        if not os.path.exists(MAIN_ZERO_NOTE):
            return False

        main_mtime = os.path.getmtime(MAIN_ZERO_NOTE)
        now_time = time.time()
        hours_elapsed = (now_time - main_mtime) / 3600.0

        if force or hours_elapsed >= 24.0 or not os.path.exists(BACKUP_ZERO_NOTE):
            shutil.copyfile(MAIN_ZERO_NOTE, BACKUP_ZERO_NOTE)
            # Add backup frontmatter header to second zero.md
            with open(BACKUP_ZERO_NOTE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Ensure title is second zero
            with open(BACKUP_ZERO_NOTE, "w", encoding="utf-8") as f:
                f.write("---\ntitle: second zero\naliases: [second zero, Backup Index, MOC Backup]\n"
                        "tags: [moc, backup, second-brain, zero-engine]\ntype: index_backup\n"
                        f"last_backup_sync: '{datetime.date.today().isoformat()}'\n---\n\n"
                        "# second zero (Vault Backup)\n\n")
                # Write body excluding original title
                skip_header = True
                for line in lines:
                    if line.startswith("# ZERO"):
                        skip_header = False
                        continue
                    if not skip_header:
                        f.write(line)

            logger.info("Successfully synced main ZERO.md to 'second zero.md' backup.")
            return True
        else:
            logger.info(f"Backup sync pending: {24.0 - hours_elapsed:.1f} hours remaining.")
            return False
    except Exception as e:
        logger.error(f"Error syncing second zero backup: {e}")
        return False
