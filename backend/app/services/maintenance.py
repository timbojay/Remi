"""Background maintenance tasks for the knowledge graph.

Simplified version of Remi's 18-task cogitate system.
Runs periodically when no chat is active.
"""

import asyncio
from datetime import datetime, timezone
from app.db import knowledge_graph as kg
from app.db import vector_store
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

        # Task 4: Generate questions from coverage gaps
        await _generate_questions()
        await _wait_for_chat_idle()

        # Task 5: Infer transitive relationships
        await _infer_relationships()
        await _wait_for_chat_idle()

        # Task 6: Invalidate biography cache if data changed
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
    """Find and suppress duplicate facts — exact match first, then semantic similarity."""
    db = await get_db()

    # Phase 1: Exact string match (fast)
    cursor = await db.execute(
        """SELECT LOWER(value) as lval, COUNT(*) as cnt, GROUP_CONCAT(id) as ids
           FROM facts
           WHERE is_suppressed = 0
           GROUP BY lval
           HAVING cnt > 1"""
    )
    dupes = await cursor.fetchall()
    exact_count = 0

    for dupe in dupes:
        ids = dupe["ids"].split(",")
        keep_id = ids[0]
        for remove_id in ids[1:]:
            await db.execute(
                "UPDATE facts SET is_suppressed = 1, suppression_reason = 'duplicate' WHERE id = ?",
                (remove_id,),
            )
            exact_count += 1

    if dupes:
        await db.commit()

    # Phase 2: Semantic similarity dedup via embeddings
    semantic_count = 0
    try:
        cursor = await db.execute(
            "SELECT id, value, significance, confidence FROM facts WHERE is_suppressed = 0 ORDER BY significance DESC, confidence DESC"
        )
        all_facts = [dict(r) for r in await cursor.fetchall()]

        # Index all facts that aren't yet indexed
        for f in all_facts:
            await vector_store.index_fact(f["id"], f["value"])

        # Check each fact for semantic duplicates
        suppressed_ids = set()
        for f in all_facts:
            if f["id"] in suppressed_ids:
                continue
            similar = await vector_store.find_similar_facts(f["value"], threshold=0.90, limit=5)
            for hit in similar:
                if hit["fact_id"] != f["id"] and hit["fact_id"] not in suppressed_ids:
                    # Suppress the duplicate (lower significance/confidence one)
                    await db.execute(
                        "UPDATE facts SET is_suppressed = 1, suppression_reason = 'semantic_duplicate' WHERE id = ?",
                        (hit["fact_id"],),
                    )
                    suppressed_ids.add(hit["fact_id"])
                    semantic_count += 1

        if semantic_count:
            await db.commit()
    except Exception as e:
        print(f"[maintenance] Semantic dedup error: {e}")

    total = exact_count + semantic_count
    if total:
        print(f"[maintenance] Suppressed {exact_count} exact + {semantic_count} semantic duplicate facts")


async def _generate_questions():
    """Generate template-based questions from coverage gaps."""
    count = await kg.generate_questions_from_gaps()
    if count:
        print(f"[maintenance] Generated {count} new questions from coverage gaps")


async def _infer_relationships():
    """Infer transitive relationships (grandparent, sibling, etc.) from existing graph."""
    db = await get_db()

    # Load all relationships
    cursor = await db.execute(
        """SELECT r.from_entity_id, r.to_entity_id, r.relationship_type, r.is_bidirectional
           FROM relationships r
           JOIN entities e1 ON r.from_entity_id = e1.id AND e1.is_suppressed = 0
           JOIN entities e2 ON r.to_entity_id = e2.id AND e2.is_suppressed = 0"""
    )
    rels = [dict(r) for r in await cursor.fetchall()]

    if not rels:
        return

    # Build adjacency: entity_id → list of (other_id, rel_type)
    adj: dict[str, list[tuple[str, str]]] = {}
    for r in rels:
        adj.setdefault(r["from_entity_id"], []).append((r["to_entity_id"], r["relationship_type"]))
        if r["is_bidirectional"]:
            adj.setdefault(r["to_entity_id"], []).append((r["from_entity_id"], r["relationship_type"]))

    inferred = 0

    # Rule 1: parent_child + parent_child = grandparent
    for a, a_rels in adj.items():
        for b, ab_type in a_rels:
            if ab_type != "parent_child":
                continue
            for c, bc_type in adj.get(b, []):
                if bc_type == "parent_child" and c != a:
                    result = await kg.add_relationship(
                        from_entity_id=a, to_entity_id=c,
                        relationship_type="grandparent",
                        confidence=0.7, source="inferred",
                    )
                    if not result.get("already_exists"):
                        inferred += 1

    # Rule 2: shared parent = sibling
    # Build parent → children map
    children_of: dict[str, list[str]] = {}
    for r in rels:
        if r["relationship_type"] == "parent_child":
            children_of.setdefault(r["from_entity_id"], []).append(r["to_entity_id"])

    for parent, children in children_of.items():
        for i, c1 in enumerate(children):
            for c2 in children[i + 1:]:
                result = await kg.add_relationship(
                    from_entity_id=c1, to_entity_id=c2,
                    relationship_type="sibling",
                    is_bidirectional=True,
                    confidence=0.7, source="inferred",
                )
                if not result.get("already_exists"):
                    inferred += 1

    if inferred:
        print(f"[maintenance] Inferred {inferred} new relationships")


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
