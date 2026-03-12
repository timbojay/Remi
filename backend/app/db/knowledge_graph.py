"""Unified data access layer for the knowledge graph."""

import json
import uuid
from datetime import datetime, timezone
from app.db.database import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


# ─── BIOGRAPHY SUMMARY CACHE ─────────────────────────────────────────
# Invalidated whenever facts or entities are added/updated/deleted.
# Avoids re-fetching all rows from SQLite on every conversation turn.

_summary_cache: dict = {"text": None, "dirty": True}


def _invalidate_summary_cache() -> None:
    """Mark the summary cache as stale. Called on any write operation."""
    _summary_cache["dirty"] = True


# ─── FACTS ───────────────────────────────────────────────────────────

async def _resolve_entity_id(db, short_id: str) -> str | None:
    """Resolve a short entity ID (first 8 chars) to a full UUID."""
    if not short_id:
        return None
    # If it's already a full UUID, use it directly
    if len(short_id) > 8:
        cursor = await db.execute("SELECT id FROM entities WHERE id = ?", (short_id,))
        row = await cursor.fetchone()
        return row["id"] if row else None
    # Otherwise try prefix match
    cursor = await db.execute("SELECT id FROM entities WHERE id LIKE ?", (f"{short_id}%",))
    row = await cursor.fetchone()
    return row["id"] if row else None


