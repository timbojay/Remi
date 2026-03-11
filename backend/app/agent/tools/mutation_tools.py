"""Tools for modifying the knowledge graph. Used by the agent during EXTRACT."""

from langchain_core.tools import tool
from app.db import knowledge_graph as kg


@tool
async def add_fact(
    value: str,
    category: str,
    predicate: str = "stated",
    subject_entity_id: str = "",
    date_year: int = 0,
    date_month: int = 0,
    date_precision: str = "unknown",
    era: str = "",
    significance: int = 3,
    is_anchor: bool = False,
    confidence: float = 0.7,
) -> str:
    """Record a new biographical fact from the conversation.
    Only record facts the user actually stated — never infer or assume.

    Args:
        value: The fact in plain language (e.g., "Born in Austin, Texas")
        category: Life category (identity, family, education, career, residence,
                  milestone, childhood, relationships, hobbies, health, travel,
                  beliefs, daily_life, challenges, dreams)
        predicate: Type of fact (born_in, lived_in, worked_at, married, graduated, etc.)
        subject_entity_id: ID of the entity this fact is about (use first 8 chars from search)
        date_year: Year if known (0 if unknown)
        date_month: Month if known (0 if unknown)
        date_precision: exact, year, month, approximate, or unknown
        era: childhood, teens, young_adult, adult, middle_age, later_life
        significance: 1 (trivial) to 5 (life-defining)
        is_anchor: True for birth, death, marriage — structural life events
        confidence: How certain (0.0-1.0). Use 0.9 for clear statements, 0.7 for implied.
    """
    # This will be called with conversation_id injected by the extract node
    result = await kg.add_fact(
        value=value,
        category=category,
        predicate=predicate,
        subject_entity_id=subject_entity_id or None,
        date_year=date_year or None,
        date_month=date_month or None,
        date_precision=date_precision,
        era=era or None,
        confidence=confidence,
        significance=significance,
        is_anchor=is_anchor,
        conversation_id=_get_conversation_id(),
    )
    return f"Recorded fact: {value} [{result['id'][:8]}]"


@tool
async def add_entity(
    name: str,
    entity_type: str,
    relationship: str = "",
    family_role: str = "",
    description: str = "",
) -> str:
    """Record a new person, place, book, film, or other entity.
    Search first with search_entities to avoid duplicates.

    Args:
        name: Entity name
        entity_type: person, place, book, film, music, organization, school, other
        relationship: For people — family, friend, colleague, mentor, partner, acquaintance
        family_role: For family — parent, sibling, child, spouse, grandparent, aunt_uncle, cousin
        description: Brief description
    """
    result = await kg.add_entity(
        name=name,
        entity_type=entity_type,
        relationship=relationship or None,
        family_role=family_role or None,
        description=description,
        conversation_id=_get_conversation_id(),
    )
    return f"Recorded entity: {name} ({entity_type}) [{result['id'][:8]}]"


@tool
async def add_relationship(
    from_entity_id: str,
    to_entity_id: str,
    relationship_type: str,
    is_bidirectional: bool = False,
    confidence: float = 0.7,
) -> str:
    """Record a relationship between two entities.

    Args:
        from_entity_id: Source entity ID (first 8 chars or full)
        to_entity_id: Target entity ID (first 8 chars or full)
        relationship_type: parent_child, spouse, sibling, colleague, friend, etc.
        is_bidirectional: True for spouse, sibling; False for parent_child
        confidence: How certain (0.0-1.0)
    """
    result = await kg.add_relationship(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relationship_type=relationship_type,
        is_bidirectional=is_bidirectional,
        confidence=confidence,
        conversation_id=_get_conversation_id(),
    )
    if result.get("already_exists"):
        return "Relationship already recorded."
    return f"Recorded relationship: {relationship_type} [{result['id'][:8]}]"


@tool
async def update_fact(
    fact_id: str,
    value: str = "",
    confidence: float = -1,
    is_verified: bool = False,
) -> str:
    """Update an existing fact. Use when the user corrects or confirms information.

    Args:
        fact_id: The fact ID to update (first 8 chars or full)
        value: New value (empty string to keep current)
        confidence: New confidence (-1 to keep current)
        is_verified: Set True to promote to ground truth
    """
    result = await kg.update_fact(
        fact_id=fact_id,
        value=value or None,
        confidence=confidence if confidence >= 0 else None,
        is_verified=is_verified or None,
    )
    return f"Updated fact [{fact_id[:8]}]"


@tool
async def delete_fact(fact_id: str, reason: str) -> str:
    """Mark a fact as suppressed (soft delete). Use when the user says something is wrong.

    Args:
        fact_id: The fact to suppress
        reason: Why it's being removed
    """
    result = await kg.delete_fact(fact_id, reason)
    return f"Suppressed fact [{fact_id[:8]}]: {reason}"


@tool
async def delete_entity(entity_id: str, reason: str) -> str:
    """Mark an entity as suppressed. Use when user says a person/thing was recorded incorrectly.

    Args:
        entity_id: The entity to suppress
        reason: Why it's being removed
    """
    result = await kg.delete_entity(entity_id, reason)
    return f"Suppressed entity [{entity_id[:8]}]: {reason}"


# ─── Conversation ID injection ───────────────────────────────────────
# The extract node sets this before invoking extraction tools.

_current_conversation_id: str | None = None


def set_conversation_id(conversation_id: str):
    global _current_conversation_id
    _current_conversation_id = conversation_id


def _get_conversation_id() -> str | None:
    return _current_conversation_id


# All mutation tools for registration
MUTATION_TOOLS = [add_fact, add_entity, add_relationship, update_fact, delete_fact, delete_entity]
