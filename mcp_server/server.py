#!/usr/bin/env python3
"""
Remi — MCP Server

Exposes Remi's full knowledge graph (facts, entities, relationships, biography)
via the Model Context Protocol. Backed by the same SQLite database used by
the Remi FastAPI backend + LangGraph agent.

Works with any MCP client: Claude Desktop, Cursor, VS Code Copilot, etc.

Usage:
  # stdio transport (default — for MCP clients)
  python mcp_server/server.py

  # SSE transport (for HTTP access)
  python mcp_server/server.py --transport sse --port 8000

  # Custom database path
  python mcp_server/server.py --db /path/to/remi.db
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root so we can import backend modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# Override DB path before importing settings (allows --db flag)
_DEFAULT_DB = str(PROJECT_ROOT / "backend" / "data" / "remi.db")

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "remi",
    instructions=(
        "Remi is a biographical knowledge base for Tim Jordan. "
        "It stores facts, people, places, relationships, and life stories. "
        "Use these tools to query and update Tim's biography."
    ),
)


# ======================================================================
# Lazy DB initialisation (sets DB_PATH env var before importing kg)
# ======================================================================

_db_path: str = _DEFAULT_DB
_kg = None  # lazy-loaded knowledge_graph module


def _get_kg():
    global _kg
    if _kg is None:
        os.environ.setdefault("DB_PATH", _db_path)
        # Patch settings before importing knowledge_graph
        from app.config import settings
        settings.DB_PATH = _db_path
        from app.db import knowledge_graph
        _kg = knowledge_graph
    return _kg


# ======================================================================
# Tools — Read
# ======================================================================

@mcp.tool()
async def get_biography_summary() -> str:
    """Get a full compressed text summary of everything known about Tim,
    grouped by life category (identity, family, education, career, etc.)."""
    kg = _get_kg()
    summary = await kg.get_biography_summary()
    return summary


@mcp.tool()
async def get_facts(category: str = None, verified_only: bool = False) -> str:
    """Get biographical facts, optionally filtered by category.

    Args:
        category: Optional filter — identity, family, education, career, residence,
                  milestone, childhood, relationships, hobbies, health, travel,
                  beliefs, daily_life, challenges, dreams
        verified_only: If true, only return verified facts
    """
    kg = _get_kg()
    facts = await kg.get_all_facts(category=category, verified_only=verified_only)
    return json.dumps({"count": len(facts), "facts": facts}, indent=2)


@mcp.tool()
async def search_facts(query: str, category: str = None, era: str = None) -> str:
    """Search biographical facts by keyword.

    Args:
        query: Search term (partial match on fact value)
        category: Optional category filter
        era: Optional era filter (e.g. 'childhood', 'young_adult', 'career')
    """
    kg = _get_kg()
    results = await kg.search_facts(query, category=category, era=era)
    return json.dumps({"count": len(results), "results": results}, indent=2)


@mcp.tool()
async def get_entities(entity_type: str = None) -> str:
    """Get all known entities (people, places, organisations, etc.).

    Args:
        entity_type: Optional filter — person, place, book, film, music,
                     organization, school, other
    """
    kg = _get_kg()
    entities = await kg.get_all_entities(entity_type=entity_type)
    return json.dumps({"count": len(entities), "entities": entities}, indent=2)


@mcp.tool()
async def search_entities(query: str, entity_type: str = None) -> str:
    """Search entities by name or description.

    Args:
        query: Name or partial name to search
        entity_type: Optional type filter
    """
    kg = _get_kg()
    results = await kg.search_entities(query, entity_type=entity_type)
    return json.dumps({"count": len(results), "results": results}, indent=2)


@mcp.tool()
async def get_entity_details(entity_id: str) -> str:
    """Get full details for a specific entity, including linked facts and relationships.

    Args:
        entity_id: Full UUID or first 8 characters of the entity ID
    """
    kg = _get_kg()
    details = await kg.get_entity_details(entity_id)
    if not details:
        return json.dumps({"error": f"Entity '{entity_id}' not found."})
    return json.dumps(details, indent=2, default=str)


@mcp.tool()
async def get_family_tree() -> str:
    """Get the complete family tree — all people and their relationships,
    grouped by family role (parents, siblings, spouse, children, etc.)."""
    kg = _get_kg()
    tree = await kg.get_family_tree()
    return json.dumps(tree, indent=2, default=str)


@mcp.tool()
async def get_coverage() -> str:
    """Get coverage stats for each life domain — how well explored each area is."""
    kg = _get_kg()
    coverage = await kg.get_coverage()
    return json.dumps({"coverage": coverage}, indent=2)


@mcp.tool()
async def get_coverage_gaps() -> str:
    """Get life domains that are under-explored or completely missing.
    Useful for planning interview questions."""
    kg = _get_kg()
    gaps = await kg.get_coverage_gaps()
    if not gaps:
        return json.dumps({"message": "All life categories have good coverage!"})
    return json.dumps({"gaps": gaps, "count": len(gaps)}, indent=2)


# ======================================================================
# Tools — Write
# ======================================================================

@mcp.tool()
async def add_fact(
    value: str,
    category: str,
    predicate: str = "stated",
    subject_entity_id: str = None,
    date_year: int = None,
    date_month: int = None,
    era: str = None,
    confidence: float = 0.7,
    significance: int = 3,
    is_anchor: bool = False,
) -> str:
    """Record a new biographical fact about Tim.

    Args:
        value: The fact text (e.g. "Born in Basildon, Essex, England")
        category: Life domain — identity, family, education, career, residence,
                  milestone, childhood, relationships, hobbies, health, travel,
                  beliefs, daily_life, challenges, dreams
        predicate: How it was stated (default: 'stated')
        subject_entity_id: Optional — link this fact to a specific entity (UUID or first 8 chars)
        date_year: Year this fact relates to
        date_month: Month this fact relates to
        era: Life era (e.g. 'childhood', 'young_adult', 'career', 'current')
        confidence: 0.0–1.0 confidence score (default: 0.7)
        significance: 1–5 importance rating (default: 3)
        is_anchor: True for core, definitional facts (name, birthday, etc.)
    """
    kg = _get_kg()
    result = await kg.add_fact(
        value=value,
        category=category,
        predicate=predicate,
        subject_entity_id=subject_entity_id,
        date_year=date_year,
        date_month=date_month,
        era=era,
        confidence=confidence,
        significance=significance,
        is_anchor=is_anchor,
    )
    return json.dumps({"created": result})


@mcp.tool()
async def update_fact(
    fact_id: str,
    value: str = None,
    confidence: float = None,
    is_verified: bool = None,
) -> str:
    """Update an existing fact.

    Args:
        fact_id: Fact UUID or first 8 characters
        value: New fact text (optional)
        confidence: New confidence score (optional)
        is_verified: Mark as verified/unverified (optional)
    """
    kg = _get_kg()
    result = await kg.update_fact(fact_id, value=value, confidence=confidence, is_verified=is_verified)
    return json.dumps(result)


@mcp.tool()
async def mark_fact_verified(fact_id: str) -> str:
    """Mark a fact as verified (sets confidence to 1.0).

    Args:
        fact_id: Fact UUID or first 8 characters
    """
    kg = _get_kg()
    result = await kg.mark_verified(fact_id)
    return json.dumps(result)


@mcp.tool()
async def delete_fact(fact_id: str, reason: str) -> str:
    """Suppress (soft-delete) a fact.

    Args:
        fact_id: Fact UUID or first 8 characters
        reason: Why this fact is being removed
    """
    kg = _get_kg()
    result = await kg.delete_fact(fact_id, reason)
    return json.dumps(result)


@mcp.tool()
async def add_entity(
    name: str,
    entity_type: str,
    relationship: str = None,
    family_role: str = None,
    description: str = "",
    confidence: float = 0.7,
) -> str:
    """Add a new entity (person, place, organisation, etc.) to the knowledge graph.

    Args:
        name: Entity name
        entity_type: person, place, book, film, music, organization, school, other
        relationship: How this entity relates to Tim (e.g. 'father', 'childhood home')
        family_role: For people — parent, sibling, spouse, child, grandparent, etc.
        description: Optional description
        confidence: 0.0–1.0 confidence score (default: 0.7)
    """
    kg = _get_kg()
    result = await kg.add_entity(
        name=name,
        entity_type=entity_type,
        relationship=relationship,
        family_role=family_role,
        description=description,
        confidence=confidence,
    )
    return json.dumps({"created": result})


@mcp.tool()
async def update_entity(
    entity_id: str,
    name: str = None,
    description: str = None,
    confidence: float = None,
) -> str:
    """Update an existing entity.

    Args:
        entity_id: Entity UUID or first 8 characters
        name: New name (optional)
        description: New description (optional)
        confidence: New confidence score (optional)
    """
    kg = _get_kg()
    result = await kg.update_entity(entity_id, name=name, description=description, confidence=confidence)
    return json.dumps(result)


@mcp.tool()
async def add_relationship(
    from_entity_id: str,
    to_entity_id: str,
    relationship_type: str,
    is_bidirectional: bool = False,
    confidence: float = 0.7,
) -> str:
    """Add a relationship between two entities.

    Reads as: [from_entity] → [relationship_type] → [to_entity]
    Example: Tim → father_of → Robert

    Args:
        from_entity_id: Source entity UUID or first 8 chars
        to_entity_id: Target entity UUID or first 8 chars
        relationship_type: Type of relationship (e.g. father, mother, spouse, child, attended, worked_at)
        is_bidirectional: Whether the relationship goes both ways (default: false)
        confidence: 0.0–1.0 confidence score (default: 0.7)
    """
    kg = _get_kg()
    result = await kg.add_relationship(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relationship_type=relationship_type,
        is_bidirectional=is_bidirectional,
        confidence=confidence,
    )
    return json.dumps(result)


# ======================================================================
# Resources
# ======================================================================

@mcp.resource("remi://biography/summary")
async def biography_summary_resource() -> str:
    """Full biographical summary of Tim Jordan."""
    kg = _get_kg()
    return await kg.get_biography_summary()


@mcp.resource("remi://knowledge/coverage")
async def coverage_resource() -> str:
    """Coverage statistics for all life domains."""
    kg = _get_kg()
    coverage = await kg.get_coverage()
    gaps = await kg.get_coverage_gaps()
    return json.dumps({"coverage": coverage, "gaps": gaps}, indent=2)


# ======================================================================
# Entry point
# ======================================================================

def main():
    global _db_path

    parser = argparse.ArgumentParser(description="Remi MCP Server")
    parser.add_argument(
        "--db",
        default=_DEFAULT_DB,
        help=f"Path to SQLite database (default: {_DEFAULT_DB})",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="Transport method (default: stdio)",
    )
    parser.add_argument("--host", default="localhost", help="Host for SSE transport")
    parser.add_argument("--port", type=int, default=8000, help="Port for SSE transport")
    args = parser.parse_args()

    _db_path = args.db

    print(f"Remi MCP Server", file=sys.stderr)
    print(f"  Database: {_db_path}", file=sys.stderr)
    print(f"  Transport: {args.transport}", file=sys.stderr)

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