async def add_fact(
    value: str,
    category: str,
    predicate: str = "stated",
    subject_entity_id: str | None = None,
    date_year: int | None = None,
    date_month: int | None = None,
    date_precision: str = "unknown",
    era: str | None = None,
    confidence: float = 0.7,
    significance: int = 3,
    is_anchor: bool = False,
    conversation_id: str | None = None,
) -> dict:
    db = await get_db()
    fact_id = _id()
    now = _now()

    # Resolve short entity ID to full UUID
    if subject_entity_id:
        subject_entity_id = await _resolve_entity_id(db, subject_entity_id)

    await db.execute(
        """INSERT INTO facts
           (id, subject_entity_id, predicate, value, category,
            date_year, date_month, date_precision, era,
            confidence, significance, is_anchor, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fact_id, subject_entity_id, predicate, value, category,
         date_year, date_month, date_precision, era,
         confidence, significance, 1 if is_anchor else 0, now, now),
    )

    if conversation_id:
        await db.execute(
            "INSERT INTO provenance (id, target_type, target_id, conversation_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (_id(), "fact", fact_id, conversation_id, now),
        )

    await db.commit()
    await _update_coverage(category)
    _invalidate_summary_cache()

    return {"id": fact_id, "value": value, "category": category}


async def search_facts(
    query: str,
    category: str | None = None,
    era: str | None = None,
    limit: int = 20,
) -> list[dict]:
    db = await get_db()
    conditions = ["is_suppressed = 0", "value LIKE ?"]
    params: list = [f"%{query}%"]

    if category:
        conditions.append("category = ?")
        params.append(category)
    if era:
        conditions.append("era = ?")
        params.append(era)

    params.append(limit)
    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT id, subject_entity_id, predicate, value, category,
                   date_year, date_month, era, confidence, mention_count,
                   is_verified, is_anchor, significance
            FROM facts WHERE {where}
            ORDER BY significance DESC, confidence DESC
            LIMIT ?""",
        params,
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_all_facts(category: str | None = None, verified_only: bool = False) -> list[dict]:
    db = await get_db()
    conditions = ["is_suppressed = 0"]
    params: list = []

    if category:
        conditions.append("category = ?")
        params.append(category)
    if verified_only:
        conditions.append("is_verified = 1")

    where = " AND ".join(conditions)
    cursor = await db.execute(
        f"""SELECT id, subject_entity_id, predicate, value, category,
                   date_year, era, confidence, mention_count, is_verified,
                   is_anchor, significance
            FROM facts WHERE {where}
            ORDER BY category, significance DESC""",
        params,
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def _resolve_fact_id(db, short_id: str) -> str:
    """Resolve a short fact ID to a full UUID."""
    if len(short_id) > 8:
        return short_id
    cursor = await db.execute("SELECT id FROM facts WHERE id LIKE ?", (f"{short_id}%",))
    row = await cursor.fetchone()
    return row["id"] if row else short_id


async def update_fact(
    fact_id: str,
    value: str | None = None,
    confidence: float | None = None,
    is_verified: bool | None = None,
) -> dict:
    db = await get_db()
    fact_id = await _resolve_fact_id(db, fact_id)
    updates = ["updated_at = ?"]
    params: list = [_now()]

    if value is not None:
        updates.append("value = ?")
        params.append(value)
    if confidence is not None:
        updates.append("confidence = ?")
        params.append(confidence)
    if is_verified is not None:
        updates.append("is_verified = ?")
        params.append(1 if is_verified else 0)

    params.append(fact_id)
    await db.execute(
        f"UPDATE facts SET {', '.join(updates)} WHERE id = ?", params
    )
    await db.commit()
    _invalidate_summary_cache()
    return {"id": fact_id, "updated": True}


async def delete_fact(fact_id: str, reason: str) -> dict:
    db = await get_db()
    await db.execute(
        "UPDATE facts SET is_suppressed = 1, suppression_reason = ?, updated_at = ? WHERE id = ?",
        (reason, _now(), fact_id),
    )
    await db.commit()
    _invalidate_summary_cache()
    return {"id": fact_id, "suppressed": True, "reason": reason}


# ─── ENTITIES ────────────────────────────────────────────────────────

async def add_entity(
    name: str,
    entity_type: str,
    relationship: str | None = None,
    family_role: str | None = None,
    description: str = "",
    properties: dict | None = None,
    confidence: float = 0.7,
    conversation_id: str | None = None,
) -> dict:
    db = await get_db()
    entity_id = _id()
    now = _now()

    await db.execute(
        """INSERT INTO entities
           (id, name, entity_type, relationship, family_role, description,
            properties, confidence, first_mentioned_at, last_mentioned_at,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (entity_id, name, entity_type, relationship, family_role, description,
         json.dumps(properties or {}), confidence, now, now, now, now),
    )

    if conversation_id:
        await db.execute(
            "INSERT INTO provenance (id, target_type, target_id, conversation_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (_id(), "entity", entity_id, conversation_id, now),
        )

    await db.commit()
    _invalidate_summary_cache()
    return {"id": entity_id, "name": name, "entity_type": entity_type}


async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    db = await get_db()
    conditions = ["is_suppressed = 0", "(name LIKE ? OR description LIKE ?)"]
    params: list = [f"%{query}%", f"%{query}%"]

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    params.append(limit)
    where = " AND ".join(conditions)

    cursor = await db.execute(
        f"""SELECT id, name, entity_type, relationship, family_role,
                   description, properties, confidence, mention_count, is_verified
            FROM entities WHERE {where}
            ORDER BY mention_count DESC, confidence DESC
            LIMIT ?""",
        params,
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["properties"] = json.loads(d["properties"]) if d["properties"] else {}
        results.append(d)
    return results


async def get_all_entities(entity_type: str | None = None) -> list[dict]:
    db = await get_db()
    conditions = ["is_suppressed = 0"]
    params: list = []

    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)

    where = " AND ".join(conditions)
    cursor = await db.execute(
        f"""SELECT id, name, entity_type, relationship, family_role,
                   description, properties, confidence, mention_count, is_verified
            FROM entities WHERE {where}
            ORDER BY entity_type, mention_count DESC""",
        params,
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["properties"] = json.loads(d["properties"]) if d["properties"] else {}
        results.append(d)
    return results


async def update_entity(
    entity_id: str,
    name: str | None = None,
    description: str | None = None,
    properties: dict | None = None,
    confidence: float | None = None,
) -> dict:
    db = await get_db()
    updates = ["updated_at = ?"]
    params: list = [_now()]

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if properties is not None:
        updates.append("properties = ?")
        params.append(json.dumps(properties))
    if confidence is not None:
        updates.append("confidence = ?")
        params.append(confidence)

    params.append(entity_id)
    await db.execute(
        f"UPDATE entities SET {', '.join(updates)} WHERE id = ?", params
    )
    await db.commit()
    _invalidate_summary_cache()
    return {"id": entity_id, "updated": True}


async def delete_entity(entity_id: str, reason: str) -> dict:
    db = await get_db()
    await db.execute(
        "UPDATE entities SET is_suppressed = 1, updated_at = ? WHERE id = ?",
        (_now(), entity_id),
    )
    await db.commit()
    _invalidate_summary_cache()
    return {"id": entity_id, "suppressed": True, "reason": reason}


# ─── RELATIONSHIPS ───────────────────────────────────────────────────

async def add_relationship(
    from_entity_id: str,
    to_entity_id: str,
    relationship_type: str,
    is_bidirectional: bool = False,
    confidence: float = 0.7,
    source: str = "extracted",
    conversation_id: str | None = None,
) -> dict:
    db = await get_db()
    rel_id = _id()
    now = _now()

    # Resolve short entity IDs to full UUIDs
    from_entity_id = await _resolve_entity_id(db, from_entity_id) or from_entity_id
    to_entity_id = await _resolve_entity_id(db, to_entity_id) or to_entity_id

    try:
        await db.execute(
            """INSERT INTO relationships
               (id, from_entity_id, to_entity_id, relationship_type,
                is_bidirectional, confidence, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_id, from_entity_id, to_entity_id, relationship_type,
             1 if is_bidirectional else 0, confidence, source, now, now),
        )
    except Exception:
        # UNIQUE constraint — relationship already exists
        return {"id": None, "already_exists": True}

    if conversation_id:
        await db.execute(
            "INSERT INTO provenance (id, target_type, target_id, conversation_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (_id(), "relationship", rel_id, conversation_id, now),
        )

    await db.commit()
    return {"id": rel_id, "type": relationship_type}


# ─── ENTITY DETAILS + FAMILY TREE ────────────────────────────────────

async def get_entity_details(entity_id: str) -> dict | None:
    """Get full entity details including linked facts and relationships."""
    db = await get_db()
    entity_id = (await _resolve_entity_id(db, entity_id)) or entity_id

    cursor = await db.execute(
        "SELECT * FROM entities WHERE id = ? AND is_suppressed = 0", (entity_id,)
    )
    entity = await cursor.fetchone()
    if not entity:
        return None

    result = dict(entity)

    # Get linked facts
    cursor = await db.execute(
        """SELECT id, value, category, predicate, confidence, significance, is_verified
           FROM facts WHERE subject_entity_id = ? AND is_suppressed = 0
           ORDER BY significance DESC""",
        (entity_id,),
    )
    result["facts"] = [dict(r) for r in await cursor.fetchall()]

    # Get relationships
    cursor = await db.execute(
        """SELECT r.id, r.relationship_type, r.is_bidirectional, r.confidence,
                  e.id as other_id, e.name as other_name, e.entity_type as other_type
           FROM relationships r
           JOIN entities e ON (
               CASE WHEN r.from_entity_id = ? THEN r.to_entity_id ELSE r.from_entity_id END = e.id
           )
           WHERE (r.from_entity_id = ? OR r.to_entity_id = ?)
             AND e.is_suppressed = 0""",
        (entity_id, entity_id, entity_id),
    )
    result["relationships"] = [dict(r) for r in await cursor.fetchall()]

    return result


async def get_family_tree() -> dict:
    """Build a family tree via BFS from the user entity."""
    db = await get_db()

    # Find all person entities with family relationships
    cursor = await db.execute(
        """SELECT id, name, entity_type, relationship, family_role, description
           FROM entities
           WHERE entity_type = 'person' AND is_suppressed = 0
           ORDER BY family_role, name""",
    )
    people = [dict(r) for r in await cursor.fetchall()]

    # Get all relationships
    cursor = await db.execute(
        """SELECT r.from_entity_id, r.to_entity_id, r.relationship_type,
                  r.is_bidirectional, r.confidence
           FROM relationships r
           JOIN entities e1 ON r.from_entity_id = e1.id AND e1.is_suppressed = 0
           JOIN entities e2 ON r.to_entity_id = e2.id AND e2.is_suppressed = 0""",
    )
    relationships = [dict(r) for r in await cursor.fetchall()]

    # Build adjacency for BFS
    adj: dict[str, list[dict]] = {}
    for rel in relationships:
        from_id = rel["from_entity_id"]
        to_id = rel["to_entity_id"]
        adj.setdefault(from_id, []).append({
            "target": to_id,
            "type": rel["relationship_type"],
        })
        if rel["is_bidirectional"]:
            adj.setdefault(to_id, []).append({
                "target": from_id,
                "type": rel["relationship_type"],
            })

    # Group by family role
    tree: dict[str, list[dict]] = {}
    for person in people:
        role = person.get("family_role") or person.get("relationship") or "other"
        tree.setdefault(role, []).append({
            "id": person["id"],
            "name": person["name"],
            "role": role,
            "description": person.get("description", ""),
        })

    return {
        "people": people,
        "relationships": relationships,
        "by_role": tree,
    }


# ─── COVERAGE ────────────────────────────────────────────────────────

async def _update_coverage(category: str):
    """Incrementally update coverage stats for a category."""
    db = await get_db()
    now = _now()

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt, AVG(confidence) as avg_conf FROM facts WHERE category = ? AND is_suppressed = 0",
        (category,),
    )
    row = await cursor.fetchone()
    fact_count = row["cnt"] or 0
    avg_conf = row["avg_conf"] or 0.0

    # Determine coverage level
    if fact_count == 0:
        level = "none"
    elif fact_count <= 3:
        level = "sparse"
    elif fact_count <= 10:
        level = "moderate"
    else:
        level = "rich"

    await db.execute(
        """INSERT INTO coverage (category, fact_count, avg_confidence, coverage_level, last_discussed_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(category) DO UPDATE SET
               fact_count = ?, avg_confidence = ?, coverage_level = ?, last_discussed_at = ?, updated_at = ?""",
        (category, fact_count, avg_conf, level, now, now,
         fact_count, avg_conf, level, now, now),
    )
    await db.commit()


async def get_coverage() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM coverage ORDER BY fact_count ASC"
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_coverage_gaps() -> list[dict]:
    """Return under-explored life categories."""
    all_categories = [
        "identity", "family", "education", "career", "residence",
        "milestone", "childhood", "relationships", "hobbies",
        "health", "travel", "beliefs", "daily_life", "challenges", "dreams",
    ]

    coverage = {c["category"]: c for c in await get_coverage()}
    gaps = []

    for cat in all_categories:
        cov = coverage.get(cat)
        fact_count = cov["fact_count"] if cov else 0
        level = cov["coverage_level"] if cov else "none"

        if level in ("none", "sparse"):
            gaps.append({
                "category": cat,
                "coverage_level": level,
                "fact_count": fact_count,
            })

    return gaps


# ─── BIOGRAPHY SUMMARY ──────────────────────────────────────────────

async def get_biography_summary() -> str:
    """Build a compressed text summary of all known facts, grouped by category.

    Result is cached in memory and only rebuilt when facts/entities change.
    """
    if not _summary_cache["dirty"] and _summary_cache["text"] is not None:
        return _summary_cache["text"]

    facts = await get_all_facts()
    entities = await get_all_entities()

    if not facts and not entities:
        result = "No biographical information recorded yet."
        _summary_cache["text"] = result
        _summary_cache["dirty"] = False
        return result

    # Group facts by category
    by_cat: dict[str, list[str]] = {}
    for f in facts:
        cat = f["category"]
        by_cat.setdefault(cat, []).append(f["value"])

    # Build summary
    lines = []
    for cat in sorted(by_cat.keys()):
        cat_facts = by_cat[cat]
        lines.append(f"**{cat.replace('_', ' ').title()}**: {'; '.join(cat_facts)}")

    # Add people — flag those with unknown real names
    people = [e for e in entities if e["entity_type"] == "person"]
    if people:
        people_strs = []
        for p in people:
            props = p.get("properties") or {}
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except Exception:
                    props = {}
            name_unknown = not props.get("name_known", True)
            label = p["name"]
            if name_unknown:
                label += " (name unknown)"
            if p["family_role"] and p["family_role"].lower() not in p["name"].lower():
                label += f" [{p['family_role']}]"
            if p["description"]:
                label += f" — {p['description']}"
            people_strs.append(label)
        lines.append(f"**People**: {'; '.join(people_strs)}")

    # Add other entities
    others = [e for e in entities if e["entity_type"] != "person"]
    if others:
        other_strs = [f"{e['name']} [{e['entity_type']}]" for e in others]
        lines.append(f"**Other**: {'; '.join(other_strs)}")

    result = "\n".join(lines)
    _summary_cache["text"] = result
    _summary_cache["dirty"] = False
    return result


async def get_unnamed_people() -> list[dict]:
    """Return person entities whose real name is not yet known."""
    entities = await get_all_entities(entity_type="person")
    unnamed = []
    for e in entities:
        props = e.get("properties") or {}
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except Exception:
                props = {}
        if not props.get("name_known", True):
            unnamed.append({
                "id": e["id"],
                "label": e["name"],
                "family_role": e.get("family_role", ""),
            })
    return unnamed


async def find_unnamed_entity_by_role(family_role: str) -> dict | None:
    """Find a person entity stored under a role label (name_known=false) by family_role column.

    Used by the extract node when a real name is revealed — e.g. family_role='mother'
    finds the 'Mum' placeholder so it can be upgraded to the real name.
    """
    if not family_role:
        return None
    db = await get_db()
    # Search by family_role column directly (not by name text)
    cursor = await db.execute(
        """SELECT id, name, entity_type, relationship, family_role, description, properties
           FROM entities
           WHERE entity_type = 'person'
             AND is_suppressed = 0
             AND LOWER(family_role) = LOWER(?)
           LIMIT 10""",
        (family_role,),
    )
    rows = await cursor.fetchall()
    for row in rows:
        e = dict(row)
        props = e.get("properties") or {}
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except Exception:
                props = {}
        if not props.get("name_known", True):
            return e
    return None


# ─── VERIFICATION ────────────────────────────────────────────────────

async def get_pending_verifications(limit: int = 3, cooldown_hours: int = 24) -> list[dict]:
    """Get low-confidence facts that should be verified, with cooldown to avoid repeating."""
    db = await get_db()
    # Only return facts not recently verified (checked via agent_state)
    last_checked = await _get_agent_state("last_verification_check")
    if last_checked and cooldown_hours > 0:
        from datetime import datetime, timedelta, timezone
        try:
            last_dt = datetime.fromisoformat(last_checked)
            if datetime.now(timezone.utc) - last_dt < timedelta(hours=cooldown_hours):
                return []  # Still in cooldown
        except ValueError:
            pass

    cursor = await db.execute(
        """SELECT id, value, category, confidence, mention_count, significance
           FROM facts
           WHERE is_suppressed = 0 AND is_verified = 0 AND confidence < 0.8
           ORDER BY is_anchor DESC, significance DESC, confidence ASC
           LIMIT ?""",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def mark_verification_checked():
    """Record that we've just checked verifications (for cooldown)."""
    await _set_agent_state("last_verification_check", _now())


async def mark_verified(fact_id: str) -> dict:
    db = await get_db()
    fact_id = await _resolve_fact_id(db, fact_id)
    await db.execute(
        "UPDATE facts SET is_verified = 1, confidence = 1.0, updated_at = ? WHERE id = ?",
        (_now(), fact_id),
    )
    await db.commit()
    return {"id": fact_id, "verified": True}


async def check_contradictions(value: str, category: str) -> list[dict]:
    """Check if a new fact contradicts any verified facts in the same category."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, value, confidence
           FROM facts
           WHERE is_suppressed = 0 AND is_verified = 1 AND category = ?""",
        (category,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def _get_agent_state(key: str) -> str | None:
    """Get a value from agent_state."""
    db = await get_db()
    cursor = await db.execute("SELECT value FROM agent_state WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row["value"] if row else None


async def _set_agent_state(key: str, value: str):
    """Set a value in agent_state."""
    db = await get_db()
    await db.execute(
        """INSERT INTO agent_state (key, value, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
        (key, value, _now(), value, _now()),
    )
    await db.commit()
