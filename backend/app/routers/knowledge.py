"""Knowledge API: entities, facts, relationships, family tree."""

from fastapi import APIRouter
from app.db import knowledge_graph as kg

router = APIRouter(prefix="/api")


@router.get("/entities")
async def list_entities(entity_type: str | None = None):
    """List all entities, optionally filtered by type."""
    entities = await kg.get_all_entities(entity_type=entity_type)
    return {"entities": entities, "count": len(entities)}


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Get entity details with linked facts and relationships."""
    details = await kg.get_entity_details(entity_id)
    if not details:
        return {"error": "Entity not found"}
    return details


@router.get("/facts")
async def list_facts(category: str | None = None, verified_only: bool = False):
    """List all facts, optionally filtered by category."""
    facts = await kg.get_all_facts(category=category, verified_only=verified_only)
    return {"facts": facts, "count": len(facts)}


@router.get("/relationships")
async def list_relationships():
    """List all relationships between entities."""
    from app.db.database import get_db
    db = await get_db()
    cursor = await db.execute(
        """SELECT r.id, r.relationship_type, r.is_bidirectional, r.confidence,
                  e1.name as from_name, e1.id as from_id,
                  e2.name as to_name, e2.id as to_id
           FROM relationships r
           JOIN entities e1 ON r.from_entity_id = e1.id
           JOIN entities e2 ON r.to_entity_id = e2.id
           WHERE e1.is_suppressed = 0 AND e2.is_suppressed = 0"""
    )
    relationships = [dict(r) for r in await cursor.fetchall()]
    return {"relationships": relationships, "count": len(relationships)}


@router.get("/family-tree")
async def get_family_tree():
    """Get the family tree structure."""
    tree = await kg.get_family_tree()
    return tree


@router.get("/coverage")
async def get_coverage():
    """Get biography coverage by life category."""
    coverage = await kg.get_coverage()
    gaps = await kg.get_coverage_gaps()
    return {"coverage": coverage, "gaps": gaps}


@router.get("/timeline")
async def get_timeline():
    """Get facts organized as timeline events (only facts with dates)."""
    from app.db.database import get_db
    db = await get_db()
    cursor = await db.execute(
        """SELECT f.id, f.value, f.category, f.date_year, f.date_month,
                  f.era, f.significance, f.confidence, f.is_verified,
                  e.name as subject_name
           FROM facts f
           LEFT JOIN entities e ON f.subject_entity_id = e.id
           WHERE f.is_suppressed = 0 AND (f.date_year IS NOT NULL OR f.era IS NOT NULL)
           ORDER BY COALESCE(f.date_year, 9999), COALESCE(f.date_month, 1)"""
    )
    events = [dict(r) for r in await cursor.fetchall()]
    return {"events": events, "count": len(events)}


@router.get("/biography-summary")
async def get_biography_summary():
    """Get a compressed text summary of all known biography."""
    summary = await kg.get_biography_summary()
    return {"summary": summary}
