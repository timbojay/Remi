"""Background maintenance tasks for the knowledge graph.

Simplified version of Remi's 18-task cogitate system.
Runs periodically when no chat is active.
"""

import asyncio
from datetime import datetime, timezone
from app.db import knowledge_graph as kg
from app.db.database import get_db
from app.services.biography_generator import invalidate_cache
from app.config import settings

# Chat priority: pause maintenance during active chat
_chat_active = False
_maintenance_running = False
_task: asyncio.Task | None = None
COOLDOWN_SECONDS = 300  # 5 minutes between maintenance runs


def notify_chat_start():
    """Signal that a chat is active — pause maintenance."""
    global _chat_active
    _chat_active = True


def notify_chat_end():
    """Signal that chat is done — maintenance can resume."""
    global _chat_active
    _chat_active = False


async def _wait_for_chat_idle():
    """Wait until no chat is active."""
    while _chat_active:
        await asyncio.sleep(1)


async def run_maintenance():
    """Run all maintenance tasks once."""
    global _maintenance_running
    if _maintenance_running:
        return

    _maintenance_running = True
    print("[maintenance] Starting maintenance cycle...")

    try:
        await _wait_for_chat_idle()

        # Task 1: Refresh coverage stats
        await _refresh_coverage()
        await _wait_for_chat_idle()

        # Task 2: Deduplicate entities
        await _deduplicate_entities()
        await _wait_for_chat_idle()

        # Task 3: Deduplicate facts
        await _deduplicate_facts()
        await _wait_for_chat_idle()

        # Task 4: Invalidate biography cache if data changed
        invalidate_cache()

        print("[maintenance] Maintenance cycle complete.")
    except Exception as e:
        print(f"[maintenance] Error: {e}")
    finally:
        _maintenance_running = False


async def _refresh_coverage():
    """Refresh coverage stats for all categories."""
    categories = [
        "identity", "family", "education", "career", "residence",
        "milestone", "childhood", "relationships", "hobbies",
        "health", "travel", "beliefs", "daily_life", "challenges", "dreams",
    ]
    for cat in categories:
        await kg._update_coverage(cat)
    print("[maintenance] Coverage stats refreshed")


async def _deduplicate_entities():
    """Find and merge duplicate entities (same name, same type)."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT name, entity_type, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM entities
           WHERE is_suppressed = 0
           GROUP BY LOWER(name), entity_type
           HAVING cnt > 1"""
    )
    dupes = await cursor.fetchall()

    for dupe in dupes:
        ids = dupe["ids"].split(",")
        keep_id = ids[0]
        for remove_id in ids[1:]:
            # Move facts to the kept entity
            await db.execute(
                "UPDATE facts SET subject_entity_id = ? WHERE subject_entity_id = ?",
                (keep_id, remove_id),
            )
            # Suppress the duplicate
            await db.execute(
                "UPDATE entities SET is_suppressed = 1 WHERE id = ?",
                (remove_id,),
            )
            print(f"[maintenance] Merged duplicate entity {remove_id[:8]} into {keep_id[:8]}")

    if dupes:
        await db.commit()


async def _deduplicate_facts():
    """Find and suppress duplicate facts (same value, case-insensitive)."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT LOWER(value) as lval, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM facts
           WHERE is_suppressed = 0
           GROUP BY lval
           HAVING cnt > 1"""
    )
    dupes = await cursor.fetchall()

    for dupe in dupes:
        ids = dupe["ids"].split(",")
        keep_id = ids[0]
        for remove_id in ids[1:]:
            await db.execute(
                "UPDATE facts SET is_suppressed = 1, suppression_reason = 'duplicate' WHERE id = ?",
                (remove_id,),
            )
            print(f"[maintenance] Suppressed duplicate fact {remove_id[:8]}")

    if dupes:
        await db.commit()


async def start_maintenance_loop():
    """Start the background maintenance loop."""
    global _task
    if _task and not _task.done():
        return

    async def _loop():
        while True:
            await asyncio.sleep(COOLDOWN_SECONDS)
            await _wait_for_chat_idle()
            try:
                await run_maintenance()
            except Exception as e:
                print(f"[maintenance] Loop error: {e}")

    _task = asyncio.create_task(_loop())
    print("[maintenance] Background maintenance loop started")


def stop_maintenance_loop():
    """Stop the background maintenance loop."""
    global _task
    if _task:
        _task.cancel()
        _task = None
