"""Tools for querying the knowledge graph. Used by the agent during STRATEGIZE and RESPOND."""

from langchain_core.tools import tool
from app.db import knowledge_graph as kg


@tool
async def search_facts(query: str, category: str = "", era: str = "", limit: int = 10) -> str:
    """Search for biographical facts. Use before asking about a topic to avoid
    re-asking known information.

    Args:
        query: Search terms (names, places, events, topics)
        category: Optional filter (identity, family, education, career, etc.)
        era: Optional filter (childhood, teens, young_adult, adult, etc.)
        limit: Max results (default 10)
    """
    results = await kg.search_facts(
        query,
        category=category or None,
        era=era or None,
        limit=limit,
    )
    if not results:
        return "No matching facts found."
    lines = []
    for f in results:
        parts = [f"[{f['id'][:8]}]", f["value"]]
        if f["category"]:
            parts.append(f"({f['category']})")
        if f["is_verified"]:
            parts.append("[VERIFIED]")
        lines.append(" ".join(parts))
    return "\n".join(lines)


@tool
async def search_entities(query: str, entity_type: str = "", limit: int = 10) -> str:
    """Search for people, places, books, films, and other entities.

    Args:
        query: Name or description to search for
        entity_type: Optional filter (person, place, book, film, music, etc.)
        limit: Max results
    """
    results = await kg.search_entities(
        query,
        entity_type=entity_type or None,
        limit=limit,
    )
    if not results:
        return "No matching entities found."
    lines = []
    for e in results:
        parts = [f"[{e['id'][:8]}]", e["name"], f"({e['entity_type']})"]
        if e["relationship"]:
            parts.append(f"rel:{e['relationship']}")
        if e["description"]:
            parts.append(f"— {e['description']}")
        lines.append(" ".join(parts))
    return "\n".join(lines)


@tool
async def get_biography_summary() -> str:
    """Get a compressed summary of everything known about the subject's life.
    Use at the start of conversations or when you need broad context."""
    return await kg.get_biography_summary()


@tool
async def get_coverage_gaps() -> str:
    """Get under-explored life categories. Use to identify what to ask about next."""
    gaps = await kg.get_coverage_gaps()
    if not gaps:
        return "All life categories have moderate or rich coverage."
    lines = []
    for g in gaps:
        lines.append(f"- {g['category']}: {g['coverage_level']} ({g['fact_count']} facts)")
    return "Under-explored areas:\n" + "\n".join(lines)


@tool
async def get_pending_verifications() -> str:
    """Get facts with low confidence that should be verified with the user."""
    facts = await kg.get_pending_verifications(limit=3)
    if not facts:
        return "No facts need verification."
    lines = []
    for f in facts:
        lines.append(f"[{f['id'][:8]}] \"{f['value']}\" (confidence: {f['confidence']:.1f}, category: {f['category']})")
    return "Facts to verify:\n" + "\n".join(lines)


# All query tools for registration
QUERY_TOOLS = [search_facts, search_entities, get_biography_summary, get_coverage_gaps, get_pending_verifications]
